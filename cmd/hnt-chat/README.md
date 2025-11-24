# hnt-chat

Plaintext conversation manager for the Hinata toolchain. Each chat lives in its own directory full of timestamped Markdown files, so you can version, diff, or edit conversations with any editor.

- Stores data at `$XDG_DATA_HOME/hinata/chat/conversations` (falls back to `~/.local/share`).
- 100% CLI driven: add messages, list conversations, pin/fork threads, or let an LLM append the next reply.
- Plays nicely with the other Hinata binaries (`hnt-llm`, `hnt-edit`, `hnt-web`, `hnt-agent`) because everything stays on disk.

## Install

```sh
curl hnt-agent.org/install | sh
```

## Quick start

```sh
# create a conversation directory
conv=$(hnt-chat new)

# add messages from stdin
printf "You are a poet.\n" | hnt-chat add system -c "$conv"
printf "Write me a haiku about CPUs." | hnt-chat add user -c "$conv"

# generate the next assistant reply and save it
hnt-chat gen -c "$conv" --write

# pretty-print chat as role-tagged blocks (ready for hnt-llm)
hnt-chat pack -c "$conv"
```

The `gen` command inherits the model from `--model`, `HINATA_CHAT_MODEL`, or `HINATA_MODEL` (default: `openrouter/google/gemini-2.5-pro`) and streams output like `hnt-llm`. Add `--include-reasoning` to capture `<think>` traces both on stdout and inside `reasoning/<timestamp>.md`.

## Commands

| Command | Description |
| --- | --- |
| `hnt-chat new` | Create a fresh conversation directory. Prints the absolute path. |
| `hnt-chat add <role>` | Append a `system`, `user`, or `assistant` message from stdin. Use `--separate-reasoning` to split `<think>` blocks into `reasoning/`. |
| `hnt-chat pack` | Emit merged `<hnt-role>...</hnt-role>` blocks for piping into `hnt-llm` or `hnt-edit`. Add `--merge` to concatenate consecutive messages from the same role. |
| `hnt-chat gen` | Run an LLM call against the packed conversation. `--write` saves the assistant reply, `--output-filename` prints the saved path, and `--include-reasoning` captures thinking traces. |
| `hnt-chat list` | Show every conversation with pin/fork status. |
| `hnt-chat pin` / `hnt-chat unpin` | Toggle `meta/pinned.flag` so `list` surfaces important threads. |
| `hnt-chat fork` | Duplicate a conversation, tracking ancestry in `meta/fork_source.txt` and `meta/forks.txt`. |
| `hnt-chat title "<text>"` | Store a friendly title in `meta/title.txt`. |

## Environment controls

- `HINATA_CHAT_CONVERSATION`: default conversation path when `-c/--conversation` is omitted.
- `HINATA_CHAT_MODEL` / `HINATA_MODEL`: overrides the LLM used by `gen`.
- `XDG_DATA_HOME`: chooses where conversation folders live.

## Files on disk

```
~/.local/share/hinata/chat/conversations/
 └── 1731459479240000000/
     ├── 1731-user.md
     ├── 1731-system.md
     ├── 1731-assistant.md
     ├── reasoning/
     │   └── 1731.md
     └── meta/
         ├── title.txt
         ├── pinned.flag
         ├── model.txt
         └── fork_source.txt
```

Everything is just Markdown, so you can edit messages, run `git diff`, or feed the transcripts into other Hinata utilities whenever you like.
