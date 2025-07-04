use anyhow::Result;
use clap::{Parser, Subcommand};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use std::io::Read;
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

    #[command(flatten)]
    gen_args: GenArgs,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Generate text using an LLM (default command).
    #[command(name = "gen")]
    Gen(GenArgs),
    /// Save an API key.
    SaveKey(SaveKey),
    /// List available API keys.
    ListKeys(ListKeys),
    /// Delete an API key.
    DeleteKey(DeleteKey),
}

/// Arguments for the LLM generation task.
#[derive(Parser, Debug)]
struct GenArgs {
    /// The model to use for the LLM.
    #[arg(
        short,
        long,
        env = "HINATA_LLM_MODEL",
        default_value = "openrouter/deepseek/deepseek-chat-v3-0324:free"
    )]
    model: String,

    /// The system prompt to use.
    #[arg(short, long)]
    system: Option<String>,

    /// Include reasoning in the output.
    #[arg(long)]
    include_reasoning: bool,
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

mod key_store;

pub struct Provider {
    pub name: &'static str,
    pub api_url: &'static str,
    pub env_var: &'static str,
    pub extra_headers: &'static [(&'static str, &'static str)],
}

pub static PROVIDERS: &[Provider] = &[
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
        Some(Commands::Gen(args)) => run_llm(args).await?,
        Some(Commands::SaveKey(args)) => key_store::handle_save_key(args).await?,
        Some(Commands::ListKeys(args)) => key_store::handle_list_keys(args).await?,
        Some(Commands::DeleteKey(args)) => key_store::handle_delete_key(args).await?,
        None => run_llm(&cli.gen_args).await?,
    }

    Ok(())
}

fn build_messages_from_stdin(
    stdin_content: &str,
    system_prompt: Option<String>,
) -> anyhow::Result<Vec<Message>> {
    let mut messages = Vec::new();

    if let Some(prompt) = system_prompt {
        messages.push(Message {
            role: "system".to_string(),
            content: prompt,
        });
    }

    let mut current_pos = 0;
    let mut non_tag_content = String::new();

    while let Some(tag_start_rel) = stdin_content[current_pos..].find("<hnt-") {
        let tag_start_abs = current_pos + tag_start_rel;

        non_tag_content.push_str(&stdin_content[current_pos..tag_start_abs]);

        let remaining_from_tag = &stdin_content[tag_start_abs..];

        let tag_end_rel = match remaining_from_tag.find('>') {
            Some(pos) => pos,
            None => {
                return Err(anyhow::anyhow!(
                    "Malformed hnt chat: Unclosed tag starting at position {}",
                    tag_start_abs
                ))
            }
        };

        let open_tag = &remaining_from_tag[..=tag_end_rel];
        let tag_name = &open_tag[1..open_tag.len() - 1];

        let content_start_abs = tag_start_abs + tag_end_rel + 1;

        let closing_tag = format!("</{}>", tag_name);

        let closing_tag_start_rel = match stdin_content[content_start_abs..].find(&closing_tag) {
            Some(pos) => pos,
            None => {
                return Err(anyhow::anyhow!(
                    "Malformed hnt chat: Missing closing tag for {}",
                    open_tag
                ))
            }
        };

        let closing_tag_start_abs = content_start_abs + closing_tag_start_rel;
        let content = &stdin_content[content_start_abs..closing_tag_start_abs];

        let role = match tag_name {
            "hnt-system" => {
                if messages.iter().any(|m| m.role == "system") {
                    log::warn!("<hnt-system> tag found in stdin, but a system prompt was already provided via --system argument. The stdin system prompt will be ignored.");
                    current_pos = closing_tag_start_abs + closing_tag.len();
                    continue;
                }
                "system"
            }
            "hnt-user" => "user",
            "hnt-assistant" => "assistant",
            _ => {
                log::warn!("Unknown hnt tag '{}' found. It will be ignored.", tag_name);
                current_pos = closing_tag_start_abs + closing_tag.len();
                continue;
            }
        };

        messages.push(Message {
            role: role.to_string(),
            content: hinata_chat_tools::unescape(content),
        });

        current_pos = closing_tag_start_abs + closing_tag.len();
    }

    non_tag_content.push_str(&stdin_content[current_pos..]);

    let trimmed_user_content = non_tag_content.trim();
    if !trimmed_user_content.is_empty() {
        messages.push(Message {
            role: "user".to_string(),
            content: hinata_chat_tools::unescape(trimmed_user_content),
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
    if let Some(choice) = chunk.choices.first() {
        let delta = &choice.delta;
        let mut out = stdout();

        let reasoning_text = delta
            .reasoning_content
            .as_deref()
            .or(delta.reasoning.as_deref());
        let content_text = delta.content.as_deref();

        let has_reasoning_token = reasoning_text.is_some_and(|s| !s.is_empty());
        let has_content_token = content_text.is_some_and(|s| !s.is_empty());

        if state.phase == OutputPhase::Init {
            if has_reasoning_token {
                state.phase = OutputPhase::Thinking;
                if include_reasoning {
                    out.write_all(b"<think>").await?;
                    state.think_tag_printed = true;
                    out.write_all(reasoning_text.unwrap().as_bytes()).await?;
                }
            } else if has_content_token {
                state.phase = OutputPhase::Responding;
                out.write_all(content_text.unwrap().as_bytes()).await?;
            }
        } else if state.phase == OutputPhase::Thinking {
            if has_content_token {
                state.phase = OutputPhase::Responding;
                if state.think_tag_printed {
                    out.write_all(b"</think>\n").await?;
                    state.think_tag_printed = false;
                }
                out.write_all(content_text.unwrap().as_bytes()).await?;
            } else if has_reasoning_token && include_reasoning {
                out.write_all(reasoning_text.unwrap().as_bytes()).await?;
            }
        } else if state.phase == OutputPhase::Responding {
            if let Some(text) = content_text {
                out.write_all(text.as_bytes()).await?;
            }
        }

        out.flush().await?;
    }
    Ok(())
}

/// Main logic for running the LLM.
async fn run_llm(args: &GenArgs) -> Result<()> {
    let (provider_name, model_name_str) = match args.model.split_once('/') {
        Some((provider, model)) => (provider, model),
        None => ("openrouter", args.model.as_str()),
    };

    let provider = PROVIDERS
        .iter()
        .find(|p| p.name == provider_name)
        .ok_or_else(|| anyhow::anyhow!("Provider '{}' not found", provider_name))?;

    let api_key = match std::env::var(provider.env_var) {
        Ok(key) => Some(key),
        Err(_) => key_store::get_api_key_from_store(provider.name).await?,
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

    let messages = build_messages_from_stdin(&stdin_content, args.system.clone())?;

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
                if let Some(data) = line.strip_prefix("data: ") {
                    if data.trim() == "[DONE]" {
                        if stream_state.think_tag_printed
                            && stream_state.phase == OutputPhase::Thinking
                        {
                            let mut out = stdout();
                            out.write_all(b"</think>\n").await?;
                            out.flush().await?;
                        }
                        return Ok(());
                    }
                    match serde_json::from_str::<ApiResponseChunk>(data) {
                        Ok(api_chunk) => {
                            process_sse_data(&api_chunk, &mut stream_state, args.include_reasoning)
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
