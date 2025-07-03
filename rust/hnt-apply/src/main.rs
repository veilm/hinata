use anyhow::{bail, Context, Result};
use clap::Parser;
use std::io::Read;
use std::path::{Path, PathBuf};

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

#[derive(Debug)]
struct ChangeBlock {
    relative_path: String,
    target: String,
    replace: String,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    let mut stdin_str = String::new();
    std::io::stdin()
        .read_to_string(&mut stdin_str)
        .context("Failed to read from stdin")?;

    let mut input_to_parse = stdin_str.as_str();

    if cli.ignore_reasoning {
        let trimmed_input = input_to_parse.trim_start();
        if trimmed_input.starts_with("<think>") {
            if let Some(end_pos) = trimmed_input.find("</think>") {
                input_to_parse = &trimmed_input[end_pos + "</think>".len()..];
            }
        }
    }

    let common_root = hnt_pack::get_common_prefix(&cli.source_files)
        .context("Failed to find common root for source files")?;

    if cli.verbose {
        println!("Common root: {}", common_root.display());
    }

    let blocks = parse_blocks(input_to_parse)?;

    if cli.verbose {
        println!("Parsed {} change blocks", blocks.len());
    }

    for block in &blocks {
        if cli.verbose {
            println!("---");
        }
        apply_change_block(block, &common_root, &cli)?;
    }

    Ok(())
}

fn parse_blocks(input: &str) -> Result<Vec<ChangeBlock>> {
    let mut blocks = Vec::new();
    let mut remaining = input.trim();

    while !remaining.is_empty() {
        let (path, after_path) = remaining.split_once("<<<<<<< TARGET").with_context(|| {
            format!(
                "Invalid block: missing '<<<<<<< TARGET' after path in remaining input near: '{}'",
                &remaining[..100.min(remaining.len())]
            )
        })?;

        let path = path.trim();
        anyhow::ensure!(!path.is_empty(), "Missing file path for change block");
        anyhow::ensure!(
            path.lines().count() == 1,
            "File path contains newlines: {}",
            path
        );

        let after_target_marker = after_path.strip_prefix('\n').unwrap_or(after_path);

        let (target, after_target) = after_target_marker
            .split_once("\n=======\n")
            .with_context(|| format!("Unterminated TARGET section for path: {}", path))?;

        let (replace, after_replace) = after_target
            .split_once("\n>>>>>>> REPLACE")
            .with_context(|| format!("Unterminated REPLACE section for path: {}", path))?;

        blocks.push(ChangeBlock {
            relative_path: path.to_string(),
            target: target.to_string(),
            replace: replace.to_string(),
        });

        remaining = after_replace.trim_start();
    }

    Ok(blocks)
}

fn apply_change_block(block: &ChangeBlock, common_root: &Path, cli: &Cli) -> Result<()> {
    let full_path = common_root.join(&block.relative_path);

    if cli.verbose {
        println!("Processing block for {}", &block.relative_path);
        println!("Absolute path: {}", full_path.display());
    }

    if full_path.exists() {
        if !full_path.is_file() {
            println!("FAILED: {} is not a file", block.relative_path);
            return Ok(());
        }

        let content = std::fs::read_to_string(&full_path)
            .with_context(|| format!("Failed to read file: {}", full_path.display()))?;

        if block.target.is_empty() {
            println!(
                "FAILED: {} - empty target for existing file is not allowed.",
                block.relative_path
            );
            return Ok(());
        }

        let count = content.matches(&block.target).count();
        if count == 0 {
            bail!("FAILED: target not found in {}", block.relative_path);
        }
        if count > 1 {
            bail!(
                "FAILED: target found {} times in {}",
                count,
                block.relative_path
            );
        }

        let new_content = content.replace(&block.target, &block.replace);
        std::fs::write(&full_path, new_content)
            .with_context(|| format!("Failed to write to file: {}", full_path.display()))?;

        println!("OK: {}", block.relative_path);
    } else {
        // File does not exist
        if cli.disallow_creating {
            println!(
                "FAILED: {} - file does not exist and --disallow-creating is set",
                block.relative_path
            );
            return Ok(());
        }
        if !block.target.is_empty() {
            println!(
                "FAILED: {} - file does not exist but target is not empty for creation",
                block.relative_path
            );
            return Ok(());
        }

        if let Some(parent) = full_path.parent() {
            std::fs::create_dir_all(parent).with_context(|| {
                format!(
                    "Failed to create parent directories for {}",
                    full_path.display()
                )
            })?;
        }
        std::fs::write(&full_path, &block.replace).with_context(|| {
            format!(
                "Failed to create and write to file: {}",
                full_path.display()
            )
        })?;

        println!("CREATED: {}", block.relative_path);
    }

    Ok(())
}
