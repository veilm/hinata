use anyhow::{bail, Context, Result};
use clap::Parser;
use crossterm::{
    execute,
    style::{Color, ResetColor, SetForegroundColor},
};
use dirs;
use futures_util::StreamExt;
use hinata_core::chat;
use hinata_core::llm::{LlmConfig, LlmStreamEvent, SharedArgs};
use log::debug;
use shlex;
use simplelog::{ColorChoice, Config, LevelFilter, TermLogger, TerminalMode};
use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tempfile::NamedTempFile;
use tokio::io::AsyncWriteExt;
use tokio::process::Child;
use tokio::{self, process::Command};
use which::which;

// A guard to clean up empty files that were created during execution.
// It runs on Drop, so it will execute even if the program panics or exits early.
struct CreatedFilesGuard {
    files: Vec<PathBuf>,
}
impl CreatedFilesGuard {
    fn new() -> Self {
        Self { files: Vec::new() }
    }
    fn add(&mut self, path: PathBuf) {
        self.files.push(path);
    }
}
impl Drop for CreatedFilesGuard {
    fn drop(&mut self) {
        if self.files.is_empty() {
            return;
        }
        debug!("Running cleanup for {} created files.", self.files.len());
        for file_path in &self.files {
            if file_path.exists() {
                if let Ok(metadata) = fs::metadata(file_path) {
                    if metadata.len() == 0 {
                        debug!("Removing empty created file: {:?}", file_path);
                        // Errors on cleanup are logged but don't cause a panic.
                        if let Err(e) = fs::remove_file(file_path) {
                            debug!("Failed to remove empty file {:?}: {}", file_path, e);
                        }
                    }
                }
            }
        }
    }
}

/// Edit files using hinata LLM agent.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None,
    after_help = "Example: hnt-edit -m 'Refactor foo function' src/main.py src/utils.py")]
struct Cli {
    /// System message string or path to system message file.
    #[arg(short, long)]
    system: Option<String>,

    /// User instruction message. If not provided, $EDITOR will be opened.
    #[arg(short, long)]
    message: Option<String>,

    /// Source files to edit. Required if --continue-dir is not used.
    #[arg(name = "source_files")]
    source_files: Vec<String>,

    #[command(flatten)]
    shared: SharedArgs,

    /// Path to an existing hnt-chat conversation directory to continue from a failed edit.
    #[arg(long)]
    continue_dir: Option<PathBuf>,

    /// Do not ask the LLM for reasoning.
    #[arg(long, env = "HINATA_EDIT_IGNORE_REASONING")]
    ignore_reasoning: bool,

    /// Enable verbose logging.
    #[arg(short, long)]
    verbose: bool,
}

/// Gets user instruction from CLI arg or by launching $EDITOR.
fn get_user_instruction(message: Option<String>) -> Result<String> {
    if let Some(message) = message {
        return Ok(message);
    }

    let editor = env::var("EDITOR").context("EDITOR environment variable not set")?;
    let mut file = NamedTempFile::new_in(env::temp_dir())
        .context("Failed to create temporary file for editor")?;

    let initial_text = "Replace this text with your instructions. Then write to this file and exit your\ntext editor. Leave the file unchanged or empty to abort.";
    file.write_all(initial_text.as_bytes())?;

    let path = file.into_temp_path();

    let mut editor_parts = shlex::split(&editor).context("Failed to parse EDITOR variable")?;
    let editor_cmd = editor_parts.remove(0);

    let status = std::process::Command::new(&editor_cmd)
        .args(editor_parts)
        .arg(&path)
        .status()
        .with_context(|| format!("Failed to open editor: {}", editor))?;

    if !status.success() {
        bail!("Editor exited with a non-zero status code");
    }

    let mut instruction = String::new();
    fs::File::open(&path)
        .context("Failed to open temporary file after editing")?
        .read_to_string(&mut instruction)
        .context("Failed to read from temporary file after editing")?;

    path.close()?;

    if instruction.trim() == initial_text.trim() || instruction.trim().is_empty() {
        bail!("Aborted: No changes were made.");
    }

    Ok(instruction)
}

/// Gets system message from CLI arg, file path, or default path.
fn get_system_message(system_arg: Option<String>) -> Result<String> {
    match system_arg {
        Some(system) => {
            let path = Path::new(&system);
            if path.exists() {
                fs::read_to_string(path)
                    .with_context(|| format!("Failed to read system file: {}", system))
            } else {
                Ok(system)
            }
        }
        None => {
            let config_home = dirs::config_dir().context("Could not find a config directory")?;
            let default_path = config_home.join("hinata/prompts/main-file_edit.md");
            fs::read_to_string(&default_path)
                .with_context(|| format!("Failed to read default system file: {:?}", default_path))
        }
    }
}

/// Spawns a syntax highlighter process if configured.
fn spawn_highlighter() -> Result<Option<Child>> {
    let cmd_str = match env::var("HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD") {
        Ok(cmd) => cmd,
        Err(_) => "hlmd-st".to_string(), // Default command
    };

    let Some(parts) = shlex::split(&cmd_str) else {
        debug!("Syntax highlighter command was empty or failed to parse.");
        return Ok(None);
    };
    if parts.is_empty() || which(&parts[0]).is_err() {
        debug!(
            "Syntax highlighter '{}' not found in PATH.",
            parts.get(0).unwrap_or(&"".to_string())
        );
        return Ok(None);
    }

    debug!("Spawning syntax highlighter: {:?}", parts);
    let child = Command::new(&parts[0])
        .args(&parts[1..])
        .stdin(Stdio::piped())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .context("Failed to spawn syntax highlighter")?;

    Ok(Some(child))
}

#[tokio::main]
async fn main() -> Result<()> {
    let mut cli = Cli::parse();

    if cli.verbose {
        TermLogger::init(
            LevelFilter::Debug,
            Config::default(),
            TerminalMode::Mixed,
            ColorChoice::Auto,
        )
        .context("Failed to initialize logger")?;
    }

    if env::var("HINATA_EDIT_IGNORE_REASONING").is_ok() {
        cli.ignore_reasoning = true;
    }

    if cli.continue_dir.is_none() && cli.source_files.is_empty() {
        bail!("source_files are required when not using --continue-dir");
    }

    // This guard will clean up empty files if the program exits prematurely.
    let mut created_files_guard = CreatedFilesGuard::new();

    debug!("Arguments parsed: {:?}\n", cli);

    let (conversation_dir, source_files) = match cli.continue_dir {
        Some(dir) => {
            eprintln!("Continuing conversation from: {:?}", dir);
            if !dir.is_dir() {
                bail!("Continue directory not found: {:?}", dir);
            }
            let abs_paths_file = dir.join("absolute_file_paths.txt");
            let files_str = fs::read_to_string(&abs_paths_file)
                .with_context(|| format!("Failed to read {:?}", abs_paths_file))?;
            let files: Vec<String> = files_str.lines().map(String::from).collect();

            let packed_sources = Command::new("llm-pack")
                .arg("-s")
                .args(&files)
                .output()
                .await?
                .stdout;

            let source_ref_txt_path = dir.join("source_reference.txt");
            let source_ref_chat_filename_relative = fs::read_to_string(&source_ref_txt_path)
                .with_context(|| format!("Failed to read {:?}", source_ref_txt_path))?;
            let target_source_ref_file = dir
                .join("messages")
                .join(source_ref_chat_filename_relative.trim());

            let new_source_reference_content = format!(
                "<source_reference>\n{}</source_reference>\n",
                String::from_utf8_lossy(&packed_sources)
            );

            fs::write(&target_source_ref_file, new_source_reference_content).with_context(
                || {
                    format!(
                        "Failed to write updated source reference to {:?}",
                        target_source_ref_file
                    )
                },
            )?;

            (dir, files)
        }
        None => {
            let system_message = get_system_message(cli.system)?;
            let instruction = get_user_instruction(cli.message)?;

            for file_path in &cli.source_files {
                let path = Path::new(file_path);
                if !path.exists() {
                    if let Some(parent) = path.parent() {
                        if !parent.exists() {
                            fs::create_dir_all(parent).with_context(|| {
                                format!("Failed to create parent directory for {}", file_path)
                            })?;
                        }
                    }
                    fs::File::create(path)
                        .with_context(|| format!("Failed to create file: {}", file_path))?;
                    debug!("Created missing file: {}", file_path);
                    created_files_guard.add(path.to_path_buf());
                }
            }

            let packed_sources = Command::new("llm-pack")
                .arg("-s")
                .args(&cli.source_files)
                .output()
                .await?
                .stdout;

            let conversations_dir = chat::get_conversations_dir()?;
            let new_conv_dir = chat::create_new_conversation(&conversations_dir)?;

            let abs_paths: Result<Vec<_>, _> = cli
                .source_files
                .iter()
                .map(|p| Path::new(p).canonicalize())
                .collect();
            let abs_paths = abs_paths?
                .iter()
                .map(|p| p.to_str().unwrap().to_string())
                .collect::<Vec<_>>();
            fs::write(
                new_conv_dir.join("absolute_file_paths.txt"),
                abs_paths.join("\n"),
            )?;

            chat::write_message_file(&new_conv_dir, chat::Role::System, &system_message)
                .context("Failed to write system message")?;

            let user_request = format!("<user_request>\n{}\n</user_request>", instruction);
            chat::write_message_file(&new_conv_dir, chat::Role::User, &user_request)
                .context("Failed to write user request")?;

            let source_reference = format!(
                "<source_reference>\n{}</source_reference>",
                String::from_utf8_lossy(&packed_sources)
            );
            let source_ref_filename =
                chat::write_message_file(&new_conv_dir, chat::Role::User, &source_reference)?;
            fs::write(
                new_conv_dir.join("source_reference.txt"),
                source_ref_filename.file_name().unwrap().to_str().unwrap(),
            )?;

            (new_conv_dir, cli.source_files.clone())
        }
    };

    // --- COMMON EXECUTION FLOW ---

    let mut highlighter = spawn_highlighter()?;
    let mut highlighter_stdin = highlighter.as_mut().and_then(|h| h.stdin.take());

    let llm_config = LlmConfig {
        model: cli.shared.model.clone(),
        system_prompt: None,
        include_reasoning: !cli.ignore_reasoning || cli.shared.debug_unsafe,
    };

    let mut buffer = std::io::Cursor::new(Vec::new());
    chat::pack_conversation(&conversation_dir, &mut buffer, cli.ignore_reasoning)?;
    let prompt = String::from_utf8(buffer.into_inner())?;

    let stream = hinata_core::llm::stream_llm_response(llm_config, prompt);
    tokio::pin!(stream);

    let mut llm_output = String::new();
    while let Some(event) = stream.next().await {
        match event {
            Ok(LlmStreamEvent::Content(content)) => {
                llm_output.push_str(&content);
                if let Some(stdin) = highlighter_stdin.as_mut() {
                    stdin.write_all(content.as_bytes()).await?;
                } else {
                    print!("{}", content);
                    io::stdout().flush()?;
                }
            }
            Ok(LlmStreamEvent::Reasoning(reasoning)) if !cli.ignore_reasoning => {
                let mut stdout = io::stdout();
                execute!(stdout, SetForegroundColor(Color::Yellow))?;
                print!("{}", reasoning);
                execute!(stdout, ResetColor)?;
                stdout.flush()?;
            }
            Ok(LlmStreamEvent::Reasoning(_)) => {} // Ignore if --ignore-reasoning
            Err(e) => bail!("LLM stream error: {}", e),
        }
    }
    if let Some(mut stdin) = highlighter_stdin.take() {
        stdin.flush().await?;
    }
    println!();

    if llm_output.trim().is_empty() {
        bail!("LLM produced no output. Aborting before running hnt-apply.");
    }
    chat::write_message_file(&conversation_dir, chat::Role::Assistant, &llm_output)?;

    eprintln!("\nhnt-chat dir: {:?}", conversation_dir);

    // Run hnt-apply
    let mut child = Command::new("hnt-apply")
        .arg("--ignore-reasoning")
        .args(&source_files)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()?;

    let mut stdin = child
        .stdin
        .take()
        .context("Failed to open stdin of hnt-apply")?;
    stdin.write_all(llm_output.as_bytes()).await?;
    drop(stdin); // Close stdin to signal EOF

    let output = child.wait_with_output().await?;
    io::stdout().write_all(&output.stdout)?;

    if !output.status.success() {
        let apply_stdout = String::from_utf8_lossy(&output.stdout);
        let failure_message = format!("<hnt_apply_error>\n{}</hnt_apply_error>", apply_stdout);
        chat::write_message_file(&conversation_dir, chat::Role::User, &failure_message)?;
        bail!("hnt-apply failed with exit code {}", output.status);
    }

    Ok(())
}
