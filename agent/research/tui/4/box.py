#!/usr/bin/env python3
"""
box.py – run `nvim` in a 20-line pane, preserving shell scroll-back.
Quit with Ctrl-q.
"""

import os, pty, select, sys, tty, termios, fcntl, struct, signal
from pane import Pane

PANE_HEIGHT = 20
CHILD_CMD = ["nvim"]          # change to ["vim"] if you prefer
EXIT_KEY = b"\x11"            # Ctrl-q


def get_term_size():
    hw = struct.unpack("HH", fcntl.ioctl(sys.stdin, termios.TIOCGWINSZ, b"\0" * 8)[:4])
    return hw[1], hw[0]       # (cols, rows)


def main():
    if not sys.stdin.isatty():
        sys.exit("Run me directly in an interactive terminal.")

    cols, rows = get_term_size()
    row_offset = rows - PANE_HEIGHT + 1

    # create pty pair ----------------------------------------------------------
    master_fd, slave_fd = pty.openpty()

    # fork child ---------------------------------------------------------------
    pid = os.fork()
    if pid == 0:                                          # --- child ---
        os.setsid()                                       # new session
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(master_fd)
        os.close(slave_fd)
        # pretend the terminal is only 20 lines high
        fcntl.ioctl(0, termios.TIOCSWINSZ,
                    struct.pack("HHHH", PANE_HEIGHT, cols, 0, 0))
        os.execvp(CHILD_CMD[0], CHILD_CMD)
        return

    # --- parent ---------------------------------------------------------------
    os.close(slave_fd)
    pane = Pane(cols, PANE_HEIGHT, row_offset)

    # set raw mode on real stdin
    old_attrs = termios.tcgetattr(sys.stdin.fileno())
    tty.setcbreak(sys.stdin.fileno())

    # ensure cleanup on SIGWINCH etc.
    def cleanup(signum=None, frame=None):
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
        os.kill(pid, signal.SIGKILL)
        os.close(master_fd)
        print("\x1b[0m")          # reset attributes
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGWINCH):
        signal.signal(sig, cleanup)

    try:
        # simple select loop ---------------------------------------------------
        while True:
            r, _, _ = select.select([sys.stdin, master_fd], [], [], 0.03)
            if sys.stdin in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if data.startswith(EXIT_KEY):
                    cleanup()
                os.write(master_fd, data)

            if master_fd in r:
                out = os.read(master_fd, 4096)
                if not out:                    # child exited
                    cleanup()
                pane.feed(out)

            pane.refresh()                     # brute-force repaint
    finally:
        cleanup()


if __name__ == "__main__":
    main()

