# hnt-chat

`hnt-chat` is a command-line utility designed for managing chat conversations stored locally on the filesystem. It provides a structured way to create conversations and add messages with specific roles.

## Installation

A basic installation script is provided:

```bash
./build
```

## Concept

`hnt-chat` organizes conversations into directories.

*   **Base Directory:** Conversations are stored within a base directory. By default, this is `$XDG_CONFIG_HOME/hinata/chat/conversations`. If `$XDG_CONFIG_HOME` is not set, it falls back to `$HOME/.config/hinata/chat/conversations`. The tool automatically creates this directory structure if it doesn't exist.
*   **Conversation Directories:** Each individual chat conversation resides in its own unique subdirectory within the base directory. These subdirectories are named using nanosecond timestamps (e.g., `1678886400123456789`) to ensure uniqueness and chronological ordering.
*   **Messages:** Messages within a conversation are stored as individual files inside the corresponding conversation directory. Each message file is named using the format `<nanosecond_timestamp>-<role>.md` (e.g., `1678886405987654321-user.md`). The content of the message is written directly into this file.

## Usage

`hnt-chat` operates through subcommands.

### `hnt-chat new`

Creates a new, empty conversation directory.

```bash
hnt-chat new
```

**Output:** The command prints the absolute path to the newly created conversation directory to standard output.

**Example:**

```bash
$ hnt-chat new
/home/user/.config/hinata/chat/conversations/1710000000123456789
```

### `hnt-chat add` (alias: `add-message`)

Adds a message to a conversation. Reads the message content from standard input.

```bash
hnt-chat add <role> [options]
```

**Arguments:**

*   `<role>`: Required. Specifies the author of the message. Must be one of `user`, `assistant`, or `system`.

**Options:**

*   `-c PATH`, `--conversation PATH`: Specifies the path to the target conversation directory. If provided, this overrides any other method of selecting the conversation.
*   If `-c`/`--conversation` is *not* provided, `hnt-chat` checks the `$HINATA_CHAT_CONVERSATION` environment variable. If set, its value is used as the path to the conversation directory.
*   If neither the flag nor the environment variable is set, `hnt-chat` automatically selects the *latest* conversation directory found within the base conversations directory (determined by the alphabetically largest directory name, which corresponds to the latest timestamp). An error occurs if no conversations exist.

**Input:** The content of the message should be piped to the command's standard input.

**Output:** The command prints the *relative* filename (e.g., `1710000005987654321-user.md`) of the newly created message file to standard output. Error messages or informational messages (like which conversation is being used) are printed to standard error.

**Example 1: Add a user message to the latest conversation**

```bash
echo "Hello, world!" | hnt-chat add user
# Output (stderr, if defaulting): hnt-chat: using latest conversation directory: /home/user/.config/hinata/chat/conversations/1710000000123456789
# Output (stdout): 1710000005987654321-user.md
```

**Example 2: Add an assistant message to a specific conversation using a flag**

```bash
echo "How can I help?" | hnt-chat add assistant -c /home/user/.config/hinata/chat/conversations/1710000000123456789
# Output (stdout): 1710000006123456789-assistant.md
```

**Example 3: Add a system message using the environment variable**

```bash
export HINATA_CHAT_CONVERSATION=/path/to/specific/conv
echo "You are a helpful coding assistant." | hnt-chat add system
# Output (stdout): 1710000007123456789-system.md
unset HINATA_CHAT_CONVERSATION # Clean up env var
```

## Environment Variables

*   `XDG_CONFIG_HOME`: If set, used to determine the parent directory for `hinata/chat/conversations`. Defaults to `$HOME/.config` if unset.
*   `HINATA_CHAT_CONVERSATION`: Specifies the target conversation directory for the `add` command, unless overridden by the `-c`/`--conversation` flag.
