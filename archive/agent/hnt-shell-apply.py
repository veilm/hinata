#!/usr/bin/env python3

import sys
import os
import argparse
import subprocess
import re


def find_hnt_shell_commands(input_text):
    """
    Finds the last (i.e., the most recently closed) valid <hnt-shell> block in the input text.
    The tags must be on their own lines. Only the last block is returned.
    Returns a list containing the content string of the block (so the list has at most one element),
    or an empty list if no valid block is found.
    """
    lines = input_text.split("\n")
    # Find the last occurrence of the closing tag
    closing_index = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "</hnt-shell>":
            closing_index = i
            break

    if closing_index is None:
        return []  # no closing tag found

    # Now, look upwards for the nearest opening tag
    opening_index = None
    for i in range(closing_index - 1, -1, -1):
        if lines[i] == "<hnt-shell>":
            opening_index = i
            break

    if opening_index is None:
        return []  # no opening tag found

    content_lines = lines[opening_index + 1 : closing_index]
    content = "\n".join(content_lines)
    return [content]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "hnt-shell-apply: Takes hnt-shell formatted stdin, executes it via headlesh, "
            "and returns structured output.\n\n"
            'Usage: echo "<hnt-shell>\\ncommand\\n</hnt-shell>" | '
            "hnt-shell-apply <session_id> [--always-streams] [--exclude-executed] [--escape-backticks]"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("session_id", help="The session ID for headlesh.")
    parser.add_argument(
        "--always-streams",
        action="store_true",
        help="Always include <stdout> and <stderr> sections in the output, even if they are empty.",
    )
    parser.add_argument(
        "--exclude-executed",
        action="store_true",
        help="Do not include the <executed> section in the output.",
    )
    parser.add_argument(
        "--escape-backticks",
        action="store_true",
        help="Escape backticks in the input (` -> \\`).",
    )

    args = parser.parse_args()

    fifo_path = f"/tmp/headlesh_sessions/{args.session_id}/cmd.fifo"
    if not os.path.exists(fifo_path):
        sys.stderr.write(f"Error: FIFO {fifo_path} does not exist.\n")
        sys.exit(1)

    input_buffer = sys.stdin.read()

    if args.escape_backticks:
        # Use a negative lookbehind to replace backticks that are not already preceded by a backslash.
        # This fulfills the request to skip escaping if one or more backslashes are already present.
        input_buffer = re.sub(r"(?<!\\)`", r"\\`", input_buffer)

    hnt_shell_blocks = find_hnt_shell_commands(input_buffer)

    if not hnt_shell_blocks:
        sys.stderr.write(
            "Error: No valid <hnt-shell>...</hnt-shell> block found where tags are on their own lines.\n"
        )
        sys.exit(2)

    # "extract the content of the very last one, not including trailing whitespace on either side"
    # This means stripping the whole content block.
    content_from_last_block = hnt_shell_blocks[-1]
    # This content is used for both <executed> tag and for headlesh input, after stripping.
    command_to_execute_and_display = content_from_last_block.strip()

    # Execute the command using headlesh
    try:
        process = subprocess.run(
            ["headlesh", "exec", args.session_id],
            input=command_to_execute_and_display,
            text=True,  # Work with text (strings) for input/output
            capture_output=True,  # Capture stdout and stderr
            check=False,  # Do not raise an exception for non-zero exit codes
        )
        headlesh_stdout = process.stdout
        headlesh_stderr = process.stderr
        headlesh_exit_status = process.returncode
    except FileNotFoundError:
        sys.stderr.write(
            f"Error: 'headlesh' command not found. Make sure it is in your PATH.\n"
        )
        sys.exit(1)
    except Exception as e:  # Catch other potential subprocess errors
        sys.stderr.write(f"Error executing 'headlesh': {e}\n")
        sys.exit(1)

    # Prepare output parts
    output_parts = []
    output_parts.append("<hnt-shell_results>")

    if not args.exclude_executed:
        output_parts.append("<executed>")
        # The content for <executed> is the stripped command block.
        output_parts.append(command_to_execute_and_display)
        output_parts.append("</executed>")

    if args.always_streams or headlesh_stdout:  # Note: empty string "" is Falsy
        output_parts.append("<stdout>")
        # Remove a single trailing newline, if present, to avoid duplication by joiner
        processed_stdout = headlesh_stdout
        if processed_stdout.endswith("\n"):
            processed_stdout = processed_stdout[:-1]
        output_parts.append(processed_stdout)
        output_parts.append("</stdout>")

    if args.always_streams or headlesh_stderr:  # Note: empty string "" is Falsy
        output_parts.append("<stderr>")
        # Remove a single trailing newline, if present, to avoid duplication by joiner
        processed_stderr = headlesh_stderr
        if processed_stderr.endswith("\n"):
            processed_stderr = processed_stderr[:-1]
        output_parts.append(processed_stderr)
        output_parts.append("</stderr>")

    output_parts.append("<exit_status>")
    output_parts.append(str(headlesh_exit_status))
    output_parts.append("</exit_status>")

    output_parts.append("</hnt-shell_results>")

    # Write the final output to stdout
    # Each part (tag or content) is on its own line, joined by newlines.
    sys.stdout.write("\n".join(output_parts) + "\n")


if __name__ == "__main__":
    main()
