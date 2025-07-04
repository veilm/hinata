#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import tempfile
import io
import shlex
import shutil
import textwrap
from pathlib import Path
import atexit


# Command to pipe output through for syntax highlighting
SYNTAX_HIGHLIGHT_PIPE_CMD = ["hlmd-st"]

# more complex but feature-rich alternative
# https://github.com/kristopolous/Streamdown

# don't use. doesn't buffer
# SYNTAX_HIGHLIGHT_PIPE_CMD = ["rich", "-m", "-"]

# ANSI color codes for editor message display
USER_MESSAGE_COLOR = "\033[94m"  # Light Blue
RESET_COLOR = "\033[0m"

# Unicode characters for editor message borders
U_HORIZ_LINE = "─"


def run_command(cmd, stdin_content=None, capture_output=True, check=True, text=True):
    """Helper function to run a command."""
    try:
        process = subprocess.run(
            cmd,
            input=stdin_content,
            capture_output=capture_output,
            check=check,
            text=text,
        )
        return process
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(
            f"Error: Command '{' '.join(cmd)}' failed with exit code {e.returncode}",
            file=sys.stderr,
        )
        if e.stderr:
            print(f"Stderr:\n{e.stderr}", file=sys.stderr)
        if e.stdout:
            print(f"Stdout:\n{e.stdout}", file=sys.stderr)
        sys.exit(e.returncode)
    except Exception as e:
        print(
            f"An unexpected error occurred while running {' '.join(cmd)}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def get_user_instruction(message_arg):
    """Gets the user instruction either from args or by launching EDITOR."""
    if message_arg:
        return message_arg

    editor = os.environ.get("EDITOR", "vi")
    initial_text = """Replace this text with your instructions. Then write to this file and exit your
text editor. Leave the file unchanged or empty to abort."""

    try:
        with tempfile.NamedTemporaryFile(
            mode="w+", prefix="hnt-edit-", suffix=".md", delete=False
        ) as tmpfile:
            tmpfile.write(initial_text)
            tmpfile.flush()
            tmp_path = tmpfile.name

        # Construct the editor command.
        # shlex.split() handles editors with arguments like "code -w".
        editor_parts = shlex.split(editor)

        # Check if tui-pane should be used to spawn the editor.
        use_tui_pane = os.environ.get("HINATA_USE_TUI_PANE")
        tui_pane_path = shutil.which("tui-pane")

        if use_tui_pane and tui_pane_path:
            # Prepend tui-pane to the editor command.
            command_to_run = [tui_pane_path] + editor_parts + [tmp_path]
        else:
            command_to_run = editor_parts + [tmp_path]

        # Run the editor - use run instead of Popen to wait for it
        run_command(command_to_run, capture_output=False, check=True)

        # Read the content after editor exits
        with open(tmp_path, "r") as f:
            instruction = f.read().strip()

        # Clean up the temp file
        os.unlink(tmp_path)

        # Remove any whitespace for checking empty/unchanged
        stripped_instruction = instruction.strip()
        if not stripped_instruction or stripped_instruction == initial_text.strip():
            print("Aborted: No changes were made.", file=sys.stderr)
            sys.exit(0)
        return instruction

    except Exception as e:
        print(f"Error getting user instruction via editor: {e}", file=sys.stderr)
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)  # Ensure cleanup on error
        sys.exit(1)


def get_system_message(system_arg):
    """Gets the system message either from args or default file."""
    if system_arg:
        # Check if it's a file path that exists
        if os.path.exists(system_arg):
            try:
                with open(system_arg, "r") as f:
                    return f.read()
            except IOError as e:
                print(f"Error reading system file {system_arg}: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Assume it's the literal system message string
            return system_arg
    else:
        # Default path
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        default_path = Path(config_home) / "hinata" / "prompts" / "main-file_edit.md"
        try:
            with open(default_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            print(
                f"Error: Default system file not found: {default_path}", file=sys.stderr
            )
            sys.exit(1)
        except IOError as e:
            print(
                f"Error reading default system file {default_path}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)


# --- Helper for Debug Logging ---
def debug_log(args, *print_args, **print_kwargs):
    """Prints debug messages to stderr if --debug-unsafe is enabled."""
    if args.debug_unsafe:
        print("[DEBUG]", *print_args, file=sys.stderr, **print_kwargs)


# --- atexit cleanup function ---
def cleanup_empty_created_files(created_files, args_obj):
    """
    Called at script exit to remove any files that were created by this script
    run and are still empty.
    """
    if not created_files:
        return

    # args_obj is the parsed arguments from main(), passed to allow debug logging.
    # debug_log itself checks args_obj.debug_unsafe.
    debug_log(
        args_obj,
        f"atexit: Running cleanup for {len(created_files)} initially created files.",
    )

    for file_path in created_files:
        try:
            if file_path.exists():
                if file_path.stat().st_size == 0:
                    debug_log(
                        args_obj,
                        f"atexit: Removing blank file originally created by script: {file_path}",
                    )
                    file_path.unlink()  # Remove the empty file
                else:
                    debug_log(
                        args_obj,
                        f"atexit: File originally created by script is not empty, retaining: {file_path}",
                    )
            else:
                # This case means the file was created by us, but then removed before cleanup
                # (e.g., by LLM explicitly, or user/another process).
                debug_log(
                    args_obj,
                    f"atexit: File originally created by script no longer exists, nothing to remove: {file_path}",
                )
        except Exception as e:
            # Fallback to direct print for errors during cleanup, as debug_log might itself fail or args_obj could be an issue.
            error_message = f"ERROR during atexit cleanup for {file_path}: {e}"
            if args_obj and hasattr(args_obj, "debug_unsafe") and args_obj.debug_unsafe:
                print(f"[DEBUG] {error_message}", file=sys.stderr)
                # Optionally, print full traceback in debug mode for cleanup errors
                # import traceback
                # traceback.print_exc(file=sys.stderr)
            else:
                # Always print critical errors from atexit to stderr
                print(error_message, file=sys.stderr)


def main():
    # --- Syntax Highlighting Check ---
    syntax_highlight_enabled = False
    effective_syntax_cmd = None  # This will hold the command list to execute

    # Check environment variable first
    env_cmd_str = os.environ.get("HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD")
    if env_cmd_str:
        try:
            # Parse the command string, respecting quotes and spaces
            effective_syntax_cmd = shlex.split(env_cmd_str)
            if effective_syntax_cmd:  # Ensure shlex.split didn't return empty list
                syntax_highlight_enabled = True
            else:
                print(
                    f"Warning: HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD is set but resulted in an empty command after parsing: '{env_cmd_str}'. Highlighting disabled.",
                    file=sys.stderr,
                )
                env_cmd_str = None  # Treat as if not set for fallback logic
        except ValueError as e:
            print(
                f"Warning: Could not parse HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD: '{env_cmd_str}'. Error: {e}. Highlighting disabled.",
                file=sys.stderr,
            )
            env_cmd_str = None  # Treat as if not set for fallback logic

    # If environment variable wasn't used or was invalid, try the default
    if not env_cmd_str and SYNTAX_HIGHLIGHT_PIPE_CMD:
        # Check if the default command exists in PATH
        highlighter_executable = shutil.which(SYNTAX_HIGHLIGHT_PIPE_CMD[0])
        if highlighter_executable:
            syntax_highlight_enabled = True
            # Use the default command, but update executable with full path
            effective_syntax_cmd = SYNTAX_HIGHLIGHT_PIPE_CMD[:]  # Make a copy
            effective_syntax_cmd[0] = highlighter_executable
            # No need to print info message if using default and found
        else:
            # Only print info if default command not found and env var wasn't used
            print(
                f"Info: Default syntax highlighter '{SYNTAX_HIGHLIGHT_PIPE_CMD[0]}' not found in PATH. Highlighting disabled.",
                file=sys.stderr,
            )
    # --- End Syntax Highlighting Check ---

    parser = argparse.ArgumentParser(
        description="Edit files using hinata LLM agent.",
        epilog="Example: hnt-edit -m 'Refactor foo function' src/main.py src/utils.py",
    )
    parser.add_argument(
        "-s",
        "--system",
        help="System message string or path to system message file. Defaults to $XDG_CONFIG_HOME/hinata/prompts/01-targetreplace.md",
    )
    parser.add_argument(
        "-m",
        "--message",
        help="User instruction message. If not provided, $EDITOR will be opened.",
    )
    parser.add_argument(
        "source_files",
        nargs="*",
        help="Source files to edit. Required if --continue-dir is not used.",
    )
    parser.add_argument("--model", help="Model to use (passed through to hnt-llm)")
    parser.add_argument(
        "--continue-dir",
        metavar="CHAT_DIR",
        help="Path to an existing hnt-chat conversation directory to continue from a failed edit.",
    )
    parser.add_argument(
        "--debug-unsafe",
        action="store_true",
        help="Enable unsafe debugging options in hnt-llm",
    )
    parser.add_argument(
        "--ignore-reasoning",
        action="store_true",
        help="Do not ask the LLM for reasoning. Also checks $HINATA_EDIT_IGNORE_REASONING.",
    )
    args = parser.parse_args()

    if os.environ.get("HINATA_EDIT_IGNORE_REASONING"):
        args.ignore_reasoning = True

    # If --continue-dir is not used, source_files are required.
    if not args.continue_dir and not args.source_files:
        parser.error("source_files are required when not using --continue-dir")

    debug_log(args, "Arguments parsed:", args)

    conversation_dir = None  # Will be set by new or continue logic

    if args.continue_dir:
        # --- CONTINUATION MODE ---
        print(f"Continuing conversation from: {args.continue_dir}", file=sys.stderr)
        debug_log(args, f"Continue mode: Using directory {args.continue_dir}")
        conversation_dir = Path(args.continue_dir).resolve()  # Ensure absolute path
        if not conversation_dir.is_dir():
            print(
                f"Error: Continue directory not found: {conversation_dir}",
                file=sys.stderr,
            )
            sys.exit(1)

        # 1. Read absolute_file_paths.txt
        abs_paths_file = conversation_dir / "absolute_file_paths.txt"
        debug_log(args, f"Reading absolute paths from {abs_paths_file}...")
        source_files_from_abs_paths = []
        try:
            with open(abs_paths_file, "r") as f:
                source_files_from_abs_paths = [
                    line.strip() for line in f if line.strip()
                ]
            if not source_files_from_abs_paths:
                print(
                    f"Error: No file paths found in {abs_paths_file}", file=sys.stderr
                )
                sys.exit(1)
            debug_log(
                args,
                "Source files for continuation (absolute paths):",
                source_files_from_abs_paths,
            )
        except FileNotFoundError:
            print(
                f"Error: {abs_paths_file} not found in continue directory.",
                file=sys.stderr,
            )
            sys.exit(1)
        except IOError as e:
            print(f"Error reading {abs_paths_file}: {e}", file=sys.stderr)
            sys.exit(1)

        # Update args.source_files for hnt-apply later.
        # These are absolute paths, which hnt-apply should handle.
        args.source_files = source_files_from_abs_paths

        # 2. Locate source_reference.txt and read it
        source_ref_txt_path = conversation_dir / "source_reference.txt"
        debug_log(
            args,
            f"Reading source reference chat file path from {source_ref_txt_path}...",
        )
        target_source_ref_file_path_in_chat = None
        try:
            with open(source_ref_txt_path, "r") as f:
                source_ref_chat_filename_relative = f.read().strip()
            if not source_ref_chat_filename_relative:
                print(
                    f"Error: No filename found in {source_ref_txt_path}",
                    file=sys.stderr,
                )
                sys.exit(1)

            # The filename from source_reference.txt is the name of the message file
            # containing the source reference.
            # Standard hnt-chat places this in a 'messages/' subdirectory.
            # Fallback to checking the root of the conversation directory for compatibility.

            path_in_messages_subdir = (
                conversation_dir / "messages" / source_ref_chat_filename_relative
            )
            path_in_root_dir = conversation_dir / source_ref_chat_filename_relative

            target_source_ref_file_path_in_chat = None  # Initialize
            if path_in_messages_subdir.exists():
                target_source_ref_file_path_in_chat = path_in_messages_subdir
                debug_log(
                    args,
                    "Target source reference message file (standard location):",
                    target_source_ref_file_path_in_chat,
                )
            elif path_in_root_dir.exists():
                target_source_ref_file_path_in_chat = path_in_root_dir
                debug_log(
                    args,
                    "Target source reference message file (fallback location - root dir):",
                    target_source_ref_file_path_in_chat,
                )
            else:
                # If neither exists, report error showing checked paths.
                print(
                    f"Error: Source reference message file '{source_ref_chat_filename_relative}' not found in "
                    f"'{conversation_dir / 'messages'}' or in '{conversation_dir}'.\n"
                    f"Checked paths:\n1. {path_in_messages_subdir}\n2. {path_in_root_dir}",
                    file=sys.stderr,
                )
                sys.exit(1)

            # At this point, target_source_ref_file_path_in_chat is set and verified to exist.
            # Additional debug log for the successfully found path if not already covered by above.
            if not (
                path_in_messages_subdir.exists() or path_in_root_dir.exists()
            ):  # Should not happen due to sys.exit above
                debug_log(
                    args,
                    "Target source reference message file (final verification):",
                    target_source_ref_file_path_in_chat,
                )
        except FileNotFoundError:
            print(f"Error: {source_ref_txt_path} not found.", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error reading {source_ref_txt_path}: {e}", file=sys.stderr)
            sys.exit(1)

        # 3. Recreate llm-pack output and update the source_reference chat file
        debug_log(args, "Re-running llm-pack for continuation...")
        # args.source_files now contains absolute paths from absolute_file_paths.txt
        llm_pack_cmd_cont = ["llm-pack", "-s"] + args.source_files
        debug_log(args, "llm-pack command (continuation):", llm_pack_cmd_cont)
        llm_pack_result_cont = run_command(
            llm_pack_cmd_cont, capture_output=True, check=True, text=True
        )
        packed_sources_cont = llm_pack_result_cont.stdout
        debug_log(
            args, "llm-pack (continuation) output length:", len(packed_sources_cont)
        )

        new_source_reference_content = (
            f"<source_reference>\n{packed_sources_cont}</source_reference>\n"
        )
        debug_log(
            args,
            f"Overwriting {target_source_ref_file_path_in_chat} with new source reference...",
        )
        try:
            with open(target_source_ref_file_path_in_chat, "w") as f:
                f.write(new_source_reference_content)
            debug_log(args, "Successfully updated source reference message file.")
        except IOError as e:
            print(
                f"Error writing updated source reference to {target_source_ref_file_path_in_chat}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        # File Creation and Tracking: In continue mode, we don't initially create files from CLI args.
        # The atexit hook will clean up any *new* files created empty by this run if they were tracked.
        # For now, we assume existing files specified by absolute_file_paths are not "created this run" for cleanup.
        created_files_this_run = []
        atexit.register(cleanup_empty_created_files, created_files_this_run, args)
    else:
        # --- NORMAL (NEW CONVERSATION) MODE ---
        # args.source_files are relative paths from CLI.

        # --- File Creation and Tracking ---
        created_files_this_run = []
        # args.source_files contains strings. We'll process them.
        # The original args.source_files (list of strings) will be passed to hnt-pack etc.

        source_file_paths_for_checking = [Path(f) for f in args.source_files]

        for file_path_obj in source_file_paths_for_checking:
            if not file_path_obj.exists():
                if not file_path_obj.parent.is_dir():
                    print(
                        f"Error: Parent directory for new file '{file_path_obj}' must exist.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                try:
                    file_path_obj.touch()  # Create the file empty
                    debug_log(args, f"Created missing file: {file_path_obj}")
                    created_files_this_run.append(file_path_obj)  # Track it for cleanup
                except OSError as e:
                    print(
                        f"Error: Could not create file {file_path_obj}: {e}",
                        file=sys.stderr,
                    )
                    sys.exit(
                        1
                    )  # Critical error, cannot proceed if a specified file can't be created

        # Register the cleanup function to be called at script exit.
        # This passes the list of files we created and the args object (for debug logging).
        atexit.register(cleanup_empty_created_files, created_files_this_run, args)
        # --- End File Creation and Tracking ---

        # 1. Get system message
        debug_log(args, "Getting system message...")
        system_message = get_system_message(args.system)
        debug_log(args, "System message source:", args.system or "default path")
        # Log first few lines for brevity
        debug_log(
            args,
            "System message content (first 100 chars):\n",
            textwrap.shorten(system_message, width=100, placeholder="..."),
        )

        # 2. Get user instruction
        debug_log(args, "Getting user instruction...")
        instruction = get_user_instruction(args.message)
        debug_log(
            args,
            "User instruction source:",
            "args.message" if args.message else "$EDITOR",
        )
        debug_log(
            args,
            "User instruction content (first 100 chars):\n",
            textwrap.shorten(instruction, width=100, placeholder="..."),
        )

        # 3. Run llm-pack
        debug_log(args, "Running llm-pack...")
        llm_pack_cmd = ["llm-pack", "-s"] + args.source_files
        debug_log(args, "llm-pack command:", llm_pack_cmd)
        llm_pack_result = run_command(
            llm_pack_cmd, capture_output=True, check=True, text=True
        )
        packed_sources = llm_pack_result.stdout
        debug_log(args, "llm-pack output (packed sources) length:", len(packed_sources))
        debug_log(
            args,
            "llm-pack output (first 200 chars):\n",
            textwrap.shorten(packed_sources, width=200, placeholder="..."),
        )

        # 4. Create a new chat conversation
        debug_log(args, "Creating new chat conversation via hnt-chat new...")
        hnt_chat_new_cmd = ["hnt-chat", "new"]
        debug_log(args, "hnt-chat new command:", hnt_chat_new_cmd)
        hnt_chat_new_result = run_command(
            hnt_chat_new_cmd, capture_output=True, check=True, text=True
        )
        conversation_dir_str = hnt_chat_new_result.stdout.strip()
        if not conversation_dir_str or not os.path.isdir(conversation_dir_str):
            print(
                f"Error: hnt-chat new did not return a valid directory path: '{conversation_dir_str}'",
                file=sys.stderr,
            )
            sys.exit(1)
        conversation_dir = Path(conversation_dir_str).resolve()  # Store as Path object
        debug_log(args, "Conversation directory created:", conversation_dir)

        # 4a. Compute and write absolute file paths
        debug_log(args, "Computing absolute paths for source files...")
        absolute_paths = []
        for f_path_str in args.source_files:
            try:
                # Path(f_path_str).resolve() gives the absolute path
                # Path.resolve() handles non-existent files correctly for our purpose (creates an absolute path string)
                # if it's a new file to be created. If it must exist, an error would be raised.
                # Since we touch/create files earlier, this should be fine.
                abs_path = Path(f_path_str).resolve()
                absolute_paths.append(str(abs_path))
                debug_log(args, f"  Original: {f_path_str}, Absolute: {abs_path}")
            except Exception as e:
                # This might happen if f_path_str is somehow invalid for Path resolution
                # though unlikely given prior checks and creations.
                print(
                    f"Warning: Could not resolve absolute path for {f_path_str}: {e}",
                    file=sys.stderr,
                )
                debug_log(args, f"Error resolving path for {f_path_str}: {e}")
                # Decide if this is critical. For now, let's add a placeholder or skip.
                # For robustness, we'll skip problematic ones but log it.
                # Or, we could append the original relative path as a fallback. Let's stick to absolute or nothing.

        if absolute_paths:
            abs_paths_file = Path(conversation_dir) / "absolute_file_paths.txt"
            debug_log(args, f"Writing absolute paths to {abs_paths_file}...")
            try:
                with open(abs_paths_file, "w") as f:
                    for p in absolute_paths:
                        f.write(p + "\n")
                debug_log(
                    args, f"Successfully wrote absolute paths to {abs_paths_file}."
                )
            except IOError as e:
                print(
                    f"Warning: Could not write absolute file paths to {abs_paths_file}: {e}",
                    file=sys.stderr,
                )
                debug_log(args, f"IOError writing {abs_paths_file}: {e}")
            except (
                Exception
            ) as e:  # Catch any other unexpected errors during file write
                print(
                    f"Warning: Unexpected error writing {abs_paths_file}: {e}",
                    file=sys.stderr,
                )
                debug_log(args, f"Unexpected error writing {abs_paths_file}: {e}")
        else:
            debug_log(
                args, "No absolute paths were resolved or source_files list was empty."
            )

        # 5. Add system message to conversation
        debug_log(args, "Adding system message via hnt-chat add...")
        hnt_chat_add_system_cmd = [
            "hnt-chat",
            "add",
            "system",
            "-c",
            str(conversation_dir),
        ]
        debug_log(args, "hnt-chat add system command:", hnt_chat_add_system_cmd)
        run_command(
            hnt_chat_add_system_cmd,
            stdin_content=system_message,
            # capture_output=False, # Don't need filename output - Capture it instead
            check=True,
            text=True,
        )
        debug_log(args, "System message added.")

        # 6. Add user request message to conversation
        debug_log(args, "Adding user request message via hnt-chat add...")
        # \n after instruction because it gets stripped
        user_request_content = f"<user_request>\n{instruction}\n</user_request>\n"
        hnt_chat_add_user_cmd = ["hnt-chat", "add", "user", "-c", str(conversation_dir)]
        debug_log(args, "hnt-chat add user command (request):", hnt_chat_add_user_cmd)
        debug_log(
            args,
            "User request content (first 100 chars):\n",
            textwrap.shorten(user_request_content, width=100, placeholder="..."),
        )
        run_command(
            hnt_chat_add_user_cmd,
            stdin_content=user_request_content,
            # capture_output=False, # Don't need filename output - Capture it instead
            check=True,
            text=True,
        )
        debug_log(args, "User request message added.")

        # 7. Add source reference message to conversation
        debug_log(args, "Adding source reference message via hnt-chat add...")
        source_reference_content = (
            f"<source_reference>\n{packed_sources}</source_reference>\n"
        )
        # Reuse the command list, it's the same
        debug_log(args, "hnt-chat add user command (source):", hnt_chat_add_user_cmd)
        debug_log(
            args,
            "Source reference content (first 100 chars):\n",
            textwrap.shorten(source_reference_content, width=100, placeholder="..."),
        )
        # Capture the output filename for the source reference
        add_source_ref_result = run_command(
            hnt_chat_add_user_cmd,
            stdin_content=source_reference_content,
            capture_output=True,  # Capture the filename output
            check=True,
            text=True,
        )
        source_ref_filename = add_source_ref_result.stdout.strip()
        debug_log(args, "Source reference message added:", source_ref_filename)

        # 7a. Write source reference path to source_reference.txt
        if source_ref_filename:
            debug_log(args, "Writing source reference path to source_reference.txt...")
            source_ref_txt_path = Path(conversation_dir) / "source_reference.txt"
            try:
                with open(source_ref_txt_path, "w") as f:
                    f.write(source_ref_filename)  # Write the path directly
                debug_log(args, "Successfully wrote to", source_ref_txt_path)
            except IOError as e:
                print(
                    f"Warning: Could not write {source_ref_txt_path}: {e}",
                    file=sys.stderr,
                )
                debug_log(args, f"IOError writing {source_ref_txt_path}: {e}")
            except Exception as e:
                print(
                    f"Warning: Unexpected error writing {source_ref_txt_path}: {e}",
                    file=sys.stderr,
                )
                debug_log(args, f"Unexpected error writing {source_ref_txt_path}: {e}")
        else:
            debug_log(
                args,
                "Warning: Did not get a filename for the source reference message.",
            )

        # Show user query if it came from EDITOR
        if not args.message:
            # Nicer display for user message from editor
            current_message_idx = (
                0  # For future multi-message support, currently hardcoded
            )

            title_str = f" User Message <{current_message_idx}> "
            # Design based on user's example visual:
            # ───────────────── User Message <0> ─────────────────
            # For idx=0, title " User Message <0> " is 18 chars.
            # Original total dashes: 13 (left) + 21 (right) = 34.
            # New even distribution: 17 dashes left, 17 dashes right.
            # Total length (for idx=0) = 17 + 18 (title) + 17 = 52 characters.

            # Calculate even padding for horizontal lines
            original_total_dashes = 13 + 21
            dashes_left = original_total_dashes // 2
            dashes_right = (
                original_total_dashes - dashes_left
            )  # Ensures total is preserved if odd

            header_line_part1 = U_HORIZ_LINE * dashes_left
            header_line_part2 = U_HORIZ_LINE * dashes_right

            header_display = f"{header_line_part1}{title_str}{header_line_part2}"
            footer_display = U_HORIZ_LINE * (
                len(header_line_part1) + len(title_str) + len(header_line_part2)
            )

            sys.stdout.write(USER_MESSAGE_COLOR)
            print(header_display)
            print(instruction)  # print() adds a newline after instruction content
            print(footer_display)
            sys.stdout.write(RESET_COLOR)
            sys.stdout.write(
                "\n"
            )  # Match original script's extra newline after the block
            sys.stdout.flush()

    # --- COMMON EXECUTION FLOW ---
    # `conversation_dir` (Path object) and `args.source_files` (list of strings) are now set for both modes.

    # 8. Run hnt-chat gen, stream and capture output
    debug_log(args, "Running hnt-chat gen...")
    hnt_chat_gen_cmd = [
        "hnt-chat",
        "gen",
        "--write",
        "--merge",
        "-c",
        str(conversation_dir),  # hnt-chat expects string path
    ]
    if not args.ignore_reasoning:
        hnt_chat_gen_cmd.extend(["--include-reasoning", "--separate-reasoning"])
    if args.model:
        hnt_chat_gen_cmd.extend(["--model", args.model])
        debug_log(args, "Using model:", args.model)
    if args.debug_unsafe:
        hnt_chat_gen_cmd.append("--debug-unsafe")
        debug_log(args, "Passing --debug-unsafe to hnt-chat gen")
    # if we wanted the filename: hnt_chat_gen_cmd.append("--output-filename")
    debug_log(args, "hnt-chat gen command:", hnt_chat_gen_cmd)

    llm_output_capture = io.StringIO()  # Renamed from hnt_llm_output_capture
    rich_process = None  # Initialize rich_process outside try
    debug_log(args, "Syntax highlighting enabled:", syntax_highlight_enabled)
    if syntax_highlight_enabled:
        debug_log(args, "Syntax highlight command:", effective_syntax_cmd)

    try:
        debug_log(args, "Starting hnt-chat gen process via Popen...")
        # Use Popen for streaming stdout (hnt-chat gen doesn't need stdin)
        chat_gen_process = subprocess.Popen(
            hnt_chat_gen_cmd,
            stdin=subprocess.DEVNULL,  # Explicitly provide no stdin
            stdout=subprocess.PIPE,
            stderr=sys.stderr,  # Pipe stderr directly to terminal
            text=True,
            bufsize=1,  # Line buffered, might help with streaming
        )
        debug_log(args, f"hnt-chat gen process started. PID: {chat_gen_process.pid}")

        # Start syntax highlighter process if enabled
        if syntax_highlight_enabled:
            debug_log(args, "Starting syntax highlighter process via Popen...")
            try:
                # Use the command determined earlier (from env var or default)
                rich_process = subprocess.Popen(
                    effective_syntax_cmd,
                    stdin=subprocess.PIPE,
                    stdout=sys.stdout,  # Pipe rich output directly to terminal stdout
                    stderr=sys.stderr,  # Pipe rich errors directly to terminal stderr
                    text=True,
                )
                debug_log(
                    args, f"Syntax highlighter process started. PID: {rich_process.pid}"
                )
            except FileNotFoundError:
                # Use the actual command that was attempted
                debug_log(
                    args,
                    f"Syntax highlighter command '{effective_syntax_cmd[0]}' not found.",
                )
                print(
                    f"Error: Syntax highlighter command '{effective_syntax_cmd[0]}' not found.",
                    file=sys.stderr,
                )
                syntax_highlight_enabled = False  # Disable if Popen fails
            except Exception as e:
                debug_log(args, f"Error starting syntax highlighter: {e}")
                print(f"Error starting syntax highlighter: {e}", file=sys.stderr)
                syntax_highlight_enabled = False  # Disable on other errors
        else:
            debug_log(
                args,
                "Syntax highlighting not enabled, skipping highlighter process start.",
            )

        # Stream stdout from hnt-chat gen, capture it, and pipe to rich if enabled
        # No stdin writing needed for hnt-chat gen
        debug_log(args, "Starting hnt-chat gen stdout reading loop...")
        while True:
            line = chat_gen_process.stdout.readline()  # Use chat_gen_process
            if not line:
                debug_log(args, "hnt-chat gen stdout loop: EOF")  # Update log message
                break

            # Log the received line if debugging
            debug_log(
                args, f"hnt-chat gen stdout recv: {repr(line)}"
            )  # Update log message

            # Always capture the raw output
            llm_output_capture.write(
                line
            )  # Use llm_output_capture (already renamed in previous step)

            # Pipe to syntax highlighter OR print directly
            if syntax_highlight_enabled and rich_process:
                try:
                    rich_process.stdin.write(line)
                    rich_process.stdin.flush()
                except BrokenPipeError:
                    # Rich process might have exited (e.g., if user Ctrl+C'd)
                    print("Warning: Syntax highlighter pipe broken.", file=sys.stderr)
                    syntax_highlight_enabled = False  # Stop trying to write
                    # Print remaining lines directly
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except Exception as e:
                    print(f"Error writing to syntax highlighter: {e}", file=sys.stderr)
                    syntax_highlight_enabled = False  # Stop trying to write
                    sys.stdout.write(line)
                    sys.stdout.flush()

            else:
                # Highlighting disabled or failed, print directly
                sys.stdout.write(line)
                sys.stdout.flush()

        # Close rich stdin if it was used
        if rich_process and rich_process.stdin:
            try:
                rich_process.stdin.close()
            except Exception as e:
                print(
                    f"Warning: Error closing syntax highlighter stdin: {e}",
                    file=sys.stderr,
                )

        # Wait for hnt-chat gen process to finish and check return code
        debug_log(args, "Waiting for hnt-chat gen process to finish...")
        chat_gen_rc = chat_gen_process.wait()
        debug_log(args, "hnt-chat gen process finished with return code:", chat_gen_rc)
        if chat_gen_rc != 0:
            debug_log(args, "hnt-chat gen failed.")
            # stderr was already piped to terminal
            print(
                f"\nError: '{' '.join(hnt_chat_gen_cmd)}' failed with exit code {chat_gen_rc}. See stderr above.",
                file=sys.stderr,
            )
            # Don't exit immediately if rich also needs cleanup/check
            # sys.exit(chat_gen_rc) # Moved after potential rich wait

    except FileNotFoundError:
        print(
            f"Error: Command not found during Popen: {hnt_chat_gen_cmd[0]}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(
            f"An unexpected error occurred while running {' '.join(hnt_chat_gen_cmd)}: {e}",
            file=sys.stderr,
        )
        # Ensure processes are terminated if they are still running
        if "chat_gen_process" in locals() and chat_gen_process.poll() is None:
            chat_gen_process.terminate()
            chat_gen_process.wait()  # Ensure termination
        if rich_process and rich_process.poll() is None:
            rich_process.terminate()
            rich_process.wait()  # Ensure termination
        sys.exit(1)
    finally:
        # Ensure resources are cleaned up even if errors occurred mid-stream

        # Wait for rich process if it was started
        rich_rc = 0
        if rich_process:
            rich_rc = rich_process.wait()
            if rich_rc != 0:
                # Rich errors likely already went to stderr, but log rc
                print(
                    f"Info: Syntax highlighter exited with code {rich_rc}",
                    file=sys.stderr,
                )

        # Now check hnt-chat gen's return code and exit if it failed
        # Use the previously captured return code
        if "chat_gen_rc" in locals() and chat_gen_rc != 0:
            sys.exit(chat_gen_rc)

    final_llm_output = llm_output_capture.getvalue()  # Renamed capture variable
    llm_output_capture.close()
    debug_log(args, "Captured hnt-chat gen output length:", len(final_llm_output))
    debug_log(
        args,
        "Captured hnt-chat gen output (first 200 chars):\n",
        textwrap.shorten(final_llm_output, width=200, placeholder="..."),
    )

    # Check if output is empty (might happen if hnt-chat gen failed silently or produced nothing)
    if not final_llm_output.strip():
        debug_log(args, "hnt-chat gen output is empty or whitespace only.")
        print(
            "Warning: hnt-chat gen produced no output. Aborting before running hnt-apply.",
            file=sys.stderr,
        )
        sys.exit(1)  # Or a specific error code

    # Print conversation directory before applying changes
    print(f"\nhnt-chat dir: {str(conversation_dir)}", file=sys.stderr)

    # 9. Run hnt-apply (step number updated)
    debug_log(args, "Running hnt-apply...")
    hnt_apply_cmd = ["hnt-apply", "--ignore-reasoning"] + args.source_files
    debug_log(args, "hnt-apply command:", hnt_apply_cmd)
    debug_log(args, "Piping captured hnt-chat gen output to hnt-apply stdin.")

    hnt_apply_stdout_capture = io.StringIO()
    hnt_apply_rc = 0
    try:
        debug_log(args, "Starting hnt-apply process via Popen...")
        apply_process = subprocess.Popen(
            hnt_apply_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,  # Stream stderr directly
            text=True,
            bufsize=1,  # Line buffered potentially
        )
        debug_log(args, f"hnt-apply process started. PID: {apply_process.pid}")

        # Write hnt-chat gen output to hnt-apply's stdin
        debug_log(args, f"Writing {len(final_llm_output)} bytes to hnt-apply stdin...")
        try:
            apply_process.stdin.write(final_llm_output)
            apply_process.stdin.close()  # Signal EOF
            debug_log(args, "Finished writing to hnt-apply stdin.")
        except BrokenPipeError:
            debug_log(
                args, "hnt-apply stdin pipe broken (process may have exited early?)."
            )
        except Exception as e:
            debug_log(args, f"Error writing to hnt-apply stdin: {e}")
            # Process might still be running, continue to reading stdout

        # Stream hnt-apply stdout, capture it
        debug_log(args, "Starting hnt-apply stdout reading loop...")
        while True:
            line = apply_process.stdout.readline()
            if not line:
                debug_log(args, "hnt-apply stdout loop: EOF")
                break

            debug_log(args, f"hnt-apply stdout recv: {repr(line)}")

            # Capture
            hnt_apply_stdout_capture.write(line)
            # Stream
            sys.stdout.write(line)
            sys.stdout.flush()

        # Wait for hnt-apply to finish
        debug_log(args, "Waiting for hnt-apply process to finish...")
        hnt_apply_rc = apply_process.wait()
        debug_log(args, "hnt-apply process finished with return code:", hnt_apply_rc)

    except FileNotFoundError:
        print(f"Error: Command not found: {hnt_apply_cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(
            f"An unexpected error occurred while running {' '.join(hnt_apply_cmd)}: {e}",
            file=sys.stderr,
        )
        # Ensure process is terminated if it's still running
        if "apply_process" in locals() and apply_process.poll() is None:
            apply_process.terminate()
            apply_process.wait()
        sys.exit(1)

    # Check hnt-apply's exit code
    if hnt_apply_rc != 0:
        captured_apply_stdout = hnt_apply_stdout_capture.getvalue()
        hnt_apply_stdout_capture.close()  # Close the StringIO buffer

        print(
            f"\nError: '{' '.join(hnt_apply_cmd)}' failed with exit code {hnt_apply_rc}.",
            file=sys.stderr,
        )
        debug_log(args, "hnt-apply failed. Adding its stdout to the chat conversation.")
        debug_log(args, "Captured hnt-apply stdout length:", len(captured_apply_stdout))

        # 10. Add hnt-apply's raw stdout as a new user message if it failed
        hnt_chat_add_user_failure_cmd = [
            "hnt-chat",
            "add",
            "user",
            "-c",
            str(conversation_dir),  # hnt-chat expects string path
        ]
        debug_log(
            args, "hnt-chat add user command (failure):", hnt_chat_add_user_failure_cmd
        )
        debug_log(
            args,
            "Failure message content (hnt-apply stdout) length:",
            len(captured_apply_stdout),
        )
        try:
            run_command(
                hnt_chat_add_user_failure_cmd,
                stdin_content=captured_apply_stdout,
                check=True,
                text=True,
            )
            debug_log(args, "hnt-apply failure message added to chat.")
        except Exception as e:
            # Log this error, but proceed to exit with hnt-apply's error code
            print(
                f"Error adding hnt-apply failure message to chat: {e}", file=sys.stderr
            )
            debug_log(args, f"hnt-chat add user failed during error handling: {e}")

        sys.exit(hnt_apply_rc)  # Exit hnt-edit with hnt-apply's error code
    else:
        hnt_apply_stdout_capture.close()  # Close the buffer even on success
        debug_log(args, "hnt-apply finished successfully.")


if __name__ == "__main__":
    main()
