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

    messages_html = []
    # Regex to extract role: e.g., 1234567890123-user.md
    # It also captures 'assistant-reasoning' correctly.
    filename_pattern = re.compile(
        r"^\d+-(system|user|assistant|assistant-reasoning)\.md$", re.IGNORECASE
    )

    try:
        # Sort files by name, which includes the timestamp prefix, ensuring chronological order.
        message_files = sorted(
            f for f in conv_path.iterdir() if f.is_file() and f.name.endswith(".md")
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading messages in conversation '{conversation_id}': {str(e)}",
        )

    for msg_file in message_files:
        match = filename_pattern.match(msg_file.name)
        role = "unknown"
        if match:
            role = match.group(
                1
            ).lower()  # system, user, assistant, assistant-reasoning

        try:
            content = msg_file.read_text(encoding="utf-8")
            escaped_content = html.escape(content)
        except Exception as e:
            escaped_content = f"Error reading file: {html.escape(str(e))}"
            role = "unknown"  # Mark as unknown if content can't be read

        messages_html.append(f"""
        <div class="message message-{role}">
            <div class="message-header">
                <span class="message-role">{html.escape(role)}</span>
                <span class="message-filename">{html.escape(msg_file.name)}</span>
            </div>
            <div>{escaped_content}</div>
        </div>
        """)

    return f"""
    <html>
        <head>
            <title>Conversation: {html.escape(conversation_id)}</title>
            <style>{COMMON_STYLES}</style>
        </head>
        <body>
            <div class="container">
                <a href="/" class="back-link">&larr; Back to Conversations List</a>
                <h1>Conversation: {html.escape(conversation_id)}</h1>
                {"".join(messages_html) if messages_html else "<p>No messages found in this conversation.</p>"}
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
