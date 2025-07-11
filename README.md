<p align="center">
<img src="https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/hinata.png" width="250">
</p>

<p align="center">
agentic AI pair programming in your terminal. except minimalist, modular, extensible
</p>

# quick tour

### [`hnt-agent`](./hnt-agent/)
simple [`hnt-chat`](./hnt-chat/) and [`headlesh`](./headlesh/) wrapper
for letting an LLM operate a persistent shell

```
$ git log --oneline | head -1
b8b305b refactor: Handle recoil animations during enemy fade-out state

$ hnt-agent \
	-m "please check the diff, then commit all changes with a meaningful message" \
	--model "openrouter/anthropic/claude-opus-4" \
	--no-confirm
I'll check the repository diff first to see what changes have been made, then
create a meaningful commit message.
[...]

$ git log --oneline | head -2
40f034e style: Convert changelog dates to YYYY-MM-DD format
b8b305b refactor: Handle recoil animations during enemy fade-out state
```

the persistent shell is the only direct "tool" the model has access to. all
other possible functionality (e.g. browser navigation with
[`browse`](./util/browse/), file editing with
[`hnt-edit`](./hnt-edit/)) is implemented as CLI utilities that the LLM can
leverage

not as aesthetic as Claude Code. UX is WIP

### [`hnt-edit`](./hnt-edit/)
simple [`hnt-chat`](./hnt-chat/) wrapper for editing source code or other
plaintext files

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

### [`hnt-chat`](./hnt-chat/)
simple [`hnt-llm`](./hnt-llm/) wrapper, for chat history management using
plaintext files and conversation directories
```
$ conversation=$(hnt-chat new)
$ echo "please write a 2-line stanza about the user's given theme" | hnt-chat add system
$ echo "iteration" | hnt-chat add user

$ ls $conversation
1751202665600525690-system.md
1751202669679594679-user.md

$ hnt-chat generate --write --model deepseek/deepseek-chat
Code repeats in loops so tight,
Each pass refines till it's just right.

$ ls $conversation
1751202665600525690-system.md
1751202669679594679-user.md
1751202692095544873-assistant.md
```

### [`hnt-llm`](./hnt-llm/)
basic LLM API in/out. significantly faster startup than openai-python
```
$ echo "hello Claude! ❄️" | hnt-llm --model openrouter/anthropic/claude-3-opus
Hello! It's great to meet you. I hope you're having a wonderful day! ❄️☃️
```

has optional ~encrypted credential management using `hnt-llm save-key`

# build and install everything
```
git clone https://github.com/veilm/hinata
./hinata/install.sh
```

system dependencies: [Rust](https://rustup.rs/), `pkg-config`

# full architecture
- [`hnt-llm`](./hnt-llm/): simple, performant text backend. pipe text input
in, receive LLM text response out
- [`hnt-chat`](./hnt-chat/): wrapper around `hnt-llm` for managing
conversations and message history, using simple conv directories and message
markdown files
- [`llm-pack`](./hnt-pack/): take source code filenames as CLI args. write
LLM packed prompt to stdout
- [`hnt-apply`](./hnt-apply/): take LLM output including TARGET/REPLACE
blocks as stdin. make edits to those files on the LLM's behalf
- [`hlmd-st`](./fmt/highlight/): take LLM markdown output, including
code blocks as stdin. write syntax highlighted ver to stdout
- [`hnt-edit`](./hnt-edit/): (very low-budget) aider clone. wrapper that
uses `llm-pack` to format source code. sends it along with user instructions to
`hnt-chat`. optionally displays it using `hlmd-st`/custom. then uses `hnt-apply`
to parse the LLM's desired edits
- [`hnt-web`](./web/): simple 80/20 web app wrapping `hnt-chat`.
sufficient for my own casual usage and mobile/{filesystem storage} requirement
- [`headlesh`](./headlesh/): CLI headless shell manager. create
shell sessions and easily read/write to them
- [`hnt-agent`](./hnt-agent/): wrapper around `headlesh` for allowing an LLM
to use a shell and receive output, in a feedback loop
- [`browse`](./util/browse/): CLI for navigating your (not headless)
GUI Chromium-based browser programmatically. intended for LLM web browsing

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
