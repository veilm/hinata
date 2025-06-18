"""
pane.py – tiny helper that translates VT100 escape sequences
coming from a child pty into real-terminal output restricted
to a rectangular “box” (row_offset … row_offset+height-1).
"""

import sys, itertools
from typing import List
import pyte


class Pane:
    def __init__(self, cols: int, rows: int, row_offset: int):
        self.rows, self.cols = rows, cols
        self.row_offset = row_offset          # where the pane starts on host term
        self.screen = pyte.Screen(cols, rows)
        self.parser = pyte.ByteStream(self.screen)

    # feed raw bytes coming from the child pty
    def feed(self, data: bytes):
        self.parser.feed(data)

    # repaint everything (brute-force – good enough for PoC)
    def refresh(self):
        buf: List[str] = []
        buf.append("\x1b7")                   # save cursor
        for r in range(self.rows):
            # move cursor to the correct absolute row on the host terminal
            buf.append(f"\x1b[{self.row_offset + r};1H")
            line = self.screen.display[r]
            buf.append(line.ljust(self.cols))
        buf.append("\x1b8")                   # restore cursor
        sys.stdout.write("".join(buf))
        sys.stdout.flush()

    # tell child pty that its window size is rows×cols
    def winsize_ioctl(self, fd):
        import fcntl, struct, termios
        fcntl.ioctl(
            fd,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", self.rows, self.cols, 0, 0),
        )
