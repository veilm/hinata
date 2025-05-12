import os
import pty
import signal
import time
import sys
import threading
import select
import errno

# Global dictionary to store completion status and time.
# Accessed by the signal handler and the main thread.
completion_info = {"completed": False, "end_time": None}

# Event to signal the PTY draining thread to stop.
drain_stop_event = threading.Event()

def handle_sigusr1(signum, frame):
    """Signal handler for SIGUSR1. Records command completion time."""
    completion_info["completed"] = True
    completion_info["end_time"] = time.time()

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
        pass # Simply let the thread exit.

def main():
    # Register the signal handler for SIGUSR1.
    signal.signal(signal.SIGUSR1, handle_sigusr1)

    parent_pid = os.getpid()
    user_command = "date; ls -l; sleep 2.5"
    
    # Append a command to signal the parent process upon completion.
    signal_command = f"kill -SIGUSR1 {parent_pid}"
    # The shell executes commands sequentially. If user_command fails,
    # `kill` should still run unless `set -e` is active (not default for `sh -c`).
    full_command_for_shell = f"{user_command}; {signal_command}"

    start_time = time.time()
    print(f"Parent PID: {parent_pid}")
    print(f"Attempting to run command via PTY: /bin/sh -c '{full_command_for_shell}'")

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
                os.execvpe("/bin/sh", ["/bin/sh", "-c", full_command_for_shell], os.environ)
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
                except InterruptedError: # Standard in Python 3.3+
                    # Another signal (not SIGUSR1) was caught. Loop to check completion_info.
                    pass
                except OSError as e:
                    # For broader compatibility (e.g., older Python or specific OS behavior)
                    # check for EINTR if InterruptedError is not specific enough.
                    if e.errno == errno.EINTR:
                        pass # Interrupted by a signal, loop.
                    else:
                        raise # Re-raise other OSErrors.

            # SIGUSR1 received; command is considered finished.
            end_time = completion_info["end_time"]
            duration = end_time - start_time

            print(f"\nSignal received: Command execution presumed finished.")
            print(f"  Start time: {start_time:.4f}")
            print(f"  End time:   {end_time:.4f} (time of signal reception)")
            print(f"  Duration:   {duration:.4f} seconds")

            # Child process will exit shortly after sending the signal.
            # Cleanup (drainer, master_fd, waitpid) is handled in 'finally'.

    except Exception as e:
        print(f"An error occurred in the parent process: {e}", file=sys.stderr)
    finally:
        # Signal the drainer thread to stop and wait for it to join.
        if drain_thread:  # Check if drain_thread object was created.
            drain_stop_event.set()
            if drain_thread.is_alive():
                drain_thread.join(timeout=1.0) # Short timeout for drainer to exit.

        # Close the master PTY file descriptor if it was opened.
        if master_fd >= 0:  # Check if master_fd seems valid.
            try:
                os.close(master_fd)
            except OSError:
                pass # e.g., Bad file descriptor if already closed.

        # Manage the child process: ensure it's terminated and reaped.
        if child_pid > 0:  # If child was successfully forked.
            # If parent is exiting (e.g., due to KeyboardInterrupt)
            # and command hasn't signaled completion, try to kill the child.
            if not completion_info["completed"]:
                try:
                    os.kill(child_pid, signal.SIGKILL)  # Force kill.
                except ProcessLookupError:  # Child already exited.
                    pass
                except OSError: # Other errors (e.g., permission - unlikely).
                    pass
            
            # Always attempt to reap the child to prevent zombies.
            try:
                # Blocking wait for child to exit.
                os.waitpid(child_pid, 0)
            except ChildProcessError: # Child already reaped or PID invalid.
                pass
            except InterruptedError: # waitpid can also be interrupted.
                # For a demo, not looping on waitpid here is acceptable.
                # A zombie might be left if waitpid is interrupted here and not handled.
                pass
            except OSError: # Other OS-level errors with waitpid.
                pass

if __name__ == "__main__":
    main()