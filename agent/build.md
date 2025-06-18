# Build Script — Quick Reference

This shell script automates the local build and installation of the **Hinata agent** utilities.

## High-level Flow
1. `#!/bin/sh -e`  
   Abort immediately on any failing command (`set -e`).

2. **Change to script directory**  
   `cd "$(dirname "$0")"` ensures relative paths work regardless of where the script is invoked from.

3. **Verify (or build) `headlesh` dependency**  
   ```
   if ! which headlesh; then
       ./headlesh/build
   fi
   ```
   ‑– Re-compiles `headlesh` only if it is missing from `PATH`.

4. **Prepare prompt assets**  
   ```
   prompts_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts
   mkdir -p "$prompts_dir"
   cp prompts/* "$prompts_dir"
   ```
   Copies all prompt files to the user’s config directory.

5. **Mark helper scripts executable**  
   ```
   chmod +x ./hnt-shell-apply.py
   chmod +x ./hnt-agent.py
   ```

6. **System-wide install (requires sudo)**  
   ```
   bin=/usr/local/bin
   sudo cp ./hnt-shell-apply.py "$bin/hnt-shell-apply"
   sudo cp ./hnt-agent.py       "$bin/hnt-agent"
   ```
   Places the two Python entry-point scripts on the global `PATH`.

7. **User-visible status messages**  
   Echo statements prefix lines with `agent/build:` for easy log searching.

## Key Files Installed
| Destination file     | Source                              | Purpose                    |
|----------------------|-------------------------------------|----------------------------|
| `$prompts_dir/*`     | `prompts/*`                         | Prompt templates           |
| `/usr/local/bin/hnt-shell-apply` | `hnt-shell-apply.py` | Shell integration helper   |
| `/usr/local/bin/hnt-agent`       | `hnt-agent.py`       | Main agent entry-point     |

Run the script (`./build`) to set up or refresh the local installation.