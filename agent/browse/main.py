#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
import websockets

CDP_PORT = 58205
DEFAULT_URL = "about:blank"
CDP_DIR = "/tmp/hnt-agent-cdp"
CONNECTED_FILE = os.path.join(CDP_DIR, "connected.json")
# USER_DATA_DIR = os.path.join(CDP_DIR, "user-data")


def panic(msg):
    """Prints an error message to stderr and exits with status 1."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def check_dependencies():
    """Checks for required executables."""
    for exe in ["chromium", "chromium-browser"]:
        if shutil.which(exe):
            return exe
    panic("'chromium' or 'chromium-browser' not found in PATH")


def start_session(url, port):
    """Starts a Chromium session and connects to it."""
    executable = check_dependencies()
    # os.makedirs(USER_DATA_DIR, exist_ok=True)

    command = [
        executable,
        f"--remote-debugging-port={port}",
        # f"--user-data-dir={USER_DATA_DIR}",
        url,
    ]
    print(command)

    try:
        subprocess.Popen(command)
        print(f"Chromium started.", file=sys.stderr)
    except FileNotFoundError:
        panic(f"'{executable}' not found. Please install it.")

    # Wait for browser to start up
    time.sleep(1)

    # Automatically connect
    print("Connecting...", file=sys.stderr)
    connect(port, url)


def connect(port, url_to_find):
    """
    Connects to a CDP target and saves connection info.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as response:
            if response.status != 200:
                panic(f"HTTP request failed with status {response.status}")

            data = json.loads(response.read().decode("utf-8"))
            target_page = None
            for page in data:
                if page.get("url") == url_to_find and page.get("type") == "page":
                    target_page = page
                    break

            if target_page:
                os.makedirs(CDP_DIR, exist_ok=True)
                with open(CONNECTED_FILE, "w") as f:
                    json.dump(target_page, f, indent=4)
                print(f"Connected to {url_to_find}", file=sys.stderr)
            else:
                page_urls = [p.get("url", "N/A") for p in data]
                panic(
                    f"Could not find a page with URL: {url_to_find}.\n"
                    f"Available page URLs: {page_urls}"
                )
    except urllib.error.URLError as e:
        panic(
            f"Could not connect to browser on port {port}. Is it running with --remote-debugging-port={port}? Error: {e}"
        )
    except Exception as e:
        panic(f"An error occurred: {e}")


async def eval_js(js_code, debug=False):
    """
    Evaluates JavaScript in the connected tab via CDP.
    Returns the result of the evaluation.
    """
    if not os.path.exists(CONNECTED_FILE):
        panic("Not connected. Run 'start' or 'connect' command first.")

    with open(CONNECTED_FILE, "r") as f:
        connection_info = json.load(f)

    ws_url = connection_info.get("webSocketDebuggerUrl")
    if not ws_url:
        panic(f"webSocketDebuggerUrl not found in {CONNECTED_FILE}")

    try:
        async with websockets.connect(ws_url) as websocket:
            request_id = random.randint(0, 1000000000)
            payload = {
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {"expression": js_code, "awaitPromise": True},
            }
            if debug:
                print(f"-> {json.dumps(payload)}", file=sys.stderr)
            await websocket.send(json.dumps(payload))

            while True:
                response_raw = await websocket.recv()
                if debug:
                    print(f"<- {response_raw}", file=sys.stderr)
                response = json.loads(response_raw)

                if response.get("id") == request_id:
                    if "error" in response:
                        panic(f"CDP error: {response['error']['message']}")

                    result_wrapper = response.get("result", {})
                    if "exceptionDetails" in result_wrapper:
                        exc_details = result_wrapper["exceptionDetails"]["exception"]
                        panic(
                            f"JS exception: {exc_details.get('description', 'No description')}"
                        )

                    result = result_wrapper.get("result", {})
                    result_type = result.get("type")
                    result_subtype = result.get("subtype")

                    if result_type == "undefined":
                        return None
                    elif result_subtype == "null":
                        return "null"
                    elif result_type == "object":
                        return result.get("description", "[object Object]")
                    elif "value" in result:
                        return result["value"]
                    return None
    except Exception as e:
        panic(f"An error occurred during WebSocket communication: {e}")


def get_headless_browse_js_path():
    """Checks for headless-browse.js and returns its path."""
    default_xdg_data_home = os.path.join(os.path.expanduser("~"), ".local", "share")
    xdg_data_home = os.environ.get("XDG_DATA_HOME", default_xdg_data_home)

    headless_browse_js = os.path.join(
        xdg_data_home, "hinata/agent/web/headless-browse.js"
    )

    if not os.path.isfile(headless_browse_js):
        panic(f"headless-browse.js not found at {headless_browse_js}")

    return headless_browse_js


async def read_page(headless_browse_js_path, instant=False, debug=False):
    """
    Reads the current page content using headless-browse.js.
    Saves page content to /tmp/browse/formattedTree.txt, and renames
    an existing formattedTree.txt to formattedTree-prev.txt.
    Returns the new page content as a string.
    """
    with open(headless_browse_js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    llm_pack_options = "{ instant: true }" if instant else "{}"

    js_to_run = (
        js_content
        + "\n"
        + "(async () => {"
        + f" await llmPack({llm_pack_options});"
        + " llmDisplayVisual();"
        + " return window.formattedTree;"
        + "})()"
    )

    formatted_tree = await eval_js(js_to_run, debug)

    if formatted_tree is None:
        panic(
            "read_page: formatted_tree is None. JS execution might have failed silently."
        )

    browse_tmp_dir = "/tmp/browse"
    os.makedirs(browse_tmp_dir, exist_ok=True)

    formatted_tree_path = os.path.join(browse_tmp_dir, "formattedTree.txt")
    formatted_tree_prev_path = os.path.join(browse_tmp_dir, "formattedTree-prev.txt")

    if os.path.exists(formatted_tree_path):
        shutil.move(formatted_tree_path, formatted_tree_prev_path)

    with open(formatted_tree_path, "w", encoding="utf-8") as f:
        f.write(formatted_tree)

    return formatted_tree


def main():
    """
    Main function to parse arguments and execute commands.
    """
    parser = argparse.ArgumentParser(
        description="A tool for controlling a browser via Chrome DevTools Protocol."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start command
    start_parser = subparsers.add_parser(
        "start", help="Start a new chromium instance and connect to it."
    )
    start_parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"URL to open (default: {DEFAULT_URL})."
    )
    start_parser.add_argument(
        "--port", type=int, default=CDP_PORT, help=f"CDP port (default: {CDP_PORT})."
    )

    # connect command
    connect_parser = subparsers.add_parser(
        "connect", help="Connect to an existing browser tab."
    )
    connect_parser.add_argument(
        "--port", type=int, default=CDP_PORT, help=f"CDP port (default: {CDP_PORT})."
    )
    connect_parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"URL of the tab to connect to (default: {DEFAULT_URL}).",
    )

    # eval command
    eval_parser = subparsers.add_parser(
        "eval", help="Evaluate JavaScript in the connected tab."
    )
    eval_parser.add_argument(
        "js",
        nargs="?",
        default=None,
        help="JavaScript to evaluate. Reads from stdin if not provided.",
    )
    eval_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show CDP communication.",
    )

    # open command
    open_parser = subparsers.add_parser(
        "open",
        help="Open a URL. This will change the URL of the currently connected tab.",
    )
    open_parser.add_argument("url", help="URL to open.")
    open_parser.add_argument(
        "--read", action="store_true", help="Read the page after opening."
    )
    open_parser.add_argument(
        "--instant", action="store_true", help="Use instant mode for reading."
    )
    open_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show CDP communication.",
    )

    # read command
    read_parser = subparsers.add_parser(
        "read", help="Read the content of the current page."
    )
    read_parser.add_argument(
        "--instant", action="store_true", help="Use instant mode for reading."
    )
    read_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show CDP communication.",
    )

    # read-diff command
    read_diff_parser = subparsers.add_parser(
        "read-diff", help="Read the current page and diffs with the previous read."
    )
    read_diff_parser.add_argument(
        "--instant", action="store_true", help="Use instant mode for reading."
    )
    read_diff_parser.add_argument(
        "--debug",
        action="store_true",
        help="Show CDP communication.",
    )

    args = parser.parse_args()

    if args.command == "start":
        start_session(args.url, args.port)
    elif args.command == "connect":
        connect(args.port, args.url)
    elif args.command == "eval":
        js_code = args.js
        if js_code is None:
            js_code = sys.stdin.read()

        if not js_code.strip():
            return

        result = asyncio.run(eval_js(js_code, args.debug))
        if result is not None:
            print(result)
    elif args.command == "open":
        # First, navigate
        asyncio.run(eval_js(f"window.location.href = '{args.url}'", args.debug))

        # 1749956996 headless-browse already takes care of the loading waiting.
        # otherwise the LLM can rerun `read` if needed
        # This is a bit racey. We hope the navigation has started.
        # time.sleep(2)

        if args.read:
            headless_browse_js_path = get_headless_browse_js_path()
            page_content = asyncio.run(
                read_page(headless_browse_js_path, args.instant, args.debug)
            )
            print(page_content, end="")
    elif args.command == "read":
        headless_browse_js_path = get_headless_browse_js_path()
        page_content = asyncio.run(
            read_page(headless_browse_js_path, args.instant, args.debug)
        )
        print(page_content, end="")
    elif args.command == "read-diff":
        headless_browse_js_path = get_headless_browse_js_path()
        # This call will handle saving new tree and moving old one
        asyncio.run(read_page(headless_browse_js_path, args.instant, args.debug))

        browse_tmp_dir = "/tmp/browse"
        formatted_tree_path = os.path.join(browse_tmp_dir, "formattedTree.txt")
        formatted_tree_prev_path = os.path.join(
            browse_tmp_dir, "formattedTree-prev.txt"
        )

        if not os.path.exists(formatted_tree_prev_path):
            # Create empty prev file if it doesn't exist for the diff
            with open(formatted_tree_prev_path, "w") as f:
                pass

        subprocess.run(
            [
                "git",
                "diff",
                "--no-index",
                str(formatted_tree_prev_path),
                str(formatted_tree_path),
            ]
        )


if __name__ == "__main__":
    main()
