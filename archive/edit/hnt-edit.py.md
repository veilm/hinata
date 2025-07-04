# hnt-edit.py – Quick Reference

Small CLI helper that ties together `llm-pack`, `hnt-chat`, and `hnt-apply`  
to realise **file-editing with Hinata LLM agents**.  
Think of it as “git add + commit -m + push + PR review + apply” for AI.

---

## Top-Level Flow (`main()`)

1. **Parse CLI args**  
   `--message/-m`, `--system/-s`, `--model`, `--continue-dir`, `--debug-unsafe`,  
   `[source_files ...]`.

2. **Syntax-highlight support**  
   • Checks `$HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD` or fallback to `SYNTAX_HIGHLIGHT_PIPE_CMD`.  
   • Runs highlighter (`hlmd-st`, *rich*, etc.) on streamed LLM output.

3. **Continuation vs. New Conversation**
   - **Continuation (`--continue-dir`)**  
     • Reads `absolute_file_paths.txt` & `source_reference.txt`.  
     • Re-runs `llm-pack` to refresh `<source_reference>` message in the chat log.
   - **New run (default)**  
     • Creates missing source files (tracks them for later cleanup).  
     • Fetches system prompt (`get_system_message`) and user instruction (`get_user_instruction`).  
     • Packs sources with `llm-pack`.  
     • Starts new `hnt-chat` conversation; records absolute paths, system, user, and source messages.

4. **Stream LLM Generation** (`hnt-chat gen`)  
   • Pipes output through optional syntax highlighter.  
   • Mirrors to terminal **and** captures to memory.

5. **Apply Patches** (`hnt-apply`)  
   • Feeds captured output.  
   • On failure, adds raw `hnt-apply` stdout back into the chat as a user message for debugging.

6. **Cleanup**  
   • `atexit` hook deletes any empty files the script auto-created.  
   • Ensures subprocesses terminate; propagates exit codes.

---

## Helper Functions

| Function | Purpose |
|----------|---------|
| `run_command` | Thin wrapper around `subprocess.run` with nice error reporting. |
| `get_user_instruction` | Opens `$EDITOR` if `-m` not supplied; aborts if unchanged. |
| `get_system_message` | Pulls system prompt from arg, file, or `$XDG_CONFIG_HOME`. |
| `debug_log` | Conditional stderr logger toggled by `--debug-unsafe`. |
| `cleanup_empty_created_files` | Removes placeholder files created for non-existent paths. |

---

## Environment Variables

- `EDITOR` – editor for interactive message authoring (default `vi`).
- `HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD` – override highlighter command.
- `XDG_CONFIG_HOME` – base for default prompt path.

---

## Key External Tools

`llm-pack`, `hnt-chat`, `hnt-apply`, optional highlighter (`hlmd-st`/`rich`).

---