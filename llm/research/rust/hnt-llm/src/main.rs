use anyhow::{Context, Result};
use base64::{engine::general_purpose, Engine as _};
use clap::{Parser, Subcommand};
use futures_util::StreamExt;
use log;
use rand::RngCore;
use reqwest;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use tokio::io::{stdout, AsyncWriteExt};



// The structs needed for building the API request JSON payload.
#[derive(Serialize, Deserialize, Debug)]
struct ApiRequest {
    model: String,
    messages: Vec<Message>,
    stream: bool,
}

#[derive(Serialize, Deserialize, Debug)]
struct Message {
    role: String,
    content: String,
}

// The structs needed for deserializing the API's streaming response.
#[derive(Deserialize, Debug)]
struct ApiResponseChunk {
    choices: Vec<Choice>,
}

#[derive(Deserialize, Debug)]
struct Choice {
    delta: Delta,
}

#[derive(Deserialize, Debug)]
struct Delta {
    content: Option<String>,
    reasoning: Option<String>,
    reasoning_content: Option<String>,
}

/// A command-line interface for the hnt-llm binary.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,

    /// The model to use for the LLM.
    #[arg(short, long, env = "HINATA_LLM_MODEL", default_value = "openrouter/deepseek/deepseek-chat-v3-0324:free")]
    model: String,

    /// The system prompt to use.
    #[arg(short, long)]
    system: Option<String>,

    /// Include reasoning in the output.
    #[arg(long)]
    include_reasoning: bool,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Save an API key.
    SaveKey(SaveKey),
    /// List available API keys.
    ListKeys(ListKeys),
    /// Delete an API key.
    DeleteKey(DeleteKey),
}

/// Save a new API key with a given name.
#[derive(Parser, Debug)]
struct SaveKey {
    /// The name of the key to save.
    name: String,
}

/// List all saved API keys.
#[derive(Parser, Debug)]
struct ListKeys {}

/// Delete an API key by name.
#[derive(Parser, Debug)]
struct DeleteKey {
    /// The name of the key to delete.
    name: String,
}

struct Provider {
    name: &'static str,
    api_url: &'static str,
    env_var: &'static str,
    extra_headers: &'static [(&'static str, &'static str)],
}

static PROVIDERS: &[Provider] = &[
    Provider {
        name: "openai",
        api_url: "https://api.openai.com/v1/chat/completions",
        env_var: "OPENAI_API_KEY",
        extra_headers: &[],
    },
    Provider {
        name: "openrouter",
        api_url: "https://openrouter.ai/api/v1/chat/completions",
        env_var: "OPENROUTER_API_KEY",
        extra_headers: &[
            ("HTTP-Referer", "https://github.com/hinata-team/hinata-lang"),
            ("X-Title", "Hinata-LLM"),
        ],
    },
    Provider {
        name: "deepseek",
        api_url: "https://api.deepseek.com/chat/completions",
        env_var: "DEEPSEEK_API_KEY",
        extra_headers: &[],
    },
    Provider {
        name: "google",
        api_url: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        env_var: "GOOGLE_API_KEY",
        extra_headers: &[],
    },
];

#[tokio::main]
async fn main() -> Result<()> {
    env_logger::init();
    let cli = Cli::parse();



    match &cli.command {
        Some(Commands::SaveKey(args)) => handle_save_key(args).await?,
        Some(Commands::ListKeys(args)) => handle_list_keys(args).await?,
        Some(Commands::DeleteKey(args)) => handle_delete_key(args).await?,
        None => {
            run_llm(&cli).await?;
        }
    }

    Ok(())
}

fn build_messages_from_stdin(
    stdin_content: &str,
    system_prompt: Option<String>,
) -> anyhow::Result<Vec<Message>> {
    use regex::Regex;

    let mut messages = Vec::new();

    if let Some(prompt) = system_prompt {
        messages.push(Message {
            role: "system".to_string(),
            content: prompt,
        });
    }

    // This regex captures content within <hnt-tag>...</hnt-tag>
    let tag_re = Regex::new(r"(?s)<(hnt-[\w-]+)>(.*?)</([\w-]+)>").unwrap();
    let mut non_tag_content = String::new();
    let mut last_end = 0;

    for cap in tag_re.captures_iter(stdin_content) {
        let full_match = cap.get(0).unwrap();
        non_tag_content.push_str(&stdin_content[last_end..full_match.start()]);
        last_end = full_match.end();

        let tag_name = cap.get(1).unwrap().as_str();
        let content = cap.get(2).unwrap().as_str();
        let close_tag_name = cap.get(3).unwrap().as_str();

        if tag_name != close_tag_name {
            log::warn!(
                "Mismatched hnt tag: <{}> closed by </{}>. Skipping.",
                tag_name,
                close_tag_name
            );
            continue;
        }

        let role = match tag_name {
            "hnt-system" => {
                if messages.iter().any(|m| m.role == "system") {
                    log::warn!("<hnt-system> tag found in stdin, but a system prompt was already provided via --system argument. The stdin system prompt will be ignored.");
                    continue;
                }
                "system"
            }
            "hnt-user" => "user",
            "hnt-assistant" => "assistant",
            _ => {
                log::warn!("Unknown hnt tag '{}' found. It will be ignored.", tag_name);
                continue;
            }
        };

        messages.push(Message {
            role: role.to_string(),
            content: hinata_escape::unescape(content),
        });
    }

    non_tag_content.push_str(&stdin_content[last_end..]);

    let trimmed_user_content = non_tag_content.trim();
    if !trimmed_user_content.is_empty() {
        messages.push(Message {
            role: "user".to_string(),
            content: hinata_escape::unescape(trimmed_user_content),
        });
    }

    Ok(messages)
}

#[derive(PartialEq)]
enum OutputPhase {
    Init,
    Thinking,
    Responding,
}

struct StreamState {
    phase: OutputPhase,
    think_tag_printed: bool,
}

impl StreamState {
    fn new() -> Self {
        StreamState {
            phase: OutputPhase::Init,
            think_tag_printed: false,
        }
    }
}

async fn process_sse_data(
    chunk: &ApiResponseChunk,
    state: &mut StreamState,
    include_reasoning: bool,
) -> Result<()> {
    if let Some(choice) = chunk.choices.get(0) {
        let delta = &choice.delta;
        let mut out = stdout();

        // Handle reasoning
        if delta.reasoning.is_some() {
            if state.phase == OutputPhase::Init {
                state.phase = OutputPhase::Thinking;
                if include_reasoning {
                    out.write_all(b"<think>").await?;
                    out.flush().await?;
                    state.think_tag_printed = true;
                }
            }
        }

        if let Some(reasoning_content) = &delta.reasoning_content {
            if state.phase == OutputPhase::Thinking && include_reasoning {
                out.write_all(reasoning_content.as_bytes()).await?;
                out.flush().await?;
            }
        }

        // Handle content
        if let Some(content) = &delta.content {
            if state.phase == OutputPhase::Thinking {
                state.phase = OutputPhase::Responding;
                if state.think_tag_printed {
                    out.write_all(b"</think>\n").await?;
                    // Flushed with content to make it appear atomic
                }
            } else if state.phase == OutputPhase::Init {
                state.phase = OutputPhase::Responding;
            }

            if state.phase == OutputPhase::Responding {
                out.write_all(content.as_bytes()).await?;
                out.flush().await?;
            }
        }
    }
    Ok(())
}


/// Main logic for running the LLM.
async fn run_llm(cli: &Cli) -> Result<()> {
    let (provider_name, model_name_str) = match cli.model.split_once('/') {
        Some((provider, model)) => (provider, model),
        None => ("openrouter", cli.model.as_str()),
    };

    let provider = PROVIDERS
        .iter()
        .find(|p| p.name == provider_name)
        .ok_or_else(|| anyhow::anyhow!("Provider '{}' not found", provider_name))?;

    let api_key = match std::env::var(provider.env_var) {
        Ok(key) => Some(key),
        Err(_) => get_api_key_from_store(provider.name).await?,
    }
    .ok_or_else(|| {
        anyhow::anyhow!(
            "API key for '{}' not found. Please set {} or save the key with `hnt-llm save-key {}`",
            provider.name,
            provider.env_var,
            provider.name
        )
    })?;

    let mut stdin_content = String::new();
    std::io::stdin().read_to_string(&mut stdin_content)?;

    let messages = build_messages_from_stdin(&stdin_content, cli.system.clone())?;

    let api_request = ApiRequest {
        model: model_name_str.to_string(),
        messages,
        stream: true,
    };

    let client = reqwest::Client::new();
    let url = provider.api_url.replace("{model}", model_name_str);

    let mut req_builder = client.post(url).bearer_auth(api_key).json(&api_request);

    for (key, value) in provider.extra_headers {
        req_builder = req_builder.header(*key, *value);
    }

    let res = req_builder.send().await?;

    if !res.status().is_success() {
        let status = res.status();
        let text = res.text().await?;
        return Err(anyhow::anyhow!(
            "API request failed with status {}: {}",
            status,
            text
        ));
    }

    let mut stream_state = StreamState::new();
    let mut stream = res.bytes_stream();
    let mut buffer = Vec::new();

    while let Some(item) = stream.next().await {
        buffer.extend_from_slice(&item?);

        while let Some((pos, len)) = {
            let pos_crlf = buffer.windows(4).position(|w| w == b"\r\n\r\n");
            let pos_lf = buffer.windows(2).position(|w| w == b"\n\n");

            match (pos_crlf, pos_lf) {
                (Some(p_crlf), Some(p_lf)) => {
                    if p_crlf < p_lf {
                        Some((p_crlf, 4))
                    } else {
                        Some((p_lf, 2))
                    }
                }
                (Some(p_crlf), None) => Some((p_crlf, 4)),
                (None, Some(p_lf)) => Some((p_lf, 2)),
                (None, None) => None,
            }
        } {
            let message_bytes = buffer.drain(..pos + len).collect::<Vec<u8>>();
            let message = String::from_utf8_lossy(&message_bytes);

            for line in message.lines() {
                if line.starts_with("data: ") {
                    let data = &line["data: ".len()..];
                    if data.trim() == "[DONE]" {
                        if stream_state.think_tag_printed && stream_state.phase == OutputPhase::Thinking
                        {
                            let mut out = stdout();
                            out.write_all(b"</think>\n").await?;
                            out.flush().await?;
                        }
                        return Ok(());
                    }
                    match serde_json::from_str::<ApiResponseChunk>(data) {
                        Ok(api_chunk) => {
                            process_sse_data(&api_chunk, &mut stream_state, cli.include_reasoning)
                                .await?;
                        }
                        Err(e) => {
                            log::warn!("Failed to deserialize chunk: {} - data: '{}'", e, data);
                        }
                    }
                }
            }
        }
    }

    if stream_state.think_tag_printed && stream_state.phase == OutputPhase::Thinking {
        let mut out = stdout();
        out.write_all(b"</think>\n").await?;
        out.flush().await?;
    }

    Ok(())
}

/// Handles the 'save-key' subcommand.
async fn handle_save_key(args: &SaveKey) -> Result<()> {
    let config_dir = get_hinata_dir("config")?;
    let data_dir = get_hinata_dir("data")?;
    ensure_local_key(&data_dir)?;

    let keys_path = config_dir.join("keys");

    let api_key = rpassword::prompt_password(format!("Enter API key for '{}': ", args.name))
        .with_context(|| "Failed to read API key from prompt")?;

    let mut lines = if keys_path.exists() {
        fs::read_to_string(&keys_path)?
            .lines()
            .map(String::from)
            .collect()
    } else {
        Vec::new()
    };

    let key_prefix = format!("{}=", args.name);
    let key_exists = lines.iter().any(|line| line.starts_with(&key_prefix));
    lines.retain(|line| !line.starts_with(&key_prefix));

    let local_key = read_local_key(&data_dir)?;
    let mut data_to_encrypt = api_key.into_bytes();
    xor_crypt(&local_key, &mut data_to_encrypt);

    let encoded_key = general_purpose::STANDARD.encode(&data_to_encrypt);
    lines.push(format!("{}={}", args.name, encoded_key));

    fs::write(&keys_path, lines.join("\n") + "\n")?;
    set_permissions(&keys_path)?;

    if key_exists {
        println!("Updated key '{}'.", args.name);
    } else {
        println!("Saved key '{}'.", args.name);
    }

    Ok(())
}

/// Handles the 'list-keys' subcommand.
async fn handle_list_keys(_args: &ListKeys) -> Result<()> {
    let config_dir = get_hinata_dir("config")?;
    let keys_path = config_dir.join("keys");

    if !keys_path.exists() {
        println!("No keys saved.");
        return Ok(());
    }

    let content = fs::read_to_string(keys_path)?;
    let keys: Vec<_> = content
        .lines()
        .filter_map(|line| line.split('=').next())
        .collect();

    if keys.is_empty() {
        println!("No keys saved.");
    } else {
        println!("Saved API keys:");
        for key in keys {
            println!("- {}", key);
        }
    }

    Ok(())
}

/// Handles the 'delete-key' subcommand.
async fn handle_delete_key(args: &DeleteKey) -> Result<()> {
    let config_dir = get_hinata_dir("config")?;
    let keys_path = config_dir.join("keys");

    if !keys_path.exists() {
        println!("Key '{}' not found.", args.name);
        return Ok(());
    }

    let lines: Vec<String> = fs::read_to_string(&keys_path)?
        .lines()
        .map(String::from)
        .collect();

    let key_prefix = format!("{}=", args.name);
    let mut key_found = false;
    let new_lines: Vec<_> = lines
        .into_iter()
        .filter(|line| {
            if line.starts_with(&key_prefix) {
                key_found = true;
                false
            } else {
                true
            }
        })
        .collect();

    if !key_found {
        println!("Key '{}' not found.", args.name);
        return Ok(());
    }

    fs::write(&keys_path, new_lines.join("\n") + "\n")?;
    set_permissions(&keys_path)?;

    println!("Deleted key '{}'.", args.name);

    Ok(())
}

async fn get_api_key_from_store(key_name: &str) -> anyhow::Result<Option<String>> {
    let config_dir = get_hinata_dir("config")?;
    let keys_path = config_dir.join("keys");

    if !keys_path.exists() {
        return Ok(None);
    }

    let content = fs::read_to_string(&keys_path)?;
    let key_prefix = format!("{}=", key_name);

    if let Some(line) = content.lines().find(|line| line.starts_with(&key_prefix)) {
        if let Some(encoded_key) = line.splitn(2, '=').nth(1) {
            let data_dir = get_hinata_dir("data")?;
            let local_key = read_local_key(&data_dir)?;
            let mut encrypted_data = general_purpose::STANDARD.decode(encoded_key)?;
            xor_crypt(&local_key, &mut encrypted_data);
            let api_key = String::from_utf8(encrypted_data)?;
            return Ok(Some(api_key));
        }
    }

    Ok(None)
}

fn get_hinata_dir(dir_type: &str) -> anyhow::Result<PathBuf> {
    let base_dir = match dir_type {
        "config" => dirs::config_dir(),
        "data" => dirs::data_dir(),
        _ => return Err(anyhow::anyhow!("Invalid directory type specified: '{}'", dir_type)),
    };

    let dir = base_dir
        .ok_or_else(|| anyhow::anyhow!("Could not find {} directory", dir_type))?
        .join("hinata");

    fs::create_dir_all(&dir).with_context(|| format!("Failed to create directory at {}", dir.display()))?;
    Ok(dir)
}

fn ensure_local_key(data_dir: &Path) -> anyhow::Result<()> {
    let key_path = data_dir.join(".local_key");
    if !key_path.exists() {
        let mut key = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut key);
        fs::write(&key_path, key).with_context(|| "Failed to write local key")?;
        set_permissions(&key_path)?;
    }
    Ok(())
}

fn read_local_key(data_dir: &Path) -> anyhow::Result<Vec<u8>> {
    let key_path = data_dir.join(".local_key");
    fs::read(&key_path).with_context(|| "Failed to read local key")
}

fn xor_crypt(key: &[u8], data: &mut [u8]) {
    for (i, byte) in data.iter_mut().enumerate() {
        *byte ^= key[i % key.len()];
    }
}

fn set_permissions(path: &Path) -> anyhow::Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let perms = std::fs::Permissions::from_mode(0o600);
        fs::set_permissions(path, perms)
            .with_context(|| format!("Failed to set permissions on {}", path.display()))?;
    }
    // On non-UNIX systems, this is a no-op.
    Ok(())
}