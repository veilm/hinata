#!/usr/bin/env python3
"""
mini_mux.py – one-file “tiny tmux” that confines a full-screen TUI
(Nvim, Helix, Kakoune, …) to the bottom 20 lines **without losing
scroll-back** in the host terminal.

 • std-lib only – no external deps
 • works with colours, mouse, bracketed-paste
 • quit with Ctrl-q
"""

import os, pty, fcntl, termios, struct, tty, select, signal, sys, re

# ------------------------------------------------------------------- config
HEIGHT = 20
CMD = os.environ.get("CMD", "nvim").split()  # use env-var to test Kakoune
QUIT_KEY = b"\x11"  # Ctrl-q


# ------------------------------------------------------------------- helpers
def term_size(fd=0):
    rows, cols, *_ = struct.unpack(
        "HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    )
    return rows, cols


def set_winsz(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


# ---------------------------------------------------------------- translator
CSI_RE = re.compile(rb"\x1b\[([0-9;?]*)([@-~])")
ALTSCREEN_RE = re.compile(rb"\x1b\[\?(1049|1047|47)[hl]")


class Translator:
    """Confines child output to a pane that starts on row_off for HEIGHT lines,
    rewriting only the handful of CSI codes that would break containment."""

    def __init__(self, row_off: int, height: int, master_fd: int):
        self.row_off, self.height = row_off, height
        self.master_fd = master_fd  # needed to fake alt-screen reply
        self.buf = bytearray()

    def write(self, data: bytes):
        self.buf.extend(data)
        out = bytearray()

        while True:
            m = CSI_RE.search(self.buf)
            if not m:
                break
            out.extend(self.buf[: m.start()])  # literal bytes up to CSI

            params = (m.group(1) or b"").decode()
            final = chr(m.group(2)[0])
            seq = m.group(0)

            # ---- 1) swallow alt-screen but ACK to child --------------------
            if ALTSCREEN_RE.fullmatch(seq):
                os.write(self.master_fd, b"\x1b]0;?1049;ok\x07")  # fake “ok”
                # nothing sent to real terminal – keeps scroll-back visible

            # ---- 2) CUP / HVP – move cursor -------------------------------
            elif final in "Hf":
                row, col = (params.split(";") + ["1", "1"])[:2]
                row = int(row) if row else 1
                col = int(col) if col else 1
                out.extend(f"\x1b[{self.row_off + row - 1};{col}H".encode())

            # ---- 3) scroll-region -----------------------------------------
            elif final == "r":
                top, bot = (params.split(";") + ["1", str(self.height)])[:2]
                top = int(top) if top else 1
                bot = int(bot) if bot else self.height
                out.extend(
                    f"\x1b[{self.row_off + top - 1};{self.row_off + bot - 1}r".encode()
                )

            # ---- 4) ED – clear screen variations ---------------------------
            elif final == "J" and params in ("2", "0", ""):
                out.extend(self._clear_pane())

            else:
                out.extend(seq)  # untouched

            self.buf = self.buf[m.end() :]

        out.extend(self.buf)
        self.buf.clear()
        sys.stdout.buffer.write(out)
        sys.stdout.flush()

    def _clear_pane(self) -> bytes:
        b = bytearray(b"\x1b7")  # save cursor
        for i in range(self.height):
            b.extend(f"\x1b[{self.row_off + i};1H\x1b[2K".encode())
        b.extend(b"\x1b8")  # restore
        return b


# ---------------------------------------------------------------- main logic
def run():
    if not sys.stdin.isatty():
        sys.exit("Run inside an interactive terminal.")

    rows, cols = term_size()
    row_off = rows - HEIGHT + 1  # first line of the pane (1-based)

    master, slave = pty.openpty()
    pid = os.fork()

    if pid == 0:  # ---------- child ----------
        os.setsid()
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        os.close(master)
        os.close(slave)
        set_winsz(0, HEIGHT, cols)
        os.execvp(CMD[0], CMD)
        return

    # -------------------------- parent -------------------------------------
    os.close(slave)
    trans = Translator(row_off, HEIGHT, master)

    # confine host scroll region once, put cursor in pane’s top-left
    sys.stdout.write(f"\x1b[{row_off};{rows}r\x1b[{row_off};1H")
    sys.stdout.flush()

    old_attr = termios.tcgetattr(0)
    tty.setcbreak(0)

    def cleanup(signum=None, frame=None):
        # restore full scroll region *before* we print anything else
        sys.stdout.write("\x1b[r\x1b[?25h")
        sys.stdout.flush()
        termios.tcsetattr(0, termios.TCSADRAIN, old_attr)
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        os.close(master)
        # leave cursor at bottom of real screen – no stray clear
        sys.stdout.write(f"\x1b[{rows};1H")
        sys.stdout.flush()
        sys.exit(0)

    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGWINCH):
        signal.signal(s, cleanup)

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


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run()
