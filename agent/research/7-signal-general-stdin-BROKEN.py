#!/usr/bin/env python3

import os
import signal
import time
import sys
import subprocess
import errno
import tempfile
import shutil  # For removing the temp directory

# Global dictionary to store completion status.
# Accessed by the signal handler and the main thread.
completion_info = {"completed": False}

# No PTY drainer thread needed.


def handle_sigusr1(signum, frame):
    """Signal handler for SIGUSR1. Records command completion."""
    completion_info["completed"] = True
    # No longer storing time, just completion status.


# No drain_pty_output function needed.


def main():
    # Register the signal handler for SIGUSR1.
    signal.signal(signal.SIGUSR1, handle_sigusr1)

    parent_pid = os.getpid()
    print(f"Parent PID: {parent_pid}")

    # Create a temporary directory to hold the FIFO
    # This makes cleanup easier.
    temp_dir = tempfile.mkdtemp(prefix="bash-stdin-")
    cmd_fifo_path = os.path.join(temp_dir, "cmd.fifo")

    # Create temporary files for stdout, stderr, and exit status
    # These files persist after the script finishes.
    stdout_tmpfile = tempfile.NamedTemporaryFile(
        delete=False, prefix="bash-stdout-", suffix=".txt"
    )
    stderr_tmpfile = tempfile.NamedTemporaryFile(
        delete=False, prefix="bash-stderr-", suffix=".txt"
    )
    exit_status_tmpfile = tempfile.NamedTemporaryFile(
        delete=False, prefix="bash-exit-", suffix=".txt"
    )

    stdout_file_path = stdout_tmpfile.name
    stderr_file_path = stderr_tmpfile.name
    exit_status_file_path = exit_status_tmpfile.name

    # Close the file handles immediately, we only need the paths.
    stdout_tmpfile.close()
    stderr_tmpfile.close()
    exit_status_tmpfile.close()

    # Create the named pipe (FIFO)
    try:
        os.mkfifo(cmd_fifo_path)
        print(f"Created FIFO: {cmd_fifo_path}")
    except OSError as e:
        print(f"Failed to create FIFO: {e}", file=sys.stderr)
        shutil.rmtree(temp_dir)  # Clean up directory
        sys.exit(1)

    # Prompt user for the command
    try:
        user_command = input("Enter command to run via bash stdin: ")
    except EOFError:
        print("\nNo command entered. Exiting.", file=sys.stderr)
        # Clean up FIFO and directory before exiting
        os.unlink(cmd_fifo_path)
        shutil.rmtree(temp_dir)
        # Also clean up output files created so far
        os.unlink(stdout_file_path)
        os.unlink(stderr_file_path)
        os.unlink(exit_status_file_path)
        sys.exit(1)

    # Construct the full shell script to be executed by the bash process
    # Wrap user command in parentheses to capture combined output/status
    # Send SIGUSR1 signal to the parent process *after* everything else.
    signal_command = f"kill -SIGUSR1 {parent_pid}"
    full_bash_script = (
        f"( {user_command} ) > {stdout_file_path} 2> {stderr_file_path} ; "
        f"echo $? > {exit_status_file_path} ; "
        f"{signal_command}\n"  # Ensure newline at the end
    )

    print(f"Bash will execute script from FIFO:")
    print("--- Script Start ---")
    print(full_bash_script.strip())
    print("--- Script End ---")
    print(f"Starting bash and waiting for signal...")

    # This function will run in the child process right before execing bash
    def setup_fifo_stdin():
        # Module dependencies 'os' and 'sys' are global.
        # This function runs in the child process just before exec.
        # If any os call here fails (e.g., os.open, os.dup2), the exception
        # will be caught by the Popen machinery in the child, pickled,
        # sent to the parent, and re-raised by Popen in the parent.
        # This prevents the parent from hanging if child setup fails.

        # Open the FIFO for reading. This call will block until the parent
        # opens the FIFO for writing.
        fd = os.open(cmd_fifo_path, os.O_RDONLY)

        # Duplicate the FIFO's read descriptor to be the child's stdin (fd 0).
        # sys.stdin.fileno() is normally 0.
        if fd != sys.stdin.fileno():
            os.dup2(fd, sys.stdin.fileno())
            os.close(fd)  # Close the original fd as it's now duplicated to stdin.
        # If os.open happened to return fd 0 (e.g., if stdin was closed prior),
        # then fd is already stdin, so no dup2 or close(fd) is needed.

    # Initialize bash_process for the finally block.
    bash_process = None
    fifo_write_stream = None  # Initialize write stream variable

    try:
        # --- Start the bash process FIRST ---
        # The child process, in preexec_fn (setup_fifo_stdin), will attempt to
        # open the FIFO for reading (os.O_RDONLY). This call in the child will
        # block until the parent opens the FIFO for writing.
        # If preexec_fn fails (e.g., FIFO path incorrect), setup_fifo_stdin will
        # raise an exception. Popen catches this, communicates it to the parent,
        # and the Popen call in the parent re-raises it.
        bash_process = subprocess.Popen(
            ["/bin/bash"],
            preexec_fn=setup_fifo_stdin,  # Child sets up its stdin from FIFO
            stdout=subprocess.DEVNULL,  # Redirect child's stdout to /dev/null
            stderr=subprocess.DEVNULL,  # Redirect child's stderr to /dev/null
            close_fds=True,  # Close other FDs in child before exec
        )
        # Popen returns control to the parent here. The child process is forked
        # and is executing preexec_fn; it's likely blocked on its os.open(O_RDONLY).

        # --- Now, PARENT opens FIFO for writing ---
        # This call will block until the child opens its end for reading (which it
        # should be attempting in preexec_fn). Once both ends are open, both calls unblock.
        # If the child process terminated prematurely (e.g., an error in preexec_fn
        # that Popen didn't catch, or some other issue), this open call in the
        # parent might hang. However, the modified preexec_fn (letting exceptions
        # propagate) makes it more likely that Popen would raise an error above,
        # preventing this line from being reached if preexec_fn failed.
        try:
            # Using a file object for easier writing of the script.
            fifo_write_stream = open(cmd_fifo_path, "w")
        except OSError as e:
            print(
                f"Failed to open FIFO {cmd_fifo_path} for writing: {e}", file=sys.stderr
            )
            # If this fails, Popen might have started a child that needs cleanup.
            # The 'finally' block will handle bash_process.
            raise  # Re-raise to go to outer try's except/finally.

        # At this point, FIFO is open on both ends. Child's preexec_fn completes,
        # bash is exec'd with its stdin connected to the read end of the FIFO.
        # Parent has the write end.
        # --- Write the command script to the FIFO ---
        try:
            # Write using the stream opened by the parent.
            fifo_write_stream.write(full_bash_script)
            fifo_write_stream.flush()  # Ensure data is sent to the pipe buffer
            # DO NOT close fifo_write_stream here yet. Closing it signals EOF to bash.
            # We close it in the finally block to ensure it happens even if errors occur later.
            # However, bash needs EOF to stop reading stdin and execute the final kill command.
            # Let's close it *after* writing but *before* waiting for the signal.
            # If writing fails, it will be closed in finally.
            fifo_write_stream.close()
            fifo_write_stream = None  # Indicate it's closed

        except OSError as e:
            # This might happen if bash exits prematurely before/during write
            print(
                f"Error writing to FIFO: {e}. Bash might have exited.", file=sys.stderr
            )
            # Writing failed, proceed to finally block for cleanup.
            # fifo_write_stream should be closed there if still open.
            raise  # Re-raise to ensure we don't wait for signal

        # --- Wait for the signal ---
        print("Waiting for completion signal...")
        while not completion_info["completed"]:
            try:
                signal.pause()  # Atomically wait for any signal.
            except InterruptedError:
                pass  # Signal received, loop will check completion_info
            except OSError as e:
                if e.errno == errno.EINTR:
                    pass  # Interrupted by a signal, loop.
                else:
                    raise  # Re-raise other OSErrors.

        # SIGUSR1 received; command execution finished (according to bash script).
        print("\nSignal received: Command finished executing via bash.")
        print("Temporary files:")
        print(f"  FIFO Path:    {cmd_fifo_path} (will be deleted)")
        print(f"  Stdout:       {stdout_file_path}")
        print(f"  Stderr:       {stderr_file_path}")
        print(f"  Exit Status:  {exit_status_file_path}")

        # Bash process should exit shortly after sending the signal and reading EOF.
        # Wait for it to ensure proper cleanup.

    except Exception as e:
        print(f"An error occurred in the parent process: {e}", file=sys.stderr)
    finally:
        # Ensure the write stream to the FIFO is closed.
        if fifo_write_stream and not fifo_write_stream.closed:
            try:
                print("Closing FIFO write stream in finally block...")
                fifo_write_stream.close()
            except OSError as e:
                print(f"Warning: Error closing FIFO write stream: {e}", file=sys.stderr)

        # Manage the bash process: ensure it's terminated and reaped.
        if bash_process:
            # If parent is exiting (e.g., due to KeyboardInterrupt)
            # and command hasn't signaled completion, try to kill bash.
            if not completion_info["completed"]:
                print(
                    "\nInterrupt received before command completion signal.",
                    file=sys.stderr,
                )
                print("Attempting to terminate bash process...", file=sys.stderr)
                try:
                    # Try SIGTERM first
                    bash_process.terminate()
                    try:
                        # Wait briefly for graceful termination
                        bash_process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        print(
                            "Bash did not terminate gracefully, sending SIGKILL.",
                            file=sys.stderr,
                        )
                        bash_process.kill()  # Force kill
                except ProcessLookupError:
                    print("Bash process already exited.", file=sys.stderr)
                except Exception as e:
                    print(f"Error terminating bash process: {e}", file=sys.stderr)

            # Always attempt to wait for the process to prevent zombies,
            # unless we already waited successfully above.
            if bash_process.poll() is None:  # Check if it's still running
                try:
                    print("Waiting for bash process to exit...")
                    bash_process.wait()
                    print("Bash process exited.")
                except ChildProcessError:
                    pass  # Process already reaped or invalid
                except InterruptedError:
                    print(
                        "Wait interrupted, bash process might become a zombie.",
                        file=sys.stderr,
                    )
                except Exception as e:
                    print(f"Error waiting for bash process: {e}", file=sys.stderr)

        # Clean up the FIFO and its directory
        try:
            os.unlink(cmd_fifo_path)
        except OSError as e:
            # Ignore 'file not found' or errors if it couldn't be created
            if e.errno != errno.ENOENT:
                print(
                    f"Warning: Could not remove FIFO {cmd_fifo_path}: {e}",
                    file=sys.stderr,
                )
        try:
            shutil.rmtree(temp_dir)
        except OSError as e:
            print(
                f"Warning: Could not remove temp directory {temp_dir}: {e}",
                file=sys.stderr,
            )

        # Note: Output/Error/Status files are NOT deleted here as per requirements.


if __name__ == "__main__":
    main()
