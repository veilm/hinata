# HINATA / agent / headlesh — High-level README

This directory holds the **headlesh** subsystem of the HINATA agent.

What it is  
• `headlesh` is a single-binary helper that gives the agent (and any user) **persistent POSIX-shell sessions** you can re-attach to by sending scripts through FIFOs.  
• Think of it as “`tmux` for batch scripts” — create a named session once and keep **stateful shells** alive for fast, repeatable automation.

Why it exists  
• Long-running CI / automation flows often need to keep environment state (cwd, exports, functions, history) between steps. Spawning a fresh shell each time is slow and loses context; `headlesh` avoids that.  
• The agent talks to these sessions instead of forking new shells.

How it works (in one breath)  
`headlesh create` forks a daemonised server shell, exposes `cmd.fifo`, then waits for envelopes from `headlesh exec`; each envelope contains three temporary FIFO paths and a script. The server sources the script, streams `stdout`/`stderr` back through the FIFOs, writes the numeric exit status, and keeps running until `headlesh exit` tells it to shut down. `headlesh list` reports live sessions.

Key files in this folder  
• **headlesh.c** – the implementation (see headlesh.md for a quick-reference of all functions/flows)  
• **build** – POSIX shell script that compiles & installs the binary  
• **build.md** – human-oriented walkthrough of the build script  
• **headlesh.md** – in-depth CLI, protocol & control-flow reference (server, client, helpers)

Where to read next  
Need…                      | Read…  
---------------------------|------------------------------  
Build / install details    | **build.md**  
CLI syntax & examples      | **headlesh.md** → “Four CLI sub-commands”  
FIFO protocol / invariants | **headlesh.md** → “Control flow” & “Important invariants”  
Source-level internals     | `headlesh.c` (grep the function names listed in headlesh.md)

In most cases **headlesh.md** answers *runtime* questions, while **build.md** answers *compile/install* ones. This file (HINATA.md) is only the map.