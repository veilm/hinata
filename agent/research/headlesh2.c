#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>  // For flock
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define CMD_FIFO_PATH "/tmp/headlesh_cmd_fifo"
#define LOCK_FILE_PATH "/tmp/headlesh.lock"
#define BUFFER_SIZE 4096

// Globals for cleanup
const char* g_cmd_fifo_path_ptr = CMD_FIFO_PATH;
const char* g_lock_file_path_ptr = LOCK_FILE_PATH;
int g_lock_fd = -1;
pid_t g_bash_pid = -1;

void print_error_and_exit(const char* msg) {
	perror(msg);
	exit(EXIT_FAILURE);
}

void cleanup_server_resources(void) {
	printf("Server: Cleaning up resources...\n");
	if (g_bash_pid > 0) {
		printf("Server: Terminating bash process (PID: %d)...\n", g_bash_pid);
		kill(g_bash_pid, SIGTERM);  // Try to terminate bash gracefully
		sleep(1);                   // Give bash a moment to exit
		// Check if it exited
		int status;
		if (waitpid(g_bash_pid, &status, WNOHANG) == 0) {
			// If not exited, force kill
			printf(
			    "Server: Bash process did not terminate gracefully, sending "
			    "SIGKILL.\n");
			kill(g_bash_pid, SIGKILL);
			waitpid(g_bash_pid, NULL, 0);  // Reap child
		} else {
			printf("Server: Bash process terminated.\n");
		}
		g_bash_pid = -1;
	}

	// Unlink command FIFO
	if (unlink(g_cmd_fifo_path_ptr) == -1 && errno != ENOENT) {
		perror("Server cleanup: unlink command FIFO failed");
	} else {
		printf("Server cleanup: Unlinked command FIFO %s.\n",
		       g_cmd_fifo_path_ptr);
	}

	// Unlock and unlink lock file
	if (g_lock_fd != -1) {
		if (flock(g_lock_fd, LOCK_UN) == -1) {
			perror("Server cleanup: flock LOCK_UN failed");
		}
		if (close(g_lock_fd) == -1) {
			perror("Server cleanup: close lock_fd failed");
		}
		if (unlink(g_lock_file_path_ptr) == -1 && errno != ENOENT) {
			perror("Server cleanup: unlink lock file failed");
		} else {
			printf("Server cleanup: Unlinked lock file %s.\n",
			       g_lock_file_path_ptr);
		}
		g_lock_fd = -1;
	}
}

void handle_signal(int sig) {
	printf("\nServer: Caught signal %d, initiating shutdown...\n", sig);
	// cleanup_server_resources() will be called by atexit,
	// but exit() ensures it's triggered.
	exit(EXIT_FAILURE);
}

void start_server_mode() {
	int bash_stdin_pipe[2];  // Pipe for server to write to bash's stdin
	int cmd_fifo_fd = -1;    // FD for reading commands from CMD_FIFO_PATH
	char buffer[BUFFER_SIZE];

	// 1. Setup lock file to ensure singleton server
	g_lock_fd = open(LOCK_FILE_PATH, O_CREAT | O_RDWR, 0666);
	if (g_lock_fd == -1) {
		print_error_and_exit("Server: Failed to open/create lock file");
	}
	if (flock(g_lock_fd, LOCK_EX | LOCK_NB) == -1) {
		if (errno == EWOULDBLOCK) {
			fprintf(stderr,
			        "Server: Another instance of headlesh server is already "
			        "running.\n");
			close(g_lock_fd);  // Close the FD we opened
			g_lock_fd = -1;    // Prevent cleanup from trying to operate on it
			exit(EXIT_FAILURE);
		}
		print_error_and_exit("Server: flock failed");
	}
	printf("Server: Lock acquired: %s\n", LOCK_FILE_PATH);

	// 2. Register cleanup and signal handlers
	if (atexit(cleanup_server_resources) != 0) {
		flock(g_lock_fd, LOCK_UN);  // Unlock before erroring out
		close(g_lock_fd);
		unlink(LOCK_FILE_PATH);
		print_error_and_exit(
		    "Server: Failed to register atexit cleanup function");
	}
	signal(SIGINT, handle_signal);
	signal(SIGTERM, handle_signal);
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write() errors instead

	// 3. Create CMD_FIFO for client communication
	unlink(CMD_FIFO_PATH);  // Remove if it already exists
	if (mkfifo(CMD_FIFO_PATH, 0666) == -1) {
		print_error_and_exit("Server: mkfifo for command FIFO failed");
	}
	printf("Server: Command FIFO created: %s\n", CMD_FIFO_PATH);

	// 4. Create pipe for bash's stdin
	if (pipe(bash_stdin_pipe) == -1) {
		print_error_and_exit("Server: pipe for bash stdin failed");
	}

	// 5. Fork bash process
	g_bash_pid = fork();
	if (g_bash_pid == -1) {
		print_error_and_exit("Server: fork failed");
	}

	if (g_bash_pid == 0) {          // Child process (bash)
		close(bash_stdin_pipe[1]);  // Close write end of bash_stdin_pipe

		// Redirect stdin from the pipe
		if (dup2(bash_stdin_pipe[0], STDIN_FILENO) == -1) {
			perror("Child(bash): dup2 stdin failed");
			exit(EXIT_FAILURE);
		}
		close(bash_stdin_pipe[0]);  // Close original read end

		// stdout and stderr are inherited from the server, going to its
		// terminal

		// Clean up unnecessary file descriptors for the child related to server
		// logic
		if (g_lock_fd != -1) close(g_lock_fd);
		// The command FIFO is not used by the bash child directly

		// Execute bash (non-interactive, reads commands from stdin pipe)
		// Adding "-s" might be useful if we want to ensure it reads from stdin
		// even if it thinks it's interactive For now, just "bash" is simplest
		// and matches the `tail | bash` pattern.
		execlp("bash", "bash", NULL);
		// If execlp returns, it's an error
		perror("Child(bash): execlp bash failed");
		exit(EXIT_FAILURE);
	} else {                        // Parent process (server logic)
		close(bash_stdin_pipe[0]);  // Close read end of bash_stdin_pipe
		int bash_stdin_writer_fd = bash_stdin_pipe[1];

		printf("Headlesh server started. Server PID: %d. Bash PID: %d.\n",
		       getpid(), g_bash_pid);

		int server_running = 1;
		while (server_running) {
			// Check if bash child is still alive
			int status;
			pid_t result = waitpid(g_bash_pid, &status, WNOHANG);
			if (result == g_bash_pid) {
				printf("Server: Bash process (PID: %d) exited.\n", g_bash_pid);
				if (WIFEXITED(status)) {
					printf("Server: Bash exited with status %d.\n",
					       WEXITSTATUS(status));
				} else if (WIFSIGNALED(status)) {
					printf("Server: Bash terminated by signal %d.\n",
					       WTERMSIG(status));
				}
				g_bash_pid = -1;  // Mark as not running
				server_running = 0;
				break;
			} else if (result == -1 &&
			           errno != ECHILD) {  // ECHILD is ok if already reaped.
				perror("Server: waitpid failed for bash process");
				g_bash_pid = -1;
				server_running = 0;
				break;
			}

			if (cmd_fifo_fd == -1) {  // If FIFO not open, try to open it
				printf("Server: Opening command FIFO '%s' for reading...\n",
				       CMD_FIFO_PATH);
				cmd_fifo_fd = open(CMD_FIFO_PATH, O_RDONLY);
				if (cmd_fifo_fd == -1) {
					if (errno == EINTR)
						continue;  // Interrupted by signal, try again
					perror("Server: Failed to open command FIFO for reading");
					// This is a critical failure if bash is still running.
					// The cleanup routine will attempt to kill bash.
					server_running = 0;
					break;
				}
				printf("Server: Command FIFO opened. Waiting for commands.\n");
			}

			ssize_t bytes_read = read(cmd_fifo_fd, buffer, BUFFER_SIZE - 1);
			if (bytes_read > 0) {
				buffer[bytes_read] = '\0';  // Null-terminate for logging
				printf("Server: Received command: %s",
				       buffer);  // Assuming command includes newline
				fflush(stdout);

				ssize_t written =
				    write(bash_stdin_writer_fd, buffer, bytes_read);
				if (written == -1) {
					if (errno == EPIPE) {
						printf(
						    "Server: Write to bash stdin failed (EPIPE). Bash "
						    "likely exited.\n");
					} else {
						perror("Server: write to bash stdin failed");
					}
					server_running = 0;  // Stop server loop
					// Bash process status will be caught by waitpid in the next
					// iteration or on exit
				}
			} else if (bytes_read == 0) {  // EOF on CMD_FIFO
				printf(
				    "Server: Client disconnected (EOF on command FIFO). "
				    "Reopening FIFO.\n");
				close(cmd_fifo_fd);
				cmd_fifo_fd = -1;  // Mark for reopening
			} else {               // bytes_read < 0
				if (errno == EINTR)
					continue;  // Interrupted by signal, retry read
				perror("Server: read from command FIFO failed");
				server_running = 0;  // Critical error, stop server
			}
		}  // end while(server_running)

		printf("Server: Shutting down main loop.\n");
		if (cmd_fifo_fd != -1) close(cmd_fifo_fd);
		close(bash_stdin_writer_fd);
		// atexit handler will manage g_bash_pid, FIFO unlinking, and lock file.
		// Explicitly call exit to ensure atexit handlers run.
		exit(EXIT_SUCCESS);
	}
}

void exec_client_mode(int argc, char* argv[]) {
	int cmd_fifo_fd;
	char command_buffer[BUFFER_SIZE];
	size_t current_len = 0;

	// 1. Construct the command string
	for (int i = 2; i < argc; i++) {
		size_t arg_len = strlen(argv[i]);
		// Check for buffer overflow: +1 for space, +1 for newline, +1 for null
		// terminator
		if (current_len + arg_len + (i > 2 ? 1 : 0) + 1 + 1 >= BUFFER_SIZE) {
			fprintf(stderr, "Client: Command too long.\n");
			exit(EXIT_FAILURE);
		}
		if (i > 2) {  // Add space before subsequent arguments
			command_buffer[current_len++] = ' ';
		}
		strcpy(command_buffer + current_len, argv[i]);
		current_len += arg_len;
	}
	if (current_len == 0) {
		fprintf(stderr, "Client: No command specified.\n");
		exit(EXIT_FAILURE);
	}
	command_buffer[current_len++] = '\n';  // Add newline for bash execution
	command_buffer[current_len] = '\0';    // Null-terminate

	// 2. Open CMD_FIFO for writing
	// We use O_WRONLY. If the server isn't reading, open might block or fail
	// depending on FIFO state. For this model, client is fire-and-forget.
	cmd_fifo_fd = open(CMD_FIFO_PATH, O_WRONLY);
	if (cmd_fifo_fd == -1) {
		if (errno == ENOENT) {
			fprintf(stderr,
			        "Client: Failed to connect to server. Is headlesh server "
			        "running?\n"
			        "(FIFO %s not found)\n",
			        CMD_FIFO_PATH);
		} else {
			perror("Client: Failed to open command FIFO for writing");
		}
		exit(EXIT_FAILURE);
	}

	// 3. Write команда to FIFO
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write errors
	ssize_t written = write(cmd_fifo_fd, command_buffer, current_len);
	if (written == -1) {
		perror("Client: Failed to write command to FIFO");
		close(cmd_fifo_fd);
		exit(EXIT_FAILURE);
	}
	if (written < current_len) {
		fprintf(stderr, "Client: Partial write to FIFO (%zd of %zu bytes).\n",
		        written, current_len);
		close(cmd_fifo_fd);
		exit(EXIT_FAILURE);
	}

	// 4. Close FIFO and exit
	if (close(cmd_fifo_fd) == -1) {
		perror("Client: Failed to close command FIFO");
		// Not necessarily fatal for the command sending itself, but good to
		// note.
	}

	printf("Client: Command sent to headlesh server.\n");
}

int main(int argc, char* argv[]) {
	if (argc < 2) {
		fprintf(stderr, "Usage: %s start | %s exec <command...>\n", argv[0],
		        argv[0]);
		return EXIT_FAILURE;
	}

	if (strcmp(argv[1], "start") == 0) {
		if (argc != 2) {
			fprintf(stderr, "Usage: %s start\n", argv[0]);
			return EXIT_FAILURE;
		}
		start_server_mode();
	} else if (strcmp(argv[1], "exec") == 0) {
		if (argc < 3) {
			fprintf(stderr, "Usage: %s exec <command...>\n", argv[0]);
			return EXIT_FAILURE;
		}
		exec_client_mode(argc, argv);
	} else {
		fprintf(stderr, "Unknown command: %s\n", argv[1]);
		fprintf(stderr, "Usage: %s start | %s exec <command...>\n", argv[0],
		        argv[0]);
		return EXIT_FAILURE;
	}

	return EXIT_SUCCESS;
}