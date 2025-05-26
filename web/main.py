import os
import sys
import re
from pathlib import Path
from typing import List
import html

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
body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; color: #333; }
h1, h2 { color: #333; }
a { color: #007bff; text-decoration: none; }
a:hover { text-decoration: underline; }
.container { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
ul { list-style-type: none; padding: 0; }
li { margin-bottom: 10px; }
.message { 
    border: 1px solid #ddd; 
    margin-bottom: 15px; 
    padding: 15px; 
    border-radius: 8px; 
    word-wrap: break-word; 
    white-space: pre-wrap; /* Preserve whitespace and newlines */
}
.message-header { 
    font-weight: bold; 
    margin-bottom: 8px; 
    font-size: 0.9em; 
    color: #555; 
    display: flex;
    justify-content: space-between;
}
.message-role { text-transform: capitalize; }
.message-filename { font-style: italic; color: #777; }

.message-system { background-color: #e9ecef; border-left: 5px solid #6c757d; }
.message-user { background-color: #e0f7fa; border-left: 5px solid #007bff; }
.message-assistant { background-color: #e8f5e9; border-left: 5px solid #28a745; }
.message-assistant-reasoning { 
    background-color: #fffde7; 
    border-left: 5px solid #ffc107; 
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9em;
}
.message-unknown { background-color: #f8f9fa; border-left: 5px solid #adb5bd; }
.back-link { display: inline-block; margin-bottom: 20px; }
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
            <title>HNT Chat Conversations</title>
            <style>{COMMON_STYLES}</style>
        </head>
        <body>
            <div class="container">
                <h1>HNT Chat Conversations</h1>
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


# To run this application:
# 1. Make sure FastAPI and Uvicorn are installed:
#    pip install fastapi uvicorn
# 2. Navigate to the directory containing the 'web' folder (i.e., your project root).
# 3. Run Uvicorn:
#    python -m uvicorn web.main:app --reload
#    (Or if your current directory is `web`: `python -m uvicorn main:app --reload`)
# 4. Open your browser to http://127.0.0.1:8000
