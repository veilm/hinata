# main.py – Quick Reference

Utility script to control a local Chromium/Chrome session through the Chrome DevTools Protocol (CDP).  
Primary use-case: programmatically open/read pages and run JavaScript from the command line.

---

## High-level Flow

1. **CLI (`main()`):** Parses sub-commands (`start`, `connect`, `eval`, `open`, `read`, `read-diff`) and dispatches to helpers.
2. **Browser bootstrap (`start_session`):**
   • Verifies `chromium`/`chromium-browser` is installed.  
   • Launches Chromium with `--remote-debugging-port`.  
   • Immediately calls `connect` to store target metadata.
3. **Session persistence:**  
   • Connection information is cached in `/tmp/hnt-agent-cdp/connected.json`.  
   • Subsequent commands (`eval`, `open`, `read*`) reuse this file to attach to the same tab.
4. **JavaScript execution (`eval_js`):**  
   • Opens websocket to the tab’s `webSocketDebuggerUrl`.  
   • Sends a `Runtime.evaluate` request and waits for the matching response id.  
   • Handles CDP / JS exceptions and returns a Python-friendly value.
5. **Page reading (`read_page`):**  
   • Loads user’s `headless-browse.js`, calls `llmPack` & `llmDisplayVisual`.  
   • Captures all `console.log` output via `_get_console_log_wrapper`.  
   • Persists tree to `/tmp/browse/formattedTree.txt`, maintaining a previous copy.
6. **Diff helper (`read-diff`):**  
   • Calls `read_page` then runs `git diff` between current and previous trees.

---

## Important Files / Paths

Constant | Purpose
---------|--------
`CDP_DIR`            | Temp dir for connection metadata
`CONNECTED_FILE`     | JSON descriptor of the currently attached tab
`/tmp/browse/…`      | Stores latest + previous `formattedTree.txt` dumps

---

## Key Functions

Function | Role
---------|-----
`panic(msg)`                              | Uniform error+exit helper
`check_dependencies()`                    | Finds Chromium binary
`start_session(url, port, debug=False)`   | Launch + auto-connect
`connect(port, url)`                      | Look up tab via `json/list`
`eval_js(js_code, debug=False)`           | Async CDP evaluator
`get_headless_browse_js_path()`           | Locates `headless-browse.js`
`_get_console_log_wrapper(js_code)`       | Injects console capture shim
`read_page(path, instant, debug)`         | Run `headless-browse.js` + dump output
`main()`                                  | CLI entrypoint

---

## Command Cheat-sheet

Command                | Effect
-----------------------|---------------------------------------------------------
`start --url U`        | Launch new Chromium at U and auto-connect
`connect --url U`      | Attach to existing tab at U
`eval [--debug] JS`    | Run raw JS (or stdin) in connected tab
`open URL [--read]`    | Navigate current tab; optional immediate `read`
`read [--instant]`     | Dump current page’s formatted tree
`read-diff`            | Same as `read`, then `git diff` vs previous tree

---

*Tip:* Pass `--debug` to many commands to see Chromium/stdout or low-level CDP JSON.