# hnt-chat
wrapper around `hnt-llm` for managing conversations and message history

## build
```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/chat
./build
```

## concept
- `hnt-chat` organizes conversations into directories, within `$XDG_DATA_HOME/hinata/chat/conversations/`
- each conversation is a directory, identified by a unix timestamp in
nanoseconds. `$XDG_DATA_HOME/hinata/chat/conversations/conversationTimestamp/`
- a conversation is a list of messages
- each message is composed of a nanosecond ID, a role, and its content. it is
represented by a file inside the conversation directory
- each message file is named `messageNanosecondId-messageRole.md` and directly
contains the content for that message within it
- `hnt-chat` reads the files there matching this format alphabetically (and so
in order of ascending date), so you can, for example, delete messages by
deleting files. branching manually is janky but possible by making a backup of
the conv directory and editing message file content

## usage
### `hnt-chat new`
`new` creates a new, empty conv directory and outputs its absolute path

```sh
$ hnt-chat new
/home/user/.local/share/hinata/chat/conversations/1710000000123456789
```

### `hnt-chat add`
`add` adds static input as a message to the conversation, from stdin

```bash
hnt-chat add <role> [options]
```

role is either `user`, `assistant`, or `system`

**Options:**

- `-c PATH`, `--conversation PATH`: Specifies the path to the target conversation directory. If provided, this overrides any other method of selecting the conversation.
- If `-c`/`--conversation` is *not* provided, `hnt-chat` checks the `$HINATA_CHAT_CONVERSATION` environment variable. If set, its value is used as the path to the conversation directory.
- If neither the flag nor the environment variable is set, `hnt-chat` automatically selects the *latest* conversation directory found within the base conversations directory (determined by the alphabetically largest directory name, which corresponds to the latest timestamp). An error occurs if no conversations exist.

it reads the message content from stdin, and will write the filename of the
created message file to stdout, relative to the configured conv directory

```bash
# create conv and store directory
conv1=$(hnt-chat new)

# a new conv (conv2) is created but won't be used because we only captured the previous one
hnt-chat new > /dev/null

# create message and capture filename in stdout
f=$(echo "hello!" | hnt-chat add user -c "$conv1")

# this will now print our "hello!" message
cd "$conv1"
cat "$f"

# this will write to conv2 because no conversation is specified and conv2 is the
# latest by date/dirname
echo "hello. this is the first message in conv2" | hnt-chat add assistant
```

### `hnt-chat gen`
`gen` generates an LLM assistant message, with the current state of the
conversation as input. it has the same options as `add` for specifying the
conversation

it passes the conversation to the `hnt-llm` backend and streams back the LLM
response to stdout

**Options:**
- `-w|--write` will save the generation as a role=assistant message in the
current conversation after it's finished streaming
- `--output-filename` implies `--write` and will add an additional final line to
stdout to display the created assistant message's filename
- `-m|--model MODEL` will pass a model argument to `hnt-llm`. see [available
model providers](https://github.com/michaelskyba/hinata/tree/main/llm#supported-model-providers)
- `--merge`: consecutive messages with the same role will be concatenated into a
single message before being sent to the LLM. useful for organization
- `--include-reasoning`: Passes `--include-reasoning` to `hnt-llm`. The LLM may
include reasoning within `<think>...</think>` tags as part of its output.
- `--separate-reasoning`: Implies `--include-reasoning` and `--write`. If the
LLM output begins with a `<think>...</think>` block, this block is saved to a
separate `[timestamp]-assistant-reasoning.md` file. The rest of the output is
saved as the main assistant message. The reasoning file is for reference and not
used in future `gen` contexts.

### `hnt-chat pack`
`pack` packs a conversation into one text stream, suitably escaped as XML input
for `hnt-llm`. this is used internally by `hnt-chat gen`
