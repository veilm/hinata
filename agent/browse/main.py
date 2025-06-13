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

    if "console.log" in js_code:
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


def open_url(url):
    """Opens a URL in qutebrowser."""
    command = f":open {url}"
    subprocess.run(["qutebrowser", command])


def read_page(headless_browse_js_path, instant=False):
    """Reads the current page content using headless-browse.js."""
    with open(headless_browse_js_path, "r", encoding="utf-8") as f:
        js_content = f.read()
    llm_pack_options = "{ instant: true }" if instant else ""
    eval_js(
        js_content
        + f"""\n
await llmPack({llm_pack_options});
llmDisplayVisual();
console.log(window.formattedTree);"""
    )


def main():
    """Parses command-line arguments and executes the corresponding command."""
    usage = f"""Usage: {sys.argv[0]} <command> [args]
Commands:
  start          Starts a qutebrowser session if not running
  eval           Reads JS from stdin and evaluates it
  open [--read] [--instant] <URL>     Opens a URL and optionally reads it
  read [--instant]           Reads the content of the current page"""

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
        args = sys.argv[2:]
        read_flag = "--read" in args
        if read_flag:
            args.remove("--read")

        instant_flag = "--instant" in args
        if instant_flag:
            args.remove("--instant")

        if len(args) != 1:
            panic(f"'open' command requires exactly one URL argument.\n{usage}")
        url = args[0]

        open_url(url)
        if read_flag:
            read_page(headless_browse_js_path, instant=instant_flag)
    elif command == "read":
        args = sys.argv[2:]
        instant_flag = "--instant" in args
        if instant_flag:
            args.remove("--instant")

        if args:
            panic(f"'read' command takes at most one argument: --instant.\n{usage}")

        read_page(headless_browse_js_path, instant=instant_flag)
    else:
        panic(f"Unknown command: '{command}'.\n{usage}")


if __name__ == "__main__":
    main()
