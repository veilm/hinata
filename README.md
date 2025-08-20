<p align="center">
<img src="https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/hinata.png" width="200">
</p>

<p align="center">
agentic, extensible AI pair programming in your terminal
</p>

---

## Install

```sh
curl hnt-agent.org/install | sh
```

Requirements: Go, Linux/macOS

## What

A collection of composable CLI tools that give LLMs agency in your terminal. Each tool does one thing well and can be piped together.

**Core tools:**
- `hnt-agent` - LLM with persistent shell access
- `hnt-edit` - Targeted file editing with TARGET/REPLACE blocks
- `hnt-chat` - Conversation management via plaintext files
- `hnt-llm` - Direct LLM API access

## Usage

Interactive:
```sh
hnt-agent
```

Let an LLM handle your git workflow, without any prompts:
```sh
hnt-agent --yes --auto-exit -m "check diff and commit with meaningful message"
```

Edit multiple files at once:
```sh
hnt-edit -m "enable debug mode" src/*.h
```

Direct LLM interaction:
```sh
echo "explain quantum computing in one sentence" | hnt-llm
```

## Architecture

```mermaid
graph LR
	hnt-chat --> hnt-llm
	hnt-edit --> hnt-chat
	hnt-agent --> hnt-edit
	hnt-web --> hnt-chat
```

Additional utilities extend functionality through standard CLI composition.

- `browse`: non-headless (=> high-trust) Chromium browser automation
- `llm-pack`: source bundling files
- `shell-exec`: ultra lightweight, headless shell input/output
- `tui-select`: minimal fzf clone for interactively selecting a line from stdin
- `hnt-apply`: parse TARGET/REPLACE blocks (used internally by `hnt-edit`)
- for LLM memory, see [Cathedral](https://github.com/veilm/cathedral)

## Philosophy

- Tools, not frameworks
- Text streams, not APIs
- Composable by humans and LLMs alike
- Fast startup, minimal dependencies

## Support

[@sucralose__](https://x.com/sucralose__) · [Issues](https://github.com/veilm/hinata/issues)

## License

MIT
