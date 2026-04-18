Hello Claude Code / Codex / other LLM agent! Please read this short tutorial carefully. If any of its content is truncated by your read file tool, please examine the lines in smaller chunks.

`hnt-chat` (hinata chat) is a CLI utility for interacting with LLMs. Hinata models LLM interactions as conversations, where each conversation is a directory, composed of some metadata and an ordered list of message files. Each message file has a timestamp and role (kept in its filename) and its message content (the plaintext content in the file).

Here is an example interaction, creating a conversation directory, and exchanging messages with an LLM.

```bash
# Create the message directory
conv=$(hnt-chat new)

# hnt-chat new creates blank directories in a central location, often in XDG_DATA_HOME
echo $conv
# => /home/oboro/.local/share/hinata/chat/conversations/1767739651468480524

# alternatively, make a directory anywhere you'd like and use it as your conversation
conv=/tmp/my-hinata-conv
mkdir -p $conv

# Add a static message to the conversation using `hnt-chat add <system|user|assistant>`
# System messages can be used for instructions at the start of a conversation. Most LLMs only support one system message per conversation, which has to be the very first message
# In practice, 90% of the time, modern LLMs work better if you simply specify your instructions as a user message, than have some kind of role-based "You are an expert code reviewer" system prompt
f1=$(echo "Always respond with rhymes, often incorporating the topic of water." | hnt-chat add system -c $conv)
f2=$(echo "Hello!" | hnt-chat add user -c $conv)

# hnt-chat add <role> outputs the created message filename
echo $f1 $f2
# => 1767739952897305113-system.md 1767739954576862523-user.md
# These files are created as plaintext in your conversation directory
ls $conv
# => 1767739952897305113-system.md
# => 1767739954576862523-user.md

# You can use hnt-chat add assistant, to set a static LLM response. But in most
# cases you want the LLM to generate a response, not for you to provide it on its
# behalf
# Use hnt-chat gen, to generate an LLM response

# Different models have different capabilities and quirks
# Gemini 3.1 Pro on openrouter is recent, intelligent, and otherwise usually a safe pick
model=openrouter/google/gemini-3.1-pro-preview

# --include-reasoning will save the CoT (chain of thought; internal reasoning)
# summary returned by the API for the generation. it's helpful for debugging the
# LLM's decisions
# --output-filename + --write will generate the LLM response, save it as a
# message file in the conversation, and print its filename.
f3=$(hnt-chat gen -c $conv --model $model --include-reasoning --output-filename --write)

# LLM generations can take up to a few minutes, so for subprocesses, avoid small
# timeouts like 10 seconds or 30 seconds

# now you can read the LLM response by reading
cat $conv/$f3
# => A kind hello, the tide rolls in,
# => Let our new conversation now begin.

# if you want to continue the conversation, you can now add another user
# message, and then generate another assistant message

# if you need to delete or edit a message, you can simply delete or modify the
# markdown files in $conv. the conversation history is equal to $conv/*.md,
# ordered by the message timestamps in their filenames

# if an LLM is ever responding in an unexpected way, it's usually a good idea to
# debug by examining $conv and reading your existing input messages, to confirm
# they're as you expect
```
