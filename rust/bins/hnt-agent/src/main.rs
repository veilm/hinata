use anyhow::Result;
use chrono::Utc;
use clap::Parser;
use headlesh::Session;
use hinata_core::chat;
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

#[tokio::main]
async fn main() -> Result<()> {
    // 1. Set up headless session
    let session_id = format!("hnt-agent-{}", Utc::now().timestamp_nanos_opt().unwrap());
    let session = Session::create(session_id.clone()).await?;
    session.spawn(None).await?;
    let _session_guard = SessionGuard { session };

    let cli = Cli::parse();
    println!("{:#?}", cli);

    // 2. Get system and user messages (from args, files, or $EDITOR)

    // 3. Create a new chat conversation (e.g., using `hinata_core::chat::create_new_conversation`)

    // 4. Add system message and initial user instructions to the conversation.
    //    This may involve pre-canned steps like checking `pwd` and `os-release`.

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
