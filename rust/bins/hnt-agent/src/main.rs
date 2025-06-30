use anyhow::{bail, Context, Result};
use chrono::Utc;
use clap::Parser;
use headlesh::Session;
use hinata_core::chat;
use std::env;
use std::fs;
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
        // Since `drop` can't be async, we must block on a new runtime to call async functions.
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            self.session.exit().await.ok();
        });
    }
}

fn get_user_instruction(message: Option<String>) -> Result<String> {
    if let Some(message) = message {
        return Ok(message);
    }

    let editor = env::var("EDITOR").context("EDITOR environment variable not set")?;

    let temp_file_name = format!("hnt-agent-msg-{}.txt", Utc::now().timestamp_nanos_opt().unwrap());
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
    // 1. Set up headless session
    let session_id = format!("hnt-agent-{}", Utc::now().timestamp_nanos_opt().unwrap());
    let session = Session::create(session_id.clone()).await?;
    session.spawn(None).await?;
    let _session_guard = SessionGuard { session };

    let cli = Cli::parse();

    // 2. Get system and user messages (from args, files, or $EDITOR)
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
    let user_instruction = get_user_instruction(cli.message)?;

    // 3. Create a new chat conversation (e.g., using `hinata_core::chat::create_new_conversation`)
    let conversations_dir = chat::get_conversations_dir()?;
    let conversation_dir = chat::create_new_conversation(&conversations_dir)?;

    // 4. Add system message and initial user instructions to the conversation.
    //    This may involve pre-canned steps like checking `pwd` and `os-release`.
    if let Some(prompt) = system_prompt {
        chat::write_message_file(&conversation_dir, chat::Role::System, &prompt)?;
    }
    chat::write_message_file(
        &conversation_dir,
        chat::Role::User,
        &user_instruction,
    )?;

    eprintln!(
        "Created conversation: {}",
        conversation_dir.to_string_lossy()
    );

    // 5. Start the main interaction loop:
    //    a. Generate LLM response (`hnt-chat gen`).
    //    b. Parse response, looking for shell command blocks.
    //    c. If commands, confirm with user (unless --no-confirm) and execute in session (`hnt-shell-apply`).
    //    d. Add command output back to the conversation history.
    //    e. If no commands, or after execution, prompt for next steps (e.g., new instructions, quit).
    //    f. Loop until completion or user abort.

    // 6. Clean up headless session on exit is handled by SessionGuard.

    Ok(())
}
