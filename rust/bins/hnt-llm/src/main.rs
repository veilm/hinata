use anyhow::Result;
use clap::{Parser, Subcommand};
use hinata_core::{
    key_management::{
        handle_delete_key, handle_list_keys, handle_save_key, DeleteKeyArgs, ListKeysArgs,
        SaveKeyArgs,
    },
    llm::{generate, GenArgs},
};
use log::LevelFilter;
use simplelog::{ColorChoice, Config, TermLogger, TerminalMode};

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[arg(long, hide = true)]
    pub debug_unsafe: bool,

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

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    if cli.debug_unsafe {
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
            generate(&args).await?;
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
            generate(&cli.gen_args).await?;
        }
    }

    Ok(())
}
