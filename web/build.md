# build (shell script) — Quick Reference

Purpose  
Install and update the “hnt-web” front-end assets and CLI on the local machine.

High-level flow  
1. `cd` into the script’s own directory.  
2. Verify required tools are present:  
   • `uv` — aborts if missing.  
   • `hnt-chat` — if missing, triggers its build via `../chat/build`.  
3. Determine install path `web="$XDG_DATA_HOME|$HOME/.local/share/…/web"` and copy `static/*` there.  
4. Make `hnt-web.py` executable and copy it to `/usr/local/bin/hnt-web` (requires `sudo`).  
5. Emit status messages at each step.

Key side-effects  
• Creates/updates web asset directory.  
• Installs/updates executable `hnt-web` system-wide.  
• Exits on any command failure because of `set -e`.

Edit points  
If you need to modify:  
• Tool checks → look at the two `which` blocks.  
• Install location → update the `web` variable.  
• Binary install path → change `sudo cp … /usr/local/bin/…`.