#include <errno.h>
#include <fcntl.h>
#include <signal.h>  // For SIGPIPE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define FIFO_PATH "/tmp/my_bash_fifo_for_c_program"
#define LOG_FILE "bash.log"
#define BUFFER_SIZE 4096

// Global for atexit handler to clean up FIFO
const char* g_fifo_path = FIFO_PATH;

void cleanup_fifo_on_exit(void) { unlink(g_fifo_path); }

void print_error_and_exit(const char* msg) {
	perror(msg);
	exit(EXIT_FAILURE);
}

int main() {
	pid_t child_pid;
	int bash_stdin_fifo_fd;    // FIFO for bash's stdin (parent writes, child
	                           // reads)
	int child_stdout_pipe[2];  // Pipe for bash's stdout
	int child_stderr_pipe[2];  // Pipe for bash's stderr
	FILE* log_fp = NULL;

	// Ignore SIGPIPE, so write() returns EPIPE instead of terminating the
	// process
	signal(SIGPIPE, SIG_IGN);

	// --- 1. Create FIFO for bash's stdin ---
	// Clean up preexisting FIFO if any
	struct stat st_fifo;
	if (lstat(FIFO_PATH, &st_fifo) == 0) {
		if (S_ISFIFO(st_fifo.st_mode)) {
			if (unlink(FIFO_PATH) == -1) {
				print_error_and_exit("Failed to unlink existing FIFO");
			}
		} else {
			fprintf(stderr,
			        "Error: %s exists and is not a FIFO. Please remove it.\n",
			        FIFO_PATH);
			exit(EXIT_FAILURE);
		}
	}
	if (mkfifo(FIFO_PATH, 0666) == -1) {
		print_error_and_exit("mkfifo failed");
	}
	atexit(cleanup_fifo_on_exit);  // Register FIFO cleanup

	// --- 2. Create pipes for bash's stdout and stderr ---
	if (pipe(child_stdout_pipe) == -1) {
		print_error_and_exit("pipe for stdout failed");
	}
	if (pipe(child_stderr_pipe) == -1) {
		print_error_and_exit("pipe for stderr failed");
	}

	// --- 3. Fork child process ---
	child_pid = fork();

	if (child_pid == -1) {
		print_error_and_exit("fork failed");
	}

	if (child_pid == 0) {
		// --- Child Process ---
		int fifo_fd_child;

		// Redirect stdin from FIFO
		fifo_fd_child = open(FIFO_PATH, O_RDONLY);
		if (fifo_fd_child == -1) {
			perror("Child: Failed to open FIFO for reading");
			exit(EXIT_FAILURE);
		}
		if (dup2(fifo_fd_child, STDIN_FILENO) == -1) {
			perror("Child: dup2 stdin failed");
			exit(EXIT_FAILURE);
		}
		close(fifo_fd_child);

		// Redirect stdout to pipe
		close(child_stdout_pipe[0]);  // Close read end of stdout pipe
		if (dup2(child_stdout_pipe[1], STDOUT_FILENO) == -1) {
			perror("Child: dup2 stdout failed");
			exit(EXIT_FAILURE);
		}
		close(child_stdout_pipe[1]);

		// Redirect stderr to pipe
		close(child_stderr_pipe[0]);  // Close read end of stderr pipe
		if (dup2(child_stderr_pipe[1], STDERR_FILENO) == -1) {
			perror("Child: dup2 stderr failed");
			exit(EXIT_FAILURE);
		}
		close(child_stderr_pipe[1]);

		// Execute bash
		// Using "bash -i" can make it behave more like an interactive shell if
		// needed, but for simple command execution, "bash" is fine.
		execlp("bash", "bash", NULL);

		// execlp only returns on error
		perror("Child: execlp bash failed");
		exit(EXIT_FAILURE);
	} else {
		// --- Parent Process ---
		fd_set read_fds;
		char buffer[BUFFER_SIZE];
		int max_fd;

		// Open FIFO for writing to bash's stdin
		// This might block until the child opens it for reading.
		bash_stdin_fifo_fd = open(FIFO_PATH, O_WRONLY);
		if (bash_stdin_fifo_fd == -1) {
			perror("Parent: Failed to open FIFO for writing");
			kill(child_pid, SIGKILL);  // Kill child if we can't setup control
			waitpid(child_pid, NULL, 0);
			exit(EXIT_FAILURE);
		}

		// Close unused ends of pipes
		close(child_stdout_pipe[1]);  // Close write end of stdout pipe
		close(child_stderr_pipe[1]);  // Close write end of stderr pipe

		// Open log file
		log_fp = fopen(LOG_FILE, "a");
		if (log_fp == NULL) {
			perror("Parent: Failed to open log file");
			close(bash_stdin_fifo_fd);
			close(child_stdout_pipe[0]);
			close(child_stderr_pipe[0]);
			kill(child_pid, SIGKILL);
			waitpid(child_pid, NULL, 0);
			exit(EXIT_FAILURE);
		}
		printf("Parent: Logging bash output to %s\n", LOG_FILE);
		printf(
		    "Parent: Enter commands for bash. Type 'exit' in bash to quit.\n");

		// File descriptors to monitor
		int user_input_fd = STDIN_FILENO;
		int bash_out_fd = child_stdout_pipe[0];
		int bash_err_fd = child_stderr_pipe[0];

		int bash_process_alive = 1;

		while (bash_process_alive || bash_out_fd != -1 || bash_err_fd != -1) {
			FD_ZERO(&read_fds);
			max_fd = 0;

			if (user_input_fd != -1) {
				FD_SET(user_input_fd, &read_fds);
				if (user_input_fd > max_fd) max_fd = user_input_fd;
			}
			if (bash_out_fd != -1) {
				FD_SET(bash_out_fd, &read_fds);
				if (bash_out_fd > max_fd) max_fd = bash_out_fd;
			}
			if (bash_err_fd != -1) {
				FD_SET(bash_err_fd, &read_fds);
				if (bash_err_fd > max_fd) max_fd = bash_err_fd;
			}

			if (max_fd == 0 && !bash_process_alive) {  // No more FDs to monitor
				                                       // and bash exited
				// this check might be redundant if bash_out/err_fd correctly
				// become -1 and bash_process_alive is false
				break;
			}

			// If only user_input_fd is left but bash is gone, no point in
			// reading user input
			if (user_input_fd != -1 && !bash_process_alive &&
			    bash_stdin_fifo_fd != -1) {
				printf(
				    "Parent: Bash process terminated, closing input pipe to "
				    "bash.\n");
				close(bash_stdin_fifo_fd);
				bash_stdin_fifo_fd = -1;
				// We might stop prompting user if bash is gone.
				// For simplicity, we'll let select handle it by user_input_fd
				// no longer being written to bash. Or, we can close
				// user_input_fd monitoring: close(user_input_fd); // This would
				// close parent's actual STDIN, not good. Just set it to -1 for
				// select logic.
				printf(
				    "Parent: No longer accepting user input as bash has "
				    "exited.\n");
				FD_CLR(
				    user_input_fd,
				    &read_fds);  // Ensure user input is not processed for bash
				user_input_fd = -1;  // Stop monitoring user input for bash
			}

			int activity = select(max_fd + 1, &read_fds, NULL, NULL, NULL);

			if (activity == -1) {
				if (errno == EINTR)
					continue;  // Interrupted by signal, try again
				perror("Parent: select failed");
				break;
			}

			// Check if bash process has exited
			if (bash_process_alive) {
				int status;
				pid_t result = waitpid(child_pid, &status, WNOHANG);
				if (result == child_pid) {
					printf("Parent: Bash process exited ");
					if (WIFEXITED(status)) {
						printf("with status %d.\n", WEXITSTATUS(status));
					} else if (WIFSIGNALED(status)) {
						printf("due to signal %d.\n", WTERMSIG(status));
					} else {
						printf("(unknown reason).\n");
					}
					bash_process_alive = 0;
					// If bash stdin pipe is still open, close it.
					// Bash won't read anymore, so further writes could block or
					// EPIPE.
					if (bash_stdin_fifo_fd != -1) {
						close(bash_stdin_fifo_fd);
						bash_stdin_fifo_fd = -1;
					}
				} else if (result == -1) {
					perror("Parent: waitpid failed");
					bash_process_alive = 0;  // Assume the worst
				}
			}

			// Handle user input
			if (user_input_fd != -1 && FD_ISSET(user_input_fd, &read_fds)) {
				if (bash_stdin_fifo_fd !=
				    -1) {  // Only process if bash is potentially listening
					printf("bash_cmd> ");
					fflush(stdout);
					ssize_t len = read(user_input_fd, buffer, BUFFER_SIZE - 1);
					if (len > 0) {
						buffer[len] = '\0';  // Null-terminate
						ssize_t written =
						    write(bash_stdin_fifo_fd, buffer, len);
						if (written == -1) {
							if (errno == EPIPE) {
								printf(
								    "Parent: Write to bash stdin failed "
								    "(EPIPE), bash likely exited.\n");
								close(bash_stdin_fifo_fd);
								bash_stdin_fifo_fd = -1;
								// bash_process_alive should be updated by
								// waitpid soon if not already
							} else {
								perror("Parent: write to bash stdin failed");
								// Potentially close bash_stdin_fifo_fd and stop
								// user input
							}
						}
					} else if (len == 0) {  // EOF from user (Ctrl+D)
						printf("Parent: EOF on stdin. Closing pipe to bash.\n");
						if (bash_stdin_fifo_fd != -1) {
							close(bash_stdin_fifo_fd);
							bash_stdin_fifo_fd = -1;
						}
						user_input_fd = -1;  // Stop reading user input
					} else {                 // read error
						perror("Parent: read from stdin failed");
						user_input_fd = -1;  // Stop reading user input
						if (bash_stdin_fifo_fd != -1) {
							close(bash_stdin_fifo_fd);  // Close pipe to bash on
							                            // error too
							bash_stdin_fifo_fd = -1;
						}
					}
				}
			}

			// Handle bash stdout
			if (bash_out_fd != -1 && FD_ISSET(bash_out_fd, &read_fds)) {
				ssize_t len = read(bash_out_fd, buffer, BUFFER_SIZE);
				if (len > 0) {
					fwrite(buffer, 1, len, log_fp);
					fflush(log_fp);     // Ensure it's written immediately
				} else if (len == 0) {  // EOF from bash stdout
					printf("Parent: EOF on bash stdout pipe.\n");
					close(bash_out_fd);
					bash_out_fd = -1;
				} else {  // read error
					if (errno != EAGAIN &&
					    errno != EWOULDBLOCK) {  // Ignore non-blocking "errors"
						perror("Parent: read from bash stdout failed");
						close(bash_out_fd);
						bash_out_fd = -1;
					}
				}
			}

			// Handle bash stderr
			if (bash_err_fd != -1 && FD_ISSET(bash_err_fd, &read_fds)) {
				ssize_t len = read(bash_err_fd, buffer, BUFFER_SIZE);
				if (len > 0) {
					fwrite(buffer, 1, len, log_fp);
					fflush(log_fp);     // Ensure it's written immediately
				} else if (len == 0) {  // EOF from bash stderr
					printf("Parent: EOF on bash stderr pipe.\n");
					close(bash_err_fd);
					bash_err_fd = -1;
				} else {  // read error
					if (errno != EAGAIN &&
					    errno != EWOULDBLOCK) {  // Ignore non-blocking "errors"
						perror("Parent: read from bash stderr failed");
						close(bash_err_fd);
						bash_err_fd = -1;
					}
				}
			}

			// If bash exited and all its output pipes are drained and closed:
			if (!bash_process_alive && bash_out_fd == -1 && bash_err_fd == -1) {
				break;
			}
		}

		printf("Parent: Exiting main loop.\n");

		// Final cleanup
		if (bash_stdin_fifo_fd != -1) close(bash_stdin_fifo_fd);
		if (bash_out_fd != -1) close(bash_out_fd);
		if (bash_err_fd != -1) close(bash_err_fd);
		if (log_fp) fclose(log_fp);

		// Ensure child is reaped if not already by WNOHANG loop
		if (bash_process_alive) {  // Should generally be false here if loop
			                       // exited correctly
			printf("Parent: Waiting for bash process to fully terminate...\n");
			waitpid(child_pid, NULL, 0);
		}
		printf("Parent: Program finished.\n");
	}
	return EXIT_SUCCESS;
}