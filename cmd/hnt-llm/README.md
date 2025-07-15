# hnt-llm (Go version)

A verbatim Go rewrite of the Rust hnt-llm tool - a streamlined CLI for interacting with multiple LLM providers through a unified interface.

## Features

- Exact same functionality as the Rust version
- Same escaping/unescaping logic for hnt-user/hnt-assistant/hnt-system tags
- Support for OpenAI, OpenRouter, DeepSeek, and Google providers
- Encrypted local API key storage
- Streaming responses
- Reasoning mode support

## Building

```bash
cd go/hnt-llm
go mod download
make build
```

## Usage

Same as the Rust version:

```bash
# Basic usage
echo "Tell me a joke" | ./bin/hnt-llm

# Use specific model
echo "Explain quantum computing" | ./bin/hnt-llm --model openai/gpt-4o

# With system prompt
echo "Write a haiku" | ./bin/hnt-llm --system "You are a poet"

# Include reasoning
echo "What's 18% of 420?" | ./bin/hnt-llm --include-reasoning
```

## Key Management

```bash
# Save a key
./bin/hnt-llm save-key openai

# List saved keys
./bin/hnt-llm list-keys

# Delete a key
./bin/hnt-llm delete-key openai
```

## Package Structure

- `pkg/llm/` - Core LLM functionality (streaming, message building)
- `pkg/escaping/` - Exact port of Rust escaping/unescaping logic
- `pkg/keymanagement/` - Encrypted API key storage
- `cmd/hnt-llm/` - Main CLI application

The packages are designed to be reusable in other Go utilities within the hinata ecosystem.