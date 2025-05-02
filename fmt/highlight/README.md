# hlmd-st
a minimal 80/20 syntax highlighting CLI for markdown, supporting streaming

![demo](https://raw.githubusercontent.com/michaelskyba/michaelskyba.github.io/refs/heads/master/static/1746143521-highlight.png)

## install
requires uv

```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/fmt/highlight
sudo cp ./hlmd-st /usr/local/bin/

# uv might need to install pygments on first run
echo install | hlmd-st
```

## usage
it just takes the raw markdown stream as stdin (e.g. from `hnt-llm`) and writes
the ansi colored version to stdout

uses terminal colors because we're assuming some form of pywal rather than slop
gruvbox/monokai

demo:
```
hlmd-st < research/test.md
```
