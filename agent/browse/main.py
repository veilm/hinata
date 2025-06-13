#!/usr/bin/env python3

import sys
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def panic(msg):
    """Prints an error message to stderr and exits with status 1."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def check_dependencies():
    """Checks for required executables and files. Returns path to headless-browse.js."""
    if not shutil.which("qb-eval"):
        panic("'qb-eval' not found in PATH")
    if not shutil.which("qutebrowser"):
        panic("'qutebrowser' not found in PATH")

    xdg_data_home = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    headless_browse_js = xdg_data_home / "hinata/agent/web/headless-browse.js"

    if not headless_browse_js.is_file():
        panic(f"headless-browse.js not found at {headless_browse_js}")

    return headless_browse_js


def start_session():
    """Starts a qutebrowser session if one is not already running."""
    try:
        subprocess.run(["pgrep", "qutebrowser"], check=True, capture_output=True)
        print("WARNING: qutebrowser is already running.", file=sys.stderr)
    except subprocess.CalledProcessError:
        # qutebrowser is not running, start it in the background.
        subprocess.Popen(["qutebrowser", "qute://help/changelog.html"])


def eval_js(js_code):
    """Evaluates JavaScript code using either qb-eval or qutebrowser."""
    # qutebrowser displays the direct output on the screen which we don't want,
    # because it gets messy. Having undefined at the end will silence it.
    js_code += "\n; undefined"

    if "qbe_out" in js_code:
        # Pipe JS to qb-eval and forward its stdout/stderr to ours.
        # stdout/stderr are inherited from parent by default.
        subprocess.run(["qb-eval"], input=js_code.encode())
    else:
        # Write JS to a temp file and run qutebrowser :jseval
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as tmp_file:
            tmp_file.write(js_code)
            tmp_file_path = tmp_file.name

        try:
            command = f":jseval -f -w main {tmp_file_path}"
            subprocess.run(["qutebrowser", command])
        finally:
            os.unlink(tmp_file_path)


def open_url(url, headless_browse_js_path):
    """Opens a URL in qutebrowser and then runs headless-browse.js."""
    command = f":open {url}"
    subprocess.run(["qutebrowser", command])

    with open(headless_browse_js_path, "r", encoding="utf-8") as f:
        js_content = f.read()
    eval_js(
        js_content
        + "\n\nllmPack(); llmDisplayVisual(); window.qbe_out = formattedTree;"
    )


def main():
    """Parses command-line arguments and executes the corresponding command."""
    usage = f"""Usage: {sys.argv[0]} <command> [args]
Commands:
  start          Starts a qutebrowser session if not running
  eval           Reads JS from stdin and evaluates it
  open <URL>     Opens a URL in qutebrowser"""

    headless_browse_js_path = check_dependencies()

    if len(sys.argv) < 2:
        panic(f"No command specified.\n{usage}")

    command = sys.argv[1]

    if command == "start":
        if len(sys.argv) != 2:
            panic(f"'start' command takes no arguments.\n{usage}")
        start_session()
    elif command == "eval":
        if len(sys.argv) != 2:
            panic(
                f"'eval' command takes no arguments; it reads JS from stdin.\n{usage}"
            )
        js_code = sys.stdin.read()
        eval_js(js_code)
    elif command == "open":
        if len(sys.argv) != 3:
            panic(f"'open' command requires a URL argument.\n{usage}")
        url = sys.argv[2]
        open_url(url, headless_browse_js_path)
    else:
        panic(f"Unknown command: '{command}'.\n{usage}")


if __name__ == "__main__":
    main()
