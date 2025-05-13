#!/usr/bin/env python3

import sys
import os
import argparse
import subprocess


def find_hnt_shell_commands(input_text):
    """
    Scans the input text for <hnt-shell> ... </hnt-shell> blocks where
    tags are on their own lines.
    Returns a list of content strings from valid blocks.
    """
    lines = input_text.split("\n")
    valid_blocks_contents = []

    i = 0
    while i < len(lines):
        # Check for opening tag on its own line
        if lines[i] == "<hnt-shell>":
            # open_tag_line_idx = i # Not strictly needed beyond this point with collector
            content_lines_collector = []
            j = i + 1  # Start looking for content or closing tag from next line
            while j < len(lines):
                # Check for closing tag on its own line
                if lines[j] == "</hnt-shell>":
                    # Found a valid block. Content is lines between open_tag_line_idx and j.
                    current_block_content = "\n".join(content_lines_collector)
                    valid_blocks_contents.append(current_block_content)
                    i = j  # Continue search after this closing tag
                    break
                # Collect the current line as part of the content
                content_lines_collector.append(lines[j])
                j += 1
            # If the inner loop finished without break, it means an opening tag
            # was found but not its corresponding closing tag.
            # In this case, 'i' will be incremented by the outer loop at its end,
            # effectively skipping this unclosed tag and its content.
            # The outer loop continues from 'j' (if block found) or 'i+1' (if no block or unclosed).
        i += 1

    return valid_blocks_contents


def main():
    parser = argparse.ArgumentParser(
        description=(
            "hnt-shell-apply: Takes hnt-shell formatted stdin, executes it via headlesh, "
            "and returns structured output.\n\n"
            'Usage: echo "<hnt-shell>\\ncommand\\n</hnt-shell>" | '
            "hnt-shell-apply <session_id> [--always-streams] [--exclude-executed]"
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

    args = parser.parse_args()

    fifo_path = f"/tmp/headlesh_sessions/{args.session_id}/cmd.fifo"
    if not os.path.exists(fifo_path):
        sys.stderr.write(f"Error: FIFO {fifo_path} does not exist.\n")
        sys.exit(1)

    input_buffer = sys.stdin.read()

    hnt_shell_blocks = find_hnt_shell_commands(input_buffer)

    if not hnt_shell_blocks:
        sys.stderr.write(
            "Error: No valid <hnt-shell>...</hnt-shell> block found where tags are on their own lines.\n"
        )
        sys.exit(1)

    if len(hnt_shell_blocks) > 1:
        sys.stderr.write(
            "Warning: Multiple valid <hnt-shell> blocks found. Only the last one will be considered.\n"
        )

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
