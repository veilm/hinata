# Hinata Web – Top-Level Developer Quick Reference
*(directory: `/src/hinata/web`)*

WHY THIS FOLDER EXISTS  
----------------------
It is **the entire “web front-end” layer** of the Hinata project:

1. **REST + static server** – `hnt-web.py` (FastAPI)  
2. **Browser UI bundle** – `static/…` (HTML/CSS/JS)  
3. **Installer helper** – `build` shell script  

Together they let a user open `http://localhost:2027`, browse conversations,
and talk to an LLM—while delegating all heavy lifting to the **`hnt-chat`
CLI** that lives in a *sibling* `/hinata/chat` directory.

HOW THE PIECES TALK  
-------------------
Browser ⇄ `/api/...` (FastAPI) ⇄ `hnt-chat` CLI ⇄ on-disk conversation folder

• Static files are served verbatim out of `static/`.  
• Each API call is a thin wrapper that shells out to `hnt-chat` for
  conversation manipulation or message generation.  
• Conversations are stored on disk under  
  `$XDG_DATA_HOME or ~/.local/share/hinata/chat/conversations`.

FOLDER MAP & WHERE TO READ NEXT  
-------------------------------
Need to… | Start with
---------|-------------------------------
Understand API routes / server flow | **`hnt-web.md`** → then skim `hnt-web.py`
Hack on the browser UI              | **`static/HINATA.md`** → then open files in `static/`
Change install paths / prerequisites | **`build.md`** → and edit the `build` script
See full CLI capabilities           | *outside scope* → `/src/hinata/chat/` docs & code

COMMON DEV TASKS (1-MIN GUIDE)  
------------------------------
• **Add an API endpoint** → modify `hnt-web.py` (before the static mounts).  
• **Tweak front-end look/feel** → edit HTML/CSS in `static/`, JS in
  `static/js/script.js`.  
• **Ship a new static asset** → place it in `static/`, rerun `build` to copy.  
• **Change default port/host** → bottom of `hnt-web.py` (`uvicorn.run`).

EXTERNAL DEPENDENCIES  
---------------------
• `hnt-chat` – must be on `$PATH`; provides all LLM & conversation logic.  
• `uv` (or any shell) – required by the `build` helper.  
• `uvicorn` – auto-installed with FastAPI, used when you run `python hnt-web.py`.

That’s the bird’s-eye view—jump into the docs listed above for deep dives.