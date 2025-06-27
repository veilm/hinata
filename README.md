<p align="center">
<img src="https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/hinata.png" width="250">
</p>

<p align="center">
agentic AI pair programming in your terminal. except minimalist, modular, extensible
</p>

# quick tour

### [`hnt-agent`](./agent)
simple hnt-chat and headlesh wrapper for letting an LLM operate a persistent shell

```
$ hnt-agent \
	-m "please check the repo diff. then commit all changes with a meaningful message" \
	--model "openrouter/anthropic/claude-opus-4" \
	--no-confirm
I'll check the repository diff first to see what changes have been made, then create a meaningful commit message.
[...]

$ git log --oneline | head -1
40f034e style: Convert changelog dates to YYYY-MM-DD format
```

the persistent shell is the only direct "tool" the model has access. all other
possible functionality (e.g. browser navigation, file editing) is implemented as
CLI utilities that the LLM can leverage. like `hnt-edit`

not as aesthetic as Claude Code. UX is WIP

### [`hnt-edit`](./edit)
simple hnt-chat wrapper for editing source code or other plaintext files

```
$ hnt-edit \
	-m "please enable debugging in the config" \
	--model "deepseek/deepseek-chat" \
	$(fd -g "*.h")
I'll enable debugging by changing the DEBUG flag from 0 to 1 in util.h. Here's the edit:
[...]

$ git diff
diff --git a/src/util.h b/src/util.h
index badefee..5eb3e0d 100644
--- a/src/util.h
+++ b/src/util.h
@@ -1,6 +1,6 @@
 #pragma once
 
-#define DEBUG 0
+#define DEBUG 1
 
 #define debug(fmt, ...) \
 	do { if (DEBUG) fprintf(stderr, "%-20s " fmt, \
```

in my experience, hnt-edit's editing performance is higher than Aider's for my
usual Gemini 2.5 Pro infra and web use cases, as of Apr 2025. (functional
differences: system prompt and design of TARGET/REPLACE parser)

### [`hnt-chat`](./chat/)
simple `hnt-llm` wrapper, for chat history management using plaintext files and
conversation directories
```
$ conversation=$(hnt-chat new)
$ echo "please write a poem about the user's given theme" | hnt-chat add system
$ echo "iteration" | hnt-chat add user

$ ls $conversation
1747512247695244498-system.md
1747512250714528664-user.md

$ hnt-chat generate --write --model deepseek/deepseek-chat
**Iteration**  

Again, the brushstroke on the page,  
A line retraced, a word replayed.
[...]
```

### [`hnt-llm`](./llm/)
basic LLM API in/out. significantly faster startup than openai-python
```
$ echo "hello! ❄️" | hnt-llm --model openrouter/anthropic/claude-3.5-sonnet
Hi there! Nice snowflake emoji! How are you today? ☺️
```

has optional ~encrypted credential management using `hnt-llm save-key`

# build everything
```
git clone https://github.com/veilm/hinata
cd hinata
./build
```

- dependencies (you likely already have them): C libjasson and libcurl
- optional dependencies: uv (pygments syntax highlighting)

# full architecture
- [`hnt-llm`](./llm/README.md): simple, performant text backend. pipe text input
in, receive LLM text response out
- [`hnt-chat`](./chat/README.md): wrapper around `hnt-llm` for managing
conversations and message history, using simple conv directories and message
markdown files
- [`llm-pack`](./edit/llm-pack/README.md): take source code filenames as CLI
args. write LLM packed prompt to stdout
- [`hnt-apply`](./edit/README.md): take LLM output including TARGET/REPLACE
blocks as stdin. make edits to those files on the LLM's behalf
- [`hlmd-st`](./fmt/highlight/README.md): take LLM markdown output, including
code blocks as stdin. write syntax highlighted ver to stdout
- [`hnt-edit`](./edit/README.md): (very low-budget) aider clone. wrapper that
uses `llm-pack` to format source code. sends it along with user instructions to
`hnt-chat`. optionally displays it using `hlmd-st`/custom. then uses `hnt-apply`
to parse the LLM's desired edits
- [`hnt-web`](./web/README.md): simple 80/20 web app wrapping hnt-chat.
sufficient for my own casual usage and mobile/{filesystem storage} requirement
- [`headlesh`](./agent/headlesh/README.md): CLI headless shell manager. create
shell sessions and easily read/write to them
- [`hnt-agent`](./agent/): wrapper around `headlesh` for allowing an LLM to use
a shell and receive output, in a feedback loop
- [`browse`](./agent/browse): CLI for navigating your (not headless) GUI
Chromium-based browser programmatically. intended for LLM web browsing

# bugs / support
feel free to @ me on X or make a GitHub issue, for literally any reason

you don't need to read any documentation or even try installing. I'd be happy to
answer any possible questions

# philosophy

**Goal: unequivocally mog yacine's setup**

- Have something like Aider / Claude code / codex but ~~impossible to use~~
extensible
- As much as possible, unify your environment so that LLMs and humans can use
the same tools in the same ways: simple CLI programs that wrap each other
- Integrate other ideas as they're leaked by Pliny/Tibor/etc.
- Ideally LLM Chat is simple to layer on top as a wrapper over composable
features (e.g. memory)
- Maintain benchmarks on included prompts and scaffolding on private code (rvm,
iqd, etc.) for reference and for maliciously farming and baiting engagement on X
- Be reasonable in the design of backends. like Aider not like Open WebUI

## credit
other projects used for inspiration:
- [Aider](https://aider.chat/)
- [Cursor](https://www.cursor.com/)
- [openai-python](https://github.com/openai/openai-python)
- [simonw/llm](https://github.com/simonw/llm)
- [Streamdown](https://github.com/day50-dev/Streamdown)
