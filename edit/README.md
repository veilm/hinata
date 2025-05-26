# hnt-edit
an initial test for an aider-like system

## install
```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/edit
./build
```

This will compile any other necessary CLI dependencies from within this repo.
No Python dependencies are required. There are two deps for C but you will
almost certainly already have them installed

## usage
Basic usage:
```
$ hnt-edit <file1> [file2 ...] [-m|--message user_message] [--model provider/model]
```

The LLM will read your user message and use your given files for reference,
potentially making edits to them using
[an aider-like TARGET/REPLACE format](https://github.com/michaelskyba/hinata/blob/main/edit/prompts/main-file_edit.md).

See [the hnt README](https://github.com/michaelskyba/hinata/tree/main/hnt) for
the list of supported model providers.

If you don't include a message in the CLI args, `$EDITOR` will be used for
input.

By default it will use a pre-written system prompt, stored in
`$XDG_CONFIG_HOME/hinata/prompts`. You can input your own prompt with the `-s
system_prompt_string` option. But if your system prompt doesn't describe the
edit format to the LLM, it will have no awareness of it and thus no way to edit
files. Using a blank prompt like `-s ""` is fine if you only need read access,
such as for asking questions about the code, though.

## failures
```
hnt-chat dir: /home/oboro/.local/share/[...]

hnt-apply: Processing blocks...
Error: Target not found in file /tmp/dir/1748287186/foo.py
Target (length 37):
---
print("foo")
---
[1] foo.py: FAILED
```

If the LLM fails to adhere to the edit format, hnt-apply will automatically
produce an error message and add it to the conversation. If you wish for the LLM
to attempt a followup, you can use
```
hnt-edit --continue-dir CHAT_DIR
```

## syntax highlighting
the LLM markdown output can be automatically piped to a syntax highlighting CLI.
by default it looks in `$PATH` for
[`hlmd-st`](https://github.com/michaelskyba/hinata/tree/main/fmt/highlight)

you can choose your own by setting `$HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD`, which
will override the `hlmd-st` check. e.g. setting it to `cat` will be equivalent
to disabling syntax highlighting since piping into cat returns your input
verbatim

keep in mind that your highlighting CLI needs to support streaming, which is not
the case for popular options like `rich-cli` and `pygmentize` that buffer the
entire stdin before parsing it. `hlmd-st` works as expected

the higlighter will not intefere with the LLM's edit format; `hnt-apply` is
given the raw LLM generation rather than your highlighter's output

## debugging
`--debug-unsafe`

warning: will likely leak your API key

## ss (`hlmd-st`)

![with syntax highlighting](https://github.com/michaelskyba/michaelskyba.github.io/blob/master/static/1746146910-hnt-edit.png?raw=true)
