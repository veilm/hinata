use anyhow::{Context, Result};
use common_path;
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
