Hinata / agent / browse — Overview
==================================

This sub-package is three small, well-separated parts that cooperate to let a
Python CLI drive a **headless Chromium tab** and extract a clean text/tree view
of any web page.

Component            | What it is (1-line)                                          | Where to read more
---------------------|--------------------------------------------------------------|--------------------
`headless-browse.js` | In-browser scraper → builds a lightweight DOM tree,          | **headless-browse.md**
                     | exports helpers `llmPack / llmDisplay / llmDisplayVisual`.   |
`main.py`            | Command-line wrapper around Chrome DevTools Protocol (CDP)   | **main.md**
                     | that starts/attaches to Chromium, injects the JS above,      |
                     | and dumps / diffs the tree.                                  |
`build` script       | Installs the two artefacts above (`headless-browse.js`       | **build.md**
                     | to XDG data dir, `main.py` as the `browse` CLI).             |

Typical developer workflow
--------------------------
1. Run `./build` (or see *build.md*) once to place the artefacts on your system.  
2. Use the new `browse` CLI:  
   • `browse start --url https://example.com`  
   • `browse read` or `browse read-diff` to snapshot the page tree.  
3. If you need to tweak the way the DOM is parsed/filtered, edit  
   `headless-browse.js` and re-run `./build`.

Where to look when…
--------------------
Need to…                          → Open…
• Change which tags are skipped, visibility rules, IDs, etc.     → headless-browse.md  
• Learn CDP message flow, add a new CLI sub-command, or diagnose | main.md  
  a connection issue.                                            |  
• See installation paths, permission requirements, or package    | build.md  
  your own release.                                              |  

File/Path Cheatsheet
--------------------
Path                                   | Purpose
-------------------------------------- | -----------------------------------------
`$(XDG_DATA_HOME)/hinata/agent/web/`    | Runtime location of `headless-browse.js`
`/usr/local/bin/browse`                 | Executable wrapper for `main.py`
`/tmp/hnt-agent-cdp/connected.json`     | Cached CDP target info (auto-generated)
`/tmp/browse/{formattedTree.txt,prev}`  | Latest & previous tree dumps

That’s all you need to orient yourself—dive into the individual quick-reference
docs above for line-by-line details.