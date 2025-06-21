# TUI tools

A collection of simple TUI tools that work in the current terminal screen without using the alternate screen buffer.

## Build

To build all tools, run the build script:

```sh
./build
```

This will compile `tui-select.c` and `tui-pane.c` and install them as `tui-select` and `tui-pane` in `/usr/local/bin/`. The install step requires `sudo` privileges.

---

## tui-select

![tui-select screenshot](https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/1750335491-tui-select.png)

A simple `fzf`-like selector for the terminal.

It reads lines from `stdin`, allows you to select one, and prints the selected line to `stdout`.

It does not use the alternate screen buffer, instead drawing the selection menu at the bottom of the current screen, preserving your scrollback buffer.

### Usage

Pipe a list of newline-separated items to `tui-select`:

```sh
ls -1 | tui-select
```

If the program is not run in an interactive terminal (e.g. when piping output to another command), it will print the first line it receives from stdin and exit.

#### Options

- `--height <lines>`: Set the height of the selection menu. Default is 10.
- `--color <0-7>`: Set the color of the selection highlight. The value should be an ANSI color code from 0 to 7.

Example:

```sh
# Show a menu with 20 lines and a green highlight for the selected item.
seq 1 100 | tui-select --height 20 --color 2
```

### Keybindings

| Key(s)                                | Action                       |
| ------------------------------------- | ---------------------------- |
| `Up`, `Alt-k`, `Ctrl-k`, `Shift-Tab`  | Move selection up            |
| `Down`, `Alt-j`, `Ctrl-j`, `Tab`      | Move selection down          |
| `Enter`                               | Confirm selection and exit   |
| `Esc`, `Ctrl-c`, `Ctrl-d`             | Abort and exit without selecting |

---

## tui-pane

A simplified `tmux`-like tool that runs a command in a new pane within your current terminal screen.

It creates a persistent pane at the bottom of the terminal, runs the provided command inside it, and renders the command's output within that pane. It does this without using the alternate screen buffer, preserving your scrollback.

The pane is created near your current cursor position if possible, otherwise at the bottom of the screen. By default, it is 20 lines high.

### Usage

Run any command inside a `tui-pane`:

```sh
tui-pane htop
```

Or run an editor:

```sh
tui-pane nvim my_file.txt
```

`tui-pane` forwards all keyboard input to the running command. To exit, you must exit the command running inside the pane (e.g., press `q` in `htop` or `:q` in `vim`).
