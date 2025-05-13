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


# Command to pipe output through for syntax highlighting
SYNTAX_HIGHLIGHT_PIPE_CMD = ["hlmd-st"]


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
    args = parser.parse_args()
    debug_log(args, "Arguments parsed:", args)

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
        args, "User instruction source:", "args.message" if args.message else "$EDITOR"
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
        print(
            f"Error: hnt-chat new did not return a valid directory path: '{conversation_dir}'",
            file=sys.stderr,
        )
        sys.exit(1)
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
    run_command(hnt_chat_add_user_cmd, stdin_content=instruction, check=True, text=True)
    debug_log(args, "User request message added.")

    if not args.message:  # Show user query if it came from EDITOR
        print(
            "-" * 40, file=sys.stdout
        )  # Print to stdout for visibility before LLM output
        print(instruction, file=sys.stdout)
        print("-" * 40 + "\n", file=sys.stdout)
        sys.stdout.flush()

    # 6. Run hnt-chat gen to get LLM message
    debug_log(args, "Running hnt-chat gen...")
    hnt_chat_gen_cmd = ["hnt-chat", "gen", "--write", "-c", conversation_dir]
    if args.model:
        hnt_chat_gen_cmd.extend(["--model", args.model])
        debug_log(args, "Using model:", args.model)
    if args.debug_unsafe:
        hnt_chat_gen_cmd.append("--debug-unsafe")
        debug_log(args, "Passing --debug-unsafe to hnt-chat gen")
    debug_log(args, "hnt-chat gen command:", hnt_chat_gen_cmd)

    gen_process_result = run_command(
        hnt_chat_gen_cmd, capture_output=True, check=True, text=True
    )
    llm_message_raw = gen_process_result.stdout
    debug_log(args, "Captured hnt-chat gen output length:", len(llm_message_raw))
    debug_log(
        args,
        "LLM Raw Message (first 200 chars):\n",
        textwrap.shorten(llm_message_raw, width=200, placeholder="..."),
    )

    if not llm_message_raw.strip():
        debug_log(args, "hnt-chat gen output is empty or whitespace only.")
        print(
            "Warning: LLM produced no output. Continuing to hnt-shell-apply.",
            file=sys.stderr,
        )
        # It's possible an empty response implies "do nothing" or is an error the user needs to see via hnt-shell-apply.

    # 6a. Pipe LLM message to hlmd-st (if found) -> hnt-agent's stdout
    debug_log(args, "Displaying LLM message (via syntax highlighter if enabled)...")
    sys.stdout.write("\n--- LLM Response ---\n")  # Marker for clarity
    if syntax_highlight_enabled:
        debug_log(args, "Using syntax highlighter command:", effective_syntax_cmd)
        try:
            highlight_process = subprocess.Popen(
                effective_syntax_cmd,
                stdin=subprocess.PIPE,
                stdout=sys.stdout,
                stderr=sys.stderr,
                text=True,
            )
            highlight_process.communicate(input=llm_message_raw)
            if highlight_process.returncode != 0:
                debug_log(
                    args,
                    f"Syntax highlighter exited with code {highlight_process.returncode}",
                )
        except FileNotFoundError:
            debug_log(
                args,
                f"Syntax highlighter command '{effective_syntax_cmd[0]}' not found. Printing raw.",
            )
            print(
                f"Warning: Syntax highlighter '{effective_syntax_cmd[0]}' not found. Printing raw output.",
                file=sys.stderr,
            )
            sys.stdout.write(llm_message_raw)
        except Exception as e:
            debug_log(args, f"Error running syntax highlighter: {e}. Printing raw.")
            print(
                f"Warning: Error during syntax highlighting: {e}. Printing raw output.",
                file=sys.stderr,
            )
            sys.stdout.write(llm_message_raw)
    else:
        sys.stdout.write(llm_message_raw)

    if llm_message_raw and not llm_message_raw.endswith("\n"):
        sys.stdout.write("\n")  # Ensure newline for separation
    sys.stdout.flush()

    print(f"\nhnt-chat dir: {conversation_dir}", file=sys.stderr)

    # 7. Pipe the raw LLM message to hnt-shell-apply and capture its output
    debug_log(args, "Running hnt-shell-apply with LLM message as stdin...")
    hnt_shell_apply_cmd = ["hnt-shell-apply"]
    debug_log(args, "hnt-shell-apply command:", hnt_shell_apply_cmd)

    shell_apply_process = run_command(
        hnt_shell_apply_cmd,
        stdin_content=llm_message_raw,
        capture_output=True,  # We need its stdout and stderr
        check=False,  # Manually check returncode
        text=True,
    )

    shell_apply_stdout = shell_apply_process.stdout
    shell_apply_stderr = shell_apply_process.stderr  # Useful if it fails
    shell_apply_rc = shell_apply_process.returncode

    debug_log(args, f"hnt-shell-apply exited with code {shell_apply_rc}")
    if shell_apply_stdout:
        debug_log(
            args,
            "hnt-shell-apply stdout (first 200 chars):\n",
            textwrap.shorten(shell_apply_stdout, width=200, placeholder="..."),
        )
    if shell_apply_stderr:
        debug_log(
            args,
            "hnt-shell-apply stderr (first 200 chars):\n",
            textwrap.shorten(shell_apply_stderr, width=200, placeholder="..."),
        )

    # 8. Print hnt-shell-apply's stdout and stderr.
    if shell_apply_stdout:
        sys.stdout.write("\n--- Output from hnt-shell-apply ---\n")  # Marker
        sys.stdout.write(shell_apply_stdout)
        if not shell_apply_stdout.endswith("\n"):
            sys.stdout.write("\n")
    sys.stdout.flush()

    if shell_apply_stderr:  # Print its stderr to our stderr
        sys.stderr.write("\n--- Error output from hnt-shell-apply ---\n")  # Marker
        sys.stderr.write(shell_apply_stderr)
        if not shell_apply_stderr.endswith("\n"):
            sys.stderr.write("\n")
    sys.stderr.flush()

    # 8b. Add hnt-shell-apply's stdout to the conversation as another user message
    # Per request: "add it (stdout of hnt-shell-apply) to the same conversation as another user message"
    # This should happen regardless of hnt-shell-apply's success, as errors might be useful context.
    if shell_apply_stdout:  # Only add if there IS stdout
        debug_log(args, "Adding hnt-shell-apply stdout to chat conversation...")
        run_command(
            hnt_chat_add_user_cmd,  # Reusing the command list from earlier
            stdin_content=shell_apply_stdout,
            check=True,  # This 'hnt-chat add' operation should ideally succeed
            text=True,
        )
        debug_log(args, "hnt-shell-apply stdout added to chat.")
    else:
        debug_log(args, "hnt-shell-apply produced no stdout; not adding to chat.")

    if shell_apply_rc != 0:
        print(
            f"\nError: hnt-shell-apply exited with code {shell_apply_rc}.",
            file=sys.stderr,
        )
        sys.exit(shell_apply_rc)
    else:
        debug_log(args, "hnt-shell-apply finished successfully.")


if __name__ == "__main__":
    main()
