Hinata – Root-Level Developer Quick Reference
============================================

What is **Hinata**?  
A self-contained toolbox that glues a large-language model (LLM) to three worlds:

• Your **POSIX shell & local files** – run code, inspect output, auto-edit.  
• **Remote model providers** – OpenAI, Gemini, DeepSeek, … via a tiny C client.  
• **Web browsers / REST UI** – optional FastAPI + static frontend.

Think “CLI Swiss-army knife for everyday AI-assisted dev work”, not a monolith.
Every feature lives in a small, build-once, copy-anywhere binary or script.

Typical runtime paths (bird-eye)
--------------------------------
1. Terminal assistant  
   `hnt-agent` (agent/) ─▶ `hnt-chat` (chat/) ─▶ `hnt-llm` (llm/) ─▶ LLM  
   └─╾  keeps a *headlesh* shell session open and may inject `<hnt-shell>` blocks.

2. In-place source editing  
   `hnt-edit` (edit/) → `llm-pack` → **LLM** → `hnt-apply` (edit/) ⇒ patches disk.

3. Browser UI  
   Browser ⇆ `hnt-web` (web/, FastAPI) ⇆ `hnt-chat` ⇒ same data folder as #1.

Folder map & when to open each sub-HINATA
-----------------------------------------
Need to… | Jump to
---------|----------------------------------------------
Run an interactive *LLM ⇄ shell* agent | agent/HINATA.md
Create / inspect conversations          | chat/HINATA.md
Call the LLM or tweak provider flags    | llm/HINATA.md
Apply AI-generated code patches         | edit/HINATA.md
Serve or hack the web frontend          | web/HINATA.md

How the pieces fit together
---------------------------
                         +-------------+
        +--------------▶ | hnt-llm (C) | ──────▶ Provider HTTP
        |                +-------------+
        |                       ▲
        |                       | (stdin / stdout JSON)
+--------------+         +-------------+
| hnt-chat (Py)| ───────▶ | hnt-escape |  (tag filter)
+--------------+         +-------------+
      ▲  ▲                    ▲
      │  └───── used by ──────┘
      │
 +-----------+     +-----------+
 | hnt-agent |     | hnt-edit  |   (both Python CLIs)
 +-----------+     +-----------+
      │                 │
      │                 └──▶ `hnt-apply` / shell / editor
      └──▶ headlesh (persistent shell) & browse/ (Chromium CDP)
All binaries/scripts live under `/usr/local/bin` after running each subdir’s
`build` helper.

External prerequisites
----------------------
• POSIX shell, gcc/clang, Python 3.9+, libcurl, jansson.  
• Chromium (for agent/browse), FastAPI+uvicorn (for web).  
• Provider API keys in env (`OPENAI_API_KEY`, etc.).

One-minute orientation checklist
--------------------------------
1. Clone → `cd src/hinata/<module>` → `./build` (installs that part).  
2. Want a REPL with shell access? → `hnt-agent`.  
3. Need code edits? → `hnt-edit <path>` then follow prompts.  
4. Prefer a browser? → `python -m hinata.web.hnt_web`.  

For everything else, open the per-module **HINATA.md** listed above—each is a
2-3-minute read that links to deeper, per-file docs.

Happy hacking!