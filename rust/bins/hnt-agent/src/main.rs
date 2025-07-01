use anyhow::{bail, Context, Result};
use chrono::Utc;
use clap::Parser;
use futures_util::StreamExt;
use headlesh::Session;
use hinata_core::chat;
use hinata_core::llm::LlmConfig;
use regex::Regex;
use std::env;
use std::fs;
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

    /// Model to use (passed through to hnt-chat gen).
    #[arg(long)]
    model: Option<String>,

    /// Enable unsafe debugging options in hinata tools.
    #[arg(long)]
    debug_unsafe: bool,

    /// Skip confirmation steps before executing commands or adding messages.
    #[arg(long)]
    no_confirm: bool,
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

fn get_user_instruction(message: Option<String>) -> Result<String> {
    if let Some(message) = message {
        return Ok(message);
    }

    let editor = env::var("EDITOR").context("EDITOR environment variable not set")?;

    let temp_file_name = format!(
        "hnt-agent-msg-{}.txt",
        Utc::now().timestamp_nanos_opt().unwrap()
    );
    let temp_file_path = env::temp_dir().join(temp_file_name);

    fs::write(&temp_file_path, b"")?;

    let status = StdCommand::new(&editor)
        .arg(&temp_file_path)
        .status()
        .with_context(|| format!("Failed to open editor: {}", editor))?;

    if !status.success() {
        bail!("Editor exited with a non-zero status code");
    }

    let instruction = fs::read_to_string(&temp_file_path)
        .context("Failed to read user instruction from temporary file")?;
    fs::remove_file(temp_file_path).ok(); // Ignore error on cleanup

    if instruction.trim().is_empty() {
        bail!("User instruction is empty. Aborting.");
    }

    Ok(instruction)
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    eprintln!("TRACE: Right after Cli::parse().");

    // 1. Set up headless session
    eprintln!("TRACE: Before creating the session ID.");
    let session_id = format!("hnt-agent-{}", Utc::now().timestamp_nanos_opt().unwrap());
    eprintln!("TRACE: After creating the session ID: {}", &session_id);
    eprintln!("TRACE: Before Session::create.");
    let session = Session::create(session_id.clone()).await?;
    eprintln!("TRACE: After Session::create.");
    eprintln!("TRACE: Before session.spawn.");
    session.spawn(None)?;
    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    eprintln!("TRACE: After session.spawn.");
    let _session_guard = SessionGuard { session };
    eprintln!("TRACE: After instantiating SessionGuard.");

    // 2. Get system and user messages (from args, files, or $EDITOR)
    eprintln!("TRACE: Before getting the system prompt.");
    let system_prompt = if let Some(system) = cli.system {
        let path = Path::new(&system);
        if path.is_file() {
            Some(fs::read_to_string(path)?)
        } else {
            Some(system)
        }
    } else {
        None
    };
    eprintln!("TRACE: After getting the system prompt.");
    eprintln!("TRACE: Before getting the user instruction.");
    let user_instruction = get_user_instruction(cli.message)?;
    eprintln!("TRACE: After getting the user instruction.");

    // 3. Create a new chat conversation (e.g., using `hinata_core::chat::create_new_conversation`)
    eprintln!("TRACE: Before creating the conversation directory.");
    let conversations_dir = chat::get_conversations_dir()?;
    let conversation_dir = chat::create_new_conversation(&conversations_dir)?;
    eprintln!("TRACE: After creating the conversation directory.");

    // 4. Add system message and start priming sequence.
    if let Some(ref prompt) = system_prompt {
        eprintln!("TRACE: Before writing system message file.");
        chat::write_message_file(&conversation_dir, chat::Role::System, &prompt)?;
        eprintln!("TRACE: After writing system message file.");
    }

    // Priming sequence
    eprintln!("TRACE: Starting priming sequence.");
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

    eprintln!(
        "\n> Executing priming command:\n---\n{}\n---",
        priming_command
    );
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
    eprintln!("TRACE: Priming sequence finished.");

    // Add the real user instruction
    eprintln!("TRACE: Before writing user message file.");
    chat::write_message_file(&conversation_dir, chat::Role::User, &user_instruction)?;
    eprintln!("TRACE: After writing user message file.");

    eprintln!(
        "Created conversation: {}",
        conversation_dir.to_string_lossy()
    );

    // 5. Start the main interaction loop:
    eprintln!("TRACE: Right before the main loop starts.");
    loop {
        // a. Pack conversation and generate LLM response
        let mut buffer = Cursor::new(Vec::new());
        chat::pack_conversation(&conversation_dir, &mut buffer, false)?;
        let prompt_bytes = buffer.into_inner();
        let prompt = String::from_utf8(prompt_bytes)
            .context("Failed to convert packed conversation to string")?;

        let config = LlmConfig {
            model: cli
                .model
                .clone()
                .unwrap_or_else(|| "openrouter/deepseek/deepseek-chat-v3-0324:free".to_string()),
            system_prompt: system_prompt.clone(),
            include_reasoning: cli.debug_unsafe,
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

        println!("{}", llm_response);

        // Parse LLM response for the last <hnt-shell> command and execute it.
        let re = Regex::new(r"(?s)<hnt-shell>(.*?)</hnt-shell>")?;
        if let Some(captures) = re.captures_iter(&llm_response).last() {
            if let Some(command_match) = captures.get(1) {
                let command_text = command_match.as_str().trim();
                eprintln!("\n> Executing command:\n---\n{}\n---", command_text);

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
            eprintln!("LLM provided no action. Exiting.");
            break;
        }
    }

    // 6. Clean up headless session on exit is handled by SessionGuard.

    Ok(())
}
