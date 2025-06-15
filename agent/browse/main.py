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
                        pass
                    elif result_subtype == "null":
                        print("null")
                    elif result_type == "object":
                        print(result.get("description", "[object Object]"))
                    elif "value" in result:
                        print(result["value"])

                    break
    except Exception as e:
        panic(f"An error occurred during WebSocket communication: {e}")


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

        asyncio.run(eval_js(js_code, args.debug))


if __name__ == "__main__":
    main()
