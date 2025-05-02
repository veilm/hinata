# highlight-md-stream
a minimal 80/20 syntax highlighting CLI for markdown, supporting streaming

![demo](https://raw.githubusercontent.com/michaelskyba/michaelskyba.github.io/refs/heads/master/static/1746143521-highlight.png)

## install
requires uv

```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/fmt/highlight
sudo cp ./highlight-md-stream /usr/local/bin/

# uv might need to install pygments on first run
echo install | highlight-md-stream
```

## usage
it just takes the raw markdown stream as stdin (e.g. from `hnt-llm`) and writes
the ansi colored version to stdout

demo:
```
highlight-md-stream < research/test.md
```
