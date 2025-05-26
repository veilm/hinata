#!/usr/bin/env -S uv run --script

# /// script
# name = "hnt-web"
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
from typing import List, Dict, Any
import uvicorn

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()


# Pydantic model for title update requests
class TitleUpdateRequest(BaseModel):
    title: str


# Function to determine the XDG_DATA_HOME based directory for web assets
def get_web_data_dir() -> Path:
    """
    Determines the base directory for web assets.
    Uses $XDG_DATA_HOME/hinata/web, defaulting to
    $HOME/.local/share/hinata/web if $XDG_DATA_HOME is not set.
    Raises HTTPException if the directory cannot be confirmed.
    """
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        base_data_dir = Path(xdg_data_home)
    else:
        home_dir = Path.home()
        if not home_dir:
            raise HTTPException(
                status_code=500, detail="Could not determine home directory."
            )
        base_data_dir = home_dir / ".local" / "share"

    web_dir = base_data_dir / "hinata" / "web"

    # The build script is responsible for creating this directory and populating it.
    # hnt-web.py will assume it exists and is readable.
    if not web_dir.is_dir():
        # This error indicates a potential issue with deployment or setup.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Web data directory not found or is not a directory: {web_dir}. "
                "Please ensure build.sh has been run successfully."
            ),
        )
    return web_dir


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


# API endpoint to list conversations
@app.get("/api/conversations")
async def api_list_conversations() -> Dict[str, List[Dict[str, str]]]:
    conv_data_list = []
    try:
        conv_base_dir = get_conversations_dir()
        conversation_dirs = sorted(
            [d for d in conv_base_dir.iterdir() if d.is_dir()],
            key=lambda p: p.name,
            reverse=True,  # Show newest first based on ID
        )

        for conv_dir in conversation_dirs:
            conv_id = conv_dir.name
            title_file = conv_dir / "title.txt"
            title = "-"

            try:
                if title_file.is_file():
                    title_content = title_file.read_text(encoding="utf-8").strip()
                    if title_content:
                        title = title_content
                    else:  # File exists but is empty or whitespace
                        title_file.write_text("-", encoding="utf-8")
                        title = "-"
                else:  # File does not exist
                    title_file.write_text("-", encoding="utf-8")
                    title = "-"
            except Exception as e:
                # Log error reading/writing title.txt, but proceed with default title
                print(f"Error processing title for {conv_id}: {e}", file=sys.stderr)
                title = "-"  # Fallback title

            conv_data_list.append({"id": conv_id, "title": title})

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error listing conversations: {str(e)}"
        )
    return {"conversations": conv_data_list}


# API endpoint to read a specific conversation
@app.get("/api/conversation/{conversation_id}")
async def api_read_conversation(conversation_id: str) -> Dict[str, Any]:
    try:
        conv_base_dir = get_conversations_dir()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    conv_path = conv_base_dir / conversation_id

    if not conv_path.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Conversation '{conversation_id}' not found."
        )

    messages_data: List[Dict[str, str]] = []
    other_files_data: List[Dict[str, Any]] = []

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

    matched_message_file_paths.sort(key=lambda p: p.name)

    for msg_file_path in matched_message_file_paths:
        match = filename_pattern.match(msg_file_path.name)
        role = "unknown"
        if match:
            role = match.group(1).lower()

        content_text = ""
        try:
            content_text = msg_file_path.read_text(encoding="utf-8")
        except Exception as e:
            content_text = f"Error reading file: {str(e)}"
            role = "unknown"  # Fallback role if content is unreadable

        messages_data.append(
            {"role": role, "filename": msg_file_path.name, "content": content_text}
        )

    if other_file_paths:
        other_file_paths.sort(key=lambda p: p.name)
        PEEK_SIZE = 4096

        for other_file_path in other_file_paths:
            file_data: Dict[str, Any] = {
                "filename": other_file_path.name,
                "is_text": False,
                "content": None,
                "error_message": None,
            }

            try:
                is_likely_text_content = True
                with open(other_file_path, "rb") as f:
                    chunk = f.read(PEEK_SIZE)

                if b"\0" in chunk:
                    is_likely_text_content = False
                    file_data["error_message"] = (
                        "[File content not displayed: likely binary]"
                    )
                else:
                    try:
                        chunk.decode("utf-8")  # Check if initial chunk is decodable
                        # Try to read full content if chunk decodes
                        try:
                            full_content = other_file_path.read_text(encoding="utf-8")
                            file_data["is_text"] = True
                            file_data["content"] = full_content
                        except UnicodeDecodeError:
                            is_likely_text_content = False
                            file_data["error_message"] = (
                                "[File content not displayed: not valid UTF-8]"
                            )
                        except Exception as read_err:  # Handle other read errors like file too large etc.
                            is_likely_text_content = False
                            file_data["error_message"] = (
                                f"[File content not displayed: error reading full file - {str(read_err)}]"
                            )

                    except UnicodeDecodeError:
                        is_likely_text_content = False
                        file_data["error_message"] = (
                            "[File content not displayed: initial chunk not UTF-8]"
                        )

                if not is_likely_text_content and not file_data["error_message"]:
                    # Generic fallback if not marked as text and no specific error yet
                    file_data["error_message"] = (
                        "[File content not displayed: format not recognized as text]"
                    )

            except Exception as e:
                file_data["error_message"] = f"[Error accessing file: {str(e)}]"
                print(  # Log server-side for debugging
                    f"Error processing other file {other_file_path}: {e}",
                    file=sys.stderr,
                )

            other_files_data.append(file_data)

    # Read conversation title
    title = "-"  # Default title
    title_file_path = conv_path / "title.txt"
    try:
        if title_file_path.is_file():
            title_content = title_file_path.read_text(encoding="utf-8").strip()
            if title_content:
                title = title_content
    except Exception as e:
        # Log error reading title, but proceed with default
        print(
            f"Error reading title for conversation {conversation_id}: {e}",
            file=sys.stderr,
        )
        # title remains "-"

    return {
        "conversation_id": conversation_id,
        "title": title,
        "messages": messages_data,
        "other_files": other_files_data,
    }


# API endpoint to update a conversation's title
@app.put("/api/conversation/{conversation_id}/title")
async def update_conversation_title(conversation_id: str, request: TitleUpdateRequest):
    try:
        conv_base_dir = get_conversations_dir()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    conv_path = conv_base_dir / conversation_id
    if not conv_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found.",
        )

    title_file_path = conv_path / "title.txt"
    new_title = request.title.strip()
    if not new_title:  # If stripping results in an empty string, save as "-"
        new_title = "-"

    try:
        title_file_path.write_text(new_title, encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error writing title for conversation '{conversation_id}': {str(e)}",
        )

    return JSONResponse(
        content={"message": "Title updated successfully", "new_title": new_title},
        status_code=status.HTTP_200_OK,
    )


# Setup static file serving after API routes are defined
try:
    WEB_DATA_DIR = get_web_data_dir()

    # Serve CSS files
    app.mount("/css", StaticFiles(directory=WEB_DATA_DIR / "css"), name="css")
    # Serve JavaScript files
    app.mount("/js", StaticFiles(directory=WEB_DATA_DIR / "js"), name="js")

    # Serve index.html for the root path
    @app.get("/", response_class=FileResponse)
    async def serve_index():
        return FileResponse(WEB_DATA_DIR / "index.html")

    # Serve conversation.html for specific conversation view paths
    @app.get(
        "/conversation-page/{conversation_id_path:path}", response_class=FileResponse
    )
    async def serve_conversation_page(conversation_id_path: str):
        # conversation_id_path is used by FastAPI for routing,
        # but the actual file served is always conversation.html.
        # JavaScript on the client side will use the path to fetch specific data.
        return FileResponse(WEB_DATA_DIR / "conversation.html")

except HTTPException as e:
    # If get_web_data_dir() raises an HTTPException (e.g. dir not found),
    # FastAPI won't start correctly if we try to mount StaticFiles.
    # We can't easily add a startup error page here without more complex setup.
    # This print will at least show an error during startup if run directly.
    print(f"FATAL STARTUP ERROR: {e.detail}", file=sys.stderr)

    # Optionally, re-raise or sys.exit(1) if running in a context where that helps.
    # For uvicorn, it might shut down if app setup fails badly.
    # Adding dummy routes to let it start and show error via HTTP might be an option:
    @app.get("/")
    @app.get("/{path:path}")
    async def startup_error_page():
        raise e  # Re-raise the caught HTTPException


if __name__ == "__main__":
    # Run the application directly using Uvicorn when hnt-web.py is executed.
    # Reload=True is convenient for development.
    # Pass the app object directly to Uvicorn to avoid module import issues,
    # especially when the script is run from a location like /usr/local/bin.
    # uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)

    uvicorn.run(app, host="127.0.0.1", port=8000)
