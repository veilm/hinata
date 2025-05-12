#!/usr/bin/env python3
import os
import pty
import subprocess
import select
import sys
import shlex

#--- helpers ---------------------------------------------------------------
def read_until(fd: int, token: bytes, timeout: float = 10.0) -> bytes:
    """
    Read from *fd* until *token* appears (CRs are ignored) or *timeout* expires.
    """
    buf = b""
    while True:
        if token in buf.replace(b"\r", b""):     # tolerate \r\n vs \n
            return buf
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            raise RuntimeError(f"Timeout waiting for {token!r}")
        chunk = os.read(fd, 4096)
        if not chunk:                       # EOF
            break
        buf += chunk
    return buf

def send(fd: int, cmd: str) -> None:
    """Write *cmd* + newline to *fd* (bytes)."""
    os.write(fd, cmd.encode() + b"\n")

def extract_last_output(raw: bytes, marker: str) -> str:
    """
    Return the line immediately preceding a line that is *exactly* the marker.
    """
    text  = raw.decode(errors="replace")
    lines = [ln.rstrip("\r") for ln in text.splitlines()]

    # walk backwards to find the marker line
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == marker:          # full-line match
            return lines[i - 1].strip() if i else ""
    raise ValueError(f"Marker {marker!r} not found in PTY output")

#--- set up environment ----------------------------------------------------
env = os.environ.copy()
env["PS1"] = ""        # empty interactive prompt
env["ENV"] = ""        # ksh-style init file — cleared
env["BASH_ENV"] = ""   # bash’s non-interactive init file — cleared

#--- open a PTY and spawn bash --------------------------------------------
master_fd, slave_fd = pty.openpty()

bash = subprocess.Popen(
    ["bash", "--noprofile", "--norc", "-i"],
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    env=env,
    close_fds=True,
)

os.close(slave_fd)      # not needed in parent

# Drain any initial output (usually nothing because no rc files)
try:
    select.select([master_fd], [], [], 0.2)
    os.read(master_fd, 4096)
except OSError:
    pass

#--- 1. pwd in the starting directory -------------------------------------
MARK1 = "__END1__"
send(master_fd, "pwd")
send(master_fd, f"echo {MARK1}")

raw1 = read_until(master_fd, MARK1.encode())
bash_cwd = extract_last_output(raw1, MARK1)
py_cwd   = os.getcwd()

assert bash_cwd == py_cwd, (
    f"Mismatch: bash returned {bash_cwd!r}, "
    f"Python os.getcwd() is {py_cwd!r}"
)
print(f"[✓] bash CWD matches Python: {bash_cwd}")

#--- 2. change to $HOME ----------------------------------------------------
MARK2 = "__END2__"
send(master_fd, "cd \"$HOME\"")
send(master_fd, "pwd")
send(master_fd, f"echo {MARK2}")

raw2 = read_until(master_fd, MARK2.encode())
bash_home = extract_last_output(raw2, MARK2)
py_home   = os.path.expanduser("~")

assert bash_home == py_home, (
    f"Mismatch: bash returned {bash_home!r}, "
    f"Python home is {py_home!r}"
)
print(f"[✓] bash HOME matches Python: {bash_home}")

#--- tidy up ---------------------------------------------------------------
bash.terminate()
bash.wait()
os.close(master_fd)
