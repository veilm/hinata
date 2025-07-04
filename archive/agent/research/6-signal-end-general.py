import os
import pty
import signal
import time
import sys
import threading
import select
import errno
import tempfile

# Global dictionary to store completion status.
# Accessed by the signal handler and the main thread.
completion_info = {"completed": False}

# Event to signal the PTY draining thread to stop.
drain_stop_event = threading.Event()


def handle_sigusr1(signum, frame):
    """Signal handler for SIGUSR1. Records command completion."""
    completion_info["completed"] = True
    # No longer storing time, just completion status.


def drain_pty_output(master_fd):
    """
    Reads from the PTY master file descriptor and discards the output.
    This prevents the child process from blocking if it generates output.
    Runs in a separate thread.
    """
    try:
        while not drain_stop_event.is_set():
            # Use select to wait for data with a timeout.
            # This allows periodic checks of drain_stop_event.
            readable, _, _ = select.select([master_fd], [], [], 0.1)  # 100ms timeout
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)  # Read up to 4KB
                    if not data:  # EOF on master_fd (child closed PTY slave)
                        break
                    # Data is read and intentionally discarded.
                except OSError:
                    # master_fd might have been closed or another error occurred.
                    break
            # If select timed out, loop again to check drain_stop_event.
    except Exception:
        # Catch-all for unexpected errors in the drainer thread.
        pass  # Simply let the thread exit.


def main():
    # Register the signal handler for SIGUSR1.
    signal.signal(signal.SIGUSR1, handle_sigusr1)

    parent_pid = os.getpid()
    print(f"Parent PID: {parent_pid}")

    # Create temporary files (they won't be deleted automatically)
    # Use 'w+' for cmd_file to write to it, 'w' isn't needed for others initially
    cmd_tmpfile = tempfile.NamedTemporaryFile(
        mode="w+", delete=False, prefix="ptycmd-", suffix=".sh"
    )
    stdout_tmpfile = tempfile.NamedTemporaryFile(
        delete=False, prefix="ptycmd-", suffix=".stdout"
    )
    stderr_tmpfile = tempfile.NamedTemporaryFile(
        delete=False, prefix="ptycmd-", suffix=".stderr"
    )
    exit_status_tmpfile = tempfile.NamedTemporaryFile(
        delete=False, prefix="ptycmd-", suffix=".exit"
    )

    # Immediately close the file handles for stdout/stderr/exit_status, we only need their names for redirection.
    stdout_tmpfile.close()
    stderr_tmpfile.close()
    exit_status_tmpfile.close()

    cmd_file_path = cmd_tmpfile.name
    stdout_file_path = stdout_tmpfile.name
    stderr_file_path = stderr_tmpfile.name
    exit_status_file_path = exit_status_tmpfile.name

    # Prompt user for the command
    try:
        user_command = input("Enter command to run in PTY: ")
    except EOFError:
        print("\nNo command entered. Exiting.", file=sys.stderr)
        # Clean up the created temporary files before exiting
        os.unlink(cmd_file_path)
        os.unlink(stdout_file_path)
        os.unlink(stderr_file_path)
        os.unlink(exit_status_file_path)
        sys.exit(1)

    # Write the user command to the command temp file
    cmd_tmpfile.write(user_command + "\n")  # Add newline for safety
    cmd_tmpfile.flush()
    cmd_tmpfile.close()  # Close it after writing

    # Construct the shell command for execution within the PTY
    # . cmd_file > stdout_file 2> stderr_file ; echo $? > exit_status_file ; kill -SIGUSR1 parent_pid
    signal_command = f"kill -SIGUSR1 {parent_pid}"
    full_command_for_shell = (
        f". {cmd_file_path} > {stdout_file_path} 2> {stderr_file_path} ; "
        f"echo $? > {exit_status_file_path} ; "
        f"{signal_command}"
    )

    print(f"Executing in PTY: /bin/sh -c '{full_command_for_shell}'")
    print("Waiting for signal...")

    # Initialize variables for the finally block's safety checks.
    child_pid = -1
    master_fd = -1
    drain_thread = None

    try:
        # Fork a child process connected to a new PTY.
        child_pid, master_fd = pty.fork()

        if child_pid == 0:  # Child process
            # pty.fork() (via login_tty) handles setsid() and PTY slave setup
            # for stdin, stdout, stderr.
            try:
                # Execute the command using /bin/sh.
                os.execvpe(
                    "/bin/sh", ["/bin/sh", "-c", full_command_for_shell], os.environ
                )
            except Exception as e:
                # If execvpe fails, child must exit. Write error to its stderr (PTY slave).
                sys.stderr.write(f"Child execvpe failed: {e}\n")
                sys.exit(127)  # Standard exit code for command not found / exec error.

        else:  # Parent process
            # Start the PTY draining thread.
            drain_thread = threading.Thread(target=drain_pty_output, args=(master_fd,))
            drain_thread.daemon = True  # Allow main program to exit if thread is stuck.
            drain_thread.start()

            # Wait for the SIGUSR1 signal indicating command completion.
            while not completion_info["completed"]:
                try:
                    signal.pause()  # Atomically wait for any signal.
                except InterruptedError:  # Standard in Python 3.3+
                    # Another signal (not SIGUSR1) was caught. Loop to check completion_info.
                    pass
                except OSError as e:
                    # For broader compatibility (e.g., older Python or specific OS behavior)
                    # check for EINTR if InterruptedError is not specific enough.
                    if e.errno == errno.EINTR:
                        pass  # Interrupted by a signal, loop.
                    else:
                        raise  # Re-raise other OSErrors.

            # SIGUSR1 received; command execution finished.
            print("\nSignal received: Command finished.")
            print("Temporary files:")
            print(f"  Command:      {cmd_file_path}")
            print(f"  Stdout:       {stdout_file_path}")
            print(f"  Stderr:       {stderr_file_path}")
            print(f"  Exit Status:  {exit_status_file_path}")

            # Child process will exit shortly after sending the signal.
            # Cleanup (drainer, master_fd, waitpid) is handled in 'finally'.
            # Temporary files are intentionally not deleted here.

    except Exception as e:
        print(f"An error occurred in the parent process: {e}", file=sys.stderr)
    finally:
        # Signal the drainer thread to stop and wait for it to join.
        if drain_thread:  # Check if drain_thread object was created.
            drain_stop_event.set()
            if drain_thread.is_alive():
                drain_thread.join(timeout=1.0)  # Short timeout for drainer to exit.

        # Close the master PTY file descriptor if it was opened.
        if master_fd >= 0:  # Check if master_fd seems valid.
            try:
                os.close(master_fd)
            except OSError:
                pass  # e.g., Bad file descriptor if already closed.

        # Manage the child process: ensure it's terminated and reaped.
        if child_pid > 0:  # If child was successfully forked.
            # If parent is exiting (e.g., due to KeyboardInterrupt)
            # and command hasn't signaled completion, try to kill the child.
            if not completion_info["completed"]:
                try:
                    os.kill(child_pid, signal.SIGKILL)  # Force kill.
                except ProcessLookupError:  # Child already exited.
                    pass
                except OSError:  # Other errors (e.g., permission - unlikely).
                    pass

            # Always attempt to reap the child to prevent zombies.
            try:
                # Blocking wait for child to exit.
                os.waitpid(child_pid, 0)
            except ChildProcessError:  # Child already reaped or PID invalid.
                pass
            except InterruptedError:  # waitpid can also be interrupted.
                # If interrupted, a zombie might be left. In a real application,
                # might need to loop here. For this script, we proceed.
                pass
            except OSError:  # Other OS-level errors with waitpid.
                pass
        # Note: Temporary files are NOT deleted here as per requirements.


if __name__ == "__main__":
    main()
