use anyhow::{bail, Context, Result};
use clap::{ArgAction, Parser, Subcommand};
use futures_util::StreamExt;
use hinata_core::chat::{self, Role};
use hinata_core::llm::{stream_llm_response, LlmConfig, LlmStreamEvent, SharedArgs};
use std::env;
use std::fs;
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

        /// For 'assistant' role only. If input starts with <think>...</think>, save it to a separate reasoning file.
        #[arg(long, action = ArgAction::SetTrue)]
        separate_reasoning: bool,
    },

    /// Pack conversation messages for processing
    #[command(alias = "package")]
    Pack {
        /// Path to the conversation directory (overrides env var, defaults to latest)
        #[arg(short, long)]
        conversation: Option<PathBuf>,

        /// Merge consecutive messages from the same author
        #[arg(long, action = ArgAction::SetTrue)]
        merge: bool,
    },

    /// Generate the next message in a conversation
    Gen {
        /// Path to the conversation directory (overrides env var, defaults to latest)
        #[arg(short, long)]
        conversation: Option<PathBuf>,

        /// Write the generated output as a new assistant message
        #[arg(short = 'w', long, action = ArgAction::SetTrue)]
        write: bool,

        /// Implies --write. Also prints the filename of the created assistant message
        #[arg(long, action = ArgAction::SetTrue)]
        output_filename: bool,

        /// Include reasoning in the output, wrapped in <think> tags.
        #[arg(long, action = ArgAction::SetTrue)]
        include_reasoning: bool,

        /// Merge consecutive messages from the same author
        #[arg(long, action = ArgAction::SetTrue)]
        merge: bool,

        #[command(flatten)]
        shared: SharedArgs,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::New => handle_new_command()?,
        Commands::Add {
            role,
            conversation,
            separate_reasoning,
        } => handle_add_command(role, conversation, separate_reasoning)?,
        Commands::Pack {
            conversation,
            merge,
        } => handle_pack_command(conversation, merge)?,
        Commands::Gen {
            shared,
            conversation,
            merge,
            write,
            output_filename,
            include_reasoning,
        } => {
            handle_gen_command(
                shared,
                conversation,
                merge,
                write,
                output_filename,
                include_reasoning,
            )
            .await?
        }
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
fn handle_add_command(
    role: Role,
    conversation_path: Option<PathBuf>,
    separate_reasoning: bool,
) -> Result<()> {
    let conv_dir = determine_conversation_dir(conversation_path.as_deref())
        .context("Failed to determine conversation directory")?;

    let mut content = String::new();
    io::stdin()
        .read_to_string(&mut content)
        .context("Failed to read from stdin")?;

    if role == Role::Assistant && separate_reasoning && content.starts_with("<think>") {
        if let Some(end_tag_pos) = content.find("</think>") {
            let split_pos = end_tag_pos + "</think>".len();
            let reasoning_content = &content[..split_pos];
            let main_content = content[split_pos..].trim_start();

            chat::write_message_file(&conv_dir, Role::AssistantReasoning, reasoning_content)
                .context("Failed to write reasoning file")?;

            let relative_path = chat::write_message_file(&conv_dir, Role::Assistant, main_content)
                .context("Failed to write assistant message file")?;

            println!("{}", relative_path.display());
            return Ok(());
        }
    }

    let relative_path = chat::write_message_file(&conv_dir, role, &content)
        .context("Failed to write message file")?;

    println!("{}", relative_path.display());
    Ok(())
}

/// Handles the 'pack' command by packing a conversation to stdout.
fn handle_pack_command(conversation_path: Option<PathBuf>, merge: bool) -> Result<()> {
    let conv_dir = determine_conversation_dir(conversation_path.as_deref())
        .context("Failed to determine conversation directory")?;

    let mut stdout = io::stdout().lock();
    chat::pack_conversation(&conv_dir, &mut stdout, merge)
        .context("Failed to pack conversation")?;

    Ok(())
}

/// Handles the 'gen' command by generating a new message from a model.
async fn handle_gen_command(
    shared: SharedArgs,
    conversation_path: Option<PathBuf>,
    merge: bool,
    write: bool,
    output_filename: bool,
    include_reasoning: bool,
) -> Result<()> {
    let conv_dir = determine_conversation_dir(conversation_path.as_deref())
        .context("Failed to determine conversation directory")?;

    let should_write = write || output_filename;

    fs::write(conv_dir.join("model.txt"), &shared.model).context("Failed to write model file")?;

    let config = LlmConfig {
        model: shared.model,
        system_prompt: None,
        include_reasoning: shared.debug_unsafe || include_reasoning,
    };

    let mut writer = Vec::new();
    chat::pack_conversation(&conv_dir, &mut writer, merge)
        .context("Failed to pack conversation")?;

    let packed_string =
        String::from_utf8(writer).context("Failed to convert packed conversation to string")?;

    let stream = stream_llm_response(config, packed_string);

    let mut content_buffer = String::new();
    let mut reasoning_buffer = String::new();
    let mut stdout = tokio::io::stdout();
    tokio::pin!(stream);

    let mut has_printed_think_tag = false;
    while let Some(event) = stream.next().await {
        match event.context("Error from LLM stream")? {
            LlmStreamEvent::Content(text) => {
                if has_printed_think_tag {
                    stdout
                        .write_all(b"</think>")
                        .await
                        .context("Failed to write to stdout")?;
                    has_printed_think_tag = false;
                }
                stdout
                    .write_all(text.as_bytes())
                    .await
                    .context("Failed to write to stdout")?;
                stdout.flush().await.context("Failed to flush stdout")?;
                content_buffer.push_str(&text);
            }
            LlmStreamEvent::Reasoning(text) => {
                if include_reasoning || shared.debug_unsafe {
                    if !has_printed_think_tag {
                        stdout
                            .write_all(b"<think>")
                            .await
                            .context("Failed to write to stdout")?;
                        has_printed_think_tag = true;
                    }
                    stdout
                        .write_all(text.as_bytes())
                        .await
                        .context("Failed to write to stdout")?;
                    stdout.flush().await.context("Failed to flush stdout")?;
                    reasoning_buffer.push_str(&text);
                }
            }
        }
    }

    if has_printed_think_tag {
        stdout
            .write_all(b"</think>")
            .await
            .context("Failed to write to stdout")?;
        stdout.flush().await.context("Failed to flush stdout")?;
    }

    let mut assistant_file_path: Option<PathBuf> = None;

    if should_write {
        if include_reasoning {
            if !reasoning_buffer.is_empty() {
                chat::write_message_file(
                    &conv_dir,
                    Role::AssistantReasoning,
                    &format!("<think>{}</think>", reasoning_buffer),
                )
                .context("Failed to write reasoning file")?;
            }
            let path = chat::write_message_file(&conv_dir, Role::Assistant, &content_buffer)
                .context("Failed to write assistant message file")?;
            assistant_file_path = Some(path);
        } else {
            let full_response = if !reasoning_buffer.is_empty() {
                format!("<think>{}</think>\n{}", reasoning_buffer, content_buffer)
            } else {
                content_buffer
            };

            if !full_response.is_empty() {
                let path = chat::write_message_file(&conv_dir, Role::Assistant, &full_response)
                    .context("Failed to write assistant message file")?;
                assistant_file_path = Some(path);
            }
        }
    }

    if output_filename {
        if let Some(path) = assistant_file_path {
            println!();
            println!("{}", path.display());
        }
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
