use anyhow::{Context, Result};
use clap::Parser;
use std::fs;
use std::path::PathBuf;

/// A utility to pack source files for language models.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    /// A list of one or more source files to process
    #[arg(required = true, name = "source_files")]
    source_files: Vec<PathBuf>,

    /// Disable printing the markdown code fences (```)
    #[arg(short = 'n', long)]
    no_fences: bool,

    /// Print only the common ancestor directory of the source files and then exit
    #[arg(short = 'p', long)]
    print_common_path: bool,

    /// Sort the files alphabetically by their absolute paths before processing
    #[arg(short = 's', long)]
    sort: bool,
}

#[derive(Debug, Clone)]
struct FileInfo {
    absolute_path: PathBuf,
    relative_path: PathBuf,
}

/// Calculates the longest common path prefix for a slice of absolute file paths.
fn get_common_prefix(paths: &[PathBuf]) -> Result<PathBuf> {
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

fn main() -> Result<()> {
    let cli = Cli::parse();

    // 1. Resolve all input file paths to their canonical, absolute paths and ensure they are files.
    let mut absolute_paths: Vec<PathBuf> = cli
        .source_files
        .into_iter()
        .map(|path| {
            let abs_path = fs::canonicalize(&path)
                .with_context(|| format!("Failed to find or access path: {}", path.display()))?;
            if !abs_path.is_file() {
                return Err(anyhow::anyhow!(
                    "Input path is not a file: {}",
                    path.display()
                ));
            }
            Ok(abs_path)
        })
        .collect::<Result<_>>()?;

    // 2. If -p flag is present, calculate and print common path, then exit.
    if cli.print_common_path {
        let common_path = get_common_prefix(&absolute_paths)?;
        println!("{}", common_path.display());
        return Ok(());
    }

    // 3. If -s flag is present, sort files by absolute path.
    if cli.sort {
        absolute_paths.sort();
    }

    // 4. Calculate common path prefix to determine relative paths.
    let common_prefix = get_common_prefix(&absolute_paths)?;

    let files_info: Vec<FileInfo> = absolute_paths
        .iter()
        .map(|abs_path| {
            let rel_path = abs_path.strip_prefix(&common_prefix).with_context(|| {
                format!(
                    "Failed to create relative path for {} from base {}",
                    abs_path.display(),
                    common_prefix.display()
                )
            })?;
            Ok(FileInfo {
                absolute_path: abs_path.clone(),
                relative_path: rel_path.to_path_buf(),
            })
        })
        .collect::<Result<Vec<FileInfo>>>()?;

    // 5. Print the packed output.
    if !cli.no_fences {
        println!("```");
    }

    println!("<file_paths>");
    for info in &files_info {
        // Use forward slashes for cross-platform compatibility in output.
        println!(
            "{}",
            info.relative_path.to_string_lossy().replace('\\', "/")
        );
    }
    println!("</file_paths>");

    for info in &files_info {
        println!(); // Blank line between file blocks.

        // Use forward slashes for cross-platform compatibility in output.
        let relative_path_str = info.relative_path.to_string_lossy().replace('\\', "/");
        println!("<{}>", relative_path_str);

        let content = fs::read_to_string(&info.absolute_path).with_context(|| {
            format!(
                "Failed to read file content: {}",
                info.absolute_path.display()
            )
        })?;

        print!("{}", content);
        if !content.ends_with('\n') {
            println!();
        }

        println!("</{}>", relative_path_str);
    }

    if !cli.no_fences {
        println!("```");
    }

    Ok(())
}
