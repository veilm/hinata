use anyhow::{Context, Result};
use common_path;
use std::fs;
use std::path::PathBuf;

/// Calculates the longest common path prefix for a slice of absolute file paths.
pub fn get_common_prefix(paths: &[PathBuf]) -> Result<PathBuf> {
    if paths.is_empty() {
        return Err(anyhow::anyhow!(
            "Cannot find common path of an empty list of paths."
        ));
    }

    if paths.len() == 1 {
        // For a single file, the common prefix is its parent directory.
        return Ok(paths[0]
            .parent()
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "Could not get parent of single file path: {}",
                    paths[0].display()
                )
            })?
            .to_path_buf());
    }

    // For multiple files, use the common-path crate.
    let common = common_path::common_path_all(paths.iter().map(PathBuf::as_path))
        .context("Could not find a common path for the source files")?;

    // If the common path resolves to a file (e.g., /a/b.txt is a prefix for /a/b.txt.gz),
    // then the common parent directory should be used.
    if common.is_file() {
        Ok(common
            .parent()
            .ok_or_else(|| {
                anyhow::anyhow!("Could not get parent of common path: {}", common.display())
            })?
            .to_path_buf())
    } else {
        Ok(common)
    }
}

/// Packs a list of files into a single string, with metadata.
pub fn pack_files(paths: &[PathBuf]) -> Result<String> {
    if paths.is_empty() {
        return Ok(String::new());
    }

    let common_prefix = get_common_prefix(paths)?;

    let mut relative_paths = Vec::new();
    let mut file_content_blocks = Vec::new();

    for path in paths {
        let rel_path = path.strip_prefix(&common_prefix).with_context(|| {
            format!(
                "Path {} does not have prefix {}",
                path.display(),
                common_prefix.display()
            )
        })?;

        relative_paths.push(rel_path.display().to_string());

        let content = fs::read_to_string(path)
            .with_context(|| format!("Failed to read file {}", path.display()))?;

        let file_block = format!(
            "<{}>\n{}</{}>",
            rel_path.display(),
            content,
            rel_path.display()
        );
        file_content_blocks.push(file_block);
    }

    let mut result = String::new();
    result.push_str("<file_paths>\n");
    result.push_str(&relative_paths.join("\n"));
    result.push_str("\n</file_paths>\n\n");
    result.push_str(&file_content_blocks.join("\n\n"));

    Ok(result)
}
