#!/usr/bin/env python3
import sys
import argparse
import subprocess
import os
import fcntl
import select
import shlex
import signal
from collections import deque


def render(height, cmd, status, output_buffer):
    """Renders the TUI box."""
    try:
        term_width, _ = os.get_terminal_size()
    except OSError:
        term_width = 80  # Default if not a real TTY

    # Restore cursor to the saved top-left position of our TUI window
    sys.stdout.write("\033[u")

    # Top border
    title = f" CMD: {cmd} "
    if len(title) > term_width - 2:
        title = title[: term_width - 5] + "... "
    sys.stdout.write("\033[2K")  # Clear line
    sys.stdout.write(f"┌{title.center(term_width - 2, '─')}┐")

    # Content
    content_height = height - 2
    visible_lines = []
    if content_height > 0:
        visible_lines = list(output_buffer)[-content_height:]

    for i in range(max(0, content_height)):
        sys.stdout.write(f"\033[1B\r")  # Move down one line, to column 0
        sys.stdout.write("\033[2K")
        line_content = ""
        if i < len(visible_lines):
            line_content = visible_lines[i]

        if len(line_content) > term_width - 4:
            line_content = line_content[: term_width - 5] + "…"

        sys.stdout.write(f"│ {line_content.ljust(term_width - 4)} │")

    # Bottom border
    if height > 1:
        sys.stdout.write(f"\033[1B\r")
        sys.stdout.write("\033[2K")

    footer = f" {status} "
    sys.stdout.write(f"└{footer.center(term_width - 2, '─')}┘")

    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="Run a command in a TUI window.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example:
  # Create a script that prints the date every second for 5s
  echo 'for i in $(seq 1 5); do date; sleep 1; done' > /tmp/test.sh
  chmod +x /tmp/test.sh
  ./minimal_tui.py --height 10 --cmd /tmp/test.sh
""",
    )
    parser.add_argument(
        "--height", type=int, required=True, help="Height of the TUI window."
    )
    parser.add_argument("--cmd", type=str, required=True, help="Command to execute.")
    args = parser.parse_args()

    HEIGHT = args.height
    CMD = args.cmd

    if not sys.stdout.isatty():
        print("Not a TTY, can't create TUI. Aborting.", file=sys.stderr)
        sys.exit(1)

    # Setup TUI area: reserve space and save cursor position
    sys.stdout.write("\033[?25l")  # Hide cursor
    for _ in range(HEIGHT):
        print()
    sys.stdout.write(f"\033[{HEIGHT}A")  # Move cursor up
    sys.stdout.write("\033[s")  # Save cursor position for TUI root

    output_buffer = deque()
    incomplete_line = b""
    proc = None
    status = "STARTING"
    interrupted = False

    try:
        proc = subprocess.Popen(
            shlex.split(CMD),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            preexec_fn=os.setsid,
        )

        flags = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        poller = select.poll()
        poller.register(proc.stdout, select.POLLIN)

        status = "RUNNING"

        while proc.poll() is None or poller.poll(0):
            if poller.poll(100):
                try:
                    data = proc.stdout.read()
                    if data:
                        lines = (incomplete_line + data).split(b"\n")
                        incomplete_line = lines.pop()
                        for line in lines:
                            output_buffer.append(line.decode("utf-8", errors="replace"))
                except IOError:
                    pass

            if proc.poll() is not None:
                status = f"DONE (rc={proc.returncode})"

            render(HEIGHT, CMD, status, output_buffer)

    except KeyboardInterrupt:
        interrupted = True
        status = "KILLED (Ctrl+C)"
    finally:
        if incomplete_line:
            output_buffer.append(incomplete_line.decode("utf-8", errors="replace"))

        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=1)
                if not interrupted:
                    status = f"TERMINATED (rc={proc.returncode})"
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=1)
                    if not interrupted:
                        rc = proc.returncode if proc.poll() is not None else "?"
                        status = f"KILLED (rc={rc})"
                except Exception:
                    if not interrupted:
                        status = "KILLED (force failed)"
        elif proc and not interrupted:
            status = f"DONE (rc={proc.returncode})"

        # Final render
        render(HEIGHT, CMD, status, output_buffer)

        # Cleanup cursor and position
        sys.stdout.write("\033[u")  # Go to top of TUI
        sys.stdout.write(f"\033[{HEIGHT}B\r")  # Go below TUI
        sys.stdout.write("\033[?25h")  # Show cursor
        sys.stdout.flush()
        print()  # Extra newline for clean prompt


if __name__ == "__main__":
    main()
