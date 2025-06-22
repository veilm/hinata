use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use futures_util::StreamExt;
use hinata_core::chat::{self, Role};
use hinata_core::llm::{stream_llm_response, GenArgs, LlmConfig, LlmStreamEvent};
use std::env;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use tokio::io::AsyncWriteExt;

#[derive(Parser)]
#[command(author, version, about = "Hinata Chat CLI tool.", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Create a new conversation directory
    #[command(alias = "new-conversation")]
    New,

    /// Add a message to a conversation
    #[command(alias = "add-message")]
    Add {
        /// The role of the message author
        #[arg(value_parser = clap::value_parser!(Role))]
        role: Role,

        /// Path to the conversation directory (overrides env var, defaults to latest)
        #[arg(short, long)]
        conversation: Option<PathBuf>,
    },

    /// Pack conversation messages for processing
    #[command(alias = "package")]
    Pack {
        /// Path to the conversation directory (overrides env var, defaults to latest)
        #[arg(short, long)]
        conversation: Option<PathBuf>,
    },

    /// Generate the next message in a conversation
    Gen {
        /// Path to the conversation directory (overrides env var, defaults to latest)
        #[arg(short, long)]
        conversation: Option<PathBuf>,

        #[command(flatten)]
        args: GenArgs,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::New => handle_new_command()?,
        Commands::Add { role, conversation } => handle_add_command(role, conversation)?,
        Commands::Pack { conversation } => handle_pack_command(conversation)?,
        Commands::Gen { args, conversation } => handle_gen_command(args, conversation).await?,
    }

    Ok(())
}

/// Handles the 'new' command by creating a new conversation directory.
fn handle_new_command() -> Result<()> {
    let base_conv_dir = chat::get_conversations_dir()
        .context("Failed to determine the base conversations directory")?;
    let new_conv_path = chat::create_new_conversation(&base_conv_dir)
        .context("Failed to create a new conversation")?;
    let absolute_path = new_conv_path
        .canonicalize()
        .with_context(|| format!("Failed to canonicalize path: {:?}", new_conv_path))?;
    println!("{}", absolute_path.display());
    Ok(())
}

/// Handles the 'add' command by reading from stdin and writing a new message file.
fn handle_add_command(role: Role, conversation_path: Option<PathBuf>) -> Result<()> {
    let conv_dir = determine_conversation_dir(conversation_path.as_deref())
        .context("Failed to determine conversation directory")?;

    let mut content = String::new();
    io::stdin()
        .read_to_string(&mut content)
        .context("Failed to read from stdin")?;

    let relative_path = chat::write_message_file(&conv_dir, role, &content)
        .context("Failed to write message file")?;

    println!("{}", relative_path.display());
    Ok(())
}

/// Handles the 'pack' command by packing a conversation to stdout.
fn handle_pack_command(conversation_path: Option<PathBuf>) -> Result<()> {
    let conv_dir = determine_conversation_dir(conversation_path.as_deref())
        .context("Failed to determine conversation directory")?;

    let mut stdout = io::stdout().lock();
    chat::pack_conversation(&conv_dir, &mut stdout).context("Failed to pack conversation")?;

    Ok(())
}

/// Handles the 'gen' command by generating a new message from a model.
async fn handle_gen_command(args: GenArgs, conversation_path: Option<PathBuf>) -> Result<()> {
    let conv_dir = determine_conversation_dir(conversation_path.as_deref())
        .context("Failed to determine conversation directory")?;

    let mut writer = Vec::new();
    chat::pack_conversation(&conv_dir, &mut writer).context("Failed to pack conversation")?;

    let packed_string =
        String::from_utf8(writer).context("Failed to convert packed conversation to string")?;

    let config = LlmConfig {
        model: args.model,
        system_prompt: args.system,
        include_reasoning: args.include_reasoning,
    };
    let stream = stream_llm_response(config, packed_string);

    let mut response_buffer = String::new();
    let mut stdout = tokio::io::stdout();
    tokio::pin!(stream);

    while let Some(event) = stream.next().await {
        match event.context("Error from LLM stream")? {
            LlmStreamEvent::Content(text) => {
                stdout
                    .write_all(text.as_bytes())
                    .await
                    .context("Failed to write to stdout")?;
                stdout.flush().await.context("Failed to flush stdout")?;
                response_buffer.push_str(&text);
            }
            LlmStreamEvent::Reasoning(_) => {}
        }
    }

    if !response_buffer.is_empty() {
        chat::write_message_file(&conv_dir, Role::Assistant, &response_buffer)
            .context("Failed to write assistant message file")?;
    }

    Ok(())
}

/// Determines the target conversation directory based on CLI args, env var, or latest.
fn determine_conversation_dir(cli_path: Option<&Path>) -> Result<PathBuf> {
    let conv_path = if let Some(path) = cli_path {
        path.to_path_buf()
    } else if let Ok(env_path_str) = env::var("HINATA_CHAT_CONVERSATION") {
        PathBuf::from(env_path_str)
    } else {
        let base_dir = chat::get_conversations_dir()?;
        chat::find_latest_conversation(&base_dir)?.ok_or_else(|| {
            anyhow::anyhow!("No conversation specified and no existing conversations found.")
        })?
    };

    if !conv_path.exists() {
        bail!("Conversation directory not found: {}", conv_path.display());
    }
    if !conv_path.is_dir() {
        bail!(
            "Specified conversation path is not a directory: {}",
            conv_path.display()
        );
    }

    Ok(conv_path)
}
