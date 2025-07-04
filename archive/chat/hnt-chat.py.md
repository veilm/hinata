# hnt-chat.py – Quick Structural/Functional Reference
*(Generate/maintain automatically – keep short but complete)*

## 1. Purpose
Command-line helper that organises “Hinata Chat” conversation folders and
interacts with companion tools:

* **hnt-escape** – escapes/encodes markdown for transport
* **hnt-llm**     – language-model back-end

## 2. High-level Flow
```
hnt-chat <command> [options] | stdin
        ├── new     → create blank conversation dir
        ├── add     → append message markdown file
        ├── pack    → serialise messages for downstream tools
        └── gen     → call hnt-llm, optionally append reply
```

All conversation directories live in  
`$XDG_DATA_HOME/hinata/chat/conversations/`  
(or `~/.local/share/hinata/chat/conversations/` by default).

## 3. Directory / File Scheme
```
<conv_base>/<timestamp_ns>-<role>.md        # user / assistant / system
<conv_base>/<timestamp_ns>-assistant-reasoning.md (optional)
<conv_base>/model.txt                       # last requested model
```

Nanosecond timestamps virtually guarantee uniqueness; collisions are retried.

## 4. Main Functions

| Function | Responsibility |
|----------|----------------|
| `get_conversations_dir()` | Return & ensure base directory. |
| `create_new_conversation(dir)` | Make new timestamped conversation dir. |
| `find_latest_conversation(dir)` | Return lexicographically last dir. |
| `determine_conversation_dir(args, base)` | Resolve `--conversation`, env var or latest. |
| `_write_message_file(dir, role, content)` | Write message, returns filename. |
| `_pack_conversation_stream(dir, out, merge)` | Core packer: writes `<hnt-role>…</hnt-role>` pairs through `hnt-escape`, merging consecutive roles if requested. |
| `pack_conversation_to_buffer(dir, merge)` | Convenience wrapper around the above. |

### Command Handlers (hooked by `argparse`)
* `handle_new_command()`  
  Create new conversation and print absolute path.

* `handle_add_command(args)`  
  Read **stdin**, save as `user/assistant/system` message.  
  `--separate-reasoning`: split leading `<think>…</think>` block into *assistant-reasoning* file.

* `handle_pack_command(args)`  
  Stream packed conversation to **stdout**. `--merge` squashes consecutive roles.

* `handle_gen_command(args)`  
  1. Packs conversation (`--merge` optional).  
  2. Runs `hnt-llm` (`--model`, `--debug-unsafe`, `--include-reasoning`).  
  3. Streams LLM output to **stdout**.  
  4. If `--write`/`--output-filename`/`--separate-reasoning`: saves assistant reply (and optional reasoning split) to conversation.

## 5. Error Handling
All fatal errors write to **stderr** then `sys.exit(1)` (or subprocess code).
Common cases: directory creation, file IO, missing external commands.

## 6. Entry Point
```python
if __name__ == "__main__":
    main()
```
`main()` sets up `argparse` sub-parsers and dispatches to the handler via
`set_defaults(func=…)`.

---
*Revision note: summary only – edit hnt-chat.md if code changes affect API.*