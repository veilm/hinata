use anyhow::{bail, Context, Result};
use chrono::Utc;
use clap::Parser;
use crossterm::{
    execute,
    style::{Color, Print, ResetColor, SetForegroundColor},
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
use std::path::Path;
use std::process::Command as StdCommand;
use tokio;

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

fn print_styled_block(title: &str, content: &str, color: Color) -> Result<()> {
    execute!(
        stdout(),
        SetForegroundColor(color),
        Print(format!("--- [ {} ] ---\n", title)),
        Print(content),
        Print("\n---\n"),
        ResetColor
    )
    .context("Failed to write styled output to stdout")?;
    Ok(())
}

fn get_input_from_editor(initial_text: &str, use_pane: bool) -> Result<String> {
    let editor = env::var("EDITOR").context("EDITOR environment variable not set")?;

    let temp_file_name = format!(
        "hnt-agent-msg-{}.txt",
        Utc::now().timestamp_nanos_opt().unwrap()
    );
    let temp_file_path = env::temp_dir().join(temp_file_name);

    fs::write(&temp_file_path, initial_text)?;

    let status = if use_pane {
        StdCommand::new("hnt-tui")
            .arg("pane")
            .arg(&editor)
            .arg(&temp_file_path)
            .status()
            .with_context(|| format!("Failed to open editor in pane: {}", editor))?
    } else {
        StdCommand::new(&editor)
            .arg(&temp_file_path)
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

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

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

    // Priming sequence
    debug!("Starting priming sequence.");
    let priming_user_message =
        "Could you please check the current directory and some basic OS info?";
    chat::write_message_file(&conversation_dir, chat::Role::User, priming_user_message)?;

    let priming_command = "pwd\ncat /etc/os-release";
    let priming_assistant_response = format!("<hnt-shell>\n{}\n</hnt-shell>", priming_command);
    chat::write_message_file(
        &conversation_dir,
        chat::Role::Assistant,
        &priming_assistant_response,
    )?;

    println!();
    print_styled_block("Executing Priming Command", priming_command, Color::Cyan)?;
    let captured_output = _session_guard
        .session
        .exec_captured(priming_command)
        .await?;

    let result_message = format!(
        "<hnt-shell_results>\n<stdout>\n{}</stdout>\n<stderr>\n{}</stderr>\n<exit_code>{}</exit_code>\n</hnt-shell_results>",
        captured_output.stdout,
        captured_output.stderr,
        captured_output.exit_status.code().unwrap_or(1)
    );
    chat::write_message_file(&conversation_dir, chat::Role::User, &result_message)?;
    debug!("Priming sequence finished.");

    // Add the real user instruction
    debug!("Before writing user message file.");
    chat::write_message_file(&conversation_dir, chat::Role::User, &user_instruction)?;
    debug!("After writing user message file.");

    eprintln!(
        "Created conversation: {}",
        conversation_dir.to_string_lossy()
    );

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
            model: cli.shared.model.clone(),
            system_prompt: None,
            include_reasoning: cli.shared.debug_unsafe,
        };

        let stream = hinata_core::llm::stream_llm_response(config, prompt);

        let mut llm_response = String::new();
        tokio::pin!(stream);
        while let Some(event) = stream.next().await {
            match event? {
                hinata_core::llm::LlmStreamEvent::Content(content) => {
                    llm_response.push_str(&content);
                }
                hinata_core::llm::LlmStreamEvent::Reasoning(_) => {
                    // For now, well just ignore reasoning events.
                }
            }
        }

        // Add assistants response to the conversation
        chat::write_message_file(&conversation_dir, chat::Role::Assistant, &llm_response)?;

        print_styled_block("LLM Response", &llm_response, Color::Green)?;

        // Parse LLM response for the last <hnt-shell> command and execute it.
        let re = Regex::new(r"(?s)<hnt-shell>(.*?)</hnt-shell>")?;
        if let Some(captures) = re.captures_iter(&llm_response).last() {
            if let Some(command_match) = captures.get(1) {
                let command_text = command_match.as_str().trim();

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
                    let mut select = TuiSelect::new(options, &args, tty)?;
                    let selection = select.run()?;

                    match selection.as_deref() {
                        Some("Yes. Proceed to execute Hinata's shell commands.") => {
                            // User said yes, proceed.
                        }
                        Some("No, and provide new instructions instead.") => {
                            // New instructions
                            let new_instructions = get_input_from_editor("", cli.use_pane)?;
                            chat::write_message_file(
                                &conversation_dir,
                                chat::Role::User,
                                &new_instructions,
                            )?;
                            continue;
                        }
                        _ => {
                            // Some("No. Abort execution.") or None
                            eprintln!("Aborting execution.");
                            break;
                        }
                    }
                }

                println!();
                print_styled_block("Executing Command", command_text, Color::Cyan)?;

                let captured_output = _session_guard.session.exec_captured(command_text).await?;

                let result_message = format!(
                    "<hnt-shell_results>\n<stdout>\n{}</stdout>\n<stderr>\n{}</stderr>\n<exit_code>{}</exit_code>\n</hnt-shell_results>",
                    captured_output.stdout,
                    captured_output.stderr,
                    captured_output.exit_status.code().unwrap_or(1)
                );

                // Add command output as a new user message to continue the conversation
                chat::write_message_file(&conversation_dir, chat::Role::User, &result_message)?;
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
            let mut select = TuiSelect::new(options, &args, tty)?;
            let selection = select.run()?;

            match selection.as_deref() {
                Some("Provide new instructions for the LLM.") => {
                    let new_instructions = get_input_from_editor("", cli.use_pane)?;
                    chat::write_message_file(
                        &conversation_dir,
                        chat::Role::User,
                        &new_instructions,
                    )?;
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
