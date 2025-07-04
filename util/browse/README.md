# browse

`browse` is a command-line tool for controlling a web browser, designed for use with LLM-based agents. It uses the Chrome DevTools Protocol to launch and interact with a Chromium-based browser. Its key feature is the `read` command, which intelligently extracts a simplified, structured representation of a webpage's content, making it easier for language models to understand and process.

## Installation

### Dependencies

-   **Python 3**: The main script is written in Python.
-   **`websockets` library**: A Python dependency. Install it via pip:
    ```sh
    pip install websockets
    ```
-   **Chromium-based browser**: You need `chromium` or `chromium-browser` installed and available in your `PATH`.

### Installing the tool

A `build` script is provided for installation. It will:
1.  Copy the necessary `headless-browse.js` script to `~/.local/share/hinata/agent/web/`.
2.  Make `main.py` executable and copy it to `/usr/local/bin/browse`, which may require `sudo`.

To install, run:
```sh
./build
```

## Usage

The tool works by managing a connection to a specific browser tab. You start a session, which opens a browser window, and then you can issue commands to interact with the page in that tab.

### Example Workflow

1.  **Start a new browser session and open a page:**
    ```sh
    browse start --url https://www.google.com
    ```
    This will launch a new Chromium window.

2.  **Read the page content:**
    The `read` command processes the page's DOM and outputs a structured text format.
    ```sh
    browse read
    ```

3.  **Navigate to a new URL and read it immediately:**
    ```sh
    browse open https://news.ycombinator.com --read
    ```

4.  **Execute arbitrary JavaScript:**
    ```sh
    browse eval "console.log(document.title)"
    ```

### Commands

-   `browse start [--debug] [--url <url>] [--port <port>]`
    Starts a new Chromium instance and connects to it. The connection information is saved locally for subsequent commands.

-   `browse connect [--url <url>] [--port <port>]`
    Connects to a specific tab in an already running Chromium instance that was started with the `--remote-debugging-port` flag.

-   `browse open <url> [--read] [--instant]`
    Navigates the currently connected tab to the specified URL. If `--read` is provided, it will also read the page content after navigation.

-   `browse read [--instant] [--debug]`
    Reads the content of the current page using `headless-browse.js`. The output is a simplified tree structure of the DOM, designed to be easy for an LLM to parse.
    -   The `--instant` flag processes the page immediately, without waiting for dynamic content to settle.

-   `browse read-diff [--instant] [--debug]`
    Reads the current page and shows a `git diff` between the new content and the content from the previous `read` or `read-diff` command.

-   `browse eval "[javascript code]"`
    Evaluates a string of JavaScript in the context of the current page. The script can also be piped from `stdin`. Any `console.log` output from the script is captured and printed to `stdout`.

    top-level await works here because your input is automatically wrapped in an async function
