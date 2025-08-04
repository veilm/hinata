# hnt-agent

An LLM-powered shell agent that executes commands suggested by AI models

## Overview

`hnt-agent` is an interactive CLI tool that allows you to describe tasks in natural language and have an AI model generate and execute shell commands to accomplish those tasks. It provides a conversational interface with the ability to review commands before execution, maintain context across sessions, and customize the agent's behavior.

## Features

- **Natural Language Interface**: Describe what you want to do in plain English
- **Command Preview & Confirmation**: Review suggested commands before execution
- **Session Management**: Resume previous conversations and maintain context
- **Streaming Responses**: See the AI's thinking process in real-time
- **Custom Prompts**: Configure system prompts for specialized behaviors
- **Shell State Persistence**: Maintains working directory and environment variables across turns
- **Theme Support**: Snow (true color) and ANSI terminal color themes
- **Unicode Spinners**: Visual feedback during command execution with configurable spinners
- **Editor Integration**: Use your preferred text editor, or the built-in textarea for multi-line input

## Installation
```
curl hnt-agent.org/install | sh
```

## Configuration

### Prompts

Default prompts are loaded from:
- `$HINATA_PROMPTS_DIR/hnt-agent/main-shell_agent.md` (if environment variable is set)
- `$XDG_CONFIG_HOME/hinata/prompts/hnt-agent/main-shell_agent.md`
- `~/.config/hinata/prompts/hnt-agent/main-shell_agent.md`

### Agent Instructions

You can provide additional instructions for the agent by creating:
- `$XDG_CONFIG_HOME/hinata/agent/HINATA.md`
- `~/.config/hinata/agent/HINATA.md`

### Environment Variables

- `HINATA_MODEL` or `HINATA_AGENT_MODEL`: Default LLM model to use
- `HINATA_PROMPTS_DIR`: Custom directory for prompt files
- `HNT_AGENT_DEBUG`: Enable debug logging
- `NO_UNICODE`: Disable Unicode characters (use ASCII fallback)
- `HINATA_ENABLE_UNICODE_DETECTION`: Enable automatic Unicode support detection

## Usage

### Basic Usage

```bash
# Interactive mode - prompts for input
hnt-agent

# Direct command with message
hnt-agent -m "find all Python files modified in the last week"

# Skip confirmation prompts
hnt-agent -m "list files" --no-confirm

# Use a specific model
hnt-agent --model openrouter/anthropic/claude-3.5-sonnet -m "explain this directory structure"
```
### Examples

#### Quick File Operations
```bash
hnt-agent -m "create a new Python project structure with src/, tests/, and docs/ directories"
```

#### Data Processing
```bash
hnt-agent -m "find all CSV files in the current directory and count the total number of lines"
```

#### System Information
```bash
hnt-agent -m "show system resource usage and top 5 processes by memory"
```

#### Development Tasks
```bash
hnt-agent -m "set up a git repository, create a .gitignore for Node.js, and make initial commit"
```

#### Piping Input
```bash
echo "analyze these log files for errors" | hnt-agent --stdin
```

#### Resume Previous Session
```bash
# Sessions are stored in XDG_DATA_HOME/hinata/conversations/
hnt-agent -s ~/.local/share/hinata/chat/conversations/1754322938197910903
```
