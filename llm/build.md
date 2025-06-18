# build (shell script) – quick reference

Purpose  
• Automate compilation and installation of two C programs, `hnt-llm` and `hnt-escape`.

High-level flow  
1. `#!/bin/sh -e` – exit immediately on any error.  
2. `cd "$(dirname "$0")"` – switch to the directory containing this script so all relative paths resolve correctly.  
3. First `gcc` invocation  
   • Builds `hnt-llm` from `main.c`.  
   • Flags: `-O2 -Wall -Wextra -Werror -std=c99 -pedantic`.  
   • Links against `libcurl` and `libjansson`.  
4. Second `gcc` invocation  
   • Builds `hnt-escape` from `escape.c` with the same warning/optimization flags (no extra libs).  
5. `sudo cp ./hnt-llm ./hnt-escape /usr/local/bin/`  
   • Installs the freshly built binaries system-wide.  
6. Echo confirmation message.

Key points  
• Strict compilation (`-Wall -Wextra -Werror -pedantic`) ensures code quality.  
• Requires super-user privileges to copy binaries into `/usr/local/bin`.  
• Adding new binaries or source files: replicate gcc block(s) and extend the final `cp` line.