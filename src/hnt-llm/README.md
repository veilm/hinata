# hnt-llm

A streamlined CLI for interacting with multiple LLM providers through a unified interface.

## Installation
```sh
git clone https://github.com/veilm/hinata
./hinata/install.sh
```

## Quick Start

```sh
# Basic usage - defaults to OR's free DeepSeek-V3
echo "Tell me a joke about Rust" | hnt-llm

# Use a specific model
echo "Explain quantum computing" | hnt-llm --model openai/gpt-4o

# Add a system prompt
echo "Write a haiku" | hnt-llm --system "You are a poet"
```

## API Keys

Save your API keys ~securely (encrypted locally):

```sh
# Save a key
hnt-llm save-key openai
# Enter API key for 'openai': [hidden input]

# List saved keys
hnt-llm list-keys

# Delete a key
hnt-llm delete-key openai
```

Keys can also be set via environment variables:
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `DEEPSEEK_API_KEY`
- `GOOGLE_API_KEY`

## Conversation Format

hnt-llm uses a simple tag format for multi-turn conversations:

```sh
cat <<EOF | hnt-llm
<hnt-user>
What's the capital of France?
</hnt-user>

<hnt-assistant>
The capital of France is Paris.
</hnt-assistant>

<hnt-user>
Tell me more about it.
</hnt-user>
EOF
```

Any text outside the tags is treated as a user message:

```sh
# These are equivalent:
echo "Hello!" | hnt-llm
echo "<hnt-user>Hello!</hnt-user>" | hnt-llm
```

## Models

Specify models using the `provider/model` format:

```sh
# OpenAI
hnt-llm --model openai/gpt-4o
hnt-llm --model openai/gpt-4o-mini

# OpenRouter
hnt-llm --model openrouter/deepseek/deepseek-chat-v3-0324:free
hnt-llm --model openrouter/anthropic/claude-3.5-sonnet

# DeepSeek
hnt-llm --model deepseek/deepseek-chat

# Google
hnt-llm --model google/gemini-2.5-flash-preview-04-17
```

Set a default model:
```sh
export HINATA_MODEL="openai/gpt-4o"
```

## Advanced Features

### Reasoning Mode

Enable step-by-step reasoning output:

```sh
echo "What's 18% of 420?" | hnt-llm --include-reasoning
```

### System Prompts

Via command line:
```sh
hnt-llm --system "You are a helpful coding assistant"
```

Or inline:
```sh
cat <<EOF | hnt-llm
<hnt-system>
You are an expert in astronomy.
</hnt-system>

<hnt-user>
How far is the moon?
</hnt-user>
EOF
```

### Shell Integration

Create aliases for common tasks:

```sh
# ~/.bashrc or ~/.zshrc
alias ask='hnt-llm --model openai/gpt-4o-mini'
alias code='hnt-llm --system "You are a coding expert. Be concise."'
alias chat='hnt-llm --model anthropic/claude-3.5-sonnet'
```

Usage:
```sh
echo "What's a monad?" | ask
echo "Write a Python fibonacci function" | code
```

## Tips

- **Piping**: Combine with other tools
  ```sh
  cat error.log | hnt-llm --system "Explain this error"
  ```

- **Files**: Process file contents
  ```sh
  cat script.py | hnt-llm --system "Review this code"
  ```

## License
MIT

(README.md by Claude 4 Opus)
