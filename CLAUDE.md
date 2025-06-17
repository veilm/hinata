# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hinata is a modular, minimalist AI pair programming toolkit designed for terminal use. It follows Unix philosophy with composable CLI programs that can be used by both humans and LLMs. The project aims to be an extensible alternative to tools like Aider, Cursor, and Claude Code.

## Build Commands

**Build everything:**
```bash
./build
```

**Build individual components:**
```bash
./edit/build      # Builds hnt-edit, hnt-apply, llm-pack, and hnt-llm
./agent/build     # Builds headlesh and agent components
./chat/build      # Builds hnt-chat
./fmt/highlight/build  # Builds hlmd-st syntax highlighter
./web/build       # Builds hnt-web
```

**Dependencies:**
- Required: libcurl, libjansson (likely already installed)
- Optional: uv (for Python components), pygments (for syntax highlighting)

## Core Architecture

### Component Pipeline
The system follows a composable pipeline architecture:
```
llm-pack → hnt-llm → hnt-chat → hlmd-st → hnt-apply
```

### Key Components

**`/llm/`** - Fast C-based LLM API client supporting OpenRouter, DeepSeek, OpenAI, Google Gemini
- Use `hnt-llm` directly: `echo "prompt" | hnt-llm --model <model>`

**`/chat/`** - Conversation management using plaintext files and directories
- Creates timestamped conversation directories with .md message files
- Use `hnt-chat new` to create conversations, `hnt-chat add` to add messages

**`/edit/`** - Code editing system with TARGET/REPLACE format (Aider-like functionality)  
- `hnt-edit` is the main interface for code modifications
- `hnt-apply` applies LLM-generated TARGET/REPLACE edits to files
- `llm-pack` packages source code for LLM prompts

**`/agent/headlesh/`** - CLI headless shell manager for persistent sessions
- Manages shell sessions that can be read/written programmatically

**`/web/`** - Minimal FastAPI web interface wrapping hnt-chat

### Message Format
The system uses XML for message passing between components and TARGET/REPLACE blocks for code edits, similar to Aider's format.

### File Storage
- Conversations stored as markdown files in timestamped directories
- Plain text approach enables easy debugging and version control
- Each message is a separate .md file with timestamp prefixes

## Development Workflow

1. Use `./build` to compile all components after changes
2. Test individual components with their respective build scripts
3. The system is designed for composability - test components in isolation first
4. LLM prompts are stored in `/prompts/` directories within each component