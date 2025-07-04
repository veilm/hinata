#!/usr/bin/env python3

import os
import sys
import pty
import tty
import fcntl
import termios
import struct
import select
import atexit
import signal

# --- Configuration ---
BOX_HEIGHT = 20
BOX_Y_OFFSET = 4  # 1-based index for the top of the box

# --- Global State ---
original_termios = None
master_fd = None
child_pid = None


class AnsiParser:
    """A state-machine parser to intercept and translate ANSI escape codes."""

    def __init__(self, box_y_offset, box_height):
        self.box_y_offset = box_y_offset
        self.box_height = box_height
        self.state = "NORMAL"
        self.param_buffer = b""

    def process_data(self, data: bytes) -> bytes:
        output = b""
        for char_code in data:
            char_byte = bytes([char_code])

            if self.state == "NORMAL":
                if char_byte == b"\x1b":
                    self.state = "ESC"
                else:
                    output += char_byte
            elif self.state == "ESC":
                if char_byte == b"[":
                    self.state = "CSI_PARAM"
                    self.param_buffer = b""
                else:  # Not a CSI sequence, pass through
                    output += b"\x1b" + char_byte
                    self.state = "NORMAL"
            elif self.state == "CSI_PARAM":
                # Check for command character (a-z, A-Z)
                if 65 <= char_code <= 90 or 97 <= char_code <= 122:
                    output += self._handle_csi(self.param_buffer, char_byte)
                    self.state = "NORMAL"
                else:
                    self.param_buffer += char_byte
        return output

    def _handle_csi(self, params_bytes: bytes, cmd_byte: bytes) -> bytes:
        params_str = params_bytes.decode()
        cmd = cmd_byte.decode()

        # --- Translate Cursor Position (CUP) ---
        if cmd == "H":
            parts = params_str.split(";")
            if len(parts) == 1 and parts[0] == "":
                params = [1, 1]
            else:
                params = [int(p) if p else 1 for p in parts]

            row = params[0]
            col = params[1] if len(params) > 1 else 1

            new_row = row + self.box_y_offset - 1
            return f"\x1b[{new_row};{col}H".encode()

        # --- Translate Erase in Display (ED) ---
        if cmd == "J":
            # Any J command (Erase in Display) should be contained to the box.
            # We can approximate all of them by just clearing the entire box area.
            res = b""
            # Save cursor position, clear the box, then move cursor to box's home
            res += b"\x1b[s"
            for i in range(self.box_height):
                res += (
                    f"\x1b[{self.box_y_offset + i};1H".encode()
                )  # Move to line in box
                res += b"\x1b[2K"  # Clear entire line
            res += b"\x1b[u"
            # After clearing, nvim expects cursor at (1,1) of its screen.
            # Here we move it to the top-left of *our box*.
            res += f"\x1b[{self.box_y_offset};1H".encode()
            return res

        # Fallback for unhandled sequences: pass them through
        return b"\x1b[" + params_bytes + cmd_byte


def _cleanup():
    """Restore terminal state on exit."""
    if original_termios:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original_termios)

    # Show cursor, reset colors, reset scrolling region
    sys.stdout.write("\x1b[?25h\x1b[0m\x1b[r")

    # Move cursor to the bottom of the screen and clear everything below the box
    rows, _ = os.get_terminal_size()
    sys.stdout.write(f"\x1b[{rows};1H\x1b[J")
    sys.stdout.flush()


def _handle_winch(signum, frame):
    """Signal handler for terminal resize."""
    if master_fd is not None:
        rows, cols = os.get_terminal_size()
        # Create the struct for winsize. We only care about cols, height is fixed.
        winsize = struct.pack("HHHH", BOX_HEIGHT, cols, 0, 0)
        # Set the window size of the slave pty
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)


def main():
    global original_termios, master_fd, child_pid

    if not os.isatty(sys.stdin.fileno()):
        print("This program must be run in a TTY.", file=sys.stderr)
        sys.exit(1)

    # Save original terminal settings and register cleanup
    original_termios = termios.tcgetattr(sys.stdin.fileno())
    atexit.register(_cleanup)

    # Put the real TTY into raw mode
    tty.setraw(sys.stdin.fileno())

    # Create a new pty pair
    _master_fd, slave_fd = pty.openpty()
    master_fd = _master_fd  # Assign to global for signal handler

    # Fork to create a child process for nvim
    child_pid = os.fork()

    if child_pid == 0:
        # --- Child Process ---
        # Reset SIGWINCH handler to default for the child
        signal.signal(signal.SIGWINCH, signal.SIG_DFL)

        # Create a new session and set the slave as the controlling TTY
        os.setsid()
        os.dup2(slave_fd, sys.stdin.fileno())
        os.dup2(slave_fd, sys.stdout.fileno())
        os.dup2(slave_fd, sys.stderr.fileno())

        # Close unused file descriptors
        os.close(master_fd)
        os.close(slave_fd)

        # Launch nvim
        os.execvp("nvim", ["nvim"])
    else:
        # --- Parent Process ---
        os.close(slave_fd)

        # Set the initial size of the slave pty now that we're in the parent.
        # This avoids a race condition where the child starts and queries the
        # terminal size before the parent has had a chance to set it.
        _handle_winch(None, None)
        signal.signal(signal.SIGWINCH, _handle_winch)

        parser = AnsiParser(BOX_Y_OFFSET, BOX_HEIGHT)

        # Prepare screen
        sys.stdout.write("\x1b[H")  # Move to top-left, but don't clear the screen
        sys.stdout.write("--- Simplified tmux PoC ---\n")
        sys.stdout.write(
            "Running nvim in a 20-line box. Press Ctrl-D in nvim to exit.\n"
        )

        # Draw a decorative border for the box
        _, cols = os.get_terminal_size()
        sys.stdout.write(f"\x1b[{BOX_Y_OFFSET - 1};1H" + "┌" + "─" * (cols - 2) + "┐")
        for i in range(BOX_HEIGHT):
            sys.stdout.write(
                f"\x1b[{BOX_Y_OFFSET + i};1H│\x1b[{BOX_Y_OFFSET + i};{cols}H│"
            )
        sys.stdout.write(
            f"\x1b[{BOX_Y_OFFSET + BOX_HEIGHT};1H" + "└" + "─" * (cols - 2) + "┘"
        )
        sys.stdout.flush()

        fds = [sys.stdin.fileno(), master_fd]

        while True:
            # Check if child has exited
            try:
                wait_pid, status = os.waitpid(child_pid, os.WNOHANG)
                if wait_pid == child_pid:
                    break
            except OSError:
                break

            # Wait for I/O
            ready_to_read, _, _ = select.select(fds, [], [])

            if sys.stdin.fileno() in ready_to_read:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break  # EOF from stdin
                os.write(master_fd, data)

            if master_fd in ready_to_read:
                try:
                    data = os.read(master_fd, 1024)
                except OSError:  # EIO when slave is closed
                    break
                if not data:
                    break  # EOF from child

                processed_data = parser.process_data(data)
                sys.stdout.buffer.write(processed_data)
                sys.stdout.flush()


if __name__ == "__main__":
    main()
