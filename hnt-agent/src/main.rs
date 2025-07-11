use anyhow::{bail, Context, Result};
use chrono::Utc;
use clap::Parser;

use crossterm::{
    cursor,
    terminal::{Clear, ClearType},
};
use crossterm::{
    execute,
    style::{Color, Print, ResetColor, SetForegroundColor},
    terminal,
};
use dirs;
use futures_util::StreamExt;
use headlesh::Session;
use hinata_core::chat;
use hinata_core::llm::{LlmConfig, SharedArgs};
use hnt_tui::{SelectArgs, Tty, TuiSelect};
use log::debug;
use regex::Regex;
use shlex;

use simplelog::{ColorChoice, Config, LevelFilter, TermLogger, TerminalMode};
use std::env;
use std::fs;
use std::io::stderr;
use std::io::stdout;
use std::io::Cursor;
use std::io::{Read, Write};
use std::path::Path;

use std::process::Command as StdCommand;
use tempfile;
use tokio;
use tokio::sync::watch;

use unicode_width::UnicodeWidthStr;

mod spinner;

const MARGIN: usize = 2;

fn margin_str() -> String {
    " ".repeat(MARGIN)
}

fn indent_multiline(text: &str) -> String {
    if text.is_empty() {
        return String::new();
    }

    let mut indented = format!(
        "{}{}",
        margin_str(),
        text.replace('\n', &format!("\n{}", margin_str()))
    );

    if indented.ends_with(&margin_str()) && text.ends_with('\n') {
        indented.truncate(indented.len() - MARGIN);
    }

    indented
}

fn prompt_for_instruction(cli: &Cli) -> Result<Option<String>> {
    if cli.use_editor {
        let editor = env::var("EDITOR").context("EDITOR environment variable not set")?;
        let mut file = tempfile::Builder::new()
            .prefix("hnt-agent-")
            .suffix(".md")
            .tempfile_in(env::temp_dir())
            .context("Failed to create temporary file for editor")?;

        let initial_text = "Replace this text with your instructions. Then write to this file and exit your\ntext editor. Leave the file unchanged or empty to abort.";
        file.write_all(initial_text.as_bytes())?;

        let path = file.into_temp_path();

        let status = if cli.use_pane {
            StdCommand::new("hnt-tui")
                .arg("pane")
                .arg(&editor)
                .arg(&path)
                .status()
                .with_context(|| format!("Failed to run hnt-tui pane with editor: {}", editor))?
        } else {
            let mut editor_parts =
                shlex::split(&editor).context("Failed to parse EDITOR variable")?;
            let editor_cmd = editor_parts.remove(0);

            StdCommand::new(&editor_cmd)
                .args(editor_parts)
                .arg(&path)
                .status()
                .with_context(|| format!("Failed to open editor: {}", editor))?
        };

        if !status.success() {
            bail!("Editor exited with a non-zero status code");
        }

        let mut instruction = String::new();
        fs::File::open(&path)
            .context("Failed to open temporary file after editing")?
            .read_to_string(&mut instruction)
            .context("Failed to read from temporary file after editing")?;

        path.close()?;

        if instruction.trim() == initial_text.trim() || instruction.trim().is_empty() {
            return Ok(None);
        }

        return Ok(Some(instruction));
    }

    // Default: use inline TUI editor
    hnt_tui::inline_editor::prompt_for_input()
}

/// Interact with hinata LLM agent to execute shell commands.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    /// System message string or path to system message file.
    #[arg(long)]
    system: Option<String>,

    /// User instruction message. If not provided, a TUI editor will be opened.
    #[arg(short, long)]
    message: Option<String>,

    /// Path to the conversation directory to resume a session.
    #[arg(short, long)]
    session: Option<String>,

    /// Set the initial working directory. Overrides session's saved directory.
    #[arg(long)]
    pwd: Option<String>,

    #[command(flatten)]
    shared: SharedArgs,

    /// Do not display or save LLM reasoning.
    #[arg(long)]
    ignore_reasoning: bool,

    /// Skip confirmation steps before executing commands or adding messages.
    #[arg(long)]
    no_confirm: bool,

    /// Enable verbose logging.
    #[arg(short, long)]
    verbose: bool,

    /// Use hnt-tui pane to open the editor.
    #[arg(long, env = "HINATA_USE_PANE")]
    use_pane: bool,

    /// Use an external editor ($EDITOR) for the user instruction message.
    #[arg(long)]
    use_editor: bool,

    /// Do not escape backticks in shell commands.
    #[arg(long)]
    no_escape_backticks: bool,

    /// Always use a specific spinner by its index, instead of a random one.
    #[arg(long)]
    spinner: Option<usize>,

    /// Display shell command results as raw XML.
    #[arg(long)]
    shell_results_display_xml: bool,
}

fn print_turn_header(role: &str, turn: usize) -> Result<()> {
    let (width, _) = terminal::size()?;
    let width = width as usize;
    let mut stdout = stdout();

    let (icon, line_color) = match role {
        "hinata" => ("❄️", Color::Blue),
        // "querent" => ("🕯️", Color::Green),
        // "querent" => ("⚜️", Color::Green),
        // "querent" => ("🌙", Color::Green), // gets slightly cut off at the bottom, at least in my terminal 1751500510
        // "querent" => ("🩸", Color::Green),
        "querent" => ("🗝️", Color::Magenta),
        _ => bail!("Unknown role for turn header: {}", role),
    };

    let role_text = format!("{} {}", icon, role);
    let turn_text = format!("turn {}", turn);
    // let prefix = "─── ";
    // let prefix = "──────── ";
    let prefix = "─────── ";

    let total_text_len =
        prefix.width() + role_text.width() + " • ".width() + turn_text.width() + " ".width();
    let line_len = if width > total_text_len + MARGIN * 2 {
        width - total_text_len - MARGIN * 2
    } else {
        0
    };
    let line = "─".repeat(line_len);

    execute!(
        stdout,
        Print(margin_str()),
        SetForegroundColor(line_color),
        Print(prefix),
        SetForegroundColor(Color::White),
        Print(&role_text),
        SetForegroundColor(line_color),
        Print(" • "),
        SetForegroundColor(Color::Green),
        Print(&turn_text),
        Print(" "),
        SetForegroundColor(line_color),
        Print(&line),
        Print("\n"),
    )?;

    stdout.flush()?;
    Ok(())
}

fn print_and_wrap_text(text: &str, current_column: &mut usize, wrap_at: usize) -> Result<()> {
    let mut stdout = stdout();
    let words: Vec<&str> = text.split(' ').collect();
    for (i, word) in words.iter().enumerate() {
        let mut parts = word.split('\n').peekable();
        while let Some(part) = parts.next() {
            if !part.is_empty() {
                let part_width = part.width();

                if *current_column > MARGIN && *current_column + part_width > wrap_at {
                    print!("\n{}", margin_str());
                    *current_column = MARGIN;
                }
                print!("{}", part);
                *current_column += part_width;
            }

            if parts.peek().is_some() {
                print!("\n{}", margin_str());
                *current_column = MARGIN;
            }
        }

        if i < words.len() - 1 {
            // A space existed after the original word.
            if !word.ends_with('\n') {
                if *current_column + 1 > wrap_at {
                    print!("\n{}", margin_str());
                    *current_column = MARGIN;
                }
                print!(" ");
                *current_column += 1;
            }
        }
    }
    stdout.flush()?;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let mut cli = Cli::parse();
    if cli.use_pane {
        cli.use_editor = true;
    }

    if cli.verbose {
        TermLogger::init(
            LevelFilter::Debug,
            Config::default(),
            TerminalMode::Mixed,
            ColorChoice::Auto,
        )
        .context("Failed to initialize logger")?;
    }

    debug!("Right after Cli::parse().");

    // 1. Set up headless session
    debug!("Before creating the session ID.");
    let session_id = format!("hnt-agent-{}", Utc::now().timestamp_nanos_opt().unwrap());
    debug!("After creating the session ID: {}", &session_id);
    debug!("Before Session::create.");
    let session = Session::create(session_id.clone()).await?;
    debug!("After Session::create.");
    debug!("Before session.spawn.");

    session.spawn(None)?;
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    debug!("After session.spawn.");

    // Restore working directory if specified
    if let Some(pwd) = cli.pwd.clone().or_else(|| {
        cli.session.as_ref().and_then(|session_path| {
            let pwd_file = Path::new(session_path).join("hnt-agent-pwd.txt");
            fs::read_to_string(pwd_file).ok()
        })
    }) {
        let trimmed_pwd = pwd.trim();
        if !trimmed_pwd.is_empty() {
            if let Ok(quoted_pwd) = shlex::try_quote(trimmed_pwd) {
                let command = format!("cd {}", quoted_pwd);
                debug!("Setting initial working directory with: {}", command);
                if let Err(e) = session.exec_captured(&command).await {
                    debug!("Failed to set initial working directory: {}", e);
                }
            } else {
                debug!(
                    "Failed to quote path for initial working directory: {}",
                    trimmed_pwd
                );
            }
        }
    }

    // 3. Create a new chat conversation (e.g., using `hinata_core::chat::create_new_conversation`)
    debug!("Before creating the conversation directory.");
    let conversation_dir = if let Some(name) = &cli.session {
        // 1. If <NAME> contains a forward slash ('/'), treat it as a path.
        if name.contains('/') {
            let path = Path::new(name);
            if path.is_dir() {
                path.to_path_buf()
            } else {
                bail!(
                    "Session path '{}' does not exist or is not a directory.",
                    name
                )
            }
        } else {
            // 2. If <NAME> does not contain a slash, treat it as a session name.
            // 2a. First, check for a directory named `./<NAME>`.
            let local_path = Path::new(name);
            if local_path.is_dir() {
                local_path.to_path_buf()
            } else {
                // 2b. If not, check for a directory named `<NAME>` inside the default conversations directory.
                let conversations_dir = chat::get_conversations_dir()?;
                let session_in_default_dir = conversations_dir.join(name);
                if session_in_default_dir.is_dir() {
                    session_in_default_dir
                } else {
                    // 2c. If neither exists, return an error.
                    bail!("Session name '{}' not found in current directory or in the default conversations directory ({}).", name, conversations_dir.display())
                }
            }
        }
    } else {
        // 3. If --session is not provided, create a new conversation directory.
        let conversations_dir = chat::get_conversations_dir()?;
        chat::create_new_conversation(&conversations_dir)?
    };

    debug!("Using conversation directory: {:?}", conversation_dir);

    let session_name_for_display = conversation_dir
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();

    let result = tokio::select! {


        _ = tokio::signal::ctrl_c() => {
            session.kill().await.ok();
            eprintln!("\n{}Ctrl+C received, shutting down gracefully.", margin_str());

            Ok(())
        },

        res = async {
            // 2. Get system and user messages (from args, files, or $EDITOR)
            debug!("Before getting the system prompt.");
            let system_prompt = if let Some(system) = &cli.system {
                let path = Path::new(&system);
                if path.is_file() {
                    Some(fs::read_to_string(path)?)
                } else {
                    Some(system.clone())
                }
            } else {
                // Try to load from default config path
                dirs::config_dir().and_then(|config_dir| {
                    let prompt_path = config_dir.join("hinata/prompts/hnt-agent/main-shell_agent.md");
                    fs::read_to_string(prompt_path).ok()
                })
            };

            debug!("After getting the system prompt.");
            debug!("Before getting the user instruction.");






            let user_instruction = if let Some(message) = &cli.message {
                message.clone()
            } else if let Some(instruction) = prompt_for_instruction(&cli)? {
                instruction
            } else {
                bail!("Aborted: No instructions were provided.");
            };

            let mut human_turn_counter = 1;
            let mut turn_counter = 1;
            if cli.session.is_some() {
                let mut assistant_turn_count = 0;
                let mut user_turn_count = 0;
                let mut last_assistant_message: Option<String> = None;

                let mut entries: Vec<_> = fs::read_dir(&conversation_dir)?
                    .filter_map(Result::ok)
                    .collect();
                entries.sort_by_key(|e| e.file_name());

                for entry in entries {
                    let path = entry.path();
                    if path.is_file() {
                        if let Some(filename) = path.file_name().and_then(|n| n.to_str()) {
                            if filename.ends_with("-assistant.md") {
                                assistant_turn_count += 1;
                                last_assistant_message = Some(fs::read_to_string(&path)?);
                            } else if filename.ends_with("-user.md") {
                                let content = fs::read_to_string(&path)?;
                                if content.contains("<user_request>") {
                                    user_turn_count += 1;
                                }
                            }
                        }
                    }
                }

                if let Some(last_message) = last_assistant_message {
                    human_turn_counter = user_turn_count + 1;
                    turn_counter = assistant_turn_count + 1;

                    print_turn_header("hinata", assistant_turn_count)?;
                    execute!(stdout(), ResetColor)?;
                    let indented_message = indent_multiline(&last_message);
                    execute!(stdout(), Print(&indented_message))?;
                    println!();
                    println!();
                }
            }
            print_turn_header("querent", human_turn_counter)?;
            human_turn_counter += 1;
            // Print the human's message with reset color
            execute!(stdout(), ResetColor)?;

            let indented_instruction = indent_multiline(&user_instruction);
            execute!(stdout(), Print(&indented_instruction))?;

            // Add a blank line for spacing
            println!();
            println!();
            debug!("After getting the user instruction.");






            // 4. Add system message and start priming sequence.
            if cli.session.is_none() {
                if let Some(ref prompt) = system_prompt {
                    debug!("Before writing system message file.");
                    chat::write_message_file(&conversation_dir, chat::Role::System, &prompt)?;
                    debug!("After writing system message file.");
                }

                // Inject context from HINATA.md if it exists
                if let Some(config_dir) = dirs::config_dir() {
                    let hinata_md_path = config_dir.join("hinata/agent/HINATA.md");
                    if let Ok(content) = fs::read_to_string(hinata_md_path) {
                        if !content.trim().is_empty() {
                            let message = format!("<info>\n{}\n</info>", content);
                            chat::write_message_file(&conversation_dir, chat::Role::User, &message)?;
                            debug!("Injected HINATA.md context.");
                        }
                    }
                }
            }

            // Add the user instruction
            debug!("Before writing user message file.");
            let tagged_instruction = format!("<user_request>\n{}\n</user_request>", user_instruction);
            chat::write_message_file(&conversation_dir, chat::Role::User, &tagged_instruction)?;
            debug!("After writing user message file.");


            // eprintln!(
            //     "Created conversation: {}",
            //     conversation_dir.to_string_lossy()
            // );

            let model = cli
                .shared
                .model
                .clone()
                .or_else(|| env::var("HINATA_AGENT_MODEL").ok())
                .or_else(|| env::var("HINATA_MODEL").ok())
                .unwrap_or_else(|| "openrouter/google/gemini-2.5-pro".to_string());


            // 5. Start the main interaction loop:
            debug!("Right before the main loop starts.");
            loop {
                // a. Pack conversation and generate LLM response
                let mut buffer = Cursor::new(Vec::new());
                chat::pack_conversation(&conversation_dir, &mut buffer, false)?;
                let prompt_bytes = buffer.into_inner();
                let prompt = String::from_utf8(prompt_bytes)
                    .context("Failed to convert packed conversation to string")?;


                let config = LlmConfig {
                    model: model.clone(),
                    system_prompt: None,
                    include_reasoning: !cli.ignore_reasoning || cli.shared.debug_unsafe,
                };

                let stream = hinata_core::llm::stream_llm_response(config, prompt);

                let mut llm_response = String::new();
                let mut reasoning_buffer = String::new();
                tokio::pin!(stream);


                print_turn_header("hinata", turn_counter)?;
                execute!(stdout(), ResetColor)?;

                let (width, _) = terminal::size()?;
                let wrap_at = (width as usize).saturating_sub(MARGIN);
                let mut current_column = MARGIN;

                print!("{}", margin_str());


                let mut in_reasoning_block = false;
                let mut llm_error: Option<anyhow::Error> = None;

                execute!(stdout(), cursor::Hide)?;

                while let Some(event) = stream.next().await {
                    match event {

                        Ok(hinata_core::llm::LlmStreamEvent::Content(content)) => {
                            if in_reasoning_block {
                                execute!(stdout(), ResetColor)?;
                                in_reasoning_block = false;

                                // If reasoning ended mid-line, we must move to a new line before proceeding.
                                if current_column > MARGIN {
                                    println!();
                                }

                                // Regardless of how the reasoning ended, we want a blank line for
                                // vertical spacing before the content starts.
                                println!();

                                // Now that we are on a new line, we must print a margin.
                                // This solves the double-margin bug, as we only print a margin
                                // after explicitly creating new lines.
                                print!("{}", margin_str());
                                current_column = MARGIN;
                            }
                            llm_response.push_str(&content);
                            print_and_wrap_text(&content, &mut current_column, wrap_at)?;
                        }
                        Ok(hinata_core::llm::LlmStreamEvent::Reasoning(reasoning)) => {
                            if !cli.ignore_reasoning {
                                reasoning_buffer.push_str(&reasoning);
                                if !in_reasoning_block {
                                    execute!(stdout(), SetForegroundColor(Color::Yellow))?;
                                }
                                in_reasoning_block = true;
                                print_and_wrap_text(&reasoning, &mut current_column, wrap_at)?;
                            }
                        }
                        Err(e) => {
                            llm_error = Some(e.into());
                            break;
                        }

                    }
                }

                execute!(stdout(), cursor::Show)?;

                if in_reasoning_block {
                    execute!(stdout(), ResetColor)?;
                    let trailing_newlines = reasoning_buffer
                        .chars()
                        .rev()
                        .take_while(|&c| c == '\n')
                        .count();
                    let newlines_to_add = 2_usize.saturating_sub(trailing_newlines);
                    for _ in 0..newlines_to_add {
                        println!();
                    }
                }



                if let Some(e) = llm_error {
                    // Need to reset color in case it was left on from streaming
                    execute!(stdout(), ResetColor)?;
                    let error_message = format!("An error occurred during the LLM request: {}", e);
                    let indented_error = error_message
                        .lines()
                        .map(|line| format!("{}{}", margin_str(), line))
                        .collect::<Vec<_>>()
                        .join("\n");
                    eprintln!("\n\n{}", indented_error);



                    let options = vec!["Retry LLM request.".to_string(), "Quit.".to_string()];
                    let args = SelectArgs {
                        height: 10,
                        color: Some(4),
                        prefix: Some(format!("{}🯖🭋", margin_str())),
                    };
                    let tty = Tty::new()?;
                    let selection = {
                        let mut select = TuiSelect::new(options, &args, tty)?;
                        select.run()?
                    };

                    let lines_to_move_up = (error_message.lines().count() + 3) as u16;
                    execute!(stderr(), cursor::MoveUp(lines_to_move_up), Clear(ClearType::FromCursorDown))?;


                    match selection.as_deref() {
                        Some("Retry LLM request.") => {
                            eprintln!("{}-> Retrying LLM request.\n", margin_str());
                            continue;
                        }


                        _ => {
                            bail!("User chose to exit.");
                        }
                    }
                }

                println!();

                if !cli.ignore_reasoning && !reasoning_buffer.is_empty() {
                    let reasoning_content = format!("<think>{}</think>", reasoning_buffer);
                    chat::write_message_file(
                        &conversation_dir,
                        chat::Role::AssistantReasoning,
                        &reasoning_content,
                    )?;
                }

                // Add assistants response to the conversation
                chat::write_message_file(&conversation_dir, chat::Role::Assistant, &llm_response)?;

                // Parse LLM response for the last <hnt-shell> command and execute it.
                let re = Regex::new(r"(?s)<hnt-shell>(.*?)</hnt-shell>")?;
                if let Some(captures) = re.captures_iter(&llm_response).last() {
                    if let Some(command_match) = captures.get(1) {
                        let mut command_text = command_match.as_str().trim().to_string();

                        if !cli.no_escape_backticks {
                            // Escape backticks not preceded by a backslash
                            // The original regex `(?<!\\)` uses a negative lookbehind, which is not supported by the default `regex` engine.
                            // We replace it by matching a character that is not a backslash, or the beginning of the string, before a backtick.
                            let re_escape = Regex::new(r"(^|[^\\])`")?;
                            command_text = re_escape.replace_all(&command_text, r"$1\`").to_string();
                        }



                        if !cli.no_confirm {
                            eprintln!(
                                "\n{}Hinata has completed its turn. Your response?",
                                margin_str()
                            );
                            let options = vec![
                                "Confirm. Proceed to execute Hinata's shell block.".to_string(),
                                "Skip this execution. Provide new instructions instead.".to_string(),
                                "Exit the Hinata session.".to_string(),
                            ];

                            let args = SelectArgs {
                                height: 10,
                                color: Some(4),
                                prefix: Some(format!("{}🯖🭋", margin_str())),
                            };
                            let tty = Tty::new()?;
                            let selection = {
                                let mut select = TuiSelect::new(options, &args, tty)?;
                                select.run()?
                            };

                            execute!(stderr(), cursor::MoveUp(1), Clear(ClearType::FromCursorDown))?;


                            match selection.as_deref() {
                                Some("Confirm. Proceed to execute Hinata's shell block.") => {
                                    eprintln!("{}-> Executing command.\n", margin_str());
                                }



                                Some("Skip this execution. Provide new instructions instead.") => {
                                    eprintln!("{}-> Chose to provide new instructions.\n", margin_str());


                                    // New instructions
                                    if let Some(new_instructions) = prompt_for_instruction(&cli)? {
                                        print_turn_header("querent", human_turn_counter)?;
                                        human_turn_counter += 1;
                                        // Print the human's message with reset color
                                        execute!(stdout(), ResetColor)?;

                                        let indented_instructions =
                                            indent_multiline(&new_instructions);
                                        execute!(stdout(), Print(&indented_instructions))?;
                                        // Add a blank line for spacing, then the footer
                                        println!();
                                        println!();
                                        let tagged_instructions = format!(
                                            "<user_request>\n{}\n</user_request>",
                                            new_instructions
                                        );
                                        chat::write_message_file(
                                            &conversation_dir,
                                            chat::Role::User,
                                            &tagged_instructions,
                                        )?;
                                        turn_counter += 1;
                                        continue;

                                    } else {
                                        bail!("User aborted providing new instructions.");
                                    }
                                }


                                _ => {
                                    // Some("No. Abort execution.") or None
                                    bail!("User aborted execution.");
                                }
                            }
                        }


                        let spinner = if let Some(index) = cli.spinner {
                            if index >= spinner::SPINNERS.len() {
                                eprintln!(
                                    "{}Error: spinner index {} is out of bounds. There are {} spinners available (0-{}).",
                                    margin_str(),
                                    index,
                                    spinner::SPINNERS.len(),
                                    spinner::SPINNERS.len() - 1
                                );
                                bail!("Spinner index out of bounds.");
                            }
                            spinner::SPINNERS[index].clone()
                        } else {
                            spinner::get_random_spinner()
                        };

                        let loading_message = spinner::get_random_loading_message();
                        let (tx, rx) = watch::channel(false);

                        let spinner_task =
                            tokio::spawn(spinner::run_spinner(spinner, loading_message, margin_str(), rx));

                        let captured_output_res = session.exec_captured(&command_text).await;

                        tx.send(true).ok();
                        spinner_task.await??;



                        let captured_output = captured_output_res?;

                        // Save current working directory
                        if let Ok(pwd_output) = session.exec_captured("pwd").await {
                            if pwd_output.exit_status.success() {
                                let pwd = pwd_output.stdout.trim();
                                if !pwd.is_empty() {
                                    let pwd_file = conversation_dir.join("hnt-agent-pwd.txt");
                                    if let Err(e) = fs::write(&pwd_file, pwd) {
                                        debug!(
                                            "Failed to save working directory to {}: {}",
                                            pwd_file.display(),
                                            e
                                        );
                                    }
                                }
                            } else {
                                debug!(
                                    "`pwd` command failed when trying to save working directory. Stderr: {}",
                                    pwd_output.stderr.trim()
                                );
                            }
                        } else {
                            debug!("Failed to execute `pwd` command to save working directory.");
                        }

                        let mut parts = Vec::new();

                        let stdout_content = captured_output.stdout.trim();
                        if !stdout_content.is_empty() {
                            parts.push(format!("<stdout>\n{}\n</stdout>", stdout_content));
                        }

                        let stderr_content = captured_output.stderr.trim();
                        if !stderr_content.is_empty() {
                            parts.push(format!("<stderr>\n{}\n</stderr>", stderr_content));
                        }

                        let exit_code = captured_output.exit_status.code().unwrap_or(1);
                        if exit_code != 0 {
                            parts.push(format!("<exit_code>{}</exit_code>", exit_code));
                        }

                        let result_message = if parts.is_empty() {
                            "<hnt-shell-results></hnt-shell-results>".to_string()
                        } else {
                            format!(
                                "<hnt-shell-results>\n{}\n</hnt-shell-results>",
                                parts.join("\n")
                            )
                        };



                        // Display shell output to the user
                        if cli.shell_results_display_xml {
                            let indented_result = indent_multiline(&result_message);
                            println!("{}", &indented_result);
                            println!();

                        } else {

                            if !stdout_content.is_empty() {
                                let indented_stdout = indent_multiline(stdout_content);
                                execute!(
                                    stdout(),
                                    SetForegroundColor(Color::Cyan),
                                    Print(&indented_stdout),
                                    ResetColor,
                                    Print("\n")
                                )?;
                            }

                            if !stdout_content.is_empty() && !stderr_content.is_empty() {
                                println!();
                            }

                            if !stderr_content.is_empty() {
                                let indented_stderr = indent_multiline(stderr_content);
                                execute!(
                                    stderr(),
                                    SetForegroundColor(Color::Red),
                                    Print(&indented_stderr),
                                    ResetColor,
                                    Print("\n")
                                )?;
                            }

                            if !stdout_content.is_empty()
                                && stderr_content.is_empty()
                                && exit_code != 0
                            {
                                println!();
                            }

                            if exit_code != 0 {
                                let exit_message = format!("🫀 exit code: {}", exit_code);
                                let indented_exit_message = indent_multiline(&exit_message);
                                execute!(
                                    stdout(),
                                    SetForegroundColor(Color::Red),
                                    Print(&indented_exit_message),
                                    ResetColor,
                                    Print("\n")
                                )?;
                            }

                            println!();
                        }

                        // Add command output as a new user message to continue the conversation
                        chat::write_message_file(
                            &conversation_dir,
                            chat::Role::User,
                            &result_message,
                        )?;
                        turn_counter += 1;
                    }



                } else {
                    eprintln!(
                        "\n{}LLM provided no command. Please provide new instructions.\n",
                        margin_str()

                    );



                    if let Some(new_instructions) = prompt_for_instruction(&cli)? {
                        print_turn_header("querent", human_turn_counter)?;
                        human_turn_counter += 1;
                        // Print the human's message with reset color
                        execute!(stdout(), ResetColor)?;

                        let indented_instructions = indent_multiline(&new_instructions);
                        execute!(stdout(), Print(&indented_instructions))?;

                        // Add a blank line for spacing
                        println!();
                        println!();

                        let tagged_instructions =
                            format!("<user_request>\n{}\n</user_request>", new_instructions);
                        chat::write_message_file(
                            &conversation_dir,
                            chat::Role::User,
                            &tagged_instructions,
                        )?;
                        turn_counter += 1;
                        continue;

                    } else {
                        bail!("Aborted: User did not provide new instructions.");
                    }
                }

            }
        } => res,
    };

    if !session_name_for_display.is_empty() {
        let has_assistant_message = fs::read_dir(&conversation_dir)
            .map(|entries| {
                entries.filter_map(Result::ok).any(|entry| {
                    entry
                        .file_name()
                        .to_str()
                        .map_or(false, |s| s.ends_with("-assistant.md"))
                })
            })
            .unwrap_or(false);

        if has_assistant_message {
            eprintln!(
                "Note: To resume this session, use: --session {}",
                session_name_for_display
            );
        }
    }

    session.exit().await?;

    result
}
