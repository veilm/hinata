import fcntl
import os
import pty
import select
import shutil
import struct
import sys
import termios
import tty


def main():
    """
    Creates a 20-line "window" at the bottom of the terminal to run kak,
    without clearing the terminal scrollback.
    """
    height = 20

    if not shutil.which("kak"):
        print("Error: 'kak' command not found in PATH.", file=sys.stderr)
        sys.exit(1)

    try:
        original_stty = termios.tcgetattr(sys.stdin)
        cols, _ = os.get_terminal_size()
    except (termios.error, OSError):
        print("Not a TTY or unable to get terminal size, exiting.", file=sys.stderr)
        sys.exit(1)

    # Reserve space by printing newlines
    sys.stdout.write("\n" * (height - 1))
    sys.stdout.flush()

    # Move cursor up to start of the reserved space
    sys.stdout.write(f"\x1b[{height - 1}A")
    sys.stdout.flush()

    # Save cursor position
    sys.stdout.write("\x1b[s")
    sys.stdout.flush()

    pid, master_fd = pty.fork()

    if pid == pty.CHILD:
        # Child process: configure pty and exec kak
        try:
            winsize = struct.pack("HHHH", height, cols, 0, 0)
            fcntl.ioctl(sys.stdout.fileno(), termios.TIOCSWINSZ, winsize)
            os.execvp("kak", ["kak"])
        except Exception as e:
            # If execvp fails, the child must exit.
            print(f"Error in child process: {e}", file=sys.stderr)
            os._exit(1)

    # Parent process:
    try:
        tty.setraw(sys.stdin.fileno())

        while True:
            try:
                # Check if child has exited
                wait_pid, _ = os.waitpid(pid, os.WNOHANG)
                if wait_pid == pid:
                    break
            except ChildProcessError:
                break  # Child already reaped

            try:
                r, _, _ = select.select([sys.stdin, master_fd], [], [], 0.05)
            except select.error:
                continue  # Interrupted by signal

            if master_fd in r:
                try:
                    data = os.read(master_fd, 1024)
                    if not data:  # EOF, child exited
                        break
                    # Restore cursor before writing, as kak might hide it
                    sys.stdout.write("\x1b[u")
                    sys.stdout.write(data.decode(errors="replace"))
                    sys.stdout.flush()
                except OSError:
                    break  # EIO error, pty is gone

            if sys.stdin in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if not data:
                    break
                os.write(master_fd, data)

    finally:
        # Restore terminal state
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_stty)
        os.close(master_fd)

        # Restore cursor to where it was for kak
        sys.stdout.write("\x1b[u")
        # Move cursor down past the kak area
        sys.stdout.write(f"\x1b[{height - 1}B")
        # Clear from cursor to end of screen to remove any artifacts
        sys.stdout.write("\x1b[J")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
