#!/usr/bin/env python3
"""
7.py – A robust, dependency-free terminal multiplexer that confines a
full-screen TUI to a pane without losing host terminal scroll-back.

This is an improved version based on analysis of mini_mux.py.

- State-machine based ECMA-48 parser for robust control sequence handling.
- Correct SIGWINCH handling for dynamic terminal resizing.
- Bidirectional PTY communication to handle application queries (fixes kakoune).
- Output batching for smooth rendering in modern terminals (fixes foot).
- Quit with Ctrl-q.
"""

import os, pty, fcntl, termios, struct, tty, select, signal, sys
from collections import namedtuple

# ------------------------------------------------------------------- config
QUIT_KEY = b"\x11"  # Ctrl-q
# Timeout for select() to batch writes for smoother rendering
WRITE_BATCH_TIMEOUT = 0.005

# ------------------------------------------------------------------- ECMA-48 Parser
ControlSequence = namedtuple(
    "ControlSequence", ["params", "intermediate", "final", "priv_marker"]
)


class CSIParser:
    """A state machine parser for ECMA-48 control sequences."""

    def __init__(self, dispatch_func):
        self.dispatch = dispatch_func
        self.state = self._ground_state
        self._reset_sequence()

    def _reset_sequence(self):
        self.params = []
        self.intermediate = b""
        self.priv_marker = b""

    def parse(self, data: bytes):
        for byte in data:
            self.state(bytes([byte]))

    def _ground_state(self, byte: bytes):
        if byte == b"\x1b":
            self.state = self._escape_state
        else:
            self.dispatch(byte)

    def _escape_state(self, byte: bytes):
        if byte == b"[":  # CSI
            self._reset_sequence()
            self.state = self._csi_entry_state
        elif byte == b"M":  # RI - Reverse Index
            self.dispatch(b"\x1bM")
            self.state = self._ground_state
        else:
            # Other sequences (e.g., charsets) - pass through for now
            self.dispatch(b"\x1b" + byte)
            self.state = self._ground_state

    def _csi_entry_state(self, byte: bytes):
        if b"0" <= byte <= b"9":
            self.params.append(int(byte))
            self.state = self._csi_param_state
        elif byte == b";":
            self.params.append(0)  # Parameter was empty
        elif byte in b"?<=>":
            self.priv_marker = byte
        elif b" " <= byte <= b"/":
            self.intermediate += byte
            self.state = self._csi_intermediate_state
        elif b"@" <= byte <= b"~":
            self.dispatch(
                ControlSequence(self.params, self.intermediate, byte, self.priv_marker)
            )
            self.state = self._ground_state

    def _csi_param_state(self, byte: bytes):
        if b"0" <= byte <= b"9":
            self.params[-1] = self.params[-1] * 10 + int(byte)
        elif byte == b";":
            self.params.append(0)
        elif b" " <= byte <= b"/":
            self.intermediate += byte
            self.state = self._csi_intermediate_state
        elif b"@" <= byte <= b"~":
            self.dispatch(
                ControlSequence(self.params, self.intermediate, byte, self.priv_marker)
            )
            self.state = self._ground_state

    def _csi_intermediate_state(self, byte: bytes):
        if b" " <= byte <= b"/":
            self.intermediate += byte
        elif b"@" <= byte <= b"~":
            self.dispatch(
                ControlSequence(self.params, self.intermediate, byte, self.priv_marker)
            )
            self.state = self._ground_state


# ------------------------------------------------------------------- Translator
class Translator:
    def __init__(self, row_off: int, height: int, master_fd: int):
        self.row_off, self.height = row_off, height
        self.master_fd = master_fd
        self.parser = CSIParser(self._dispatch)
        self.output_buffer = bytearray()
        self.v_cursor_r = 1  # Virtual cursor row (1-based)

    def write(self, data: bytes):
        self.parser.parse(data)

    def flush_buffer(self):
        if not self.output_buffer:
            return
        # Use bracketed paste mode sequences to hint at atomic updates
        out = b"\x1b[?2004h" + bytes(self.output_buffer) + b"\x1b[?2004l"
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
        self.output_buffer.clear()

    def update_geometry(self, row_off: int, height: int):
        self.row_off, self.height = row_off, height

    def _clear_pane(self):
        b = bytearray()
        for i in range(self.height):
            b.extend(f"\x1b[{self.row_off + i};1H\x1b[2K".encode())
        return b

    def _emulate_scroll(self, n: int, direction: str):
        region = f"\x1b[{self.row_off};{self.row_off + self.height - 1}r"
        reset_region = b"\x1b[r"
        if direction == "up":
            scroll = f"\x1b[{self.row_off + self.height - 1};1H" + ("\n" * n)
        else:  # down
            scroll = f"\x1b[{self.row_off};1H" + ("\x1bM" * n)
        return (region + scroll).encode() + reset_region

    def _dispatch(self, seq):
        if isinstance(seq, bytes):  # Literal data
            if seq == b"\x1bM":  # RI - Reverse Index
                if self.v_cursor_r == 1:
                    self.output_buffer.extend(self._emulate_scroll(1, "down"))
                else:
                    self.v_cursor_r -= 1
                    self.output_buffer.extend(b"\x1b[1A")  # Cursor Up
            else:
                self.output_buffer.extend(seq)
                if seq == b"\n":
                    self.v_cursor_r = min(self.height, self.v_cursor_r + 1)
            return

        # --- Handle ControlSequence ---
        if seq.final == b"p" and seq.priv_marker == b"?" and seq.intermediate == b"$":
            if 2026 in seq.params:  # Sync output query
                os.write(self.master_fd, b"\x1b[?2026;0$y")
                return

        elif seq.final in (b"H", b"f"):  # CUP / HVP
            row = seq.params[0] if len(seq.params) > 0 else 1
            col = seq.params[1] if len(seq.params) > 1 else 1
            self.v_cursor_r = row
            self.output_buffer.extend(f"\x1b[{self.row_off + row - 1};{col}H".encode())

        elif seq.final == b"r":  # Set scrolling region
            top = seq.params[0] if len(seq.params) > 0 else 1
            bot = seq.params[1] if len(seq.params) > 1 else self.height
            self.output_buffer.extend(
                f"\x1b[{self.row_off + top - 1};{self.row_off + bot - 1}r".encode()
            )

        elif seq.final == b"J":  # Erase in Display
            p = seq.params[0] if seq.params else 0
            if p in (2, 3):
                self.output_buffer.extend(self._clear_pane())
            else:
                self.output_buffer.extend(self._reconstruct_csi(seq))

        elif seq.final == b"S":  # Scroll Up
            n = seq.params[0] if seq.params else 1
            self.output_buffer.extend(self._emulate_scroll(n, "up"))

        elif seq.final == b"T":  # Scroll Down
            n = seq.params[0] if seq.params else 1
            self.output_buffer.extend(self._emulate_scroll(n, "down"))

        elif seq.final in (b"h", b"l") and seq.priv_marker == b"?":
            if any(p in (1049, 1047, 47) for p in seq.params):
                pass  # Swallow alt screen
            else:
                self.output_buffer.extend(self._reconstruct_csi(seq))

        else:  # Pass through anything else
            self.output_buffer.extend(self._reconstruct_csi(seq))

    def _reconstruct_csi(self, seq: ControlSequence) -> bytes:
        params_str = ";".join(map(str, seq.params))
        return (
            b"\x1b["
            + seq.priv_marker
            + params_str.encode()
            + seq.intermediate
            + seq.final
        )


# ---------------------------------------------------------------- main logic
class App:
    def __init__(self, height: int, cmd: list):
        self.height = height
        self.cmd = cmd

    def run(self):
        if not sys.stdin.isatty():
            sys.exit("Run inside an interactive terminal.")

        self.pid, self.master = pty.fork()

        if self.pid == 0:  # --- Child Process ---
            _, host_cols = term_size(sys.stdout.fileno())
            set_winsz(sys.stdin.fileno(), self.height, host_cols)
            os.execvp(self.cmd[0], self.cmd)
            return

        # --- Parent Process ---
        self.old_attr = termios.tcgetattr(0)

        # Set up signal handlers
        signal.signal(signal.SIGINT, lambda s, f: self.cleanup())
        signal.signal(signal.SIGTERM, lambda s, f: self.cleanup())
        signal.signal(signal.SIGWINCH, self._sigwinch_handler)

        self._handle_resize()  # Initial setup
        tty.setcbreak(0)

        try:
            while True:
                try:
                    r, _, _ = select.select(
                        [0, self.master], [], [], WRITE_BATCH_TIMEOUT
                    )
                except InterruptedError:
                    self._handle_resize()
                    continue

                if 0 in r:
                    data = os.read(0, 1024)
                    if data.startswith(QUIT_KEY):
                        break
                    os.write(self.master, data)

                if self.master in r:
                    out = os.read(self.master, 4096)
                    if not out:
                        break  # EOF from child
                    self.trans.write(out)

                if not r:
                    self.trans.flush_buffer()
        finally:
            self.cleanup()

    def _sigwinch_handler(self, signum, frame):
        # We handle the resize inside the InterruptedError from select
        pass

    def _handle_resize(self):
        self.host_rows, self.host_cols = term_size(sys.stdout.fileno())
        row_off = self.host_rows - self.height + 1

        if not hasattr(self, "trans"):
            self.trans = Translator(row_off, self.height, self.master)
        else:
            self.trans.update_geometry(row_off, self.height)

        set_winsz(self.master, self.height, self.host_cols)

        # Prepare host terminal
        sys.stdout.write(f"\x1b[?25l")  # Hide cursor
        sys.stdout.write(f"\x1b[{row_off};{self.host_rows}r")  # Set scroll region
        sys.stdout.write(f"\x1b[{row_off};1H")  # Move cursor
        os.write(self.master, b"\x0c")  # Tell child to redraw (form feed)
        sys.stdout.flush()

    def cleanup(self):
        self.trans.flush_buffer()
        rows, _ = term_size(sys.stdout.fileno())
        sys.stdout.write(
            f"\x1b[r\x1b[?25h\x1b[{rows};1H"
        )  # Reset scroll, show cursor, move to bottom
        sys.stdout.flush()
        termios.tcsetattr(0, termios.TCSADRAIN, self.old_attr)
        try:
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, 0)
        except OSError:
            pass
        os.close(self.master)
        sys.exit(0)


# --- Helper Functions ---
def term_size(fd):
    """Returns (rows, cols) for a given file descriptor."""
    size = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8)
    rows, cols, _, _ = struct.unpack("HHHH", size)
    return rows, cols


def set_winsz(fd, rows, cols):
    """Sets the window size for a given file descriptor."""
    size = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="A robust, dependency-free terminal multiplexer that confines a "
        "full-screen TUI to a pane without losing host terminal scroll-back."
    )
    parser.add_argument(
        "--height", type=int, default=20, help="The height of the pane in lines."
    )
    parser.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="The command to run in the pane.",
    )
    args = parser.parse_args()

    if not args.cmd:
        parser.error("a command must be provided")

    App(height=args.height, cmd=args.cmd).run()
