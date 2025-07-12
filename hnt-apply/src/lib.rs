use anyhow::{bail, Context, Result};
use std::path::{Path, PathBuf};

// hnt-pack is expected to be a workspace crate.

#[derive(Debug)]
struct ChangeBlock {
    relative_path: String,
    target: Vec<String>,
    replace: Vec<String>,
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

    for (i, block) in blocks.iter().enumerate() {
        if verbose {
            println!("---");
        }

        apply_change_block(
            i,
            block,
            &common_root,
            &source_files,
            disallow_creating,
            verbose,
        )?;
    }

    Ok(())
}

fn parse_blocks(input: &str) -> Result<Vec<ChangeBlock>> {
    let mut blocks = Vec::new();
    let lines: Vec<String> = input.lines().map(String::from).collect();
    let mut i = 0;

    while i < lines.len() {
        // 1. Find the start of a block.
        // This is robust to conversational text before, between, and after blocks.
        let start_marker_idx = match lines[i..]
            .iter()
            .position(|line| line.trim() == "<<<<<<< TARGET")
        {
            Some(pos) => i + pos,
            None => break, // No more blocks, we're done.
        };

        // 2. The file path is the last non-empty line before the TARGET marker.
        let path = if let Some(path_line_idx) = lines[i..start_marker_idx]
            .iter()
            .rposition(|line| !line.trim().is_empty())
        {
            lines[i + path_line_idx].trim()
        } else {
            // Found a TARGET marker but no file path before it.
            // This is a malformed block, so we stop parsing gracefully.
            break;
        };

        // 3. Collect the `target` content.
        i = start_marker_idx + 1;
        let equals_marker_idx = match lines[i..].iter().position(|line| line.trim() == "=======") {
            Some(pos) => i + pos,
            None => break, // Malformed block, no separator.
        };
        let target = lines[i..equals_marker_idx].to_vec();

        // 4. Collect the `replace` content.
        i = equals_marker_idx + 1;
        let end_marker_idx = match lines[i..]
            .iter()
            .position(|line| line.trim() == ">>>>>>> REPLACE")
        {
            Some(pos) => i + pos,
            None => break, // Malformed block, no end marker.
        };
        let replace = lines[i..end_marker_idx].to_vec();

        // 5. Store the block and prepare for the next one.
        blocks.push(ChangeBlock {
            relative_path: path.to_string(),
            target,
            replace,
        });

        i = end_marker_idx + 1;
    }

    Ok(blocks)
}

fn apply_change_block(
    i: usize,
    block: &ChangeBlock,
    common_root: &Path,
    source_files: &[PathBuf],
    disallow_creating: bool,
    verbose: bool,
) -> Result<()> {
    let mut path_to_use = common_root.join(&block.relative_path);

    if !path_to_use.exists() {
        if let Some(found_path) = source_files
            .iter()
            .find(|p| p.ends_with(&block.relative_path))
        {
            path_to_use = found_path.clone();
            if verbose {
                println!(
                    "Verbose: Using fallback path {} for relative path {}",
                    path_to_use.display(),
                    &block.relative_path
                );
            }
        }
    }

    if verbose {
        println!("Processing block for {}", &block.relative_path);
        println!("Absolute path: {}", path_to_use.display());
    }

    if path_to_use.exists() {
        if !path_to_use.is_file() {
            println!("[{}] FAILED: {} is not a file", i, block.relative_path);
            return Ok(());
        }

        let content = std::fs::read_to_string(&path_to_use)
            .with_context(|| format!("Failed to read file: {}", path_to_use.display()))?;

        if block.target.is_empty() {
            if content.is_empty() {
                // This is a file creation scenario on an existing empty file.
                // Overwrite with new content.
                let mut content_to_write = block.replace.join("\n");
                if !block.replace.is_empty() {
                    content_to_write.push('\n');
                }
                std::fs::write(&path_to_use, &content_to_write).with_context(|| {
                    format!(
                        "Failed to create and write to file: {}",
                        path_to_use.display()
                    )
                })?;
                println!("[{}] CREATED: {}", i, block.relative_path);
                return Ok(());
            } else {
                // The file exists and is not empty, but the target is empty. This is an error.
                bail!(
                    "FAILED: empty target for existing, non-empty file: {}",
                    block.relative_path
                );
            }
        }

        let file_lines: Vec<String> = content.lines().map(String::from).collect();

        let positions: Vec<usize> = file_lines
            .windows(block.target.len())
            .enumerate()
            .filter(|(_, window)| *window == block.target.as_slice())
            .map(|(i, _)| i)
            .collect();

        if positions.is_empty() {
            bail!("FAILED: target not found in {}", block.relative_path);
        }
        if positions.len() > 1 {
            bail!(
                "FAILED: target found {} times in {}",
                positions.len(),
                block.relative_path
            );
        }

        let pos = positions[0];
        let mut new_lines = Vec::new();
        new_lines.extend_from_slice(&file_lines[..pos]);
        new_lines.extend_from_slice(&block.replace);
        new_lines.extend_from_slice(&file_lines[pos + block.target.len()..]);

        let mut new_content = new_lines.join("\n");
        if !new_lines.is_empty() {
            new_content.push('\n');
        }
        std::fs::write(&path_to_use, new_content)
            .with_context(|| format!("Failed to write to file: {}", path_to_use.display()))?;

        println!("[{}] OK: {}", i, block.relative_path);
    } else {
        // File does not exist
        if disallow_creating {
            println!(
                "[{}] FAILED: {} - file does not exist and --disallow-creating is set",
                i, block.relative_path
            );
            return Ok(());
        }
        if !block.target.is_empty() {
            println!(
                "[{}] FAILED: {} - file does not exist but target is not empty for creation",
                i, block.relative_path
            );
            return Ok(());
        }

        if let Some(parent) = path_to_use.parent() {
            std::fs::create_dir_all(parent).with_context(|| {
                format!(
                    "Failed to create parent directories for {}",
                    path_to_use.display()
                )
            })?;
        }
        let mut content_to_write = block.replace.join("\n");
        if !block.replace.is_empty() {
            content_to_write.push('\n');
        }
        std::fs::write(&path_to_use, &content_to_write).with_context(|| {
            format!(
                "Failed to create and write to file: {}",
                path_to_use.display()
            )
        })?;

        println!("[{}] CREATED: {}", i, block.relative_path);
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn test_simple_replace() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("file.txt");
        fs::write(&file_path, "Hello world!\n").unwrap();

        let changes = "file.txt\n\
<<<<<<< TARGET\n\
Hello world!\n\
=======\n\
Hello Rust!\n\
>>>>>>> REPLACE";

        apply_changes(vec![file_path.clone()], false, false, false, &changes).unwrap();

        let content = fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "Hello Rust!\n");
    }

    #[test]
    fn test_multiline_replace() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("file.txt");
        let initial_content = "line1\nline2\nline3\n";
        fs::write(&file_path, initial_content).unwrap();

        let changes = "file.txt\n\
<<<<<<< TARGET\n\
line2\n\
line3\n\
=======\n\
new_line2\n\
new_line3\n\
>>>>>>> REPLACE";

        apply_changes(vec![file_path.clone()], false, false, false, &changes).unwrap();

        let content = fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "line1\nnew_line2\nnew_line3\n");
    }

    #[test]
    fn test_file_creation() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("new_file.txt");

        // We need a file in the source_files to establish a common root.
        let dummy_file = dir.path().join("dummy.txt");
        fs::write(&dummy_file, "dummy content").unwrap();

        let changes = "new_file.txt\n\
<<<<<<< TARGET\n\
=======\n\
This is a new file.\n\
With two lines.\n\
>>>>>>> REPLACE";

        apply_changes(vec![dummy_file], false, false, false, &changes).unwrap();

        assert!(file_path.exists());
        let content = fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "This is a new file.\nWith two lines.\n");
    }

    #[test]
    fn test_single_newline_target() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("file.txt");

        fs::write(&file_path, "first\n\nsecond").unwrap();

        let changes = "file.txt\n\
<<<<<<< TARGET\n\
\n\
=======\n\
---\n\
>>>>>>> REPLACE";

        apply_changes(vec![file_path.clone()], false, false, false, &changes).unwrap();

        let content = fs::read_to_string(file_path).unwrap();
        assert_eq!(content, "first\n---\nsecond\n");
    }

    #[test]
    fn test_robust_to_conversational_text() {
        let dir = tempdir().unwrap();
        let file_path = dir.path().join("file.txt");
        fs::write(&file_path, "line one\nline two\n").unwrap();

        let changes = "Sure, here is the change you requested:\n\n\
file.txt\n\
<<<<<<< TARGET\n\
line one\n\
=======\n\
line 1\n\
>>>>>>> REPLACE\n\
\n\
I have replaced \"line one\" with \"line 1\".\n\
Let me know if there is anything else.";
        apply_changes(vec![file_path.clone()], false, false, false, &changes).unwrap();

        let content = fs::read_to_string(&file_path).unwrap();
        assert_eq!(content, "line 1\nline two\n");
    }
}
