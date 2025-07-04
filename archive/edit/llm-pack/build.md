# build

Quick-reference overview of `build` shell script.

## Purpose
Compile the C source code (`main.c`) into a release-ready binary named **`llm-pack`** and install it system-wide.

## Key Steps
1. **Change to Script Directory**  
   `cd "$(dirname "$0")"` ensures the subsequent commands run relative to the script’s own location.

2. **Compilation**  
   ```
   gcc -O2 -Wall -Wextra -Werror \
       -std=c99 -pedantic \
       main.c -o ./llm-pack
   ```  
   • `-O2` ‑ Optimize for speed.  
   • `-Wall -Wextra -Werror` ‑ Enable most warnings and treat them as errors.  
   • `-std=c99 -pedantic` ‑ Enforce the C99 standard strictly.  
   • Output executable is `./llm-pack`.

3. **Installation (requires sudo)**  
   `sudo cp ./llm-pack /usr/local/bin/` copies the freshly built binary into the typical user-local system binary directory so it can be executed anywhere.

4. **Completion Message**  
   `echo "llm-pack/build: compiled llm-pack"` – simple progress confirmation.

## Usage
Run from project root (or anywhere)  
```bash
./build
```  
Note: Installation step needs sudo privileges.