# Simple TUI Proof of Concept

This demonstrates how to create a TUI (Terminal User Interface) that behaves like \`fzf\` - reserving a specific number of lines in the terminal without clearing the entire screen.

## Key Concepts

The technique uses ANSI escape sequences:

1. **Save cursor position**: \`\033[s\`
2. **Restore cursor position**: \`\033[u\`
3. **Move cursor down N lines**: \`\033[{N}B\`
4. **Move cursor up N lines**: \`\033[{N}A\`
5. **Clear current line**: \`\033[2K\`
6. **Move to beginning of line**: \`\r\`

## How It Works

1. Print some empty lines to reserve space
2. Move cursor back up to the start of reserved area
3. Use cursor positioning to update specific lines
4. Each update: save position → move to target line → clear → write → restore position

## Files

- \`minimal_tui.py\` - Bare minimum example (5 lines, simple animation)
- \`simple_tui.py\` - Full featured demo (10 lines, colors, unicode, multiple animations)
- \`demo.sh\` - Run both examples

## Usage

\`\`\`bash
# Run the minimal example
./minimal_tui.py

# Run the full example
./simple_tui.py

# Or use the demo script
./demo.sh
\`\`\`

Press \`Ctrl+C\` to exit cleanly. The terminal content above the TUI remains visible!
