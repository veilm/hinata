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
$ hnt-edit <file1> [file2 ...] [-m|--message user_message]
```

The LLM will read your user message and use your given files for reference,
potentially making edits to them using
[an aider-like TARGET/REPLACE format](https://github.com/michaelskyba/hinata/blob/main/edit/prompts/01-targetreplace.md).

If you don't include a message in the CLI args, `$EDITOR` will be used for
input.

By default it will use a pre-written system prompt, stored in
`$XDG_CONFIG_HOME/hinata/prompts`. You can input your own prompt with the `-s
system_prompt_string` option. But if your system prompt doesn't describe the
edit format to the LLM, it will have no awareness of it and thus no way to edit
files. Using a blank prompt like `-s ""` is fine if you only need read access,
such as for asking questions about the code, though.

## ss
![no syntax highlighting yet?](https://raw.githubusercontent.com/michaelskyba/michaelskyba.github.io/refs/heads/master/static/hnt-edit-1745629293.jpg)
