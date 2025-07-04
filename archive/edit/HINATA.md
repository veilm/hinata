Hinata “edit/” — Bird-Eye Overview
=================================

What lives here?
----------------
Everything needed for *LLM-powered, patch-style editing* of source trees.

High-level pipeline
-------------------
`hnt-edit`  →  `llm-pack`  →  **LLM**  →  `hnt-apply`

1. **hnt-edit.py** (Python)  
   Orchestrates the whole round-trip.  
   ‑ Bundles sources (via *llm-pack*).  
   ‑ Starts / continues a chat session (*hnt-chat*, external).  
   ‑ Streams model output, highlights it, then pipes it to *hnt-apply*.

2. **llm-pack** (C, own sub-dir)  
   Emits a self-contained `<source_reference>` block for the LLM.

3. **LLM** (OpenAI, Claude, etc.)  
   Generates TARGET/REPLACE edit blocks.

4. **hnt-apply.c** (C)  
   Verifies and applies those blocks to disk, aborting on mismatch.

5. **build** (shell)  
   Convenience script that compiles / installs the above and copies default
   prompts to `~/.config/hinata/prompts`.

Key files & where to read more
------------------------------
build.md        — What the *build* script does, flags, install paths.  
hnt-edit.py.md  — CLI flags, continuation logic, env vars, cleanup.  
hnt-apply.c.md  — Exact edit-block grammar, exit codes, internals.  
llm-pack/HINATA.md — Deep-dive into the bundler sub-project.

External pieces this dir assumes
--------------------------------
hnt-chat        — Conversation manager that actually talks to the model.  
Syntax highlighter (`hlmd-st`, `rich`, …) — Optional pretty output.  
A POSIX shell, gcc/clang for C parts, Python 3.9+ for *hnt-edit*.

Got stuck?
----------
• “How do I build everything?” → *build.md* (2-min read)  
• “Why did my edit block fail?” → *hnt-apply.c.md* (search for *process_block*)  
• “What args does hnt-edit accept?” → *hnt-edit.py.md* (top table)  
• “Packing algorithm details?” → *llm-pack/HINATA.md*

That’s the big picture—happy hacking!