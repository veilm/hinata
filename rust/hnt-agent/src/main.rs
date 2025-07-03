use anyhow::{bail, Context, Result};
use chrono::Utc;
use clap::Parser;
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
use simplelog::{ColorChoice, Config, LevelFilter, TermLogger, TerminalMode};
use std::env;
use std::fs;
use std::io::stdout;
use std::io::Cursor;
use std::io::Write;
use std::path::Path;
use std::process::Command as StdCommand;
use tokio;
use unicode_width::UnicodeWidthStr;

/// Interact with hinata LLM agent to execute shell commands.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    /// System message string or path to system message file.
    #[arg(short, long)]
    system: Option<String>,

    /// User instruction message. If not provided, $EDITOR will be opened.
    #[arg(short, long)]
    message: Option<String>,

    #[command(flatten)]
    shared: SharedArgs,

    /// Skip confirmation steps before executing commands or adding messages.
    #[arg(long)]
    no_confirm: bool,

    /// Enable verbose logging.
    #[arg(short, long)]
    verbose: bool,

    /// Use hnt-tui pane to open the editor.
    #[arg(long, env = "HINATA_USE_PANE")]
    use_pane: bool,

    /// Do not escape backticks in shell commands.
    #[arg(long)]
    no_escape_backticks: bool,
}

struct SessionGuard {
    session: Session,
}

impl Drop for SessionGuard {
    fn drop(&mut self) {
        println!("Cleaning up session...");
        // Spawn a new async task to handle the cleanup.
        let session = self.session.clone(); // Clone the session to move it into the task
        tokio::spawn(async move {
            if let Err(e) = session.exit().await {
                eprintln!("Error cleaning up session: {}", e);
            }
        });
    }
}

fn get_input_from_editor(initial_text: &str, use_pane: bool) -> Result<String> {
    let editor = env::var("EDITOR").context("EDITOR environment variable not set")?;

    let temp_file_name = format!("hnt-agent-{}.md", Utc::now().timestamp_nanos_opt().unwrap());
    let temp_file_path = env::temp_dir().join(temp_file_name);

    fs::write(&temp_file_path, initial_text)?;

    let cwd = env::current_dir().context("Failed to get current working directory")?;

    let status = if use_pane {
        StdCommand::new("hnt-tui")
            .arg("pane")
            .arg(&editor)
            .arg(&temp_file_path)
            .current_dir(&cwd)
            .status()
            .with_context(|| format!("Failed to open editor in pane: {}", editor))?
    } else {
        StdCommand::new(&editor)
            .arg(&temp_file_path)
            .current_dir(&cwd)
            .status()
            .with_context(|| format!("Failed to open editor: {}", editor))?
    };

    if !status.success() {
        bail!("Editor exited with a non-zero status code");
    }

    let instruction = fs::read_to_string(&temp_file_path)
        .context("Failed to read user instruction from temporary file")?;
    fs::remove_file(temp_file_path).ok(); // Ignore error on cleanup

    Ok(instruction)
}

fn get_user_instruction(message: Option<String>, use_pane: bool) -> Result<String> {
    let instruction = if let Some(message) = message {
        message
    } else {
        get_input_from_editor("", use_pane)?
    };

    if instruction.trim().is_empty() {
        bail!("User instruction is empty. Aborting.");
    }

    Ok(instruction)
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

    let total_text_len = prefix.width()
        + role_text.width()
        + " • ".width()
        + turn_text.chars().count()
        + " ".chars().count();
    let line_len = if width > total_text_len {
        width - total_text_len
    } else {
        0
    };
    let line = "─".repeat(line_len);

    execute!(
        stdout,
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

fn print_turn_footer(color: Color) -> Result<()> {
    let (width, _) = terminal::size()?;
    let width = width as usize;
    let mut stdout = stdout();
    let line = "─".repeat(width);

    execute!(
        stdout,
        SetForegroundColor(color),
        Print(&line),
        ResetColor,
        Print("\n"),
    )?;
    stdout.flush()?;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let mut human_turn_counter = 1;

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
    let _session_guard = SessionGuard { session };
    debug!("After instantiating SessionGuard.");

    // 2. Get system and user messages (from args, files, or $EDITOR)
    debug!("Before getting the system prompt.");
    let system_prompt = if let Some(system) = cli.system {
        let path = Path::new(&system);
        if path.is_file() {
            Some(fs::read_to_string(path)?)
        } else {
            Some(system)
        }
    } else {
        // Try to load from default config path
        dirs::config_dir().and_then(|config_dir| {
            let prompt_path = config_dir.join("hinata/prompts/main-shell_agent.md");
            fs::read_to_string(prompt_path).ok()
        })
    };
    debug!("After getting the system prompt.");
    debug!("Before getting the user instruction.");
    let user_instruction = get_user_instruction(cli.message, cli.use_pane)?;
    print_turn_header("querent", human_turn_counter)?;
    human_turn_counter += 1;
    // Print the human's message with reset color
    execute!(stdout(), ResetColor, Print(&user_instruction))?;
    // Add a blank line for spacing, then the footer
    println!();
    print_turn_footer(Color::Magenta)?;
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

    eprintln!(
        "Created conversation: {}",
        conversation_dir.to_string_lossy()
    );

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
            include_reasoning: cli.shared.debug_unsafe,
        };

        let stream = hinata_core::llm::stream_llm_response(config, prompt);

        let mut llm_response = String::new();
        tokio::pin!(stream);

        print_turn_header("hinata", turn_counter)?;
        execute!(stdout(), ResetColor)?;

        let mut llm_error: Option<anyhow::Error> = None;
        while let Some(event) = stream.next().await {
            match event {
                Ok(hinata_core::llm::LlmStreamEvent::Content(content)) => {
                    llm_response.push_str(&content);
                    print!("{}", content);
                    stdout().flush()?;
                }
                Ok(hinata_core::llm::LlmStreamEvent::Reasoning(_)) => {
                    // For now, we'll just ignore reasoning events.
                }
                Err(e) => {
                    llm_error = Some(e.into());
                    break;
                }
            }
        }

        if let Some(e) = llm_error {
            // Need to reset color in case it was left on from streaming
            execute!(stdout(), ResetColor)?;
            eprintln!("\n\nAn error occurred during the LLM request: {}", e);

            let options = vec!["Retry LLM request.".to_string(), "Abort.".to_string()];
            let args = SelectArgs {
                height: 10,
                color: Some(4),
            };
            let tty = Tty::new()?;
            let selection = {
                let mut select = TuiSelect::new(options, &args, tty)?;
                select.run()?
            };

            match selection.as_deref() {
                Some("Retry LLM request.") => {
                    continue;
                }
                _ => {
                    // "Abort." or None
                    eprintln!("Aborting.");
                    break;
                }
            }
        }

        println!();
        print_turn_footer(Color::Blue)?;

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
                        "\nHinata has provided the following command. What would you like to do?"
                    );
                    let options = vec![
                        "Yes. Proceed to execute Hinata's shell commands.".to_string(),
                        "No, and provide new instructions instead.".to_string(),
                        "No. Abort execution.".to_string(),
                    ];

                    let args = SelectArgs {
                        height: 10,
                        color: Some(4),
                    };
                    let tty = Tty::new()?;
                    let selection = {
                        let mut select = TuiSelect::new(options, &args, tty)?;
                        select.run()?
                    };

                    match selection.as_deref() {
                        Some("Yes. Proceed to execute Hinata's shell commands.") => {
                            // User said yes, proceed.
                        }
                        Some("No, and provide new instructions instead.") => {
                            // New instructions
                            let new_instructions = get_input_from_editor("", cli.use_pane)?;
                            print_turn_header("querent", human_turn_counter)?;
                            human_turn_counter += 1;
                            // Print the human's message with reset color
                            execute!(stdout(), ResetColor, Print(&new_instructions))?;
                            // Add a blank line for spacing, then the footer
                            println!();
                            print_turn_footer(Color::Magenta)?;
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
                            eprintln!("Aborting execution.");
                            break;
                        }
                    }
                }

                let captured_output = _session_guard.session.exec_captured(&command_text).await?;

                // Display shell output to the user
                print_turn_footer(Color::DarkCyan)?;
                execute!(
                    stdout(),
                    SetForegroundColor(Color::White),
                    Print("Shell Output\n"),
                    ResetColor
                )?;
                if !captured_output.stdout.is_empty() {
                    print!("{}", &captured_output.stdout);
                }
                if !captured_output.stderr.is_empty() {
                    eprint!("{}", &captured_output.stderr);
                }
                // The output may or may not have a newline. The footer will draw a line
                // and add a newline, so we are guaranteed to be on a new line after this.
                print_turn_footer(Color::DarkCyan)?;

                let result_message = format!(
                    "<hnt-shell_results>\n<stdout>\n{}</stdout>\n<stderr>\n{}</stderr>\n<exit_code>{}</exit_code>\n</hnt-shell_results>",
                    captured_output.stdout,
                    captured_output.stderr,
                    captured_output.exit_status.code().unwrap_or(1)
                );

                // Add command output as a new user message to continue the conversation
                chat::write_message_file(&conversation_dir, chat::Role::User, &result_message)?;
                turn_counter += 1;
            }
        } else {
            eprintln!("LLM provided no <hnt-shell> command. What would you like to do?");
            let options = vec![
                "Provide new instructions for the LLM.".to_string(),
                "Quit. Terminate the agent.".to_string(),
            ];

            let args = SelectArgs {
                height: 10,
                color: Some(4),
            };
            let tty = Tty::new()?;
            let selection = {
                let mut select = TuiSelect::new(options, &args, tty)?;
                select.run()?
            };

            match selection.as_deref() {
                Some("Provide new instructions for the LLM.") => {
                    let new_instructions = get_input_from_editor("", cli.use_pane)?;
                    print_turn_header("querent", human_turn_counter)?;
                    human_turn_counter += 1;
                    // Print the human's message with reset color
                    execute!(stdout(), ResetColor, Print(&new_instructions))?;
                    // Add a blank line for spacing, then the footer
                    println!();
                    print_turn_footer(Color::Magenta)?;
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
                    // Some("Quit. Terminate the agent.") or None
                    eprintln!("Aborting");
                    break;
                }
            }
        }
    }

    // 6. Clean up headless session on exit is handled by SessionGuard.

    Ok(())
}
