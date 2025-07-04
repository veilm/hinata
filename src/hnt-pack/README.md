# llm-pack

A command-line tool for packaging source files into a single, LLM-friendly format. Perfect for when you need to share multiple files with AI assistants or language models.

## What it does

`llm-pack` takes your source files and combines them into a clean, structured output that preserves file paths and content relationships. It automatically handles relative paths and provides a clear file listing followed by the actual content.

## Installation

```bash
cargo install hnt-pack
```

## Usage

### Basic usage

Pack multiple files:
```bash
llm-pack src/main.rs src/lib.rs Cargo.toml
```

### Common workflows

**Pack an entire module:**
```bash
llm-pack src/auth/*.rs
```

**Pack files from different directories:**
```bash
llm-pack src/main.rs tests/integration_test.rs README.md
```

**Copy output to clipboard (macOS):**
```bash
llm-pack src/*.rs | pbcopy
```

## Options

- `-s, --sort` - Sort files alphabetically before packing
- `-n, --no-fences` - Skip the markdown code fence wrapper
- `-p, --print-common-path` - Show the common directory path and exit

## Output format

The tool generates output in this structure:

```
<file_paths>
src/main.rs
src/lib.rs
Cargo.toml
</file_paths>

<src/main.rs>
// file contents here
</src/main.rs>

<src/lib.rs>
// file contents here
</src/lib.rs>

<Cargo.toml>
# file contents here
</Cargo.toml>
```

Files are shown with paths relative to their common parent directory, making the structure clear while keeping paths concise.

## Examples

**Sort files for consistent output:**
```bash
llm-pack --sort src/**/*.rs
```

**Check the common path without packing:**
```bash
llm-pack --print-common-path ~/project/src/*.rs ~/project/tests/*.rs
# Output: /home/user/project
```

**Pack without markdown fences (for custom formatting):**
```bash
llm-pack --no-fences src/*.rs > context.txt
```

## License
MIT

README by Claude Opus 4
