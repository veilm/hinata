# build (shell script) – quick reference

Light-weight build/install helper for the Hinata tool-suite.

1. Init / safety  
   • `#!/bin/sh -e` – exit on first error.  
   • `cd "$(dirname "$0")"` – work from script’s own directory.

2. Dependency bootstrap  
   The script checks for required executables and triggers the corresponding sub-builds when they are missing.

| missing tool | recovery action (relative path)            |
|--------------|---------------------------------------------|
| `hlmd-st`    | if `uv` exists ⇒ `../fmt/highlight`         |
| `hnt-chat`   | `../chat/build`                             |
| `hnt-escape` | `../llm/build`                              |
| `llm-pack`   | `./llm-pack/build`                          |

3. Prompt bundle install  
   • Resolves destination: `${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts`.  
   • `mkdir -p` then `cp prompts/*` into that directory.

4. Binary installation prefix  
   • Uses `/usr/local/bin` (stored in `$bin`) for everything it installs.

5. Build + install `hnt-apply`  
   • Compiles `hnt-apply.c` with strict C99 flags.  
   • Copies resulting binary to `$bin/` (`sudo`).

6. Install Python helper `hnt-edit`  
   • Ensures executable bit on `hnt-edit.py`.  
   • Copies it to `$bin/hnt-edit` (`sudo`).

Result:  
• Prompts copied to config dir.  
• Binaries `hnt-apply` and `hnt-edit` available system-wide.

Run from repository root:

```sh
./build
```