llm-pack — Developer Cheat-Sheet
===============================

What is this directory?
-----------------------
`llm-pack` is a **tiny C + shell utility** whose only job is to turn an
arbitrary set of files into a single, copy-pastable “XML snippet” that Large
Language Models (LLMs) can ingest without losing binary fidelity.

Typical flow:
```bash
./build           # compile + (optionally) sudo-install /usr/local/bin/llm-pack
llm-pack *.c .gitignore README.md > out.snip
```
`out.snip` now contains:

```
<file_paths>
path/1
path/2
</file_paths>

<path/1>
…raw file bytes…
</path/1>
…
```

Why would I use it?
• Quick “bundle & paste” of code into ChatGPT / Claude.  
• Guarantees each file is delimited (no accidental merging).  
• Handles binary files and preserves newlines exactly.

File tour
---------
main.c          — Implementation of the formatter (see main.c.md).  
build           — 1-liner convenience build / install script (see build.md).  
build.md        — Explains flags/steps used by the script.  
main.c.md       — In-depth walkthrough of `main.c` design and switches.  
HINATA.md       — (this doc) high-level map.

How the pieces fit
------------------
1. **Developer runs `build`**  
   • Compiles `main.c` with strict warnings.  
   • Drops resulting binary in project dir and (optionally) `/usr/local/bin`.

2. **User invokes `llm-pack`**  
   • `main.c` parses CLI flags, resolves absolute paths, discovers common root,
     optionally sorts, and streams content to `stdout` in the agreed snippet
     format.

3. **Snippet pasted into external tools**  
   • Any LLM client, issue-tracker, or documentation platform that can display
     preformatted text is now able to reconstruct the exact original tree.

Where to read next
------------------
Need CLI flags / inner workings?           ➜ **main.c.md**  
Wondering about GCC flags / install path?  ➜ **build.md**  
Just trying to compile/run quickly?        ➜ `build` (shell script itself)

External assumptions
--------------------
• POSIX-ish environment with a C99 compiler (tested with GCC).  
• `realpath`, `qsort`, standard libc; falls back to 4096 for `PATH_MAX` if
  missing.  
• `sudo` only required for system-wide installation step.

That’s it — concise by design, low maintenance, copy-friendly.