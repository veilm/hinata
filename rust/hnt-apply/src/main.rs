use anyhow::{Context, Result};
use clap::Parser;
use std::io::Read;
use std::path::PathBuf;

// hnt-pack is expected to be a workspace crate.

/// A utility to apply file modifications based on structured blocks from stdin.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    /// A list of file paths that are the basis for the edits.
    #[arg(required = true, num_args = 1..)]
    source_files: Vec<PathBuf>,

    /// Disallow creating new files.
    #[arg(long)]
    disallow_creating: bool,

    /// Skip a leading <think>...</think> block in the input stream.
    #[arg(long)]
    ignore_reasoning: bool,

    /// Verbose logging output.
    #[arg(long)]
    verbose: bool,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    let mut stdin_str = String::new();
    std::io::stdin()
        .read_to_string(&mut stdin_str)
        .context("Failed to read from stdin")?;

    hnt_apply::apply_changes(
        cli.source_files,
        cli.disallow_creating,
        cli.ignore_reasoning,
        cli.verbose,
        &stdin_str,
    )
}
