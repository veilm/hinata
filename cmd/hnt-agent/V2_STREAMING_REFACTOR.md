# V2 Streaming Refactor

## Overview

This refactor introduces an OutputCoordinator to centralize all stdout writes, eliminating race conditions and improving streaming reliability.

## Key Changes

### 1. OutputCoordinator (`pkg/output/coordinator.go`)
- Single goroutine owns all stdout writes
- Commands are sent via channel (PrintLine, ShowSpinner, etc.)
- Eliminates race conditions between spinner and content
- Atomic display updates

### 2. StreamingSpinnerV2 (`pkg/streamspinner/streamspinner_v2.go`)
- Simplified wrapper around OutputCoordinator
- No longer manages its own goroutine
- All output goes through coordinator

### 3. Integration (`pkg/agent/streaming.go`)
- New `streamLLMResponseV2` function using OutputCoordinator
- Same logic flow but with centralized output
- Cleaner separation of concerns

## Benefits

1. **No Race Conditions**: Single writer to stdout
2. **Simpler Logic**: No complex cursor manipulation
3. **Better Reliability**: Fixes blank line issues
4. **Easier Debugging**: All output flows through one place

## Usage

Enable V2 streaming (default):
```bash
hnt-agent -m "Your message" --v2-streaming
```

Disable V2 streaming (use old method):
```bash
hnt-agent -m "Your message" --v2-streaming=false
```

## Migration Path

The refactor is incremental:
1. Both old and new streaming methods coexist
2. V2 is enabled by default but can be disabled
3. Once stable, old method can be removed

## Known Improvements

- Fixes race conditions causing blank lines
- Prevents content loss when channel is full
- Cleaner spinner state management
- More predictable output behavior

## Recent Improvements (Phase 2)

### 1. Shell Command Synchronization
- Removed hacky `time.Sleep(50ms)` after spinner
- Shell commands now use OutputCoordinator when V2 is enabled
- Proper synchronization via `Flush()` method

### 2. EOF Handling in SSE Parser
- Fixed bug where data could be lost when `ReadBytes` returns both data and `io.EOF`
- Now always processes data before checking error conditions

### 3. Proper Backpressure
- OutputCoordinator methods now block properly instead of using timeouts
- Removed fallback direct printing that caused race conditions
- Added `TryPrintLine` for non-blocking attempts when needed
- Commands queue properly applies backpressure to producers

## Future Work

1. Remove old streaming method once V2 is proven stable
2. Add metrics/logging to OutputCoordinator
3. Handle extremely long words that exceed wrap width in LineBuffer
4. Add SSE buffer size limits to prevent memory exhaustion