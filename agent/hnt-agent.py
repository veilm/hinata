#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import tempfile
import io
import shlex
import time
import shutil
import textwrap
from pathlib import Path


# ANSI color codes for UI display
USER_INSTRUCTION_COLOR = "\033[94m"  # Light Blue
LLM_RESPONSE_COLOR = "\033[92m"  # Light Green
TOOL_OUTPUT_COLOR = "\033[96m"  # Light Cyan
RESET_COLOR = "\033[0m"

# Unicode character for UI borders
U_HORIZ_LINE = "─"

# Fixed width for dividers
FIXED_DIVIDER_WIDTH = 70


# Command to pipe output through for syntax highlighting
SYNTAX_HIGHLIGHT_PIPE_CMD = ["hlmd-st"]


def get_header_footer_lines(title_text_input):
    """Generates header and footer line strings for styled output blocks using a fixed width."""
    current_divider_width = FIXED_DIVIDER_WIDTH

    # Max length for title_text_input itself, leaving space for " .. " and dashes
    # " {title} " needs len(title) + 2. Min 1 dash each side. Min 2 spaces for " ".
    # So total space for " {title} " is len(title) + 2.
    # Max title content length aims to leave at least 2 dashes and 2 spaces for the title wrapper "  ".
    # Effectively, title_text + "  " should be less than current_divider_width - 2 (for minimal dashes).
    max_title_content_len = (
        current_divider_width - 6
    )  # Allows for " XYZ.. " and minimal dashes. E.g. " -- TITLE... -- "
    if max_title_content_len < 1:  # Handle very small divider widths
        max_title_content_len = 1

    if len(title_text_input) > max_title_content_len:
        # Truncate, leaving space for "..."
        title_text = title_text_input[: max_title_content_len - 3] + "..."
    else:
        title_text = title_text_input

    title_str = f" {title_text} "

    # Now calculate dashes
    remaining_width = current_divider_width - len(title_str)
    # Ensure remaining_width is not negative if title_str itself is too long
    # (e.g. if title_str due to title_text alone is already > current_divider_width)
    if remaining_width < 0:
        remaining_width = (
            0  # No space for dashes if title itself (with spaces) is too wide
        )

    dashes_left = remaining_width // 2
    dashes_right = remaining_width - dashes_left  # Handles odd remaining_width

    header_line_part1 = U_HORIZ_LINE * dashes_left
    header_line_part2 = U_HORIZ_LINE * dashes_right

    # Construct header. It should naturally be current_divider_width long if logic is correct.
    # The slicing [:current_divider_width] is a safeguard.
    header_display = header_line_part1 + title_str + header_line_part2
    if len(header_display) > current_divider_width:  # If title_str was too wide
        header_display = (
            title_str[: current_divider_width - 3] + "..."
            if len(title_str) > current_divider_width
            else title_str
        )
        # Pad with minimal dashes if possible, or just truncate title
        if len(header_display) < current_divider_width:
            padding_needed = current_divider_width - len(header_display)
            pad_left = padding_needed // 2
            pad_right = padding_needed - pad_left
            header_display = (
                (U_HORIZ_LINE * pad_left) + header_display + (U_HORIZ_LINE * pad_right)
            )
        header_display = header_display[:current_divider_width]  # Final safety truncate

    # Footer should be a full line of dashes of current_divider_width
    footer_display = U_HORIZ_LINE * current_divider_width

    return header_display, footer_display


def run_command(cmd, stdin_content=None, capture_output=True, check=True, text=True):
    """Helper function to run a command."""
    process = None  # Initialize process to None for broader scope in error handling
    try:
        process = subprocess.run(
            cmd,
            input=stdin_content,
            capture_output=capture_output,
            check=check,  # Be mindful: if check is True, CalledProcessError is raised on non-zero exit
            text=text,
        )
        return process
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        # This block is reached if check=True and the command returns non-zero.
        # For commands where we want to handle non-zero exits specially (like hnt-shell-apply),
        # we should call run_command with check=False and inspect e.returncode ourselves.
        print(
            f"Error: Command '{' '.join(cmd)}' failed with exit code {e.returncode}",
            file=sys.stderr,
        )
        if e.stderr:  # process.stderr would be None if capture_output=False or if check=True caused immediate exit
            print(f"Stderr:\n{e.stderr}", file=sys.stderr)
        if e.stdout:  # process.stdout similar
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
    tmp_path = None  # Initialize for cleanup in case of early error
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+",
            prefix="hnt-agent-",
            suffix=".md",
            delete=False,  # Changed prefix
        ) as tmpfile:
            tmpfile.write(initial_text)
            tmpfile.flush()
            tmp_path = tmpfile.name

        run_command(
            [editor, tmp_path], capture_output=False, check=True
        )  # check=True vital here

        with open(tmp_path, "r") as f:
            instruction = f.read().strip()

        os.unlink(tmp_path)  # Clean up

        stripped_instruction = instruction.strip()
        if not stripped_instruction or stripped_instruction == initial_text.strip():
            print("Aborted: No changes were made.", file=sys.stderr)
            sys.exit(0)
        return instruction

    except Exception as e:
        print(f"Error getting user instruction via editor: {e}", file=sys.stderr)
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        sys.exit(1)


def get_system_message(system_arg, default_prompt_filename="main-shell_agent.md"):
    """Gets the system message either from args or default file."""
    if system_arg:
        if os.path.exists(system_arg):
            try:
                with open(system_arg, "r") as f:
                    return f.read()
            except IOError as e:
                print(f"Error reading system file {system_arg}: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            return system_arg
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        # Path updated as per user request: $XDG_CONFIG_HOME/hinata/prompts/main-shell_agent.md
        default_path = (
            Path(config_home) / "hinata" / "prompts" / default_prompt_filename
        )
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


def debug_log(args, *print_args, **print_kwargs):
    """Prints debug messages to stderr if --debug-unsafe is enabled."""
    if hasattr(args, "debug_unsafe") and args.debug_unsafe:
        print("[DEBUG]", *print_args, file=sys.stderr, **print_kwargs)


def stream_and_capture_llm_output(
    args, gen_cmd, use_syntax_highlight, highlighter_cmd, description
):
    """
    Runs the LLM generation command, streams its output to stdout (optionally via a syntax highlighter)
    and captures the full output.
    'description' is used as the title for the header/footer.
    """
    llm_header, llm_footer = get_header_footer_lines(description)
    sys.stdout.write(
        f"\n{LLM_RESPONSE_COLOR}"
    )  # Start color, add leading newline for separation
    print(llm_header)  # print() adds a newline after the header
    sys.stdout.flush()

    output_capture = io.StringIO()
    gen_process = None
    highlighter_process = None
    current_stream_highlight_active = use_syntax_highlight

    should_exit_code = None  # None means success, otherwise it's the code to exit with

    try:
        gen_process = subprocess.Popen(
            gen_cmd,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,  # Pipe generator's stderr directly to terminal
            text=True,
            bufsize=1,  # Line-buffered
        )
        debug_log(
            args,
            f"Generation process for '{description}' ({' '.join(gen_cmd)}) started. PID: {gen_process.pid}",
        )

        if current_stream_highlight_active and highlighter_cmd:
            debug_log(
                args,
                f"Attempting to start syntax highlighter for '{description}': {' '.join(highlighter_cmd)}",
            )
            try:
                highlighter_process = subprocess.Popen(
                    highlighter_cmd,
                    stdin=subprocess.PIPE,
                    stdout=sys.stdout,  # Highlighter output goes to terminal
                    stderr=sys.stderr,  # Highlighter stderr goes to terminal
                    text=True,
                )
                debug_log(
                    args,
                    f"Syntax highlighter process started. PID: {highlighter_process.pid}",
                )
            except FileNotFoundError:
                print(
                    f"Warning: Syntax highlighter command '{highlighter_cmd[0]}' not found. Printing raw for this response.",
                    file=sys.stderr,
                )
                debug_log(
                    args,
                    f"Syntax highlighter '{highlighter_cmd[0]}' not found, falling back to raw.",
                )
                current_stream_highlight_active = False
            except Exception as e_hl_start:
                print(
                    f"Warning: Error starting syntax highlighter: {e_hl_start}. Printing raw for this response.",
                    file=sys.stderr,
                )
                debug_log(
                    args,
                    f"Error starting syntax highlighter: {e_hl_start}, falling back to raw.",
                )
                current_stream_highlight_active = False

        # If using syntax highlighting, reset terminal color after header for hlmd-st.
        # Raw output will inherit LLM_RESPONSE_COLOR from header or apply it on fallback.
        if current_stream_highlight_active:
            sys.stdout.write(RESET_COLOR)
            sys.stdout.flush()

        # Streaming loop
        if gen_process.stdout:
            for line in iter(gen_process.stdout.readline, ""):
                output_capture.write(line)
                if (
                    current_stream_highlight_active
                    and highlighter_process
                    and highlighter_process.stdin
                ):
                    try:
                        highlighter_process.stdin.write(line)
                        highlighter_process.stdin.flush()
                    except BrokenPipeError:
                        print(
                            "Warning: Syntax highlighter pipe broken. Printing raw for remainder of this response.",
                            file=sys.stderr,
                        )
                        debug_log(
                            args,
                            "Syntax highlighter pipe broken, falling back to raw for remainder. Applying LLM_RESPONSE_COLOR.",
                        )
                        current_stream_highlight_active = False
                        sys.stdout.write(
                            LLM_RESPONSE_COLOR
                        )  # Ensure raw output is colored
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    except Exception as e_hl_write:
                        print(
                            f"Warning: Error writing to syntax highlighter: {e_hl_write}. Printing raw for remainder of this response.",
                            file=sys.stderr,
                        )
                        debug_log(
                            args,
                            f"Error writing to syntax highlighter: {e_hl_write}, falling back to raw. Applying LLM_RESPONSE_COLOR.",
                        )
                        current_stream_highlight_active = False
                        sys.stdout.write(
                            LLM_RESPONSE_COLOR
                        )  # Ensure raw output is colored
                        sys.stdout.write(line)
                        sys.stdout.flush()
                else:
                    sys.stdout.write(line)
                    sys.stdout.flush()
            gen_process.stdout.close()  # Close the pipe after reading everything

        # Wait for generator process first
        gen_rc = gen_process.wait()

        # Clean up highlighter process
        if highlighter_process:
            if highlighter_process.stdin:
                try:
                    highlighter_process.stdin.close()
                except (
                    IOError,
                    BrokenPipeError,
                ):  # Can happen if already closed or broken
                    pass
            highlighter_rc = highlighter_process.wait()
            if highlighter_rc != 0:
                # This is a warning, as hnt-chat gen might have succeeded.
                print(
                    f"Warning: Syntax highlighter exited with code {highlighter_rc}",
                    file=sys.stderr,
                )
                debug_log(
                    args, f"Syntax highlighter exited with code {highlighter_rc}."
                )

        if gen_rc != 0:
            # Stderr from gen_process should have already been printed.
            print(
                f"\nError: Generation for '{description}' ('{' '.join(gen_cmd)}') failed with exit code {gen_rc}.",
                file=sys.stderr,
            )
            should_exit_code = gen_rc
            # Defer sys.exit until after footer is printed in finally
    except FileNotFoundError:  # For gen_process Popen itself failing
        print(
            f"Error: Command for '{description}' generation not found: {gen_cmd[0]}",
            file=sys.stderr,
        )
        if gen_process and gen_process.poll() is None:
            gen_process.terminate()
        if highlighter_process and highlighter_process.poll() is None:
            highlighter_process.terminate()
        should_exit_code = 1
    except (
        Exception
    ) as e:  # Other unexpected errors during Popen/streaming for gen_process
        print(
            f"An unexpected error occurred during '{description}' generation: {e}",
            file=sys.stderr,
        )
        if gen_process and gen_process.poll() is None:
            gen_process.terminate()
        if highlighter_process and highlighter_process.poll() is None:
            highlighter_process.terminate()
        should_exit_code = 1
    finally:
        # Ensure footer is printed and colors are reset
        sys.stdout.write(LLM_RESPONSE_COLOR)  # Re-assert color for footer
        print(llm_footer)  # print() adds a newline
        sys.stdout.write(RESET_COLOR)
        sys.stdout.write("\n")  # Extra newline for spacing after the block
        sys.stdout.flush()

    if should_exit_code is not None:
        sys.exit(should_exit_code)  # Exit now if an error occurred

    captured_text = output_capture.getvalue()
    output_capture.close()
    return captured_text


def main():
    syntax_highlight_enabled = False
    effective_syntax_cmd = None

    env_cmd_str = os.environ.get("HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD")
    if env_cmd_str:
        try:
            effective_syntax_cmd = shlex.split(env_cmd_str)
            if effective_syntax_cmd:
                syntax_highlight_enabled = True
            else:
                print(
                    f"Warning: HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD is set but resulted in an empty command: '{env_cmd_str}'. Highlighting disabled.",
                    file=sys.stderr,
                )
                env_cmd_str = None
        except ValueError as e:
            print(
                f"Warning: Could not parse HINATA_SYNTAX_HIGHLIGHT_PIPE_CMD: '{env_cmd_str}'. Error: {e}. Highlighting disabled.",
                file=sys.stderr,
            )
            env_cmd_str = None

    if not env_cmd_str and SYNTAX_HIGHLIGHT_PIPE_CMD:
        highlighter_executable = shutil.which(SYNTAX_HIGHLIGHT_PIPE_CMD[0])
        if highlighter_executable:
            syntax_highlight_enabled = True
            effective_syntax_cmd = SYNTAX_HIGHLIGHT_PIPE_CMD[:]
            effective_syntax_cmd[0] = highlighter_executable
        else:
            print(
                f"Info: Default syntax highlighter '{SYNTAX_HIGHLIGHT_PIPE_CMD[0]}' not found in PATH. Highlighting disabled.",
                file=sys.stderr,
            )

    parser = argparse.ArgumentParser(
        description="Interact with hinata LLM agent to execute shell commands.",
        epilog="Example: hnt-agent -m 'List files in current directory and show disk usage'",
    )
    parser.add_argument(
        "-s",
        "--system",
        help="System message string or path to system message file. "
        "Defaults to $XDG_CONFIG_HOME/hinata/config/prompts/main-shell_agent.md",
    )
    parser.add_argument(
        "-m",
        "--message",
        help="User instruction message. If not provided, $EDITOR will be opened.",
    )
    parser.add_argument("--model", help="Model to use (passed through to hnt-chat gen)")
    parser.add_argument(
        "--debug-unsafe",
        action="store_true",
        help="Enable unsafe debugging options in hinata tools",
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation steps before executing commands or adding messages.",
    )
    args = parser.parse_args()
    debug_log(args, "Arguments parsed:", args)

    session_name = None  # Will be set to <time_ns>
    original_exit_code = (
        0  # Stores the first critical error's exit code, or 0 for success
    )
    llm_navigator_idx = 0
    shell_apply_idx = 0

    try:
        # 0. Create headlesh session
        current_time_ns = time.time_ns()
        session_name = f"hnt-agent-{current_time_ns}"
        debug_log(args, f"Attempting to create headlesh session: {session_name}")

        # run_command will print errors and sys.exit if headlesh create fails or 'headlesh' is not found.
        # This SystemExit will be caught by the `except SystemExit as e:` block below.
        run_command(
            ["headlesh", "create", session_name],
            capture_output=True,  # Discard stdout by not using the return value's stdout
            check=True,  # Panic (sys.exit) on non-zero exit code or if command not found
            text=True,
        )
        debug_log(args, f"Headlesh session {session_name} created successfully.")

        # 1. Get system message
        debug_log(args, "Getting system message...")
        system_message = get_system_message(
            args.system, default_prompt_filename="main-shell_agent.md"
        )
        debug_log(args, "System message source:", args.system or "default path")
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

        # 3. Create a new chat conversation
        debug_log(args, "Creating new chat conversation via hnt-chat new...")
        hnt_chat_new_cmd = ["hnt-chat", "new"]
        debug_log(args, "hnt-chat new command:", hnt_chat_new_cmd)
        hnt_chat_new_result = run_command(
            hnt_chat_new_cmd, capture_output=True, check=True, text=True
        )
        conversation_dir = hnt_chat_new_result.stdout.strip()
        if not conversation_dir or not os.path.isdir(conversation_dir):
            # This path should ideally be caught by run_command if hnt-chat new has issues,
            # but as a safeguard for unexpected output format:
            print(
                f"Error: hnt-chat new did not return a valid directory path: '{conversation_dir}'",
                file=sys.stderr,
            )
            sys.exit(1)  # This SystemExit will be caught
        debug_log(args, "Conversation directory created:", conversation_dir)

        # 4. Add system message to conversation
        debug_log(args, "Adding system message via hnt-chat add...")
        hnt_chat_add_system_cmd = ["hnt-chat", "add", "system", "-c", conversation_dir]
        debug_log(args, "hnt-chat add system command:", hnt_chat_add_system_cmd)
        run_command(
            hnt_chat_add_system_cmd, stdin_content=system_message, check=True, text=True
        )
        debug_log(args, "System message added.")

        # 5. Add user request message to conversation
        debug_log(args, "Adding user request message via hnt-chat add...")
        hnt_chat_add_user_cmd = [
            "hnt-chat",
            "add",
            "user",
            "-c",
            conversation_dir,
        ]  # Reused later
        debug_log(args, "hnt-chat add user command (request):", hnt_chat_add_user_cmd)

        debug_log(args, "Defining hnt-chat add assistant command...")
        hnt_chat_add_assistant_cmd = [
            "hnt-chat",
            "add",
            "assistant",
            "-c",
            conversation_dir,
        ]
        debug_log(
            args, "hnt-chat add assistant command defined:", hnt_chat_add_assistant_cmd
        )

        # Wrap user instruction in <user_request> tags
        # Use .strip() on the instruction to avoid issues with leading/trailing newlines from user input interfering with tags
        wrapped_instruction = f"<user_request>\n{instruction.strip()}\n</user_request>"
        debug_log(
            args,
            "Wrapped user instruction content (first 100 chars):\n",
            textwrap.shorten(wrapped_instruction, width=100, placeholder="..."),
        )

        # --- START OF HINATA.MD AGENT INFO PROCESSING ---
        debug_log(args, "Attempting to load HINATA.md agent info...")
        hinata_md_content_raw = None  # Raw content from file
        try:
            config_home = os.environ.get(
                "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
            )
            hinata_md_path = Path(config_home) / "hinata" / "agent" / "HINATA.md"
            debug_log(args, f"Checking for HINATA.md at: {hinata_md_path}")
            if hinata_md_path.is_file():
                with open(hinata_md_path, "r", encoding="utf-8") as f:
                    hinata_md_content_raw = f.read()
                debug_log(
                    args,
                    f"Successfully read HINATA.md (raw length: {len(hinata_md_content_raw)}).",
                )
            else:
                debug_log(
                    args, f"HINATA.md ({hinata_md_path}) not found or is not a file."
                )
                # hinata_md_content_raw remains None
        except IOError as e:
            debug_log(
                args, f"IOError reading HINATA.md ('{hinata_md_path}'): {e}. Skipping."
            )
            hinata_md_content_raw = None  # Ensure it's None on error
        except Exception as e:  # Catch any other potential errors during file access
            debug_log(
                args,
                f"Unexpected error reading HINATA.md ('{hinata_md_path}'): {e}. Skipping.",
            )
            hinata_md_content_raw = None  # Ensure it's None on error

        if (
            hinata_md_content_raw is not None
        ):  # Check if file was read successfully (content might be empty string)
            hinata_md_content_stripped = hinata_md_content_raw.strip()
            if hinata_md_content_stripped:  # And it's not just whitespace
                wrapped_hinata_info = f"<info>\n{hinata_md_content_stripped}\n</info>"
                debug_log(args, "Adding HINATA.md content as user message...")
                # hnt_chat_add_user_cmd is defined above this block
                run_command(
                    hnt_chat_add_user_cmd,
                    stdin_content=wrapped_hinata_info,
                    check=True,
                    text=True,
                )
                debug_log(args, "HINATA.md content added to chat.")
            else:
                debug_log(
                    args,
                    "HINATA.md content was empty or all whitespace after stripping and was not added to chat.",
                )
        # If hinata_md_content_raw is None, it means file not found or error reading; this is already logged.
        # --- END OF HINATA.MD AGENT INFO PROCESSING ---

        # --- START OF NEW PRE-CANNED MESSAGE PROCESSING (pwd/os-release) ---
        # 1. Define and add Fake User Request for initial info
        fake_user_request_initial_info = "<user_request>\nCould you please check the current directory and some basic OS info?\n</user_request>"
        debug_log(args, "Defined fake user request for initial info.")
        debug_log(args, "Adding fake user request (initial info) via hnt-chat add...")
        run_command(
            hnt_chat_add_user_cmd,  # Defined earlier
            stdin_content=fake_user_request_initial_info,
            check=True,
            text=True,
        )
        debug_log(args, "Fake user request (initial info) added to chat.")

        # 2. Define and add Fake Assistant Shell Command for initial info
        fake_assistant_shell_command = """<hnt-shell>
pwd
cat /etc/os-release
</hnt-shell>"""
        debug_log(
            args, "Defined fake assistant shell command message for initial info."
        )
        debug_log(
            args,
            "Adding fake assistant shell command message (initial info) via hnt-chat add...",
        )
        run_command(
            hnt_chat_add_assistant_cmd,  # Defined earlier
            stdin_content=fake_assistant_shell_command,
            check=True,
            text=True,
        )
        debug_log(
            args, "Fake assistant shell command message (initial info) added to chat."
        )

        # 3. Run hnt-shell-apply with fake_assistant_shell_command
        debug_log(
            args,
            "Running hnt-shell-apply with fake assistant shell command (initial info) as stdin...",
        )
        hnt_shell_apply_cmd_fake_initial = ["hnt-shell-apply", session_name]
        debug_log(
            args,
            "hnt-shell-apply command (fake initial):",
            hnt_shell_apply_cmd_fake_initial,
        )

        shell_apply_process_fake_initial = run_command(
            hnt_shell_apply_cmd_fake_initial,
            stdin_content=fake_assistant_shell_command,
            capture_output=True,
            check=False,  # Manually check returncode
            text=True,
        )
        shell_apply_stdout_fake_initial = shell_apply_process_fake_initial.stdout
        shell_apply_stderr_fake_initial = shell_apply_process_fake_initial.stderr
        shell_apply_rc_fake_initial = shell_apply_process_fake_initial.returncode

        debug_log(
            args,
            f"hnt-shell-apply (fake initial) exited with code {shell_apply_rc_fake_initial}",
        )
        if shell_apply_stdout_fake_initial:
            debug_log(
                args,
                "hnt-shell-apply (fake initial) stdout (first 200 chars):\n",
                textwrap.shorten(
                    shell_apply_stdout_fake_initial, width=200, placeholder="..."
                ),
            )
        if shell_apply_stderr_fake_initial:
            debug_log(
                args,
                "hnt-shell-apply (fake initial) stderr (first 200 chars):\n",
                textwrap.shorten(
                    shell_apply_stderr_fake_initial, width=200, placeholder="..."
                ),
            )

        # Add hnt-shell-apply's stdout (from fake initial command) to conversation as user message
        # This output is not displayed to the user in the UI directly, only added to chat history for LLM context.
        # Script continues regardless of this step's success/failure, similar to old pre-canned logic.
        if (
            shell_apply_rc_fake_initial == 0
            and shell_apply_stdout_fake_initial
            and shell_apply_stdout_fake_initial.strip()
        ):
            debug_log(
                args,
                "Adding fake initial hnt-shell-apply stdout to chat as user message...",
            )
            run_command(
                hnt_chat_add_user_cmd,  # Defined earlier
                stdin_content=shell_apply_stdout_fake_initial,
                check=True,
                text=True,
            )
            debug_log(args, "Fake initial hnt-shell-apply stdout added to chat.")
        elif shell_apply_rc_fake_initial == 0 and (
            not shell_apply_stdout_fake_initial
            or not shell_apply_stdout_fake_initial.strip()
        ):
            debug_log(
                args,
                "Fake initial hnt-shell-apply produced no stdout or only whitespace. Nothing to add to chat.",
            )
        else:  # Error case for hnt-shell-apply (fake initial)
            debug_log(
                args,
                f"Fake initial hnt-shell-apply failed (rc={shell_apply_rc_fake_initial}) or produced no usable stdout ({len(shell_apply_stdout_fake_initial if shell_apply_stdout_fake_initial else '')} bytes received). Output not added to chat.",
            )
        # --- END OF NEW PRE-CANNED MESSAGE PROCESSING ---

        # 4. Add the REAL user instruction message to conversation (MOVED HERE)
        # wrapped_instruction was defined before this replaced block
        debug_log(args, "Adding REAL user request message via hnt-chat add...")
        debug_log(
            args, "hnt-chat add user command (REAL request):", hnt_chat_add_user_cmd
        )
        # Log content of wrapped REAL user instruction for context at point of addition
        debug_log(
            args,
            "Wrapped REAL user instruction content (first 100 chars):\n",
            textwrap.shorten(wrapped_instruction, width=100, placeholder="..."),
        )
        run_command(
            hnt_chat_add_user_cmd,
            stdin_content=wrapped_instruction,
            check=True,
            text=True,
        )
        debug_log(args, "REAL user request message added.")

        if not args.message:  # Show user query if it came from EDITOR
            header, footer = get_header_footer_lines("User Instruction <0>")
            sys.stdout.write(USER_INSTRUCTION_COLOR)
            print(header)
            # Ensure instruction ends with a newline for clean formatting
            if instruction.endswith("\n"):
                sys.stdout.write(instruction)
            else:
                print(instruction)  # print() will add a newline
            print(footer)
            sys.stdout.write(RESET_COLOR)
            sys.stdout.write("\n")  # Mimic hnt-edit's extra newline for spacing
            sys.stdout.flush()

        print(f"\nhnt-chat dir: {conversation_dir}", file=sys.stderr)

        # 6. Run hnt-chat gen to get INITIAL LLM message
        debug_log(args, "Running hnt-chat gen for initial message...")
        hnt_chat_gen_cmd = [
            "hnt-chat",
            "gen",
            "--include-reasoning",
            "--separate-reasoning",
            "--write",
            "--merge",
            "-c",
            conversation_dir,
        ]
        if args.model:
            hnt_chat_gen_cmd.extend(["--model", args.model])
            debug_log(args, "Using model:", args.model)
        if args.debug_unsafe:
            hnt_chat_gen_cmd.append("--debug-unsafe")
            debug_log(args, "Passing --debug-unsafe to hnt-chat gen")
        debug_log(args, "hnt-chat gen command (initial):", hnt_chat_gen_cmd)

        llm_message_raw = stream_and_capture_llm_output(
            args,
            hnt_chat_gen_cmd,
            syntax_highlight_enabled,
            effective_syntax_cmd,
            description=f"LLM Navigator <{llm_navigator_idx}>",
        )
        llm_navigator_idx += 1
        debug_log(
            args, "Captured hnt-chat gen output length (initial):", len(llm_message_raw)
        )
        debug_log(
            args,
            "LLM Raw Message (initial, first 200 chars):\n",
            textwrap.shorten(llm_message_raw, width=200, placeholder="..."),
        )

        if not llm_message_raw.strip():
            debug_log(args, "Initial hnt-chat gen output is empty or whitespace only.")
            print(
                "Warning: LLM produced no initial output. Exiting.",
                file=sys.stderr,
            )
            # original_exit_code remains 0, script will exit cleanly via finally.
        else:
            # LLM Message has already been streamed and displayed.
            # (hnt-chat dir print moved to earlier in the script)

            # Start the interaction loop
            while True:
                # Confirmation before running hnt-shell-apply (using current llm_message_raw)
                if not args.no_confirm:
                    try:
                        print("")  # Ensure prompt is on a new line
                        user_choice_apply = (
                            input("proceed to hnt-shell-apply (y/n)? ").strip().lower()
                        )
                        if user_choice_apply != "y":
                            print(
                                "Aborted by user before hnt-shell-apply.",
                                file=sys.stderr,
                            )
                            break  # EXIT LOOP (cleanly)
                    except EOFError:
                        print(
                            "\nEOFError: No input for hnt-shell-apply confirmation. Aborting.",
                            file=sys.stderr,
                        )
                        sys.exit(1)  # Error exit, caught by outer try/except

                # Run hnt-shell-apply (adapting original 7)
                debug_log(args, "Running hnt-shell-apply with LLM message as stdin...")
                hnt_shell_apply_cmd = ["hnt-shell-apply", session_name]
                debug_log(args, "hnt-shell-apply command:", hnt_shell_apply_cmd)

                shell_apply_process = run_command(
                    hnt_shell_apply_cmd,
                    stdin_content=llm_message_raw,
                    capture_output=True,
                    check=False,  # Manually check returncode
                    text=True,
                )
                shell_apply_stdout = shell_apply_process.stdout
                shell_apply_stderr = shell_apply_process.stderr
                shell_apply_rc = shell_apply_process.returncode

                debug_log(args, f"hnt-shell-apply exited with code {shell_apply_rc}")
                if shell_apply_stdout:
                    debug_log(
                        args,
                        "hnt-shell-apply stdout (first 200 chars):\n",
                        textwrap.shorten(
                            shell_apply_stdout, width=200, placeholder="..."
                        ),
                    )
                if shell_apply_stderr:
                    debug_log(
                        args,
                        "hnt-shell-apply stderr (first 200 chars):\n",
                        textwrap.shorten(
                            shell_apply_stderr, width=200, placeholder="..."
                        ),
                    )

                # Print hnt-shell-apply's output (adapting original 8)
                if shell_apply_stdout:
                    tool_header, tool_footer = get_header_footer_lines(
                        f"hnt-shell-apply <{shell_apply_idx}>"
                    )
                    sys.stdout.write(
                        f"\n{TOOL_OUTPUT_COLOR}"
                    )  # Newline before header, start color
                    print(tool_header)  # print() adds newline

                    sys.stdout.write(shell_apply_stdout)  # Content
                    if not shell_apply_stdout.endswith(
                        "\n"
                    ):  # Ensure newline after content
                        sys.stdout.write("\n")

                    print(tool_footer)  # print() adds newline
                    sys.stdout.write(RESET_COLOR)  # Reset color
                    sys.stdout.write("\n")  # Extra newline for spacing
                    sys.stdout.flush()
                    shell_apply_idx += 1

                if shell_apply_stderr:
                    sys.stderr.write("\n--- Error output from hnt-shell-apply ---\n")
                    sys.stderr.write(shell_apply_stderr)
                    if not shell_apply_stderr.endswith("\n"):
                        sys.stderr.write("\n")
                sys.stderr.flush()

                # Check hnt-shell-apply return code
                if shell_apply_rc != 0:
                    print(
                        f"\nError: hnt-shell-apply exited with code {shell_apply_rc}.",
                        file=sys.stderr,
                    )
                    original_exit_code = shell_apply_rc
                    break  # EXIT LOOP (error)

                # Add hnt-shell-apply's stdout to conversation (adapting original 8b)
                if not shell_apply_stdout:
                    debug_log(
                        args,
                        "hnt-shell-apply produced no stdout. Ending interaction loop.",
                    )
                    print(
                        "hnt-shell-apply produced no stdout. Ending interaction loop.",
                        file=sys.stderr,
                    )
                    break  # EXIT LOOP (cleanly, no new info to process)

                proceed_add_to_chat = True
                if not args.no_confirm:
                    try:
                        print("")
                        user_choice_add_msg = (
                            input("add hnt-shell-apply output to user msg (y/n)? ")
                            .strip()
                            .lower()
                        )
                        if user_choice_add_msg != "y":
                            proceed_add_to_chat = False
                            print(
                                "User chose not to add hnt-shell-apply output. Ending interaction loop.",
                                file=sys.stderr,
                            )
                            break  # EXIT LOOP (cleanly, user choice)
                    except EOFError:
                        print(
                            "\nEOFError: No input for adding hnt-shell-apply output. Aborting.",
                            file=sys.stderr,
                        )
                        sys.exit(1)  # Error exit, caught by outer try/except

                if proceed_add_to_chat:
                    debug_log(
                        args, "Adding hnt-shell-apply stdout to chat conversation..."
                    )
                    run_command(  # hnt_chat_add_user_cmd is defined outside the loop
                        hnt_chat_add_user_cmd,
                        stdin_content=shell_apply_stdout,
                        check=True,  # sys.exit on error
                        text=True,
                    )
                    debug_log(args, "hnt-shell-apply stdout added to chat.")
                # else: if proceed_add_to_chat is False and not args.no_confirm, we broke the loop

                # Generate NEXT LLM message for the next iteration
                debug_log(args, "Generating next LLM response...")
                # hnt_chat_gen_cmd is already defined and includes model/debug flags

                next_llm_message_raw = stream_and_capture_llm_output(
                    args,
                    hnt_chat_gen_cmd,
                    syntax_highlight_enabled,
                    effective_syntax_cmd,
                    description=f"LLM Navigator <{llm_navigator_idx}>",
                )
                llm_navigator_idx += 1

                debug_log(
                    args,
                    "Captured hnt-chat gen output length (next iter):",
                    len(next_llm_message_raw),
                )
                debug_log(
                    args,
                    "LLM Raw Message (next iter, first 200 chars):\n",
                    textwrap.shorten(
                        next_llm_message_raw, width=200, placeholder="..."
                    ),
                )

                if not next_llm_message_raw.strip():
                    debug_log(args, "hnt-chat gen produced no further output.")
                    print(
                        "Warning: LLM produced no further output. Ending interaction loop.",
                        file=sys.stderr,
                    )
                    break  # EXIT LOOP (cleanly, no more LLM response)

                llm_message_raw = next_llm_message_raw  # Update for the next iteration
                # Loop continues

            # End of while True loop
        # End of else block (if initial llm_message_raw was not empty)

    except SystemExit as e:
        # Catches sys.exit calls from run_command (e.g., if hnt-chat or headlesh create fails)
        # or any other explicit sys.exit within the try block.
        original_exit_code = e.code if e.code is not None else 1
        # The function that called sys.exit (e.g. run_command) should have already printed an error.
    except Exception as e:
        # Catch any other unexpected exceptions from the main logic
        print(
            f"An unexpected error occurred in hnt-agent's main logic: {e}",
            file=sys.stderr,
        )
        # For more detailed debugging, one might add:
        # import traceback
        # traceback.print_exc(file=sys.stderr)
        original_exit_code = 1  # General error code
    finally:
        if session_name:  # Only attempt to exit if session_name was set
            debug_log(args, f"Attempting to exit headlesh session: {session_name}")
            try:
                # Call subprocess.run directly to have full control over error handling,
                # avoiding run_command's default sys.exit behavior in this cleanup phase.
                headlesh_exit_cmd = ["headlesh", "exit", session_name]
                debug_log(args, f"Executing: {' '.join(headlesh_exit_cmd)}")

                exit_proc = subprocess.run(
                    headlesh_exit_cmd,
                    capture_output=True,  # Capture to check, but discard output unless error
                    text=True,
                    check=False,  # Manually check returncode
                )

                if exit_proc.returncode != 0:
                    # Log error if headlesh exit fails
                    error_message = f"Error: 'headlesh exit {session_name}' failed with exit code {exit_proc.returncode}."
                    print(error_message, file=sys.stderr)
                    # headlesh might output useful info to stdout or stderr even on failure
                    if exit_proc.stdout and exit_proc.stdout.strip():
                        print(
                            f"Stdout from 'headlesh exit':\n{exit_proc.stdout.strip()}",
                            file=sys.stderr,
                        )
                    if exit_proc.stderr and exit_proc.stderr.strip():
                        print(
                            f"Stderr from 'headlesh exit':\n{exit_proc.stderr.strip()}",
                            file=sys.stderr,
                        )

                    # If the main operations were successful (original_exit_code == 0),
                    # but closing headlesh failed, this failure becomes the script's exit code.
                    if original_exit_code == 0:
                        original_exit_code = exit_proc.returncode
                else:
                    debug_log(
                        args, f"Headlesh session {session_name} exited successfully."
                    )

            except FileNotFoundError:
                # This occurs if 'headlesh' command is not found on the system.
                print(
                    f"Error: 'headlesh' command not found. Could not cleanly exit session {session_name}.",
                    file=sys.stderr,
                )
                if original_exit_code == 0:
                    original_exit_code = 1  # Mark as error if this was the only problem
            except Exception as e_exit:
                # Catch any other unexpected error during the headlesh exit attempt
                print(
                    f"An unexpected error occurred while trying to exit headlesh session '{session_name}': {e_exit}",
                    file=sys.stderr,
                )
                if original_exit_code == 0:
                    original_exit_code = 1  # Mark as error

        # Finally, exit with the determined overall exit code.
        if original_exit_code != 0:
            sys.exit(original_exit_code)
        # If original_exit_code is still 0, script exits successfully (implicitly returns 0).


if __name__ == "__main__":
    main()
