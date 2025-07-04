# hnt-tui

A lightweight TUI toolkit for interactive command-line workflows.

## Overview

`hnt-tui` provides two essential tools for enhancing your terminal experience:

- **`select`** - Transform any piped list into an interactive menu
- **`pane`** - Run commands in a dedicated TUI pane without disrupting your terminal

## Installation

```bash
git clone https://github.com/veilm/hinata
./hinata/install.sh
```

## Usage

### Interactive Selection

Turn any list into a navigable menu:

```bash
# Select a file
ls | hnt-tui select

# Choose a git branch
git branch | hnt-tui select

# Pick a process to kill
ps aux | grep node | hnt-tui select | awk '{print $2}' | xargs kill
```

**Navigation:**
- `↑/↓`, `Tab/Shift+Tab`, `{Ctrl/Alt}+{J/K}` - Navigate items
- `Enter` - Select current item
- `Esc` or `Ctrl+C` - Cancel

**Options:**

```bash
# Limit menu height (default: 10)
ls | hnt-tui select --height 5

# Customize selection color (0-7)
ls | hnt-tui select --color 3  # Yellow highlight

# Custom selection prefix
ls | hnt-tui select --prefix "→ "
```

### Command Panes (WIP)

Run commands in an isolated 20-line pane:

```bash
# Monitor logs without losing context
hnt-tui pane -- tail -f /var/log/system.log

# Run a build while keeping your place
hnt-tui pane -- cargo build --release

# Quick server for testing
hnt-tui pane -- python -m http.server 8000

# Mini window for your editor
hnt-tui pane -- nvim /tmp/calc.py
```

The pane appears below your current position and cleans up when the command exits.

## Examples

**Quick file picker:**
```bash
vim $(find . -type f | hnt-tui select)
```

**Interactive docker container selector:**
```bash
docker exec -it $(docker ps --format "table {{.Names}}" | tail -n +2 | hnt-tui select) bash
```

**Branch switcher:**
```bash
git checkout $(git branch -a | sed 's/^[* ]*//' | hnt-tui select)
```

## Tips

- `hnt-tui select` outputs to stdout, making it perfect for command substitution
- When not in an interactive terminal, `select` falls back to printing the first line
- The `pane` command preserves your terminal state and cursor position

## License
MIT

README by Claude 4 Opus
