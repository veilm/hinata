<p align="center">
<img src="https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/hinata.png" width="200">
</p>

<p align="center">
agentic AI pair programming in your terminal
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

Let an LLM handle your git workflow:
```sh
hnt-agent -m "check diff and commit with meaningful message"
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

```
hnt-llm           # text in → LLM response out
  ├─ hnt-chat     # + conversation history
  │   ├─ hnt-edit # + file editing
  │   └─ hnt-agent # + shell persistence
  └─ hnt-web      # + browser interface
```

Additional utilities like `browse` (browser automation) and `llm-pack` (source bundling) extend functionality through standard CLI composition.

## Philosophy

- Tools, not frameworks
- Text streams, not APIs  
- Composable by humans and LLMs alike
- Fast startup, minimal dependencies

## Support

[@sucralose__](https://x.com/sucralose__) · [Issues](https://github.com/veilm/hinata/issues)

## License

MIT