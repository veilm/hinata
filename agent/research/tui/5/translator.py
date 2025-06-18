"""
translator.py  –  very small ANSI/VT100 proxy that confines a child's
output to a rectangular pane on the real terminal.

Handles only the sequences that would otherwise break out of the box:
  * CUP / HVP        ESC [ row ; col H / f
  * DECSTBM          ESC [ top ; bottom r
  * ED (2J)          ESC [ 2 J
  * xterm alt-screen ESC [ ? 1049h / 1049l / 47h / 47l / 1047h / l
Everything else is forwarded untouched.
"""

import re, sys, itertools

CSI_RE = re.compile(rb"\x1b\[([0-9;?]*)([@-~])")  # generic CSI matcher
ALT_SCR_RE = re.compile(rb"\x1b\[\?(1049|1047|47)[hl]")


class Translator:
    def __init__(self, row_off: int, height: int):
        self.row_off, self.height = row_off, height
        self.buf = bytearray()

    # --------------------------------------------------------------------- io
    def write(self, data: bytes):
        """Feed bytes coming from the child pty; translated bytes are written
        directly to stdout.buffer."""
        self.buf.extend(data)
        out = bytearray()

        while True:
            m = CSI_RE.search(self.buf)
            if not m:
                break  # no complete CSI yet
            out.extend(self.buf[: m.start()])  # bytes before CSI

            params = (m.group(1) or b"").decode()
            final = chr(m.group(2)[0])
            seq = m.group(0)

            # --- filter / translate -----------------------------------------
            if ALT_SCR_RE.fullmatch(seq):
                # swallow alternate-screen commands
                pass

            elif final in "Hf":  # CUP / HVP
                row, col = (params.split(";") + ["1", "1"])[:2]
                row = int(row) if row else 1
                col = int(col) if col else 1
                out.extend(f"\x1b[{self.row_off + row - 1};{col}H".encode())

            elif final == "r":  # DECSTBM
                top, bot = (params.split(";") + ["1", str(self.height)])[:2]
                top = int(top) if top else 1
                bot = int(bot) if bot else self.height
                top += self.row_off - 1
                bot += self.row_off - 1
                out.extend(f"\x1b[{top};{bot}r".encode())

            elif final == "J" and params in ("2", ""):
                # Clear *only* our pane (brute-force but fast on modern terms)
                out.extend(self._clear_pane())

            else:
                out.extend(seq)  # pass through untouched

            self.buf = self.buf[m.end() :]  # consume

        # leftover that has no CSI yet
        out.extend(self.buf)
        self.buf.clear()

        sys.stdout.buffer.write(out)
        sys.stdout.flush()

    # ------------------------------------------------------------------ utils
    def _clear_pane(self) -> bytes:
        b = bytearray(b"\x1b7")  # save cursor
        for i in range(self.height):
            b.extend(f"\x1b[{self.row_off + i};1H\x1b[2K".encode())
        b.extend(b"\x1b8")  # restore
        return b
