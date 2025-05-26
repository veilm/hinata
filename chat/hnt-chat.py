#!/usr/bin/env python3

import os
import sys
import time
import random
import argparse
import re
import subprocess
import io  # Added for BytesIO
from pathlib import Path


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
            print("Error: Could not determine home directory.", file=sys.stderr)
            sys.exit(1)
        # Default to $HOME/.local/share as per XDG Base Directory Specification
        base_data_dir = home_dir / ".local" / "share"

    conversations_dir = base_data_dir / "hinata" / "chat" / "conversations"

    try:
        conversations_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error creating directory {conversations_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    return conversations_dir


def create_new_conversation(base_dir):
    """
    Creates a new unique conversation directory based on nanosecond timestamp.
    Handles potential collisions by waiting and retrying.
    """
    while True:
        timestamp_ns = time.time_ns()
        new_conv_path = base_dir / str(timestamp_ns)

        # Check existence first to potentially avoid unnecessary mkdir attempts
        if new_conv_path.exists():
            wait_time = random.uniform(0, 1.0)
            # print(f"Debug: Path {new_conv_path} exists, waiting {wait_time:.3f}s", file=sys.stderr)
            time.sleep(wait_time)
            continue

        try:
            # Attempt to create the directory
            # parents=False ensures we don't accidentally recreate the base dir
            # exist_ok=False ensures it fails if it was created between the .exists() check and now
            new_conv_path.mkdir(parents=False, exist_ok=False)
            return new_conv_path
        except FileExistsError:
            # Race condition: another process created it between .exists() and mkdir()
            wait_time = random.uniform(0, 1.0)
            # print(f"Debug: Race condition for {new_conv_path}, waiting {wait_time:.3f}s", file=sys.stderr)
            time.sleep(wait_time)
            # Loop continues to retry
        except OSError as e:
            print(f"Error creating directory {new_conv_path}: {e}", file=sys.stderr)
            sys.exit(1)


def find_latest_conversation(base_dir):
    """Finds the alphabetically latest directory in the base conversations dir."""
    try:
        # Use iterdir() for potentially many entries
        subdirs = sorted(
            [d for d in base_dir.iterdir() if d.is_dir()], key=lambda p: p.name
        )
        if subdirs:
            return subdirs[-1]
        else:
            return None
    except FileNotFoundError:
        # Base dir itself doesn't exist, handled by caller checks
        return None
    except OSError as e:
        print(f"Error listing directories in {base_dir}: {e}", file=sys.stderr)
        sys.exit(1)


def determine_conversation_dir(args, base_conv_dir):
    """
    Determines the target conversation directory based on args, env var, or latest.
    Includes validation checks. Exits on error.
    Returns the Path object for the conversation directory.
    """
    conv_dir_path = getattr(args, "conversation", None)  # Get path from args if present

    if conv_dir_path is None:
        env_conv_dir = os.getenv("HINATA_CHAT_CONVERSATION")
        if env_conv_dir:
            conv_dir_path = Path(env_conv_dir)
        else:
            # Use default: latest in base dir
            latest_conv = find_latest_conversation(base_conv_dir)
            if latest_conv:
                conv_dir_path = latest_conv
                print(
                    f"hnt-chat: using latest conversation directory: {conv_dir_path.resolve()}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Error: No conversation directory specified via --conversation or $HINATA_CHAT_CONVERSATION, and no existing conversations found in {base_conv_dir}.",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Validate the chosen/found directory
    if not conv_dir_path.exists():
        print(
            f"Error: Conversation directory not found: {conv_dir_path}", file=sys.stderr
        )
        sys.exit(1)
    if not conv_dir_path.is_dir():
        print(
            f"Error: Specified conversation path is not a directory: {conv_dir_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    return conv_dir_path


def handle_new_command():
    conv_base_dir = get_conversations_dir()
    new_conv_path = create_new_conversation(conv_base_dir)
    # Print the absolute path to stdout as required
    print(new_conv_path.resolve())


def handle_add_command(args):
    role = args.role
    base_conv_dir = get_conversations_dir()  # Ensure base exists

    # 1. Determine and validate conversation directory
    conv_dir_path = determine_conversation_dir(args, base_conv_dir)

    # 2. Read from stdin
    if sys.stdin.isatty():
        print("hnt-chat: reading from stdin...", file=sys.stderr)
    content = sys.stdin.read()

    # 3. Generate filename and check for existence
    timestamp_ns = time.time_ns()
    relative_filename = f"{timestamp_ns}-{role}.md"
    output_filepath = conv_dir_path / relative_filename

    if output_filepath.exists():
        print(f"Error: Output file already exists: {output_filepath}", file=sys.stderr)
        sys.exit(1)

    # 4. Write file
    try:
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        print(f"Error writing to file {output_filepath}: {e}", file=sys.stderr)
        sys.exit(1)

    # 5. Print relative filename to stdout
    print(relative_filename)


def handle_pack_command(
    args,
):
    """
    Packs messages from a conversation directory into a specific format using hnt-escape.
    """
    base_conv_dir = get_conversations_dir()  # Ensure base exists

    # 1. Determine and validate conversation directory
    conv_dir_path = determine_conversation_dir(args, base_conv_dir)

    # 2. Use the helper function to pack directly to standard output (binary buffer)
    _pack_conversation_stream(conv_dir_path, sys.stdout.buffer, args.merge)


def _pack_conversation_stream(conv_dir_path, output_stream, merge_messages=False):
    """
    Packs messages from a conversation directory into the specified output stream.

    Args:
        conv_dir_path (Path): The path to the conversation directory.
        output_stream: A file-like object opened in binary mode.
        merge_messages (bool): If True, merge consecutive messages from the same role.
    """
    try:
        message_files = sorted(
            f for f in conv_dir_path.iterdir() if f.is_file() and f.name.endswith(".md")
        )
    except OSError as e:
        print(f"Error listing files in {conv_dir_path}: {e}", file=sys.stderr)
        sys.exit(1)

    filename_pattern = re.compile(r"^(\d+)-(user|assistant|system)\.md$")

    # Variables for merging logic
    accumulated_content_parts = []
    accumulated_role = None

    def _flush_accumulated_message_content(
        out_stream, role_to_flush, content_parts_to_flush
    ):
        if not role_to_flush or not content_parts_to_flush:
            return

        full_content_raw = "".join(content_parts_to_flush)

        out_stream.write(f"<hnt-{role_to_flush}>".encode("utf-8"))
        if hasattr(out_stream, "flush"):
            out_stream.flush()

        try:
            process = subprocess.run(
                ["hnt-escape"],
                input=full_content_raw.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=sys.stderr,
                check=True,
            )
            out_stream.write(process.stdout)
        except FileNotFoundError:
            print(
                "\nError: 'hnt-escape' command not found. Make sure it's installed and in your PATH.",
                file=sys.stderr,
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(
                f"\nError: 'hnt-escape' failed while processing merged content (exit code {e.returncode}).",
                file=sys.stderr,
            )
            sys.exit(1)

        out_stream.write(f"</hnt-{role_to_flush}>\n".encode("utf-8"))
        if hasattr(out_stream, "flush"):
            out_stream.flush()

    for msg_file_path in message_files:
        match = filename_pattern.match(msg_file_path.name)
        if not match:
            continue  # Silently skip files that don't match the pattern

        current_role_from_file = match.group(2)

        if not merge_messages:
            # Original behavior: process each file individually
            output_stream.write(f"<hnt-{current_role_from_file}>".encode("utf-8"))
            if hasattr(output_stream, "flush"):
                output_stream.flush()
            try:
                with open(msg_file_path, "rb") as f_in:
                    process = subprocess.run(
                        ["hnt-escape"],
                        stdin=f_in,
                        stdout=subprocess.PIPE,
                        stderr=sys.stderr,
                        check=True,
                    )
                    output_stream.write(process.stdout)
            except FileNotFoundError:
                print(
                    f"\nError: 'hnt-escape' command not found. Make sure it's installed and in your PATH.",
                    file=sys.stderr,
                )
                sys.exit(1)
            except subprocess.CalledProcessError as e:
                print(
                    f"\nError: 'hnt-escape' failed processing {msg_file_path.name} (exit code {e.returncode}).",
                    file=sys.stderr,
                )
                sys.exit(1)
            except OSError as e:
                print(f"\nError reading file {msg_file_path}: {e}", file=sys.stderr)
                sys.exit(1)

            output_stream.write(f"</hnt-{current_role_from_file}>\n".encode("utf-8"))
            if hasattr(output_stream, "flush"):
                output_stream.flush()
        else:
            # Merge messages logic
            try:
                with open(msg_file_path, "r", encoding="utf-8") as f_content:
                    current_content_raw = f_content.read()
            except OSError as e:
                print(f"Error reading file {msg_file_path}: {e}", file=sys.stderr)
                sys.exit(1)

            if (
                accumulated_role == current_role_from_file
                and accumulated_role is not None
            ):
                accumulated_content_parts.append(current_content_raw)
            else:
                # Flush previous accumulated message if any
                _flush_accumulated_message_content(
                    output_stream, accumulated_role, accumulated_content_parts
                )

                # Start new accumulation
                accumulated_role = current_role_from_file
                accumulated_content_parts = [current_content_raw]

    # After the loop, if merging, flush any remaining accumulated message
    if merge_messages:
        _flush_accumulated_message_content(
            output_stream, accumulated_role, accumulated_content_parts
        )


def pack_conversation_to_buffer(conv_dir_path, merge_messages=False):
    """
    Packs messages from a conversation directory into a BytesIO buffer using the shared helper.
    Returns the BytesIO buffer containing the packed data.
    Args:
        conv_dir_path (Path): The path to the conversation directory.
        merge_messages (bool): If True, merge consecutive messages from the same role.
    """
    output_buffer = io.BytesIO()
    # Call the helper function to write to the buffer
    _pack_conversation_stream(conv_dir_path, output_buffer, merge_messages)

    output_buffer.seek(0)  # Rewind buffer for reading
    return output_buffer


def _write_message_file(conv_dir_path, role, content):
    """Helper to write content to a new message file. Returns relative filename."""
    timestamp_ns = time.time_ns()
    relative_filename = f"{timestamp_ns}-{role}.md"
    output_filepath = conv_dir_path / relative_filename

    if output_filepath.exists():
        # Should be rare due to nanoseconds, but handle defensively
        print(f"Error: Output file collision: {output_filepath}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return relative_filename
    except OSError as e:
        print(f"Error writing to file {output_filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def handle_gen_command(args):
    """Handles the 'gen' command to interact with hnt-llm."""
    base_conv_dir = get_conversations_dir()
    conv_dir_path = determine_conversation_dir(args, base_conv_dir)

    # Determine effective model name and write to model.txt if applicable
    effective_model_name = args.model
    if not effective_model_name:
        effective_model_name = os.getenv("HINATA_LLM_MODEL")

    if effective_model_name:
        model_file_path = conv_dir_path / "model.txt"
        try:
            with open(model_file_path, "w", encoding="utf-8") as f:
                f.write(effective_model_name + "\n")
        except OSError as e:
            print(
                f"Warning: Could not write model name to {model_file_path}: {e}",
                file=sys.stderr,
            )
            # Continue execution even if model.txt cannot be written,
            # as the main 'gen' operation might still be desired.

    # 1. Pack the conversation history into a buffer, considering the merge flag
    packed_buffer = pack_conversation_to_buffer(conv_dir_path, args.merge)

    # 2. Prepare the hnt-llm command
    llm_cmd = ["hnt-llm"]
    if effective_model_name:  # Use the determined effective_model_name
        llm_cmd.extend(["--model", effective_model_name])
    if args.debug_unsafe:
        llm_cmd.append("--debug-unsafe")

    # Handle reasoning flags
    include_reasoning_active = args.include_reasoning or args.separate_reasoning
    if include_reasoning_active:
        llm_cmd.append("--include-reasoning")

    # 3. Execute hnt-llm, stream output, and potentially capture
    captured_output_buffer = io.BytesIO()
    # --separate-reasoning implies --write
    should_write_active = args.write or args.output_filename or args.separate_reasoning
    relative_filename_written = None  # Track assistant message filename
    process = None  # Initialize process for robust error handling

    try:
        # print(f"hnt-chat: running {' '.join(llm_cmd)}...", file=sys.stderr)
        process = subprocess.Popen(
            llm_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            bufsize=0,
        )

        # Write packed data to hnt-llm's stdin
        process.stdin.write(packed_buffer.getvalue())
        process.stdin.close()  # Signal EOF

        # Stream stdout and capture if needed
        if process.stdout:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)  # Stream to our stdout
                sys.stdout.buffer.flush()
                if should_write_active:  # Capture if any form of write is active
                    captured_output_buffer.write(chunk)
            process.stdout.close()

        return_code = process.wait()

        if return_code != 0:
            print(f"Error: hnt-llm exited with status {return_code}", file=sys.stderr)
            # Don't write partial output if LLM errored
            sys.exit(return_code)

        # 4. Write captured output if requested
        if should_write_active:
            full_assistant_content = captured_output_buffer.getvalue().decode(
                "utf-8", errors="replace"
            )
            content_for_assistant_file = full_assistant_content

            if args.separate_reasoning:
                # Regex to find <think>...</think> at the beginning of the string.
                # re.DOTALL allows '.' to match newlines within the think block.
                think_block_match = re.match(
                    r"^(<think>.*?</think>)", full_assistant_content, re.DOTALL
                )
                if think_block_match:
                    extracted_reasoning = think_block_match.group(0)
                    # Write reasoning to its own file with a new timestamp
                    _write_message_file(
                        conv_dir_path, "assistant-reasoning", extracted_reasoning
                    )
                    # Update content for the main assistant file: everything after the think block
                    content_for_assistant_file = full_assistant_content[
                        len(extracted_reasoning) :
                    ].lstrip()

            # Write the (potentially modified) assistant message
            if (
                content_for_assistant_file
                or not args.separate_reasoning
                or not think_block_match
            ):  # Ensure we write empty assistant if it's all reasoning
                relative_filename_written = _write_message_file(
                    conv_dir_path, "assistant", content_for_assistant_file
                )
            # print(
            #     f"hnt-chat: wrote assistant message {relative_filename_written}",
            #     file=sys.stderr,
            # )

    except FileNotFoundError:
        print(
            f"Error: '{llm_cmd[0]}' command not found. Make sure it's installed and in your PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    except BrokenPipeError:
        # Handle case where hnt-llm might exit before reading all input or writing all output
        print(
            f"Error: Broken pipe communicating with hnt-llm. It might have exited prematurely.",
            file=sys.stderr,
        )
        # Check exit status again if possible
        if process:  # process is initialized to None, so this check is safe
            rc = process.poll()  # Non-blocking check
            if rc is not None and rc != 0:
                print(f"hnt-llm exited abnormally with status {rc}", file=sys.stderr)
                sys.exit(rc if rc > 0 else 1)
            elif rc is None:  # pragma: no cover (hard to test this specific timing)
                process.wait()  # Wait if somehow still running
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    # 5. Print filename if --output-filename was used
    if args.output_filename and relative_filename_written:
        # Always print a leading newline before the filename when requested.
        # This avoids issues with checking sys.stdout.buffer.tell() on non-seekable streams (like pipes/terminals)
        # and ensures the filename appears cleanly separated from the streamed output.
        print(f"\n{relative_filename_written}")


def main():
    """
    Main function to handle command-line arguments using argparse.
    """
    parser = argparse.ArgumentParser(description="Hinata Chat CLI tool.")
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Sub-command help"
    )

    # 'new' command
    parser_new = subparsers.add_parser(
        "new", help="Create a new conversation directory"
    )
    parser_new.set_defaults(func=handle_new_command)

    # 'add'/'add-message' command
    parser_add = subparsers.add_parser(
        "add", aliases=["add-message"], help="Add a message to a conversation"
    )
    parser_add.add_argument(
        "role",
        choices=["user", "assistant", "system"],
        help="The role of the message author",
    )
    parser_add.add_argument(
        "-c",
        "--conversation",
        type=Path,
        help="Path to the conversation directory (overrides $HINATA_CHAT_CONVERSATION, defaults to latest)",
    )
    parser_add.set_defaults(func=handle_add_command)

    # 'pack'/'package' command
    parser_pack = subparsers.add_parser(
        "pack", aliases=["package"], help="Pack conversation messages for processing"
    )
    parser_pack.add_argument(
        "-c",
        "--conversation",
        type=Path,
        help="Path to the conversation directory (overrides $HINATA_CHAT_CONVERSATION, defaults to latest)",
    )
    parser_pack.add_argument(
        "--merge",
        action="store_true",
        help="Merge consecutive messages from the same role into a single message.",
    )
    parser_pack.set_defaults(func=handle_pack_command)

    # 'gen'/'generate'/'llm' command
    parser_gen = subparsers.add_parser(
        "gen",
        aliases=["generate", "llm"],
        help="Generate text using hnt-llm with conversation context",
    )
    parser_gen.add_argument(
        "-c",
        "--conversation",
        type=Path,
        help="Path to the conversation directory (overrides $HINATA_CHAT_CONVERSATION, defaults to latest)",
    )
    parser_gen.add_argument(
        "-m",
        "--model",
        type=str,
        help="Optional model string to pass to hnt-llm",
    )
    parser_gen.add_argument(
        "-w",
        "--write",
        action="store_true",
        help="Write the generated output as a new assistant message",
    )
    parser_gen.add_argument(
        "--output-filename",
        action="store_true",
        help="Implies --write. Also prints the filename of the created assistant message",
    )
    parser_gen.add_argument(
        "--debug-unsafe",
        action="store_true",
        help="Pass the --debug-unsafe flag to the hnt-llm subprocess",
    )
    parser_gen.add_argument(
        "--merge",
        action="store_true",
        help="Merge consecutive messages from the same role before sending to LLM.",
    )
    parser_gen.add_argument(
        "--include-reasoning",
        action="store_true",
        help="Passes --include-reasoning to hnt-llm. LLM may include <think> tags.",
    )
    parser_gen.add_argument(
        "--separate-reasoning",
        action="store_true",
        help="Implies --include-reasoning and --write. Saves leading <think> block to a separate file.",
    )
    parser_gen.set_defaults(func=handle_gen_command)

    args = parser.parse_args()

    # Execute the function associated with the chosen subcommand
    if hasattr(args, "func"):
        # Pass args to handlers that need them (add, pack, gen)
        if args.command in [
            "add",
            "add-message",
            "pack",
            "package",
            "gen",
            "generate",
            "llm",
        ]:
            args.func(args)
        else:
            # Handlers like 'new' likely don't need args object
            args.func()
    else:
        # This should not happen if subparsers are required=True
        # and all subparsers have set_defaults(func=...)
        print("Error: Invalid command configuration.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
