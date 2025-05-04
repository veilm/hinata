# hnt-chat
wrapper around `hnt-llm` for managing conversations and message history

## build
```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/chat
./build
```

## concept
- `hnt-chat` organizes conversations into directories, within `$XDG_CONFIG_HOME/hinata/chat/conversations/`
- each conversation is a directory, identified by a unix timestamp in
nanoseconds. `$XDG_CONFIG_HOME/hinata/chat/conversations/conversationTimestamp/`
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
/home/user/.config/hinata/chat/conversations/1710000000123456789
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
