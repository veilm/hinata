# Hinata / llm – developer orientation

What lives here?  
A **minimal C tool-chain** that lets you pipe local text into a remote LLM and
stream the answer back, with optional tag-escaping help.

Binaries that come out of this directory
----------------------------------------
| binary        | source     | one-liner purpose |
|---------------|------------|-------------------|
| `hnt-llm`     | `main.c`   | Turn stdin ± CLI flags into a streaming HTTPS chat request and print the reply. |
| `hnt-escape`  | `escape.c` | Filter that adds/removes an underscore in `<hnt-*>` XML tags, useful when nesting prompts. |

How the pieces talk to each other
---------------------------------
1. You run `hnt-llm` (usually after echoing or cat-ing a prompt).  
2. While building its JSON payload, **`hnt-llm` shells out to `hnt-escape -u`
   for every extracted message** so the LLM sees clean, un-escaped roles.  
3. `hnt-llm` streams the request via `libcurl`, decodes SSE, and prints tokens.  

Build / install
---------------
`build` (shell script) is the single entry point: it `gcc`s both programs with
strict flags and `sudo cp`s them into `/usr/local/bin`.  
Look at **build.md** for the exact flags & extensibility tips.

Need more detail?
-----------------
• Internals of the LLM client → **main.c.md**  
  (CLI flags, JSON shape, SSE handling, providers table, error paths…)

• The tag filter FSM → **escape.c.md**  
  (state diagram, corner cases, buffer safety, CLI usage)

External expectations
---------------------
libcurl, jansson, a POSIX shell, and provider API keys in your environment
(`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`).

That’s it—read the per-file docs above when you need to dive deeper, otherwise
remember: `hnt-llm` sends, `hnt-escape` cleans, `build` stitches. Happy hacking!