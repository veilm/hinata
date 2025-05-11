import os
import pty
import select
import subprocess
import time
import fcntl

# A unique marker string to identify the end of a command's output
COMMAND_EXECUTION_MARKER = "___PTY_DEMO_CMD_END_MARKER_8J4H5G68F___"

def execute_command_and_get_output(master_fd, command_str):
    """
    Sends a command to the shell via the master_fd of a PTY,
    waits for a unique marker to be echoed, and then parses the output.
    """
    if '\n' in command_str:
        raise ValueError("Command string must not contain newlines for this simplified parser.")

    # Send the actual command, followed by a newline
    os.write(master_fd, command_str.strip().encode('utf-8') + b'\n')
    
    # Send the marker command, which will echo our unique marker string
    marker_command = f"echo '{COMMAND_EXECUTION_MARKER}'\n"
    os.write(master_fd, marker_command.encode('utf-8'))

    output_buffer = b""
    timeout_seconds = 5.0
    start_time = time.time()

    # Read from master_fd until the marker is seen or timeout occurs
    while True:
        if time.time() - start_time > timeout_seconds:
            error_message = f"Timeout waiting for marker for command: '{command_str}'.\n"
            error_message += f"Buffer so far: {output_buffer.decode(errors='replace')}"
            raise TimeoutError(error_message)

        # Wait for data to be available on master_fd (with a short timeout for the select call)
        readable, _, _ = select.select([master_fd], [], [], 0.1) 
        
        if master_fd in readable:
            try:
                data = os.read(master_fd, 4096) # Read available data
                if not data:  # EOF, shell might have exited unexpectedly
                    break 
                output_buffer += data
                # Check if the marker string is present in the accumulated buffer
                if COMMAND_EXECUTION_MARKER.encode('utf-8') in output_buffer:
                    # Marker found. We can break after attempting one tiny final read 
                    # to catch any trailing characters like the newline after the marker itself.
                    time.sleep(0.02) # Brief pause for system to flush tty buffer
                    try:
                        # Non-blocking attempt to grab any final bytes
                        more_data = os.read(master_fd, 1024) 
                        if more_data:
                            output_buffer += more_data
                    except BlockingIOError:
                        pass # No more data, which is fine
                    break 
            except BlockingIOError:
                # This might happen if O_NONBLOCK is set and select was slightly off,
                # or if select timed out and we proceed. The outer loop handles timeout.
                pass
            except OSError as e:
                # Can happen if the fd is closed, e.g. shell crashes
                # print(f"OSError during read for command '{command_str}': {e}")
                break
    
    full_output_str = output_buffer.decode('utf-8', errors='replace')
    # For debugging:
    # print(f"--- Raw output for '{command_str}' ---\n{full_output_str}\n---------------------------------")

    # Parse the output:
    # The full output typically contains:
    # 1. Echo of the command itself (e.g., "pwd\r\n")
    # 2. Actual output of the command (e.g., "/current/path\r\n")
    # 3. Echo of the marker command (e.g., "echo 'MARKER_STRING'\r\n")
    # 4. The marker string itself (e.g., "MARKER_STRING\r\n")

    all_lines = full_output_str.splitlines()
    
    # Find the line that IS the marker output.
    marker_line_idx = -1
    for i, line in enumerate(all_lines):
        if line.strip() == COMMAND_EXECUTION_MARKER:
            marker_line_idx = i
            break
    
    if marker_line_idx == -1:
        # This indicates a problem, marker wasn't found as expected.
        return f"ERROR: Marker '{COMMAND_EXECUTION_MARKER}' not found in parsed output for '{command_str}'."

    # The relevant lines are before the marker output line.
    # These lines include the command echo, command output, and marker command echo.
    candidate_lines = all_lines[:marker_line_idx]
    
    if not candidate_lines:
        return "" # No output before the marker content itself

    # Heuristics to strip command echo and marker command echo:
    # Assumes a simple shell like /bin/sh that echoes commands.
    
    start_idx = 0
    # The first line of candidates is often the echoed command.
    # Check if it contains the command string we sent.
    # .strip() on candidate_lines[0] handles potential leading/trailing whitespace/control chars.
    if candidate_lines and command_str.strip() in candidate_lines[0].strip():
        start_idx = 1
    
    end_idx = len(candidate_lines)
    # The last line of candidates is often the echoed marker command.
    if candidate_lines and start_idx < end_idx and \
       f"echo '{COMMAND_EXECUTION_MARKER}'" in candidate_lines[-1].strip():
        end_idx -= 1
        
    actual_output_lines = []
    if start_idx <= end_idx: # Ensure slice is valid (e.g. start_idx is not > end_idx)
        actual_output_lines = candidate_lines[start_idx:end_idx]
    
    # Join the remaining lines, stripping any carriage returns missed by splitlines()
    return "\n".join(line.strip('\r') for line in actual_output_lines).strip()


def pty_demo():
    master_fd, slave_fd = -1, -1 # Initialize to ensure they are defined for finally
    shell_process = None

    try:
        master_fd, slave_fd = pty.openpty()

        # Set master_fd to non-blocking for the initial flush.
        # The execute_command_and_get_output function uses select,
        # so non-blocking on master_fd is generally good practice with select.
        fl = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        # Spawn the shell (/bin/sh is simpler for this than /bin/bash -i)
        shell_process = subprocess.Popen(
            ['/bin/sh'],
            preexec_fn=os.setsid,  # Make it a session leader for easier termination
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            # universal_newlines=False (default), work with bytes
        )
        
        # The slave FD is now used by the child process (shell).
        # The parent process should close its copy of slave_fd.
        os.close(slave_fd)
        slave_fd = -1 # Mark as closed

        # Brief pause for shell to initialize, then flush any initial output (e.g., prompt fragment)
        time.sleep(0.2)
        try:
            while True: # Read any junk output
                initial_junk = os.read(master_fd, 4096)
                if not initial_junk: # Should not happen with O_NONBLOCK unless EOF
                    break
                # print(f"Flushed initial PTY junk: {initial_junk.decode(errors='replace')}")
        except BlockingIOError:
            pass # This is expected when no more data is immediately available

        # 1. Run `pwd` and capture its output
        print("Running initial 'pwd'...")
        initial_pwd = execute_command_and_get_output(master_fd, "pwd")
        print(f"Initial PWD: '{initial_pwd}'")

        # 2. Run `cd $HOME`
        #    The shell itself will expand $HOME. We get Python's view for verification.
        expected_home_dir = os.path.expanduser("~")
        print(f"Running 'cd $HOME' (shell will expand $HOME, Python expects: '{expected_home_dir}')...")
        # Output of 'cd' is typically empty; we mainly care that it executes.
        # The helper function will still wait for the marker.
        cd_output = execute_command_and_get_output(master_fd, "cd $HOME")
        if cd_output: # Should be empty for successful 'cd' in sh
             print(f"Output from 'cd $HOME' (unexpected): '{cd_output}'")
        print("'cd $HOME' command executed.")

        # 3. Run `pwd` again and capture its output
        print("Running final 'pwd'...")
        final_pwd = execute_command_and_get_output(master_fd, "pwd")
        print(f"Final PWD: '{final_pwd}'")

        # 4. Confirm that the directory changed as expected
        print("\n--- Verification ---")
        print(f"Initial PWD from PTY: '{initial_pwd}'")
        print(f"Expected PWD after 'cd $HOME' (from os.path.expanduser): '{expected_home_dir}'")
        print(f"Actual final PWD from PTY: '{final_pwd}'")

        if final_pwd == expected_home_dir:
            print("SUCCESS: PWD changed to $HOME as expected.")
        else:
            print(f"FAILURE: PWD did not change to $HOME correctly. Got '{final_pwd}', expected '{expected_home_dir}'.")
            if initial_pwd == final_pwd and initial_pwd != expected_home_dir:
                 print("Note: PWD did not change at all. 'cd $HOME' might have failed or led to the same directory.")
            elif initial_pwd == expected_home_dir and final_pwd == expected_home_dir:
                 print("Note: Initial PWD was already $HOME. 'cd $HOME' correctly resulted in PWD being $HOME.")


    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Cleanup resources
        if master_fd != -1:
            os.close(master_fd)
        if slave_fd != -1: # Should have been closed already if Popen succeeded
             os.close(slave_fd)
        
        if shell_process and shell_process.poll() is None: # If shell is still running
            # print("Terminating shell process...")
            shell_process.terminate()
            try:
                shell_process.wait(timeout=1.0) # Wait for graceful termination
            except subprocess.TimeoutExpired:
                # print("Shell process did not terminate gracefully, killing...")
                shell_process.kill()
                shell_process.wait() # Wait for kill to complete
            # print("Shell process terminated.")

if __name__ == "__main__":
    pty_demo()