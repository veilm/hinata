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
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import uvicorn
import time
import shutil

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()


# Pydantic model for title update requests
class TitleUpdateRequest(BaseModel):
    title: str


# Pydantic model for model update requests
class ModelUpdateRequest(BaseModel):
    model: str


# Pydantic model for adding new messages
class MessageAddRequest(BaseModel):
    role: str
    content: str


# Pydantic model for updating message content
class MessageContentUpdateRequest(BaseModel):
    content: str


DEFAULT_MODEL_NAME = "openrouter/deepseek/deepseek-chat-v3-0324:free"


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

    # Read conversation model
    model = DEFAULT_MODEL_NAME  # Default model
    model_file_path = conv_path / "model.txt"
    try:
        if model_file_path.is_file():
            model_content = model_file_path.read_text(encoding="utf-8").strip()
            if model_content:
                model = model_content
    except Exception as e:
        # Log error reading model, but proceed with default
        print(
            f"Error reading model.txt for conversation {conversation_id}: {e}",
            file=sys.stderr,
        )
        # model remains DEFAULT_MODEL_NAME

    return {
        "conversation_id": conversation_id,
        "title": title,
        "model": model,
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


# API endpoint to update a conversation's model
@app.put("/api/conversation/{conversation_id}/model")
async def update_conversation_model(conversation_id: str, request: ModelUpdateRequest):
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

    model_file_path = conv_path / "model.txt"
    new_model_requested = request.model.strip()

    # If the stripped model string is empty, use the default model name
    effective_model_to_save = (
        new_model_requested if new_model_requested else DEFAULT_MODEL_NAME
    )

    try:
        model_file_path.write_text(effective_model_to_save, encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error writing model.txt for conversation '{conversation_id}': {str(e)}",
        )

    return JSONResponse(
        content={
            "message": "Model updated successfully",
            "new_model": effective_model_to_save,
        },
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


# API endpoint to create a new conversation
@app.post("/api/conversations/create", status_code=status.HTTP_201_CREATED)
async def api_create_conversation():
    try:
        # Assuming `hnt-chat` is in PATH. Pass the current environment.
        process = subprocess.run(
            ["hnt-chat", "new"],
            capture_output=True,
            text=True,
            check=False,  # We handle non-zero exit codes manually
            env=os.environ.copy(),
        )

        if process.returncode == 0:
            # `hnt-chat new` outputs the full path to the new conversation directory.
            full_conversation_path_str = process.stdout.strip()
            if not full_conversation_path_str:
                # This case should ideally not happen if hnt-chat new works correctly
                error_detail = "Failed to create conversation: `hnt-chat new` did not return a path."
                print(
                    f"Error in api_create_conversation: {error_detail}", file=sys.stderr
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_detail,
                )

            # Extract just the final directory name (the ID) from the path
            new_conversation_id = Path(full_conversation_path_str).name

            return {
                "message": "Conversation created successfully.",
                "conversation_id": new_conversation_id,  # This is the directory name
            }
        else:
            error_detail = f"Failed to create conversation. `hnt-chat new` exited with code {process.returncode}."
            if process.stderr:
                error_detail += f" Stderr: {process.stderr.strip()}"
            print(f"Error in api_create_conversation: {error_detail}", file=sys.stderr)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )

    except FileNotFoundError:
        error_msg = "`hnt-chat` command not found. Please ensure it is installed and in the system PATH."
        print(f"Error in api_create_conversation: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )
    except Exception as e:
        error_msg = f"An unexpected error occurred while trying to create conversation: {str(e)}"
        print(f"Error in api_create_conversation: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@app.post(
    "/api/conversation/{conversation_id}/add-message",
    status_code=status.HTTP_201_CREATED,
)
async def api_add_message_to_conversation(
    conversation_id: str, request: MessageAddRequest
):
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

    if request.role not in ["user", "system", "assistant"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role specified. Must be 'user', 'system', or 'assistant'.",
        )

    try:
        cmd = [
            "hnt-chat",
            "add",
            request.role,
            "--conversation",
            str(conv_path.resolve()),
        ]

        process = subprocess.run(
            cmd,
            input=request.content,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )

        if process.returncode == 0:
            new_filename = process.stdout.strip()
            return {"message": "Message added successfully.", "filename": new_filename}
        else:
            error_detail = f"Failed to add message. `hnt-chat add` exited with code {process.returncode}."
            if process.stderr:
                error_detail += f" Stderr: {process.stderr.strip()}"
            print(
                f"Error in api_add_message_to_conversation: {error_detail}",
                file=sys.stderr,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )

    except FileNotFoundError:
        error_msg = "`hnt-chat` command not found. Please ensure it is installed and in the system PATH."
        print(f"Error in api_add_message_to_conversation: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )
    except Exception as e:
        error_msg = f"An unexpected error occurred while adding message: {str(e)}"
        print(f"Error in api_add_message_to_conversation: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@app.post(
    "/api/conversation/{conversation_id}/gen-assistant",
    status_code=status.HTTP_201_CREATED,
)
async def api_gen_assistant_message(conversation_id: str):
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

    model_file_path = conv_path / "model.txt"
    model_to_use = DEFAULT_MODEL_NAME

    try:
        if model_file_path.is_file():
            model_content = model_file_path.read_text(encoding="utf-8").strip()
            if model_content:
                model_to_use = model_content
    except Exception as e:
        print(
            f"Warning: Error reading model.txt for conversation {conversation_id}, using default model '{model_to_use}': {e}",
            file=sys.stderr,
        )

    try:
        cmd = [
            "hnt-chat",
            "gen",
            "--merge",
            "--separate-reasoning",
            "--model",
            model_to_use,
            "--conversation",
            str(conv_path.resolve()),
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )

        if process.returncode == 0:
            return {"message": "Assistant message generated successfully."}
        else:
            error_detail = f"Failed to generate assistant message. `hnt-chat gen` exited with code {process.returncode}."
            if process.stderr:
                error_detail += f" Stderr: {process.stderr.strip()}"
            if process.stdout and process.returncode != 0:
                error_detail += f" Stdout: {process.stdout.strip()}"

            print(
                f"Error in api_gen_assistant_message: {error_detail}", file=sys.stderr
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )

    except FileNotFoundError:
        error_msg = "`hnt-chat` command not found. Please ensure it is installed and in the system PATH."
        print(f"Error in api_gen_assistant_message: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )
    except Exception as e:
        error_msg = (
            f"An unexpected error occurred while generating assistant message: {str(e)}"
        )
        print(f"Error in api_gen_assistant_message: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


# Endpoint to archive a message
@app.post(
    "/api/conversation/{conversation_id}/message/{filename}/archive",
    status_code=status.HTTP_200_OK,
)
async def api_archive_message(conversation_id: str, filename: str):
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

    message_file_path = conv_path / filename
    if not message_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message file '{filename}' not found in conversation '{conversation_id}'.",
        )

    try:
        # Generate archived filename
        archived_filename = f"{int(time.time())}-archived-{filename}"
        archived_file_path = message_file_path.parent / archived_filename

        # Perform the move/rename operation
        message_file_path.rename(archived_file_path)

        return {
            "message": "Message archived successfully.",
            "archived_filename": archived_filename,
        }
    except Exception as e:
        error_msg = f"Error archiving message '{filename}': {str(e)}"
        print(f"Error in api_archive_message: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        )


# Endpoint to edit a message
@app.put(
    "/api/conversation/{conversation_id}/message/{filename}/edit",
    status_code=status.HTTP_200_OK,
)
async def api_edit_message(
    conversation_id: str, filename: str, request: MessageContentUpdateRequest
):
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

    message_file_path = conv_path / filename
    if not message_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message file '{filename}' not found in conversation '{conversation_id}'.",
        )

    try:
        # 1. Copy the current version to an archive file
        archived_filename = f"{int(time.time())}-archived-{filename}"
        archived_file_path = message_file_path.parent / archived_filename
        shutil.copy2(str(message_file_path), str(archived_file_path))

        # 2. Overwrite the original file with new content
        message_file_path.write_text(request.content, encoding="utf-8")

        return {
            "message": "Message updated successfully.",
            "filename": filename,
            "new_content": request.content,
            "archived_as": archived_filename,
        }
    except Exception as e:
        error_msg = f"Error editing message '{filename}': {str(e)}"
        print(f"Error in api_edit_message: {error_msg}", file=sys.stderr)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        )


@app.post(
    "/api/conversation/{conversation_id}/fork", status_code=status.HTTP_201_CREATED
)
async def api_fork_conversation(conversation_id: str):
    try:
        conv_base_dir = get_conversations_dir()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    source_conv_path = conv_base_dir / conversation_id
    if not source_conv_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source conversation '{conversation_id}' not found for forking.",
        )

    # 1. Create a new conversation (B) using hnt-chat new
    new_conversation_id = None
    new_conv_path = None
    try:
        process = subprocess.run(
            ["hnt-chat", "new"],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        if process.returncode != 0:
            error_detail = f"Failed to create new conversation base for fork. `hnt-chat new` exited with code {process.returncode}."
            if process.stderr:
                error_detail += f" Stderr: {process.stderr.strip()}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail
            )

        new_conv_full_path_str = process.stdout.strip()
        if not new_conv_full_path_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="`hnt-chat new` did not return a path for the forked conversation.",
            )
        new_conv_path = Path(new_conv_full_path_str)
        new_conversation_id = new_conv_path.name

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="`hnt-chat` command not found during fork. Please ensure it is installed and in PATH.",
        )
    except Exception as e:  # Catch other subprocess or path errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred creating new conversation base for fork: {str(e)}",
        )

    # 2. Copy every file in the A directory to B's directory
    try:
        for item in source_conv_path.iterdir():
            if item.is_file():
                shutil.copy2(item, new_conv_path / item.name)
    except Exception as e:
        # If copying fails, it's a critical error for the fork.
        # Consider cleanup of new_conv_path if it should be atomic, but for now, error out.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to copy files during fork from '{conversation_id}' to '{new_conversation_id}': {str(e)}",
        )

    # 3. Modify B's title.txt
    title_file_path_in_b = new_conv_path / "title.txt"
    effective_title_from_a = "-"  # Default if title.txt wasn't copied or was empty

    if title_file_path_in_b.is_file():
        try:
            title_content_from_a = title_file_path_in_b.read_text(
                encoding="utf-8"
            ).strip()
            if title_content_from_a:
                effective_title_from_a = title_content_from_a
        except Exception as e:
            print(
                f"Fork: Error reading title.txt from newly copied {title_file_path_in_b}, defaulting to '-': {e}",
                file=sys.stderr,
            )
            # effective_title_from_a remains "-"

    match = re.match(r"^(.*)-(\d+)$", effective_title_from_a)
    if match:
        base_title_part = match.group(1)
        numeric_suffix_part = match.group(2)
        # Ensure base_title_part is not empty if effective_title_from_a was like "-1"
        # If base_title_part is "" (e.g. title was "-1"), new title will be "-2". This is fine.
        forked_title_str = f"{base_title_part}-{int(numeric_suffix_part) + 1}"
    else:
        forked_title_str = f"{effective_title_from_a}-0"

    try:
        title_file_path_in_b.write_text(forked_title_str, encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fork: Error writing new title to {title_file_path_in_b}: {str(e)}",
        )

    return {
        "message": "Conversation forked successfully.",
        "new_conversation_id": new_conversation_id,
    }


if __name__ == "__main__":
    # Run the application directly using Uvicorn when hnt-web.py is executed.
    # Reload=True is convenient for development.
    # Pass the app object directly to Uvicorn to avoid module import issues,
    # especially when the script is run from a location like /usr/local/bin.
    # uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)

    # uvicorn.run(app, host="127.0.0.1", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=2027)
