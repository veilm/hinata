# build — quick reference

Purpose  
Install two runtime artefacts:

1. `headless-browse.js` →  
   `${XDG_DATA_HOME:-$HOME/.local/share}/hinata/agent/web`
2. `main.py` (as executable **browse**) → `/usr/local/bin/browse`

How it works  
• `set -e` – abort on first error  
• `cd "$(dirname "$0")"` – run relative to the script’s own directory  
• Create target web-directory with `mkdir -p`  
• Copy `headless-browse.js` there and echo status  
• `chmod +x main.py` – ensure it is executable  
• `sudo cp main.py /usr/local/bin/browse` – system-wide CLI install, then echo status

Dependencies / notes  
• Requires `sudo` rights for the final copy step  
• Safe to rerun; copy & `mkdir -p` are idempotent