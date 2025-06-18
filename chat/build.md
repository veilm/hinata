# build – quick reference

Purpose: Install the `hnt-chat` CLI wrapper, compiling its dependency (`hnt-llm`) if necessary.

Script flow
1. `#!/bin/sh -e` – POSIX shell, abort on first error.
2. `cd "$(dirname "$0")"` – run relative to the script’s own directory.
3. Check for `hnt-llm` binary  
   • If **not** found, execute `../llm/build` to compile it.
4. `chmod +x ./hnt-chat.py` – ensure the chat wrapper is executable.
5. `sudo cp ./hnt-chat.py /usr/local/bin/hnt-chat` – install it system-wide.
6. `echo "chat/build: installed hnt-chat"` – status message.

Key takeaway: Running `./build` guarantees `hnt-chat` ends up on the user’s PATH and that its underlying LLM dependency is built if missing.