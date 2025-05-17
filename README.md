<p align="center">
<img src="https://raw.githubusercontent.com/michaelskyba/michaelskyba.github.io/refs/heads/master/static/1747511209-hinata-simsun.png" width="217">
</p>

<p align="center">
agentic AI pair programming in your terminal. except minimalist, modular, extensible
</p>

# architecture
- [`hnt-llm`](./llm/): simple, performant text backend. pipe text input in,
receive LLM text response out
- [`hnt-chat`](./chat/): wrapper around `hnt-llm` for managing conversations and
message history, using simple conv directories and message markdown files
- [`llm-pack`](./edit/llm-pack/): take source code filenames as CLI args. write
LLM packed prompt to stdout
- [`hnt-apply`](./edit/): take LLM output including TARGET/REPLACE blocks as
stdin. make edits to those files on the LLM's behalf
- [`hlmd-st`](./fmt/highlight/): take LLM markdown output, including code blocks
as stdin. write syntax highlighted ver to stdout
- [`hnt-edit`](./edit/): (very low-budget) aider clone. wrapper that uses
`llm-pack` to format source code. sends it along with user instructions to
`hnt-chat`. optionally displays it using `hlmd-st`/custom. then uses `hnt-apply`
to parse the LLM's desired edits

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
