HINATA / agent — Top-Level Map
==============================

What this folder is  
-------------------
`hinata/agent/` bundles **small, stand-alone command-line helpers** that let a
developer (or another program) talk to three worlds at once:

1. A **persistent POSIX shell** (`headlesh`) – so later commands keep state.  
2. A local **LLM chat log** (`hnt-chat`) – to generate / refine answers.  
3. A **headless Chromium tab** (`browse`) – for live web scraping.

Glue logic lives in two Python entry points that hide almost all of the
plumbing:

| Script             | One-liner purpose                        | Read more in…          |
|--------------------|------------------------------------------|------------------------|
| `hnt-agent.py`     | Run an *LLM ⇄ shell* interactive loop    | `hnt-agent.py.md`      |
| `hnt-shell-apply.py`| Extract & run the last `<hnt-shell>` block| `hnt-shell-apply.py.md`|

Sub-packages & how they fit
---------------------------
• `headlesh/` — the C binary + docs that keep **long-lived shells** alive.  
  The Python helpers *only* ever call its CLI sub-commands.  
  → open **headlesh/HINATA.md** first, then **headlesh.c.md** or `headlesh.c`.

• `browse/`   — CDP wrapper + tiny in-browser scraper that turns any web page
  into a clean text/tree for the LLM.  
  → start with **browse/HINATA.md**, then dive into `headless-browse.js.md` or
  `main.py.md`.

• `prompts/`  — default system- and role-prompts copied into
  `$XDG_CONFIG_HOME/hinata/prompts` by `./build`.

• `build` (+ **build.md**) — installs *everything* above (`headlesh` if
  missing, Python entry points, prompt files).

High-level flow at runtime
--------------------------
1. `hnt-agent` creates a fresh `headlesh` **session** and writes the user
   instruction + system prompt to a new *hnt-chat* conversation.  
2. It asks the LLM (via `hnt-chat gen`).  
3. If the answer contains `<hnt-shell>` → `hnt-shell-apply` streams it into
   that same shell session, captures output, and feeds the results back to the
   chat before regenerating.  
4. The cycle repeats until the user quits; finally the shell session is
   closed (`headlesh exit …`).

Where to look when…
--------------------
Need to…                             | Open this doc
-------------------------------------|---------------------------------------------
Understand the **shell backend**     | `headlesh/HINATA.md` → `headlesh.c.md`
Tweak **web scraping** rules         | `browse/HINATA.md` → `headless-browse.js.md`
Modify the **agent loop / flags**    | `hnt-agent.py.md`
Change tag parsing / CLI of apply-er | `hnt-shell-apply.py.md`
See **install paths** or build steps | `build.md`

External tools referenced
-------------------------
Tool          | Why it matters                         | Package / repo
--------------|----------------------------------------|----------------
`hnt-chat`    | Stores dialog & calls the LLM          | separate repo
Chromium      | Required for `browse` CDP connection   | system package
An LLM API    | Used indirectly via `hnt-chat gen`     | e.g. OpenAI

That’s the bird’s-eye view—open the per-component quick references above for
code-level details.