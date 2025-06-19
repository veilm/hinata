# tui-select

A simple `fzf`-like selector for the terminal.

It reads lines from `stdin`, allows you to select one, and prints the selected line to `stdout`.

It does not use the alternate screen buffer, instead drawing the selection menu at the bottom of the current screen, preserving your scrollback buffer.

## Build

To build the project, run the build script:

```sh
./build
```

This will compile `tui-select.c` into `tui-select.out` and then install it as `tui-select` in `/usr/local/bin/`. The install step requires `sudo` privileges.

## Usage

Pipe a list of newline-separated items to `tui-select`:

```sh
ls -1 | tui-select
```

If the program is not run in an interactive terminal (e.g. when piping output to another command), it will print the first line it receives from stdin and exit.

### Options

- `--height <lines>`: Set the height of the selection menu. Default is 10.
- `--color <0-7>`: Set the color of the selection highlight. The value should be an ANSI color code from 0 to 7.

Example:

```sh
# Show a menu with 20 lines and a green highlight for the selected item.
seq 1 100 | tui-select --height 20 --color 2
```

## Keybindings

| Key(s)                                | Action                       |
| ------------------------------------- | ---------------------------- |
| `Up`, `Alt-k`, `Ctrl-k`, `Shift-Tab`  | Move selection up            |
| `Down`, `Alt-j`, `Ctrl-j`, `Tab`      | Move selection down          |
| `Enter`                               | Confirm selection and exit   |
| `Esc`, `Ctrl-c`, `Ctrl-d`             | Abort and exit without selecting |