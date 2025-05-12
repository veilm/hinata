#!/usr/bin/env python3

import os
import pty
import sys
import select
import fcntl
import time
import termios
import struct
import logging

# Configure logging to file
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s",
    filename="pty.log",
    filemode="wb",  # Use binary mode for raw bytes
)
# Prevent logging module from adding its own formatting to the raw data
log_handler = logging.getLogger().handlers[0]
log_handler.setFormatter(logging.Formatter("%(message)s"))

# --- Low-level PTY data logging functions ---


def log_pty_write(master_fd: int, data: bytes):
    """Writes data to the PTY master and logs it."""
    logging.debug(b"WRITE >>> " + data.replace(b"\n", b"\\n"))
    try:
        os.write(master_fd, data)
    except OSError as e:
        print(f"Error writing to PTY: {e}", file=sys.stderr)


def log_pty_read(master_fd: int, n: int) -> bytes:
    """Reads data from the PTY master and logs it."""
    try:
        data = os.read(master_fd, n)
        if data:
            logging.debug(b"READ <<< " + data.replace(b"\n", b"\\n"))
        return data
    except OSError as e:
        # Can happen if the PTY closes unexpectedly, or EIO
        print(f"Error reading from PTY: {e}", file=sys.stderr)
        return b""


# --- Main PTY handling logic ---


def run_pty_demo():
    command = ["/bin/bash", "--norc", "--noprofile"]

    # Create a new PTY pair
    master_fd, slave_fd = pty.openpty()

    # Set window size (optional, but avoids some issues)
    # Get current terminal size if possible, otherwise use default
    try:
        rows, cols = os.get_terminal_size()
    except OSError:
        rows, cols = 24, 80
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

    # Fork the process
    pid = os.fork()

    if pid == 0:
        # --- Child Process ---
        # Close the master fd, we only need the slave
        os.close(master_fd)

        # Make the PTY slave the controlling terminal
        os.setsid()

        # Set PTY slave attributes (optional, but good practice)
        # Use attributes similar to a standard terminal
        attrs = termios.tcgetattr(slave_fd)
        attrs[3] &= ~termios.ECHO  # Turn off echo for cleaner output capture
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

        # Redirect stdin, stdout, stderr to the PTY slave
        os.dup2(slave_fd, sys.stdin.fileno())
        os.dup2(slave_fd, sys.stdout.fileno())
        os.dup2(slave_fd, sys.stderr.fileno())

        # Close the original slave fd (it's duplicated now)
        os.close(slave_fd)

        # Execute the command
        try:
            os.execvp(command[0], command)
        except OSError as e:
            print(f"Error executing command: {e}", file=sys.stderr)
            sys.exit(1)  # Exit child process on exec error

    else:
        # --- Parent Process ---
        # Close the slave fd, we only need the master
        os.close(slave_fd)

        captured_output = b""
        try:
            # Make master fd non-blocking (optional but safer for loops)
            # fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)

            # Give the shell a moment to start up
            time.sleep(0.2)

            # Flush any initial output (like prompt)
            while True:
                r, _, _ = select.select([master_fd], [], [], 0.1)
                if not r:
                    break
                initial_data = log_pty_read(master_fd, 1024)
                if not initial_data:  # EOF or error
                    break
                # Optionally print initial data: print(f"Initial: {initial_data!r}")

            print("Sending 'pwd' command...")
            cmd_to_run = b"pwd\n"
            log_pty_write(master_fd, cmd_to_run)

            # Read the output of the command
            read_timeout = 1.0  # seconds
            start_time = time.time()
            while time.time() - start_time < read_timeout:
                r, _, _ = select.select([master_fd], [], [], 0.1)
                if r:
                    data = log_pty_read(master_fd, 1024)
                    if not data:  # EOF received
                        print("PTY closed unexpectedly.")
                        break
                    captured_output += data
                    # Basic check: if we see our command echoed and a newline,
                    # assume the next line is the result. This is fragile.
                    if (
                        cmd_to_run in captured_output
                        and b"\n" in captured_output.split(cmd_to_run, 1)[1]
                    ):
                        # Add a small delay to catch trailing prompt/newline
                        time.sleep(0.1)
                        # Try one last read
                        r, _, _ = select.select([master_fd], [], [], 0)
                        if r:
                            final_data = log_pty_read(master_fd, 1024)
                            if final_data:
                                captured_output += final_data
                        break  # Assume we got the output
                else:
                    # No data within the inner timeout, maybe command finished
                    pass  # Continue outer loop until read_timeout

            print("Sending 'exit' command...")
            log_pty_write(master_fd, b"exit\n")

            # Read any remaining output until EOF
            while True:
                r, _, _ = select.select([master_fd], [], [], 0.5)
                if r:
                    data = log_pty_read(master_fd, 1024)
                    if not data:  # EOF is the expected way to exit this loop
                        print("PTY closed (EOF).")
                        break
                    # Optionally print final data: print(f"Final: {data!r}")
                else:
                    # Timeout waiting for EOF - should not happen if exit worked
                    print("Timeout waiting for PTY EOF after exit.")
                    break

        except Exception as e:
            print(f"An error occurred in parent: {e}", file=sys.stderr)
        finally:
            # Wait for the child process to terminate
            try:
                pid_H, status = os.waitpid(pid, 0)
                print(f"Child process {pid_H} exited with status {status}.")
            except ChildProcessError:
                print(
                    "Child process already finished."
                )  # Can happen if read hit EOF early

            # Close the master fd
            os.close(master_fd)
            print("Master PTY FD closed.")

        print("\n--- Captured Output (raw) ---")
        print(captured_output.decode("utf-8", errors="replace"))
        print("-----------------------------\n")

        # Try to parse the captured output to find the result of 'pwd'
        # This is heuristic and depends on shell behavior (echo, prompts)
        lines = captured_output.strip().split(b"\r\n")
        pwd_result = "Not found"
        try:
            # Find the line after the 'pwd' command echo
            cmd_index = lines.index(cmd_to_run.strip())
            if cmd_index + 1 < len(lines):
                # The next non-empty line *might* be the path
                for i in range(cmd_index + 1, len(lines)):
                    potential_result = lines[i].strip()
                    if potential_result:  # Check if it's not empty
                        # Basic sanity check: does it look like a path?
                        if potential_result.startswith(
                            b"/"
                        ) or potential_result.startswith(b"~"):
                            pwd_result = potential_result.decode(
                                "utf-8", errors="replace"
                            )
                            break
        except (ValueError, IndexError):
            # If 'pwd' echo wasn't found or no lines after it
            # Fallback: Assume the last non-empty line before potential prompt might be it
            for line in reversed(lines):
                line = line.strip()
                if (
                    line and line != cmd_to_run.strip() and not line.endswith(b"#")
                ):  # Avoid prompts
                    pwd_result = line.decode("utf-8", errors="replace")
                    break

        print(f"Parsed 'pwd' result: {pwd_result}")
        print(f"\nRaw PTY communication logged to: pty.log")


if __name__ == "__main__":
    run_pty_demo()
