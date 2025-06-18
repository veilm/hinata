# Hinata Chat – Directory Quick Reference
*(Start here; jump to the per-file docs listed below when you need specifics.)*

-------------------------------------------------------------------------------

What this directory is  
----------------------
`/hinata/chat/` contains the **conversation-layer tooling** for the Hinata
project.  It is *not* the LLM itself—think of it as a thin UX and data-
management shell that sits **between the user and the model back-end**.

Key deliverables in this folder
-------------------------------
| File / doc | Role | Where to look for détails |
|------------|------|---------------------------|
| `hnt-chat.py` | Main CLI executable; orchestrates conversation folders, packs messages, and calls the LLM. | `hnt-chat.md` |
| `build` (shell script) | Installs `hnt-chat` system-wide and compiles its dependency `hnt-llm` if missing. | `build.md` |

External actors this code relies on
-----------------------------------
• **hnt-llm** – compiled sibling project (`../llm/`); performs the actual model
inference.  
• **hnt-escape** – small utility used by `hnt-chat pack` to escape Markdown for
transport.  
These are invoked as subprocesses; no Python imports needed.

How the pieces fit together
---------------------------
1. Run `./build`  
   • Ensures `hnt-llm` is built,  
   • Drops `hnt-chat` onto your `$PATH`.

2. Use the CLI:  
   ```
   hnt-chat new            # make a fresh conversation dir
   hnt-chat add < stdin    # append message (user / assistant / system)
   hnt-chat pack           # serialise convo → stdout  (for hnt-llm)
   hnt-chat gen            # call hnt-llm; optionally save reply
   ```
   Message files live under  
   `$XDG_DATA_HOME/hinata/chat/conversations/<timestamp>-<role>.md`.

3. Internally `hnt-chat gen` just
   • packs → **hnt-escape** → **hnt-llm**,  
   • then optionally writes the assistant reply back to the same folder.

Cheat-sheet for digging deeper
------------------------------
Need install behaviour?       → open **build.md**  
Need CLI commands / options?  → open **hnt-chat.md**  
Need LLM switches & models?   → see `../llm/` project docs  
Need Markdown escaping rules? → see `hnt-escape` repo / man-page  

That’s it—you now know where everything lives and how it links together.