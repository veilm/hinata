use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};

// hnt-pack is expected to be a workspace crate.

#[derive(Debug)]
struct ChangeBlock {
    relative_path: String,
    target: String,
    replace: String,
}

pub fn apply_changes(
    source_files: Vec<PathBuf>,
    disallow_creating: bool,
    ignore_reasoning: bool,
    verbose: bool,
    stdin_str: &str,
) -> Result<()> {
    let mut input_to_parse = stdin_str;

    if ignore_reasoning {
        let trimmed_input = input_to_parse.trim_start();
        if trimmed_input.starts_with("<think>") {
            if let Some(end_pos) = trimmed_input.find("</think>") {
                input_to_parse = &trimmed_input[end_pos + "</think>".len()..];
            }
        }
    }

    let common_root = hnt_pack::get_common_prefix(&source_files)
        .context("Failed to find common root for source files")?;

    if verbose {
        println!("Common root: {}", common_root.display());
    }

    let blocks = parse_blocks(input_to_parse)?;

    if verbose {
        println!("Parsed {} change blocks", blocks.len());
    }

    for block in &blocks {
        if verbose {
            println!("---");
        }
        apply_change_block(block, &common_root, disallow_creating, verbose)?;
    }

    Ok(())
}

fn parse_one_block(input: &str) -> Result<(ChangeBlock, &str)> {
    let (before_target, after_path) = input.split_once("<<<<<<< TARGET").with_context(|| {
        format!(
            "Invalid block: missing '<<<<<<< TARGET' after path in remaining input near: '{}'",
            &input[..100.min(input.len())]
        )
    })?;

    // The file path is the last non-empty line before the TARGET marker.
    // This is robust against conversational text from the LLM.
    let path = before_target
        .lines()
        .map(|line| line.trim())
        .filter(|line| !line.is_empty())
        .last()
        .with_context(|| "Missing file path for change block")?;

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

    let block = ChangeBlock {
        relative_path: path.to_string(),
        target: target.to_string(),
        replace: replace.to_string(),
    };

    Ok((block, after_replace))
}

fn parse_blocks(input: &str) -> Result<Vec<ChangeBlock>> {
    let mut blocks = Vec::new();
    let mut remaining = input.trim();

    while !remaining.is_empty() {
        match parse_one_block(remaining) {
            Ok((block, rest)) => {
                blocks.push(block);
                remaining = rest.trim_start();
            }
            Err(_) => {
                // If we can't parse a block, assume we're done.
                // This makes the parsing robust to trailing text.
                break;
            }
        }
    }

    Ok(blocks)
}

fn apply_change_block(
    block: &ChangeBlock,
    common_root: &Path,
    disallow_creating: bool,
    verbose: bool,
) -> Result<()> {
    let full_path = common_root.join(&block.relative_path);

    if verbose {
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
        if disallow_creating {
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
