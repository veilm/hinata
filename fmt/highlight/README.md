# hlmd-st
a minimal 80/20 syntax highlighting CLI for markdown, supporting streaming

![demo](https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/1746143521-highlight.png)

## install
requires uv

```sh
git clone https://github.com/veilm/hinata
cd hinata/fmt/highlight
./build
# now you have hlmd-st in /usr/local/bin
```

## usage
`hlmd-st` just takes the raw markdown stream as stdin (e.g. from `hnt-llm`) and writes
the ansi colored version to stdout. it uses terminal colors because we're
assuming some form of pywal rather than slop gruvbox/monokai

demo:
```
hlmd-st < research/test.md
```

not instant but likely much faster than your LLM generates tokens:
```
0.13user 0.02system 0:00.15elapsed 98%CPU (0avgtext+0avgdata 26644maxresident)k
0inputs+0outputs (0major+5592minor)pagefaults 0swaps
```
