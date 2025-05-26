#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi",
#     "uvicorn",
# ]
# ///

import os
import sys
import re
from pathlib import Path
from typing import List
import html
import uvicorn

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

app = FastAPI()


# Copied and adapted from chat/hnt-chat.py
# Ensure this function is aligned with how hnt-chat determines the base directory.
def get_conversations_dir():
    """
    Determines and ensures the existence of the base directory for conversations.
    Uses $XDG_DATA_HOME/hinata/chat/conversations, defaulting to
    $HOME/.local/share/hinata/chat/conversations if $XDG_DATA_HOME is not set.
    """
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        base_data_dir = Path(xdg_data_home)
    else:
        home_dir = Path.home()
        if not home_dir:
            # This should ideally not happen in a typical server environment
            # but good to have a fallback or clear error.
            # For a web app, raising an exception might be better than sys.exit.
            raise RuntimeError("Could not determine home directory.")
        base_data_dir = home_dir / ".local" / "share"

    conversations_dir = base_data_dir / "hinata" / "chat" / "conversations"

    # For a read-only web app, we might not want to create it,
    # but rather fail if it doesn't exist.
    # However, to align with the original function's behavior of ensuring existence:
    try:
        conversations_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Log error or handle appropriately for a web context
        print(
            f"Warning: Could not create directory {conversations_dir}: {e}",
            file=sys.stderr,
        )
        # Depending on requirements, might raise HTTPException here if dir is critical

    if not conversations_dir.is_dir():
        raise HTTPException(
            status_code=500,
            detail=f"Conversations directory not found or is not a directory: {conversations_dir}",
        )

    return conversations_dir


COMMON_STYLES = """
body {
    font-family: 'Consolas', 'Menlo', 'Courier New', Courier, monospace; /* Monospace font */
    margin: 0;
    padding: 20px;
    background-color: #121212; /* Dark background */
    color: #e0e0e0; /* Light text */
}
h1, h2 {
    color: #e0e0e0;
    border-bottom: 1px solid #333333;
    padding-bottom: 8px;
    margin-top: 0;
}
h1 { font-size: 1.8em; }
h2 { font-size: 1.5em; }

a {
    color: #61afef; /* A common 'dark theme' blue */
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}
.container {
    background-color: #1e1e1e; /* Slightly lighter dark for container */
    padding: 20px;
    border-radius: 0; /* Minimal: no rounded corners */
}
ul {
    list-style-type: none;
    padding: 0;
}
li {
    margin-bottom: 8px;
}
.message {
    background-color: #282828; /* Background for each message block */
    border: 1px solid #333333; /* Subtle border */
    margin-bottom: 15px;
    padding: 12px;
    border-radius: 0; /* Minimal */
    word-wrap: break-word;
    white-space: pre-wrap; /* Preserve whitespace and newlines */
}
.message-header {
    font-weight: normal;
    margin-bottom: 8px;
    font-size: 0.85em;
    color: #aaaaaa;
    display: flex;
    justify-content: space-between;
    border-bottom: 1px dashed #444444;
    padding-bottom: 6px;
}
.message-role {
    text-transform: capitalize;
    font-weight: bold; /* Role should remain distinguishable */
    color: #c0c0c0;
}
.message-filename {
    font-style: normal; /* Less emphasis */
    color: #888888;
}

.message-system {
    border-left: 4px solid #7f8c8d; /* Slate gray */
}
.message-user {
    border-left: 4px solid #61afef; /* Blue */
}
.message-assistant {
    border-left: 4px solid #98c379; /* Green */
}
.message-assistant-reasoning {
    border-left: 4px solid #e5c07b; /* Yellow/Gold */
    background-color: #2c2c2c; /* Slightly different background for reasoning block */
    /* font-family is inherited from body; specific monospace fonts from original are covered */
    font-size: 0.9em; /* Keep slightly distinct for code/reasoning blocks if desired */
    padding: 10px; /* Adjusted padding for reasoning block */
}
.message-unknown {
    border-left: 4px solid #5c6370; /* Darker gray */
}
.back-link {
    display: inline-block;
    margin-bottom: 20px;
    padding: 6px 12px; /* Adjusted padding */
    border: 1px solid #444444; /* Subtle border */
    color: #61afef; /* Match link color for consistency */
}
.back-link:hover {
    background-color: #2a2a2a; /* Subtle hover effect */
    text-decoration: none;
}
.other-files-divider {
    border: 0;
    border-top: 1px solid #444444; /* Separator color */
    margin-top: 25px;
    margin-bottom: 20px;
}
.other-file-entry {
    background-color: #2c2c2c; /* Slightly different from message for distinction */
    border: 1px solid #383838;
    padding: 10px;
    margin-bottom: 10px;
    border-radius: 0; /* Minimal */
}
.other-file-entry strong { /* Filename */
    display: block;
    margin-bottom: 5px;
    color: #c0c0c0; /* Brighter than regular text for emphasis */
}
.other-file-content {
    white-space: pre-wrap; /* Preserve whitespace and newlines */
    word-wrap: break-word; /* Wrap long lines */
    background-color: #222222; /* Slightly darker than entry bg for content block */
    padding: 8px;
    max-height: 400px; /* Limit height for very long files */
    overflow-y: auto;  /* Add scrollbar if content exceeds max-height */
    border: 1px solid #333333; /* Subtle border for the content block */
    font-size: 0.9em; /* Slightly smaller font for content, can be same as message */
}
.other-file-content-binary {
    color: #888888; /* Dim color for binary/error message */
    font-style: italic;
}
"""


@app.get("/", response_class=HTMLResponse)
async def list_conversations():
    try:
        conv_base_dir = get_conversations_dir()
        conversations = sorted(
            [d.name for d in conv_base_dir.iterdir() if d.is_dir()],
            reverse=True,  # Show newest first
        )
    except RuntimeError as e:  # From home_dir issue
        raise HTTPException(status_code=500, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="Base conversation directory not found."
        )
    except Exception as e:
        # Generic error for other potential OS issues
        raise HTTPException(
            status_code=500, detail=f"Error listing conversations: {str(e)}"
        )

    list_items = "".join(
        f'<li><a href="/conversation/{conv_name}">{conv_name}</a></li>'
        for conv_name in conversations
    )

    return f"""
    <html>
        <head>
            <title>Hinata Chat Conversations</title>
            <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🐙</text></svg>">
            <style>{COMMON_STYLES}</style>
        </head>
        <body>
            <div class="container">
                <h1>Hinata Chat Conversations</h1>
                {"<p>No conversations found.</p>" if not conversations else f"<ul>{list_items}</ul>"}
            </div>
        </body>
    </html>
    """


@app.get("/conversation/{conversation_id}", response_class=HTMLResponse)
async def read_conversation(conversation_id: str):
    try:
        conv_base_dir = get_conversations_dir()
    except RuntimeError as e:  # From home_dir issue
        raise HTTPException(status_code=500, detail=str(e))

    conv_path = conv_base_dir / conversation_id

    if not conv_path.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Conversation '{conversation_id}' not found."
        )

    messages_html_parts = []
    other_files_html_parts = []

    # Regex to extract role from standard message filenames.
    # This pattern is used to distinguish message files from other files.
    filename_pattern = re.compile(
        r"^\d+-(system|user|assistant|assistant-reasoning)\.md$", re.IGNORECASE
    )

    all_item_paths_in_dir = []
    try:
        all_item_paths_in_dir = list(conv_path.iterdir())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing files in conversation '{conversation_id}': {str(e)}",
        )

    matched_message_file_paths = []
    other_file_paths = []

    for item_path in all_item_paths_in_dir:
        if item_path.is_file():
            if filename_pattern.match(item_path.name):
                matched_message_file_paths.append(item_path)
            else:
                other_file_paths.append(item_path)

    # Sort matched message files by name (chronologically due to timestamp prefix)
    matched_message_file_paths.sort(key=lambda p: p.name)

    for msg_file_path in matched_message_file_paths:
        # At this point, msg_file_path.name is guaranteed to match filename_pattern.
        match = filename_pattern.match(msg_file_path.name)

        # Default role from filename; 'unknown' if match object is unexpectedly None (defensive).
        # Given the filtering above, match should always be a valid match object.
        role_from_filename = "unknown"
        if match:
            role_from_filename = match.group(1).lower()

        current_role_for_display = role_from_filename

        try:
            content = msg_file_path.read_text(encoding="utf-8")
            escaped_content = html.escape(content)
        except Exception as e:
            escaped_content = f"Error reading file: {html.escape(str(e))}"
            # If content can't be read, mimic original behavior by setting role to "unknown".
            current_role_for_display = "unknown"

        messages_html_parts.append(f"""
        <div class="message message-{current_role_for_display}">
            <div class="message-header">
                <span class="message-role">{html.escape(current_role_for_display)}</span>
                <span class="message-filename">{html.escape(msg_file_path.name)}</span>
            </div>
            <div>{escaped_content}</div>
        </div>
        """)

    if other_file_paths:
        other_file_paths.sort(key=lambda p: p.name)  # Sort for consistent display

        other_files_html_parts.append("<hr class='other-files-divider'>")
        other_files_html_parts.append("<h2>Other Files</h2>")
        other_files_html_parts.append("<ul>")

        PEEK_SIZE = 4096  # Max bytes to peek for binary check

        for other_file_path in other_file_paths:
            file_name_escaped = html.escape(other_file_path.name)
            file_content_display_html = ""

            try:
                # Attempt to determine if file is text or binary and read content
                is_likely_text_content = True
                # Read an initial chunk to check for binary indicators
                with open(other_file_path, "rb") as f:
                    chunk = f.read(PEEK_SIZE)

                if b"\0" in chunk:  # Null bytes are a strong indicator of a binary file
                    is_likely_text_content = False
                else:
                    try:
                        # Try to decode the chunk as UTF-8
                        chunk.decode("utf-8")
                    except UnicodeDecodeError:
                        # If chunk decoding fails, treat as not displayable text
                        is_likely_text_content = False

                if is_likely_text_content:
                    # If the chunk seems like text, try to read the full file as UTF-8 text.
                    # This might still fail or be slow for very large files.
                    try:
                        full_content = other_file_path.read_text(encoding="utf-8")
                        escaped_file_content = html.escape(full_content)
                        file_content_display_html = f"""
                        <div class="other-file-content">
                            <pre>{escaped_file_content}</pre>
                        </div>"""
                    except UnicodeDecodeError:  # Full file content is not valid UTF-8
                        is_likely_text_content = False  # Fallback to "not displayable"
                    except Exception:  # Other errors reading the full file (e.g. too large, rare FS issues)
                        # Log this specific error server-side ideally
                        is_likely_text_content = False  # Fallback to "not displayable"

                # If, after all checks, the file is not considered displayable as text
                if not is_likely_text_content:
                    file_content_display_html = """
                    <div class="other-file-content other-file-content-binary">
                        [File content not displayed: likely binary, not UTF-8, or read error.]
                    </div>"""

            except (
                Exception
            ) as e:  # Catch errors from initial open/read (e.g. permission denied)
                print(
                    f"Error processing other file {other_file_path}: {e}",
                    file=sys.stderr,
                )
                file_content_display_html = f"""
                <div class="other-file-content other-file-content-binary">
                    [Error accessing file: {html.escape(str(e))}]
                </div>"""

            other_files_html_parts.append(f"""
            <li class="other-file-entry">
                <strong>{file_name_escaped}</strong>
                {file_content_display_html}
            </li>
            """)
        other_files_html_parts.append("</ul>")

    # Construct final page content
    page_elements = []
    final_messages_html_str = "".join(messages_html_parts)
    final_other_files_html_str = "".join(other_files_html_parts)

    if final_messages_html_str:
        page_elements.append(final_messages_html_str)
    else:
        # Show "No messages" if there are no matched messages.
        # Other files, if any, will still be listed after this.
        page_elements.append("<p>No messages found in this conversation.</p>")

    # Add the "Other Files" section if it has content
    if final_other_files_html_str:
        page_elements.append(final_other_files_html_str)

    content_html = "".join(page_elements)

    return f"""
    <html>
        <head>
            <title>Conversation: {html.escape(conversation_id)}</title>
            <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🐙</text></svg>">
            <style>{COMMON_STYLES}</style>
        </head>
        <body>
            <div class="container">
                <a href="/" class="back-link">&larr; Back to Conversations List</a>
                <h1>Conversation: {html.escape(conversation_id)}</h1>
                {content_html}
            </div>
        </body>
    </html>
    """


if __name__ == "__main__":
    # Run the application directly using Uvicorn when main.py is executed.
    # This allows `python main.py` to start the server.
    # The host "127.0.0.1" makes it accessible locally, same as the previous Uvicorn instructions.
    # Reload=True is convenient for development as it restarts the server on code changes.
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
