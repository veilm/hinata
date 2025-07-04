import os
import pty
import select
import subprocess
import time
import fcntl

LOG_FILE = "pty.log"


def log_pty_output_demo():
    """
    Spawns a PTY, runs a shell, sends 'pwd', reads all output for a
    short duration, and writes it verbatim to a log file.
    """
    master_fd, slave_fd = -1, -1  # Initialize for finally block
    shell_process = None
    output_buffer = b""

    print(f"Starting PTY demo. All raw output will be logged to {LOG_FILE}")

    try:
        # Create a pseudo-terminal pair
        master_fd, slave_fd = pty.openpty()

        # Spawn the shell (/bin/bash used here)
        # Using --noprofile and --norc for a cleaner startup
        shell_process = subprocess.Popen(
            ["/bin/bash", "--noprofile", "--norc"],
            preexec_fn=os.setsid,  # Make it a session leader
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            # universal_newlines=False # Default, work with bytes
        )

        # Parent process closes its copy of the slave descriptor
        os.close(slave_fd)
        slave_fd = -1  # Mark as closed

        # Allow shell a moment to initialize
        time.sleep(0.3)

        # --- Read any initial output (like prompt fragments) ---
        # Use select with a short timeout to grab initial data without blocking indefinitely
        initial_timeout = 0.2  # seconds
        while True:
            readable, _, _ = select.select([master_fd], [], [], initial_timeout)
            if master_fd in readable:
                try:
                    initial_data = os.read(master_fd, 4096)
                    if not initial_data:  # EOF
                        print("Warning: PTY closed unexpectedly during initial read.")
                        break
                    # print(f"Captured initial data: {initial_data}") # Debug
                    output_buffer += initial_data
                    # Reset timeout if we got data, maybe more is coming quickly
                    initial_timeout = 0.05
                except OSError as e:
                    print(f"Warning: OSError during initial read: {e}")
                    break
            else:
                # select timed out, no more initial data readily available
                break
        # print("Finished capturing initial output.")

        # --- Send the 'pwd' command ---
        command = b"pwd\n"
        print(f"Sending command: {command.decode().strip()}")
        os.write(master_fd, command)

        # --- Read output after the command ---
        # Read for a fixed duration or until EOF/error after sending the command
        read_duration = 1.5  # seconds
        end_time = time.time() + read_duration

        while time.time() < end_time:
            # Wait for data, but with a timeout so the loop condition is checked
            readable, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:  # EOF
                        print("PTY closed by shell.")
                        break
                    output_buffer += data
                except OSError as e:
                    # Could happen if shell exits abruptly after PTY is readable
                    print(f"OSError during command output read: {e}")
                    break

        print(f"Finished reading PTY output ({len(output_buffer)} bytes).")

        # --- Write all captured output to log file ---
        try:
            with open(LOG_FILE, "wb") as f:
                f.write(output_buffer)
            print(f"Successfully wrote all output to {LOG_FILE}")
        except IOError as e:
            print(f"Error writing to log file {LOG_FILE}: {e}")

    except Exception as e:
        print(f"An error occurred during the PTY demo: {e}")
    finally:
        # --- Cleanup resources ---
        print("Cleaning up resources...")
        if master_fd != -1:
            try:
                os.close(master_fd)
            except OSError as e:
                print(f"Error closing master_fd: {e}")

        if slave_fd != -1:  # Should be closed already if Popen succeeded
            try:
                os.close(slave_fd)
            except OSError as e:
                print(f"Error closing slave_fd: {e}")

        if shell_process and shell_process.poll() is None:  # If shell is still running
            print("Terminating shell process...")
            try:
                shell_process.terminate()
                shell_process.wait(timeout=1.0)  # Wait for graceful termination
            except subprocess.TimeoutExpired:
                print("Shell process did not terminate gracefully, killing...")
                shell_process.kill()
                try:
                    shell_process.wait(timeout=1.0)  # Wait for kill to complete
                except subprocess.TimeoutExpired:
                    print("Warning: Shell process did not exit after kill.")
            except Exception as e:
                print(f"Error terminating/killing shell process: {e}")
            else:
                print("Shell process terminated.")
        elif shell_process:
            print(f"Shell process already exited with code: {shell_process.poll()}")


if __name__ == "__main__":
    log_pty_output_demo()
