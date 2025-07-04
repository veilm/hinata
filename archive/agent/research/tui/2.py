#!/usr/bin/env python3
import os
import pty
import sys
import select
import tty
import termios
import fcntl
import struct
import signal
import atexit

# The desired height of the box for nvim
BOX_HEIGHT = 20


def get_cursor_pos():
    """Gets the current cursor position (row, col) using ANSI escape sequences."""
    if not sys.stdout.isatty():
        return 1, 1

    # Save original terminal settings
    original_termios = termios.tcgetattr(sys.stdin)
    try:
        # Set terminal to raw mode to read response without waiting for Enter
        tty.setraw(sys.stdin.fileno())

        # Ask for cursor position (DSR - Device Status Report)
        sys.stdout.write("\x1b[6n")
        sys.stdout.flush()

        response = ""
        while True:
            char = sys.stdin.read(1)
            # 'R' is the terminator for the cursor position report
            if not char or char == "R":
                break
            response += char

        # Parse response: \x1b[<row>;<col>R
        if response.startswith("\x1b["):
            response = response[2:]
            parts = response.split(";")
            if len(parts) == 2:
                row = int(parts[0])
                col = int(parts[1])
                return row, col
    except (ValueError, IndexError, OSError):
        # Fallback if any error occurs
        pass
    finally:
        # Restore terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_termios)

    # Fallback if position reporting fails
    return 10, 1


def main():
    """
    Main function to set up the pseudo-terminal environment for nvim.
    """
    # 1. Print some content to simulate shell history being preserved above
    print("This is a proof of concept for running a program in a 'box'.")
    print("\n--- Shell History Above ---\n")
    print("$ echo 'Hello from history'")
    print("Hello from history")
    print("\n--- nvim will start below ---")

    # Get terminal size
    try:
        term_rows, term_cols = os.get_terminal_size()
    except OSError:
        print("Could not get terminal size. Exiting.")
        sys.exit(1)

    # Get the row where our box will start.
    # The cursor's current line will be the first line of our box.
    start_row, _ = get_cursor_pos()

    # We add a newline to visually separate, so the box starts on the next line
    print()  # moves cursor to the next line
    start_row += 1

    # Adjust box height if it doesn't fit on screen
    actual_box_height = min(BOX_HEIGHT, term_rows - start_row + 1)
    if actual_box_height <= 3:  # Need a few lines for nvim to be usable
        print(
            f"Not enough space on terminal to draw a box. Needs > 3 lines, has {actual_box_height}."
        )
        sys.exit(1)

    # 2. Fork the process to create a child for nvim and a parent controller
    pid, master_fd = pty.fork()

    if pid == pty.CHILD:
        # --- Child Process ---
        # This process will be replaced by nvim.

        # Set the window size of the pseudo-terminal to our box dimensions
        child_winsize = struct.pack("HHHH", actual_box_height, term_cols, 0, 0)
        fcntl.ioctl(sys.stdout.fileno(), termios.TIOCSWINSZ, child_winsize)

        # Launch nvim, replacing this child process
        # Use a common TERM type for better compatibility
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        try:
            os.execvpe("nvim", ["nvim"], env)
        except FileNotFoundError:
            # The child process cannot easily print an error message after the pty is set up.
            # We exit with a specific status code that the parent can check for.
            sys.exit(127)

    else:
        # --- Parent Process ---
        # This process acts as the terminal emulator middleman.

        # Save terminal settings to restore on exit
        original_termios = termios.tcgetattr(sys.stdin)

        # Cleanup tasks to run when the script exits
        def cleanup():
            # Restore original terminal settings
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_termios)
            # Reset scrolling region to full screen
            sys.stdout.write("\x1b[r")
            # Move cursor below our box
            sys.stdout.write(f"\x1b[{start_row + actual_box_height};1H")
            sys.stdout.flush()
            print("my-tmux exited.")

        atexit.register(cleanup)

        # Set the real terminal to raw mode to pass all keystrokes through
        tty.setraw(sys.stdin.fileno())

        # Handle terminal window resizing
        def sigwinch_handler(signum, frame):
            nonlocal term_cols
            try:
                h, w = os.get_terminal_size()
                term_cols = w
                # Propagate the new size to the child's pty
                child_winsize = struct.pack("HHHH", actual_box_height, term_cols, 0, 0)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, child_winsize)
            except OSError:
                pass

        signal.signal(signal.SIGWINCH, sigwinch_handler)

        # 3. Set up the terminal "box" using ANSI escape codes
        # Set the scrolling region to confine nvim's output
        sys.stdout.write(f"\x1b[{start_row};{start_row + actual_box_height - 1}r")
        # Move the cursor to the top-left of our box
        sys.stdout.write(f"\x1b[{start_row};1H")
        sys.stdout.flush()

        # 4. Main loop: shuttle data between user's terminal and nvim's pty
        while True:
            try:
                # Wait for data from stdin or the child process, with a timeout
                readable, _, _ = select.select([sys.stdin, master_fd], [], [], 0.1)
            except select.error as e:
                # SIGWINCH resize can interrupt select
                if e.args[0] == 4:  # EINTR
                    continue
                raise

            # Check if child process has exited
            try:
                exited_pid, exit_status = os.waitpid(pid, os.WNOHANG)
                if exited_pid == pid:
                    if os.WIFEXITED(exit_status) and os.WEXITSTATUS(exit_status) == 127:
                        # This checks for the specific exit code from the child if execvpe fails.
                        print("\r\nError: `nvim` failed to execute in child process.")
                    break
            except OSError:
                # Child process not found, probably already exited.
                break

            if sys.stdin in readable:
                user_input = os.read(sys.stdin.fileno(), 1024)
                if user_input:
                    os.write(master_fd, user_input)
                else:  # EOF from user (e.g., Ctrl+D)
                    # Close master fd to signal EOF to child
                    os.close(master_fd)

            if master_fd in readable:
                try:
                    child_output = os.read(master_fd, 1024)
                except OSError:
                    # This can happen if child closes the pty slave and exits abruptly
                    child_output = None

                if child_output:
                    # By setting the scroll region, we don't need to parse and
                    # translate ANSI codes. The terminal handles confining output
                    # to the box. This is a powerful simplification.
                    sys.stdout.buffer.write(child_output)
                    sys.stdout.flush()
                else:  # EOF from child process (nvim exited)
                    break


if __name__ == "__main__":
    # Check if nvim is available in the user's PATH
    if not any(
        os.access(os.path.join(path, "nvim"), os.X_OK)
        for path in os.environ.get("PATH", "").split(os.pathsep)
    ):
        print("`nvim` not found in your PATH. This PoC requires Neovim.")
        sys.exit(1)

    main()
