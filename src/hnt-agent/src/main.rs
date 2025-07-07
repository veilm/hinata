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

/// Interact with hinata LLM agent to execute shell commands.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    /// System message string or path to system message file.
    #[arg(short, long)]
    system: Option<String>,

    /// User instruction message. If not provided, a TUI editor will be opened.
    #[arg(short, long)]
    message: Option<String>,

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
}

fn prompt_for_instruction(cli: &Cli) -> Result<String> {
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
            bail!("Aborted: No changes were made.");
        }

        return Ok(instruction);
    }

    // Default: use inline TUI editor
    hnt_tui::inline_editor::prompt_for_input()
}

/// Gets user instruction from CLI arg, an editor, or an inline TUI.
fn get_user_instruction(cli: &Cli) -> Result<(String, bool)> {
    if let Some(message) = &cli.message {
        return Ok((message.clone(), false));
    }

    let instruction = prompt_for_instruction(cli)?;
    Ok((instruction, true))
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

    let result = tokio::select! {


        _ = tokio::signal::ctrl_c() => {
            session.kill().await.ok();
            eprintln!("\n{}Ctrl+C received, shutting down gracefully.", margin_str());
            Ok(())
        },
        res = async {
            let mut human_turn_counter = 1;
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

            let (user_instruction, _) = get_user_instruction(&cli)?;
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

            // 3. Create a new chat conversation (e.g., using `hinata_core::chat::create_new_conversation`)
            debug!("Before creating the conversation directory.");
            let conversations_dir = chat::get_conversations_dir()?;
            let conversation_dir = chat::create_new_conversation(&conversations_dir)?;
            debug!("After creating the conversation directory.");

            // 4. Add system message and start priming sequence.
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

            // Add the user instruction
            debug!("Before writing user message file.");
            let tagged_instruction = format!("<user_request>\n{}\n</user_request>", user_instruction);
            chat::write_message_file(&conversation_dir, chat::Role::User, &tagged_instruction)?;
            debug!("After writing user message file.");

            // eprintln!(
            //     "Created conversation: {}",
            //     conversation_dir.to_string_lossy()
            // );

            // 5. Start the main interaction loop:
            debug!("Right before the main loop starts.");
            let mut turn_counter = 1;
            loop {
                // a. Pack conversation and generate LLM response
                let mut buffer = Cursor::new(Vec::new());
                chat::pack_conversation(&conversation_dir, &mut buffer, false)?;
                let prompt_bytes = buffer.into_inner();
                let prompt = String::from_utf8(prompt_bytes)
                    .context("Failed to convert packed conversation to string")?;

                let config = LlmConfig {
                    model: cli.shared.model.clone(),
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
                while let Some(event) = stream.next().await {
                    match event {
                        Ok(hinata_core::llm::LlmStreamEvent::Content(content)) => {
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
                                in_reasoning_block = false;
                                print!("{}", margin_str());
                                current_column = MARGIN;
                            }
                            llm_response.push_str(&content);

                            let words: Vec<&str> = content.split(' ').collect();
                            for (i, word) in words.iter().enumerate() {
                                let mut parts = word.split('\n').peekable();
                                while let Some(part) = parts.next() {
                                    if !part.is_empty() {

                                        let part_width = part.width();

                                        if current_column > MARGIN
                                            && current_column + part_width > wrap_at
                                        {
                                            print!("\n{}", margin_str());
                                            current_column = MARGIN;
                                        }
                                        print!("{}", part);
                                        current_column += part_width;
                                    }

                                    if parts.peek().is_some() {
                                        print!("\n{}", margin_str());
                                        current_column = MARGIN;
                                    }
                                }

                                if i < words.len() - 1 {
                                    // A space existed after the original word.
                                    if !word.ends_with('\n') {
                                        if current_column + 1 > wrap_at {
                                            print!("\n{}", margin_str());
                                            current_column = MARGIN;
                                        }
                                        print!(" ");
                                        current_column += 1;
                                    }
                                }
                            }
                            stdout().flush()?;
                        }
                        Ok(hinata_core::llm::LlmStreamEvent::Reasoning(reasoning)) => {
                            if !cli.ignore_reasoning {
                                reasoning_buffer.push_str(&reasoning);
                                if !in_reasoning_block {
                                    execute!(stdout(), SetForegroundColor(Color::Yellow))?;
                                }
                                in_reasoning_block = true;
                                execute!(stdout(), Print(&reasoning))?;
                                stdout().flush()?;
                            }
                        }
                        Err(e) => {
                            llm_error = Some(e.into());
                            break;
                        }
                    }
                }

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



                    let options = vec!["Retry LLM request.".to_string(), "Abort.".to_string()];
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
                            eprintln!("{}-> Retrying LLM request.", margin_str());
                            continue;
                        }
                        _ => {
                            // "Abort." or None
                            eprintln!("{}-> Chose to abort.", margin_str());
                            break;
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
                                "\n{}Hinata has provided the following command. What would you like to do?",
                                margin_str()
                            );
                            let options = vec![
                                "Yes. Proceed to execute Hinata's shell commands.".to_string(),
                                "No, and provide new instructions instead.".to_string(),
                                "No. Abort execution.".to_string(),
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
                                Some("Yes. Proceed to execute Hinata's shell commands.") => {
                                    eprintln!("{}-> Executing command.\n", margin_str());
                                }

                                Some("No, and provide new instructions instead.") => {
                                    eprintln!("{}-> Chose to provide new instructions.\n", margin_str());
                                    // New instructions
                                    let new_instructions = prompt_for_instruction(&cli)?;
                                    print_turn_header("querent", human_turn_counter)?;
                                    human_turn_counter += 1;
                                    // Print the human's message with reset color
                                    execute!(stdout(), ResetColor)?;

                                    let indented_instructions = indent_multiline(&new_instructions);
                                    execute!(stdout(), Print(&indented_instructions))?;
                                    // Add a blank line for spacing, then the footer
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
                                }
                                _ => {
                                    // Some("No. Abort execution.") or None

                                    eprintln!("{}-> Chose to abort.", margin_str());
                                    break;
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
                            "<hnt-shell_results></hnt-shell_results>".to_string()
                        } else {
                            format!(
                                "<hnt-shell_results>\n{}\n</hnt-shell_results>",
                                parts.join("\n")
                            )
                        };

                        // Display shell output to the user
                        execute!(
                            stdout(),
                            SetForegroundColor(Color::White),
                            // Print("Shell Output\n"),
                            ResetColor
                        )?;



                        let indented_result = indent_multiline(&result_message);
                        println!("{}", &indented_result);
                        println!();

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
                        "\n{}LLM provided no command. What would you like to do?",
                        margin_str()
                    );
                    let options = vec![
                        "Provide new instructions for the LLM.".to_string(),
                        "Quit. Terminate the agent.".to_string(),
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

                    // execute!(stderr(), cursor::MoveUp(2), Clear(ClearType::FromCursorDown))?;
                    execute!(stderr(), cursor::MoveUp(1), Clear(ClearType::FromCursorDown))?;


                    match selection.as_deref() {
                        Some("Provide new instructions for the LLM.") => {
                            eprintln!("{}-> Chose to provide new instructions.\n", margin_str());

                            let new_instructions = prompt_for_instruction(&cli)?;
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
                        }
                        _ => {
                            eprintln!("{}-> Chose to quit. Farewell.", margin_str());
                            break;
                        }
                    }
                }
            }
            Ok::<(), anyhow::Error>(())
        } => res,
    };

    session.exit().await?;

    result
}
