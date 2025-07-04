use anyhow::Result;
use async_stream::stream;
use clap::Parser;
use futures_util::{Stream, StreamExt};
use serde::{Deserialize, Serialize};
use std::io::Read;
use tokio::io::{stdout, AsyncWriteExt};

/// Configuration for an LLM request.
#[derive(Debug, Clone)]
pub struct LlmConfig {
    pub model: String,
    pub system_prompt: Option<String>,
    pub include_reasoning: bool,
}

/// Events yielded by the LLM stream.
#[derive(Debug, Clone)]
pub enum LlmStreamEvent {
    Content(String),
    Reasoning(String),
}

// The structs needed for building the API request JSON payload.
#[derive(Serialize, Deserialize, Debug)]
pub struct ApiRequest {
    model: String,
    messages: Vec<Message>,
    stream: bool,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Message {
    role: String,
    content: String,
}

// The structs needed for deserializing the API's streaming response.
#[derive(Deserialize, Debug)]
pub struct ApiResponseChunk {
    choices: Vec<Choice>,
}

#[derive(Deserialize, Debug)]
pub struct Choice {
    delta: Delta,
}

#[derive(Deserialize, Debug)]
pub struct Delta {
    content: Option<String>,
    reasoning: Option<String>,
    reasoning_content: Option<String>,
}

#[derive(Parser, Debug, Clone)]
pub struct SharedArgs {
    /// The model to use for the LLM.
    #[arg(
        long,
        env = "HINATA_MODEL",
        default_value = "openrouter/deepseek/deepseek-chat-v3-0324:free"
    )]
    pub model: String,
    /// Enable unsafe debugging options.
    #[arg(long, help = "Enable unsafe debugging options.")]
    pub debug_unsafe: bool,
}

/// Arguments for the LLM generation task.
#[derive(Parser, Debug, Clone)]
pub struct GenArgs {
    #[command(flatten)]
    pub shared: SharedArgs,

    /// The system prompt to use.
    #[arg(short, long)]
    pub system: Option<String>,

    /// Include reasoning in the output.
    #[arg(long)]
    pub include_reasoning: bool,
}

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
            ("HTTP-Referer", "https://hnt-agent.org/"),
            ("X-Title", "hinata"),
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

pub fn build_messages(
    content: &str,
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

    while let Some(tag_start_rel) = content[current_pos..].find("<hnt-") {
        let tag_start_abs = current_pos + tag_start_rel;

        non_tag_content.push_str(&content[current_pos..tag_start_abs]);

        let remaining_from_tag = &content[tag_start_abs..];

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

        let closing_tag_start_rel = match content[content_start_abs..].find(&closing_tag) {
            Some(pos) => pos,
            None => {
                return Err(anyhow::anyhow!(
                    "Malformed hnt chat: Missing closing tag for {}",
                    open_tag
                ))
            }
        };

        let closing_tag_start_abs = content_start_abs + closing_tag_start_rel;
        let tag_content = &content[content_start_abs..closing_tag_start_abs];

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
            content: crate::escaping::unescape(tag_content),
        });

        current_pos = closing_tag_start_abs + closing_tag.len();
    }

    non_tag_content.push_str(&content[current_pos..]);

    let trimmed_user_content = non_tag_content.trim();
    if !trimmed_user_content.is_empty() {
        messages.push(Message {
            role: "user".to_string(),
            content: crate::escaping::unescape(trimmed_user_content),
        });
    }

    Ok(messages)
}

#[derive(PartialEq, Debug)]
enum OutputPhase {
    Init,
    Thinking,
    Responding,
}

fn find_sse_terminator(buffer: &[u8]) -> Option<(usize, usize)> {
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
}

pub fn stream_llm_response(
    config: LlmConfig,
    prompt_content: String,
) -> impl Stream<Item = Result<LlmStreamEvent>> {
    stream! {
        let (provider_name, model_name_str) = match config.model.split_once('/') {
            Some((provider, model)) => (provider, model),
            None => ("openrouter", config.model.as_str()),
        };

        let provider = match PROVIDERS.iter().find(|p| p.name == provider_name) {
            Some(p) => p,
            None => {
                yield Err(anyhow::anyhow!("Provider '{}' not found", provider_name));
                return;
            }
        };

        let api_key = match std::env::var(provider.env_var) {
            Ok(key) => Some(key),
            Err(_) => crate::key_management::get_api_key_from_store(provider.name).await?,
        }
        .ok_or_else(|| {
            anyhow::anyhow!(
                "API key for '{}' not found. Please set {} or save the key with `hnt-llm save-key {}`",
                provider.name,
                provider.env_var,
                provider.name
            )
        })?;

        let messages = build_messages(&prompt_content, config.system_prompt)?;

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
            let text = res.text().await.unwrap_or_else(|_| "Failed to read error body".to_string());
            yield Err(anyhow::anyhow!("API request failed with status {}: {}", status, text));
            return;
        }

        let mut stream = res.bytes_stream();
        let mut buffer = Vec::new();
        let mut done = false;

        while let Some(item) = stream.next().await {
            log::trace!("Raw chunk: {:?}", item);
            match item {
                Ok(bytes) => buffer.extend_from_slice(&bytes),
                Err(e) => {
                    log::error!("Error receiving chunk from LLM stream: {}", e);
                    yield Err(e.into());
                    break;
                }
            }

            while let Some((pos, len)) = find_sse_terminator(&buffer) {
                let message_block_bytes = &buffer[..pos];

                for line_bytes in message_block_bytes.split(|&b| b == b'\n') {
                    // Each line might have a trailing `\r` if the line ending was `\r\n`
                    let line_bytes = line_bytes.strip_suffix(b"\r").unwrap_or(line_bytes);

                    if let Some(data_bytes) = line_bytes.strip_prefix(b"data: ") {
                        let data_str = match std::str::from_utf8(data_bytes) {
                            Ok(s) => s,
                            Err(e) => {
                                log::warn!("Failed to decode SSE data as UTF-8: {}", e);
                                continue;
                            }
                        };

                        let data = data_str.trim();

                        if data.is_empty() {
                            continue;
                        }

                        if data == "[DONE]" {
                            done = true;
                            break;
                        }

                        match serde_json::from_str::<ApiResponseChunk>(data) {
                            Ok(api_chunk) => {
                                if let Some(choice) = api_chunk.choices.first() {
                                    let delta = &choice.delta;
                                    let reasoning_text = delta.reasoning_content.as_deref().or(delta.reasoning.as_deref());
                                    if let Some(text) = reasoning_text {
                                        if !text.is_empty() {
                                            yield Ok(LlmStreamEvent::Reasoning(text.to_string()));
                                        }
                                    }
                                    if let Some(text) = delta.content.as_deref() {
                                        if !text.is_empty() {
                                            yield Ok(LlmStreamEvent::Content(text.to_string()));
                                        }
                                    }
                                }
                            }
                            Err(e) => {
                                log::warn!("Failed to deserialize chunk: {} - data: '{}'", e, data);
                            }
                        }
                    }
                }

                // Drain the processed block and its terminator.
                buffer.drain(..pos + len);

                if done {
                    break;
                }
            }
            if done {
                break;
            }
        }
    }
}

/// Main logic for running the LLM.
pub async fn generate(args: &GenArgs) -> Result<()> {
    let mut stdin_content = String::new();
    std::io::stdin().read_to_string(&mut stdin_content)?;

    let config = LlmConfig {
        model: args.shared.model.clone(),
        system_prompt: args.system.clone(),
        include_reasoning: args.include_reasoning,
    };

    let stream = stream_llm_response(config, stdin_content);
    tokio::pin!(stream);

    let mut out = stdout();
    let mut phase = OutputPhase::Init;
    let mut think_tag_printed = false;

    while let Some(event) = stream.next().await {
        match event? {
            LlmStreamEvent::Content(text) => {
                if phase == OutputPhase::Init {
                    phase = OutputPhase::Responding;
                }
                if phase == OutputPhase::Thinking {
                    phase = OutputPhase::Responding;
                    if think_tag_printed {
                        out.write_all(b"</think>\n").await?;
                        think_tag_printed = false;
                    }
                }
                out.write_all(text.as_bytes()).await?;
            }
            LlmStreamEvent::Reasoning(text) => {
                if args.include_reasoning {
                    if phase == OutputPhase::Init {
                        phase = OutputPhase::Thinking;
                        if !think_tag_printed {
                            out.write_all(b"<think>").await?;
                            think_tag_printed = true;
                        }
                    }
                    if phase == OutputPhase::Thinking {
                        out.write_all(text.as_bytes()).await?;
                    }
                }
            }
        }
        out.flush().await?;
    }

    if think_tag_printed {
        out.write_all(b"</think>\n").await?;
        out.flush().await?;
    }

    Ok(())
}
