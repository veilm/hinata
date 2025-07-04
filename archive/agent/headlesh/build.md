# build script overview

Purpose: Compile and install the `headlesh` C program.

Step-by-step
1. `#!/bin/sh -e` – POSIX shell, abort immediately on any error.  
2. `cd "$(dirname "$0")"` – change to the directory where the script resides (so relative paths work).  
3. `gcc … headlesh.c -o ./headlesh` – compile **headlesh.c** with:
   * `-O2` optimisation  
   * `-Wall -Wextra -Werror` for strict warnings  
   * `-std=c99 -pedantic` to enforce C99 compliance  
   resulting binary: `./headlesh`.  
4. `mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/hinata/headlesh"` – ensure a per-user data directory exists (not directly used by this script but likely needed by the program).  
5. `sudo cp ./headlesh /usr/local/bin/` – copy the binary into the system-wide path so it is runnable as `headlesh` from anywhere (requires sudo/root).  
6. `echo "headlesh/build: built headlesh"` – print a completion message.

Dependencies
* GCC toolchain
* Root privileges (or write permission to `/usr/local/bin`) for the install step.

Typical usage
```sh
./build          # build & install headlesh system-wide
```