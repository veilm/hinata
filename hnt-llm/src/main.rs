use anyhow::Result;
use clap::{Parser, Subcommand};

use futures_util::stream::StreamExt;
use hinata_core::{
    key_management::{
        handle_delete_key, handle_list_keys, handle_save_key, DeleteKeyArgs, ListKeysArgs,
        SaveKeyArgs,
    },
    llm::{stream_llm_response, LlmConfig, LlmStreamEvent, SharedArgs},
};
use log::LevelFilter;
use simplelog::{ColorChoice, Config, TermLogger, TerminalMode};
use std::env;
use std::io::Read;
use tokio::io::{stdout, AsyncWriteExt};

#[derive(Parser, Debug, Clone)]
pub struct GenArgs {
    #[command(flatten)]
    pub shared: SharedArgs,

    /// The system prompt to use.
    #[arg(short, long)]
    pub system: Option<String>,

    /// Include reasoning in the output.
    #[arg(long)]
    pub include_reasoning: bool,
}

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,

    #[command(flatten)]
    gen_args: GenArgs,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Generate text using a language model. This is the default command.
    Gen(GenArgs),
    /// Save an API key for a service.
    SaveKey(SaveKeyArgs),
    /// List saved API keys.
    ListKeys(ListKeysArgs),
    /// Delete a saved API key.
    DeleteKey(DeleteKeyArgs),
}

#[derive(PartialEq, Debug)]
enum OutputPhase {
    Init,
    Thinking,
    Responding,
}

async fn do_generate(args: &GenArgs) -> Result<()> {
    let model = args
        .shared
        .model
        .clone()
        .or_else(|| env::var("HINATA_LLM_MODEL").ok())
        .or_else(|| env::var("HINATA_MODEL").ok())
        .unwrap_or_else(|| "openrouter/google/gemini-2.5-flash".to_string());

    let mut stdin_content = String::new();
    std::io::stdin().read_to_string(&mut stdin_content)?;

    let config = LlmConfig {
        model,
        system_prompt: args.system.clone(),
        include_reasoning: args.include_reasoning,
    };

    let stream = stream_llm_response(config, stdin_content);
    tokio::pin!(stream);

    let mut out = stdout();
    let mut phase = OutputPhase::Init;
    let mut think_tag_printed = false;

    while let Some(event) = stream.next().await {
        match event? {
            LlmStreamEvent::Content(text) => {
                if phase == OutputPhase::Init {
                    phase = OutputPhase::Responding;
                }
                if phase == OutputPhase::Thinking {
                    phase = OutputPhase::Responding;
                    if think_tag_printed {
                        out.write_all(b"</think>\n").await?;
                        think_tag_printed = false;
                    }
                }
                out.write_all(text.as_bytes()).await?;
            }
            LlmStreamEvent::Reasoning(text) => {
                if args.include_reasoning {
                    if phase == OutputPhase::Init {
                        phase = OutputPhase::Thinking;
                        if !think_tag_printed {
                            out.write_all(b"<think>").await?;
                            think_tag_printed = true;
                        }
                    }
                    if phase == OutputPhase::Thinking {
                        out.write_all(text.as_bytes()).await?;
                    }
                }
            }
        }
        out.flush().await?;
    }

    if think_tag_printed {
        out.write_all(b"</think>\n").await?;
        out.flush().await?;
    }

    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    let gen_args_for_logging = if let Some(Commands::Gen(args)) = &cli.command {
        &args.shared
    } else {
        &cli.gen_args.shared
    };

    if gen_args_for_logging.debug_unsafe {
        TermLogger::init(
            LevelFilter::Trace,
            Config::default(),
            TerminalMode::Mixed,
            ColorChoice::Auto,
        )
        .unwrap();
    }

    match cli.command {
        Some(Commands::Gen(args)) => {
            do_generate(&args).await?;
        }
        Some(Commands::SaveKey(args)) => {
            handle_save_key(&args).await?;
        }
        Some(Commands::ListKeys(args)) => {
            handle_list_keys(&args).await?;
        }
        Some(Commands::DeleteKey(args)) => {
            handle_delete_key(&args).await?;
        }
        None => {
            do_generate(&cli.gen_args).await?;
        }
    }

    Ok(())
}
