#!/usr/bin/env python3
"""
Simple Tmux Proof of Concept
Main program that creates a constrained terminal box for running programs
"""

import os
import sys
import pty
import select
import termios
import tty
import signal
import struct
import fcntl
import re
from typing import Optional, Tuple


class TerminalBox:
    """Manages a program running in a constrained terminal box"""

    def __init__(self, start_row: int, height: int, width: Optional[int] = None):
        self.start_row = start_row  # Where the box starts on screen
        self.height = height
        self.width = width or self._get_terminal_width()
        self.master_fd = None
        self.slave_fd = None
        self.child_pid = None
        self.old_tty = None

    def _get_terminal_width(self) -> int:
        """Get the actual terminal width"""
        size = struct.unpack("hh", fcntl.ioctl(0, termios.TIOCGWINSZ, "1234"))
        return size[1]

    def _get_terminal_size(self) -> Tuple[int, int]:
        """Get the actual terminal size (rows, cols)"""
        size = struct.unpack("hh", fcntl.ioctl(0, termios.TIOCGWINSZ, "1234"))
        return size[0], size[1]

    def setup_terminal(self):
        """Save current terminal state and prepare for raw mode"""
        # Move cursor to the start position
        print(f"\033[{self.start_row};1H", end="", flush=True)

        # Clear the box area
        for i in range(self.height):
            print(f"\033[{self.start_row + i};1H\033[K", end="", flush=True)

        # Save terminal settings
        self.old_tty = termios.tcgetattr(sys.stdin)

        # Set terminal to raw mode
        tty.setraw(sys.stdin.fileno())

    def restore_terminal(self):
        """Restore terminal to original state"""
        if self.old_tty:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_tty)

        # Move cursor below the box
        print(f"\033[{self.start_row + self.height + 1};1H", end="", flush=True)

    def translate_cursor_position(self, data: bytes) -> bytes:
        """Translate ANSI cursor positioning sequences to box coordinates"""
        # This is a simplified version - a full implementation would need
        # a complete ANSI escape sequence parser

        output = bytearray()
        i = 0

        while i < len(data):
            # Look for ESC sequences
            if (
                data[i : i + 1] == b"\x1b"
                and i + 1 < len(data)
                and data[i + 1 : i + 2] == b"["
            ):
                # Found start of escape sequence
                seq_start = i
                i += 2

                # Parse the sequence
                while i < len(data) and not (
                    65 <= data[i] <= 90 or 97 <= data[i] <= 122
                ):
                    i += 1

                if i < len(data):
                    seq = data[seq_start : i + 1]
                    translated = self._translate_escape_sequence(seq)
                    output.extend(translated)
                    i += 1
                else:
                    # Incomplete sequence
                    output.extend(data[seq_start:])
                    break
            else:
                output.append(data[i])
                i += 1

        return bytes(output)

    def _translate_escape_sequence(self, seq: bytes) -> bytes:
        """Translate a single escape sequence"""
        seq_str = seq.decode("latin-1")

        # Cursor positioning: \x1b[row;colH or \x1b[row;colf
        match = re.match(r"\x1b\[(\d+);(\d+)[Hf]", seq_str)
        if match:
            row = int(match.group(1))
            col = int(match.group(2))
            # Translate row to actual screen position
            new_row = self.start_row + row - 1
            # Ensure we stay within bounds
            if new_row >= self.start_row + self.height:
                new_row = self.start_row + self.height - 1
            return f"\x1b[{new_row};{col}H".encode("latin-1")

        # Clear screen: \x1b[2J
        if seq == b"\x1b[2J":
            # Instead of clearing whole screen, clear just our box
            result = bytearray()
            for i in range(self.height):
                result.extend(f"\x1b[{self.start_row + i};1H\x1b[K".encode("latin-1"))
            result.extend(f"\x1b[{self.start_row};1H".encode("latin-1"))
            return bytes(result)

        # Clear to end of screen: \x1b[J
        if seq == b"\x1b[J" or seq == b"\x1b[0J":
            # Clear from cursor to end of box
            # This is simplified - would need to track cursor position
            return seq

        # Home cursor: \x1b[H
        if seq == b"\x1b[H":
            return f"\x1b[{self.start_row};1H".encode("latin-1")

        # For other sequences, pass through unchanged
        return seq

    def run(self, command: list):
        """Run a command in the constrained box"""
        # Create pseudoterminal
        self.master_fd, self.slave_fd = pty.openpty()

        # Set the pty size to our box dimensions
        winsize = struct.pack("HHHH", self.height, self.width, 0, 0)
        fcntl.ioctl(self.slave_fd, termios.TIOCSWINSZ, winsize)

        # Fork and exec the command
        self.child_pid = os.fork()

        if self.child_pid == 0:
            # Child process
            os.close(self.master_fd)

            # Make the slave pty our controlling terminal
            os.setsid()
            fcntl.ioctl(self.slave_fd, termios.TIOCSCTTY)

            # Redirect stdin/stdout/stderr to the pty
            os.dup2(self.slave_fd, 0)
            os.dup2(self.slave_fd, 1)
            os.dup2(self.slave_fd, 2)
            os.close(self.slave_fd)

            # Execute the command
            os.execvp(command[0], command)
            sys.exit(1)

        # Parent process
        os.close(self.slave_fd)
        self.setup_terminal()

        try:
            self._io_loop()
        finally:
            self.restore_terminal()
            if self.child_pid:
                try:
                    os.kill(self.child_pid, signal.SIGTERM)
                    os.waitpid(self.child_pid, 0)
                except:
                    pass

    def _io_loop(self):
        """Main I/O loop - relay data between real terminal and pty"""
        while True:
            try:
                # Wait for input from either stdin or the pty
                r, _, _ = select.select([sys.stdin, self.master_fd], [], [])

                if sys.stdin in r:
                    # Input from user - send to pty
                    data = os.read(sys.stdin.fileno(), 1024)
                    if not data:
                        break
                    os.write(self.master_fd, data)

                if self.master_fd in r:
                    # Output from program - translate and display
                    try:
                        data = os.read(self.master_fd, 4096)
                        if not data:
                            break
                    except OSError:
                        break

                    # Translate coordinates and display
                    translated = self.translate_cursor_position(data)
                    sys.stdout.buffer.write(translated)
                    sys.stdout.buffer.flush()

            except KeyboardInterrupt:
                # Send Ctrl-C to the child
                os.write(self.master_fd, b"\x03")
            except Exception as e:
                print(f"\nError: {e}", file=sys.stderr)
                break


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: simple_tmux.py <command> [args...]")
        print("Example: simple_tmux.py nvim test.txt")
        sys.exit(1)

    # Print some content above the box
    print("=== Content Above Box ===")
    print("$ echo hi")
    print("hi")
    print("$ ls")
    print("file1.txt  file2.py  directory/")
    print("$ date")
    print("Wed Jun 18 10:30:00 PDT 2025")
    print("=== End Content ===")
    print()

    # Determine where to start the box
    rows, cols = struct.unpack("hh", fcntl.ioctl(0, termios.TIOCGWINSZ, "1234"))
    current_row = 9  # Approximate row after our printed content

    # Create and run the terminal box
    box = TerminalBox(start_row=current_row, height=20)
    box.run(sys.argv[1:])


if __name__ == "__main__":
    main()
