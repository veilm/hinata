# Line-Buffered Streaming with Spinner

This document describes the new line-buffered streaming feature for `hnt-agent` that provides a cleaner visual experience during LLM response streaming.

## Overview

The line-buffered streaming feature changes how LLM responses are displayed:
- **Traditional streaming**: Displays tokens as they arrive, potentially mid-word or mid-line
- **Line-buffered streaming**: Buffers tokens until a complete line is ready, then displays it all at once

## Benefits

1. **Clean visual state**: Always at the end of a complete line, never mid-word
2. **Simple spinner placement**: Spinner appears on its own line below content
3. **No complex cursor manipulation**: Eliminates the need for save/restore cursor position ANSI sequences
4. **Predictable behavior**: Consistent visual updates without flickering

## Architecture

### Components

1. **LineBuffer** (`pkg/linebuffer/linebuffer.go`)
   - Accumulates streaming tokens
   - Handles word wrapping at specified width
   - Emits complete lines when ready
   - Flushes remaining content when stream ends

2. **StreamingSpinner** (`pkg/streamspinner/streamspinner.go`)
   - Displays animated spinner during streaming
   - Clears itself when new content arrives
   - Reprints on the next line after content
   - Shows elapsed time counter

3. **Integration** (`pkg/agent/streaming.go`)
   - Connects LineBuffer with LLM streaming
   - Manages color coding for different content types
   - Handles shell block parsing

## Usage

Enable line-buffered streaming with the `--buffered-streaming` flag:

```bash
hnt-agent --buffered-streaming -m "Your message here"
```

## Visual Flow

```
[Content line 1]
[Content line 2]
[Spinner] Thinking... (2s) ⠋   <- Updates in place
```

When new content arrives:
```
[Content line 1]
[Content line 2]
[Content line 3]                <- Spinner cleared, new content printed
[Spinner] Thinking... (3s) ⠙   <- Spinner on new line
```

## Implementation Details

The spinner operates on a simple principle:
1. Print on its own line
2. Use `\r\033[K` to clear and redraw itself during animation
3. When new content arrives:
   - Clear the spinner line completely
   - Print the new content line
   - Print the spinner on a new line

This approach avoids complex ANSI cursor manipulation while providing a smooth visual experience.