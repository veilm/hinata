#!/usr/bin/env python3
"""
box.py – run `nvim` (or any full-screen TUI) in a 20-line pane
at the bottom of the current terminal without nuking scroll-back.

Quit with Ctrl-q.

Std-lib only.  Python ≥ 3.8
"""
import os, pty, fcntl, termios, struct, tty, select, signal, sys
from translator import Translator

HEIGHT      = 20
CMD         = ["nvim"]          # or ["vim"]
QUIT_KEY    = b"\x11"           # Ctrl-q

# --------------------------------------------------------------------------- helpers
def term_size(fd=0):
    rows, cols, *_ = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0"*8))
    return rows, cols

def set_winsz(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

def run():
    if not sys.stdin.isatty():
        sys.exit("Run inside an interactive terminal.")

    rows, cols = term_size()
    row_off = rows - HEIGHT + 1

    master, slave = pty.openpty()
    pid = os.fork()

    if pid == 0:                                  # ---------------- child
        os.setsid()
        os.dup2(slave, 0); os.dup2(slave, 1); os.dup2(slave, 2)
        os.close(master); os.close(slave)
        set_winsz(0, HEIGHT, cols)
        os.execvp(CMD[0], CMD)
        return

    # ---------------- parent
    os.close(slave)
    trans = Translator(row_off, HEIGHT)

    # confine real terminal’s scroll region once
    sys.stdout.write(f'\x1b[{row_off};{rows}r\x1b[{row_off};1H')
    sys.stdout.flush()

    # raw mode on stdin
    old_attr = termios.tcgetattr(0)
    tty.setcbreak(0)

    def cleanup(signum=None, frame=None):
        termios.tcsetattr(0, termios.TCSADRAIN, old_attr)
        # restore scroll region
        sys.stdout.write('\x1b[r\x1b[?25h\r')
        sys.stdout.flush()
        try: os.kill(pid, signal.SIGTERM)
        except OSError: pass
        sys.exit(0)

    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGWINCH):
        signal.signal(s, cleanup)

    # --------------- main loop
    try:
        while True:
            r, _, _ = select.select([0, master], [], [], 0.05)

            if 0 in r:
                data = os.read(0, 1024)
                if data.startswith(QUIT_KEY):
                    cleanup()
                os.write(master, data)

            if master in r:
                out = os.read(master, 4096)
                if not out:
                    cleanup()
                trans.write(out)
    finally:
        cleanup()

if __name__ == "__main__":
    run()

