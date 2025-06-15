#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import random
import sys
import urllib.request
import websockets

CDP_DIR = "/tmp/hnt-agent-cdp"
CONNECTED_FILE = os.path.join(CDP_DIR, "connected.json")


def connect(port, url_to_find):
    """
    Connects to a CDP target and saves connection info.
    """
    try:
        with urllib.request.urlopen(f"http://0.0.0.0:{port}/json/list") as response:
            if response.status != 200:
                print(
                    f"Error: HTTP request failed with status {response.status}",
                    file=sys.stderr,
                )
                sys.exit(1)

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
            else:
                print(
                    f"Error: Could not find a page with URL: {url_to_find}",
                    file=sys.stderr,
                )
                sys.exit(1)

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


async def eval_js(js_code, debug=False):
    """
    Evaluates JavaScript in the connected tab via CDP.
    """
    if not os.path.exists(CONNECTED_FILE):
        print(f"Error: Not connected. Run 'connect' command first.", file=sys.stderr)
        sys.exit(1)

    with open(CONNECTED_FILE, "r") as f:
        connection_info = json.load(f)

    ws_url = connection_info.get("webSocketDebuggerUrl")
    if not ws_url:
        print(
            f"Error: webSocketDebuggerUrl not found in {CONNECTED_FILE}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        async with websockets.connect(ws_url) as websocket:
            request_id = random.randint(0, 1000000000)
            payload = {
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {"expression": js_code},
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
                        print(
                            f"Error from CDP: {response['error']['message']}",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                    result = response.get("result", {}).get("result", {})

                    result_type = result.get("type")
                    result_subtype = result.get("subtype")

                    if result_type == "undefined":
                        pass
                    elif result_subtype == "null":
                        print("null")
                    elif result_type == "object":
                        print("[object Object]")
                    elif "value" in result:
                        print(result["value"])

                    break
    except Exception as e:
        print(f"An error occurred during WebSocket communication: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """
    Main function to parse arguments and execute commands.
    """
    parser = argparse.ArgumentParser(
        description="A basic client for the Chrome DevTools Protocol."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # connect command
    connect_parser = subparsers.add_parser("connect", help="Connect to a browser tab.")
    connect_parser.add_argument(
        "--port", type=int, default=58205, help="CDP port (default: 58205)."
    )
    connect_parser.add_argument(
        "--url",
        default="about:blank#hnt-agent-cdp",
        help="URL of the tab to connect to (default: 'about:blank#hnt-agent-cdp').",
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
        help="show exactly what we sent to the websocket and dump any messages we get back",
    )

    args = parser.parse_args()

    if args.command == "connect":
        connect(args.port, args.url)
    elif args.command == "eval":
        js_code = args.js
        if js_code is None:
            js_code = sys.stdin.read()

        if not js_code:
            return

        asyncio.run(eval_js(js_code, args.debug))


if __name__ == "__main__":
    main()
