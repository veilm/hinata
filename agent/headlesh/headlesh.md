# headlesh.c – Quick Reference

Single-binary utility that provides persistent interactive shells (session daemons)
communicated with through FIFOs.  Four CLI sub-commands are exposed:

| command | synopsis | what it does |
|---------|----------|--------------|
| create  | `headlesh create <session_id> [shell]` | Fork-daemonises a *session server* running the requested shell (default `bash`).  Creates a session directory in `/tmp/headlesh_sessions/<session_id>/` containing:<br>• `cmd.fifo` – main command FIFO clients write to<br>• `pid.lock` – lockfile + daemon PID marker. |
| exec    | `headlesh exec <session_id>` (stdin ⇒ script) | Acts as a *client*.  Builds three FIFOs unique to its PID for stdout, stderr and exit-status, formats a message `out_fifo\nerr_fifo\nstatus_fifo\n<user_script>` and writes it to `cmd.fifo`.  Then multiplexes the two output FIFOs to the caller’s stdout/stderr and finally reads the numeric exit status. |
| exit    | `headlesh exit <session_id>` | Sends the special payload `__HEADLESH_INTERNAL_EXIT_CMD__` (same envelope as *exec*) which causes the server loop to terminate and cleanup. |
| list    | `headlesh list` | Scans `/tmp/headlesh_sessions` for sub-directories with a live PID in `pid.lock`.  Prints active sessions. |

## File/Directory layout and constants
```
HEADLESH_SESSIONS_DIR       → /tmp/headlesh_sessions
SESSION_CMD_FIFO_NAME       → cmd.fifo
SESSION_LOCK_FILE_NAME      → pid.lock
OUT/ERR/STATUS_FIFO_TEMPLATE→ /tmp/headlesh_{out,err,status}_<pid>
BUFFER_SIZE                 → 65536 bytes
```

## Control flow

### Server side (`start_server_mode`)
1. Ensure session dir exists, create `cmd.fifo` & lock file, obtain exclusive flock.
2. Double-fork → detached daemon; stdout/stderr redirected to  
   `$XDG_DATA_HOME/hinata/headlesh/<session_id>/server.log`
3. Registers `atexit(cleanup_server_resources)` and signal handlers.
4. Spawns requested shell with its stdin wired through a pipe.
5. Main loop:  
   • Blocks on `cmd.fifo` → parses 3 fifo paths + script.  
   • If payload equals EXIT token → breaks.  
   • Otherwise writes script to tmp file, constructs one-liner:  
     `{ . script ; EXIT=$?; } >out 2>err ; echo $EXIT >status ; rm script`  
     and feeds it to shell stdin.
6. Detects shell exit or fatal FIFO errors → shutdown.

### Client side (`exec_client_mode`)
1. Reads user script from stdin (≤64 KiB).
2. Creates three FIFOs using caller PID.
3. Sends envelope to session server (`cmd.fifo`).
4. Opens the output FIFOs, uses `select()` to tee data to local stdout/stderr.
5. When both close, opens status FIFO, waits up to 60 s for exit code and exits
   with that code.
6. Signal handler ensures its FIFOs are unlinked on SIGINT/SIGTERM.

### Misc helpers
- `ensure_directory_exists()` – recursive `mkdir -p`.
- `construct_session_log_file_path()` – chooses `$XDG_DATA_HOME` or `$HOME/.local/share`.
- `cleanup_server_resources()` – kills shell, unlinks FIFOs/lock, removes empty session dir.
- Multiple `[server|client]_signal_handler()` variants for orderly teardown.

## Important invariants / gotchas
- Only one server per session (enforced by `flock` on lock file).
- Scripts are *sourced* (`.`) so they can modify shell state persistently.
- Users can send multi-line scripts up to 64 KiB; larger requires protocol change.
- If the sourced script performs `exit`, the whole server shell (and therefore session) terminates.
- Clients must read both output FIFOs completely before status will be available.