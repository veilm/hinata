# architecture

- [`hnt-llm`](./llm/): simple, performant text backend. pipe text input in, receive LLM text response out
- [`llm-pack`](./edit/llm-pack/): take source code filenames as CLI args. write LLM packed prompt to stdout
- [`hnt-apply`](./edit/): take LLM output including TARGET/REPLACE blocks as stdin. make edits to those files on the LLM's behalf
- [`hlmd-st`](./fmt/highlight/): take LLM markdown output, including code blocks as stdin. write syntax highlighted ver to stdout
- [`hnt-edit`](./edit/): (very low-budget) aider clone. wrapper that uses llm-pack to format source code. sends it along with user instructions to hnt-llm. then uses hnt-apply to parse the LLM's desired edits

# vague philosophy. here we go again...

[informal roadmap](https://github.com/michaelskyba/hinata/issues/1)

**Goal: unequivocally mog yapcine's setup**

- Have something like Aider / Claude code / codex but ~~impossible to use~~
extensible
- Integrate other ideas as they're leaked by Pliny/Tibor/etc
- Ideally LLM Chat is simple to layer on top as a wrapper over composable
features (e.g. memory)
- Maintain benchmarks on included prompts and scaffolding on private code (rvm,
iqd, etc.) for reference and for maliciously farming and baiting engagement on X
- Be reasonable in the design of backends. like Aider not like Open WebUI
