# hnt-agent.py – Quick Reference

High-level purpose  
------------------  
CLI wrapper that turns a free-form *user instruction* into an iterative
dialogue with the **Hinata** LLM and a persistent **headlesh** shell
session.  
It glues together four main tools:

| Tool                 | Role inside this script |
|----------------------|-------------------------|
| `headlesh`           | Creates/exits shell session used for all commands |
| `hnt-chat`           | Stores conversation (`new`, `add`, `gen`)         |
| `hnt-shell-apply`    | Executes `<hnt-shell>` blocks inside the session  |
| `hlmd-st` (optional) | Streams LLM output with syntax highlighting       |

Basic lifecycle  
---------------  
1. **Parse CLI args** (`argparse`).  
2. **Create headlesh session** whose name is `hnt-agent-<time_ns>`.  
3. **Load messages**  
   • System prompt (`--system` or default file).  
   • Optional **HINATA.md** agent info (config dir).  
   • Canned “pwd /etc/os-release” probe (adds context).  
   • Real user instruction (`--message` or `$EDITOR`).  
4. **Create chat dir** (`hnt-chat new`) and add the messages above.  
5. **Generate LLM answer** (`hnt-chat gen --include-reasoning ...`)  
   • Output is streamed with colors / optional highlighting.  
6. **Main loop**  
   a. If the answer contains `<hnt-shell>` block →  
      • Ask user confirmation (unless `--no-confirm`).  
      • Pipe block to `hnt-shell-apply` and print its stdout/stderr.  
      • Optionally add stdout back to chat and regenerate an answer.  
   b. If **no** shell block (apply returns `2`) → prompt user to *edit*
      or *quit*.  
7. **Cleanup** – always attempts `headlesh exit <session>` in `finally`.  

Important helpers  
-----------------  
• `run_command()` – thin wrapper around `subprocess.run` with uniform
  error printing + early `sys.exit`.  
• `stream_and_capture_llm_output()` – streams generator output live,
  optionally through the highlighter, while also capturing it for later
  processing.  
• `get_header_footer_lines()` + `print_user_instruction()` – pretty UI
  block formatting with ANSI colors and Unicode box-drawing chars.  
• `debug_log()` – gated by `--debug-unsafe`, prints to *stderr*.  

Key CLI options  
---------------  
```
-s / --system     system prompt string or file
-m / --message    user instruction string (otherwise $EDITOR)
--model           pass through to hnt-chat gen
--debug-unsafe    verbose debug logs (unsafe because may expose data)
--no-confirm      skip *all* interactive confirmations
```  

Return codes  
------------  
• 0  – success  
• 2  – special rc from `hnt-shell-apply` meaning “no <hnt-shell> block”  
• ≠0 – first critical failure (hnt-shell-apply, headlesh exit, etc.)  

Files / env the script cares about  
----------------------------------  
```
$XDG_CONFIG_HOME/hinata/prompts/main-shell_agent.md   (default system prompt)
$XDG_CONFIG_HOME/hinata/agent/HINATA.md               (optional extra info)
$EDITOR                                               (interactive inputs)
HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD                      (override highlighter)
```  

Tips for modification  
---------------------  
• All I/O with external commands is isolated in **one** helper → safest
  place to monkey-patch behaviour.  
• UI colours & divider width are constants at the top.  
• Syntax highlighting is optional – ensure fallbacks remain silent.  
• When adding new interactive prompts, respect the existing
  `--no-confirm` flag.  