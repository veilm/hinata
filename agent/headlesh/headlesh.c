#define _POSIX_C_SOURCE 200809L  // For kill, ftruncate, etc.

#include <errno.h>
#include <fcntl.h>
#include <limits.h>  // For PATH_MAX if needed, though not directly used for buffer sizing an example
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
#define OUT_FIFO_TEMPLATE "/tmp/headlesh_out_%d"  // %d for client PID
#define DAEMON_LOG_FILE "/var/log/headlesh/main.log"
#define BUFFER_SIZE 4096  // For general I/O and command construction

// Globals for server cleanup
const char* g_cmd_fifo_path_ptr = CMD_FIFO_PATH;
const char* g_lock_file_path_ptr = LOCK_FILE_PATH;
int g_lock_fd = -1;
pid_t g_bash_pid = -1;

// Globals for client cleanup (used by signal handler)
static char
    s_client_out_fifo_path[256];  // Static buffer for client's output FIFO path
static volatile sig_atomic_t s_client_out_fifo_created =
    0;  // Flag for client signal handler

void print_error_and_exit(const char* msg) {
	// In daemon mode, after stderr is redirected (e.g., to a log file or
	// /dev/null), perror will write to that redirected target. For a robust
	// daemon, syslog is often preferred over a simple file log.
	perror(msg);
	exit(EXIT_FAILURE);
}

void cleanup_server_resources(void) {
	// This function's printf statements will go to /dev/null if daemonized.
	// They are useful for debugging if daemonization is partial or skipped.
	// printf("Server: Cleaning up resources...\n");
	if (g_bash_pid > 0) {
		// printf("Server: Terminating bash process (PID: %d)...\n",
		// g_bash_pid);
		kill(g_bash_pid, SIGTERM);
		sleep(1);
		int status;
		if (waitpid(g_bash_pid, &status, WNOHANG) == 0) {
			// printf("Server: Bash process did not terminate gracefully,
			// sending SIGKILL.\n");
			kill(g_bash_pid, SIGKILL);
			waitpid(g_bash_pid, NULL, 0);
		}  // else { printf("Server: Bash process terminated.\n"); }
		g_bash_pid = -1;
	}

	if (unlink(g_cmd_fifo_path_ptr) == -1 && errno != ENOENT) {
		// perror("Server cleanup: unlink command FIFO failed");
	}  // else { printf("Server cleanup: Unlinked command FIFO %s.\n",
	   // g_cmd_fifo_path_ptr); }

	if (g_lock_fd != -1) {
		// flock(g_lock_fd, LOCK_UN); // flock is advisory, file will be
		// unlocked on close
		if (close(g_lock_fd) == -1) {  // Closing also releases flock
			// perror("Server cleanup: close lock_fd failed");
		}
		if (unlink(g_lock_file_path_ptr) == -1 && errno != ENOENT) {
			// perror("Server cleanup: unlink lock file failed");
		}  // else { printf("Server cleanup: Unlinked lock file %s.\n",
		   // g_lock_file_path_ptr); }
		g_lock_fd = -1;
	}
}

void server_signal_handler(int sig) {
	(void)sig;  // Mark as unused to prevent compiler warnings
	// printf("\nServer: Caught signal %d, initiating shutdown...\n", sig);
	// atexit handler (cleanup_server_resources) will be called.
	exit(EXIT_FAILURE);  // Trigger atexit
}

void start_server_mode() {
	int bash_stdin_pipe[2];
	int cmd_fifo_fd = -1;
	char buffer[BUFFER_SIZE];           // For reading commands from CMD_FIFO
	char bash_cmd_buffer[BUFFER_SIZE];  // For formatting commands to bash

	// 1. Setup lock file (before daemonizing fork, so errors are visible)
	g_lock_fd = open(LOCK_FILE_PATH, O_CREAT | O_RDWR, 0666);
	if (g_lock_fd == -1) {
		print_error_and_exit("Server: Failed to open/create lock file");
	}
	if (flock(g_lock_fd, LOCK_EX | LOCK_NB) == -1) {
		if (errno == EWOULDBLOCK) {
			fprintf(stderr,
			        "Server: Another instance is already running (lock held on "
			        "%s).\n",
			        LOCK_FILE_PATH);
			close(g_lock_fd);
			g_lock_fd = -1;
			exit(EXIT_FAILURE);
		}
		print_error_and_exit("Server: flock failed");
	}
	printf(
	    "Server: Lock acquired: %s. Daemon PID will be written to this file.\n",
	    LOCK_FILE_PATH);

	// 2. Create CMD_FIFO (before daemonizing fork)
	unlink(CMD_FIFO_PATH);  // Remove if it already exists
	if (mkfifo(CMD_FIFO_PATH, 0666) == -1) {
		print_error_and_exit("Server: mkfifo for command FIFO failed");
	}
	printf("Server: Command FIFO created: %s\n", CMD_FIFO_PATH);

	// 3. Daemonize
	printf("Server: Daemonizing...\n");
	fflush(stdout);  // Ensure messages are printed before fork

	pid_t pid = fork();  // First fork
	if (pid < 0) {
		print_error_and_exit("Server: fork (1) failed");
	}
	if (pid > 0) {  // Parent of first fork
		printf(
		    "Server: Daemonizing process initiated. Check lock file %s for "
		    "final daemon PID.\n",
		    LOCK_FILE_PATH);
		exit(EXIT_SUCCESS);  // Parent exits, child continues
	}

	// ---- Child Process 1 (continues to become daemon) ----
	if (setsid() < 0) {
		print_error_and_exit("Server: setsid failed");
	}

	signal(SIGHUP,
	       SIG_IGN);  // Ignore SIGHUP often sent when session leader exits

	pid = fork();  // Second fork
	if (pid < 0) {
		print_error_and_exit("Server: fork (2) failed");
	}
	if (pid > 0) {  // Parent of second fork (session leader) exits
		exit(EXIT_SUCCESS);
	}

	// ---- Grandchild Process (Actual Daemon) ----
	if (chdir("/") < 0) {
		print_error_and_exit("Server: chdir failed");
	}
	umask(0);

	// Redirect standard file descriptors for the daemon
	int log_fd = open(DAEMON_LOG_FILE, O_WRONLY | O_CREAT | O_APPEND, 0644);
	if (log_fd == -1) {
		// If log file cannot be opened, this is a critical failure.
		// Errors print to original stderr because redirection hasn't happened
		// yet.
		print_error_and_exit(
		    "Server: Failed to open log file " DAEMON_LOG_FILE);
	}

	// Redirect stdout to the log file
	if (close(STDOUT_FILENO) == -1) {
		dprintf(log_fd, "Server: Failed to close STDOUT_FILENO: %s\n",
		        strerror(errno));
	}
	if (dup2(log_fd, STDOUT_FILENO) == -1) {
		dprintf(log_fd, "Server: Failed to dup2 STDOUT_FILENO: %s\n",
		        strerror(errno));
		close(log_fd);
		exit(EXIT_FAILURE);
	}

	// Redirect stderr to the log file
	if (close(STDERR_FILENO) == -1) {
		fprintf(stdout, "Server: Failed to close STDERR_FILENO: %s\n",
		        strerror(errno));  // To log file
	}
	if (dup2(log_fd, STDERR_FILENO) == -1) {
		fprintf(stdout, "Server: Failed to dup2 STDERR_FILENO: %s\n",
		        strerror(errno));  // To log file
		if (log_fd != STDOUT_FILENO)
			close(log_fd);  // STDOUT_FILENO is already log_fd, check if
			                // original log_fd is different
		exit(EXIT_FAILURE);
	}

	if (log_fd != STDOUT_FILENO && log_fd != STDERR_FILENO) {
		close(log_fd);
	}
	// At this point, STDOUT and STDERR are directed to DAEMON_LOG_FILE.

	// Redirect stdin to /dev/null
	if (close(STDIN_FILENO) == -1) {
		perror("Server: Failed to close STDIN_FILENO");  // Goes to log file
	}
	int fd_stdin = open("/dev/null", O_RDWR);
	if (fd_stdin == -1) {
		perror(
		    "Server: Failed to open /dev/null for STDIN");  // Goes to log file
		exit(EXIT_FAILURE);
	}
	if (dup2(fd_stdin, STDIN_FILENO) == -1) {
		perror("Server: Failed to dup2 STDIN_FILENO");  // Goes to log file
		if (fd_stdin != STDIN_FILENO) close(fd_stdin);
		exit(EXIT_FAILURE);
	}
	if (fd_stdin != STDIN_FILENO) {
		close(fd_stdin);
	}
	// End of FD redirection. Log daemon startup.
	fprintf(stdout, "Server daemon starting. PID: %d. Logging to %s.\n",
	        getpid(), DAEMON_LOG_FILE);
	fflush(stdout);

	// Write daemon's PID to the lock file
	if (ftruncate(g_lock_fd, 0) == -1) {
		perror("Server: ftruncate lock_fd failed");  // To log file
		cleanup_server_resources();  // Manually, as atexit not yet set
		exit(EXIT_FAILURE);
	}
	char pid_str[32];
	snprintf(pid_str, sizeof(pid_str), "%d\n", getpid());
	if (write(g_lock_fd, pid_str, strlen(pid_str)) == -1) {
		perror("Server: write PID to lock_fd failed");  // To log file
		cleanup_server_resources();                     // Manually
		exit(EXIT_FAILURE);
	}
	// Note: g_lock_fd remains open and locked.

	// Register cleanup and signal handlers *IN THE DAEMON PROCESS*
	if (atexit(cleanup_server_resources) != 0) {
		perror("Server: atexit registration failed");  // To log file
		cleanup_server_resources();  // Attempt manual cleanup if atexit
		                             // registration fails
		exit(EXIT_FAILURE);
	}
	signal(SIGINT, server_signal_handler);
	signal(SIGTERM, server_signal_handler);
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write() errors instead

	// 4. Create pipe for bash's stdin
	if (pipe(bash_stdin_pipe) == -1) {
		print_error_and_exit("Server: pipe for bash_stdin failed");
	}

	// 5. Fork bash process
	g_bash_pid = fork();
	if (g_bash_pid == -1) {
		print_error_and_exit("Server: fork for bash process failed");
	}

	if (g_bash_pid == 0) {          // Child process (bash)
		close(bash_stdin_pipe[1]);  // Close write end
		if (dup2(bash_stdin_pipe[0], STDIN_FILENO) ==
		    -1) { /* Log via parent before exit? Hard. */
			_exit(EXIT_FAILURE);
		}
		close(bash_stdin_pipe[0]);

		if (g_lock_fd != -1)
			close(g_lock_fd);  // Bash doesn't need lock file FD
		// cmd_fifo_fd is also not needed by bash directly. (It will be -1 here
		// anyway)

		execlp("bash", "bash", NULL);  // Or "bash", "-s", NULL
		// If execlp returns, it's an error
		_exit(EXIT_FAILURE);  // Use _exit in child after fork to avoid running
		                      // atexit handlers
	} else {                  // Parent process (daemon server logic)
		close(bash_stdin_pipe[0]);  // Close read end
		int bash_stdin_writer_fd = bash_stdin_pipe[1];

		// Daemon is running. No printf here as stdout is /dev/null.

		int server_running = 1;
		while (server_running) {
			int status;
			pid_t result = waitpid(g_bash_pid, &status, WNOHANG);
			if (result == g_bash_pid) {  // Bash exited
				g_bash_pid = -1;
				server_running = 0;  // Stop server
				break;
			} else if (result == -1 && errno != ECHILD) {
				g_bash_pid = -1;
				server_running = 0;
				break;
			}

			if (cmd_fifo_fd == -1) {  // If CMD_FIFO not open, try to open it
				cmd_fifo_fd = open(CMD_FIFO_PATH, O_RDONLY);
				if (cmd_fifo_fd == -1) {
					if (errno == EINTR) continue;
					server_running = 0;
					break;  // Critical error
				}
			}

			ssize_t bytes_read = read(cmd_fifo_fd, buffer, BUFFER_SIZE - 1);
			if (bytes_read > 0) {
				buffer[bytes_read] = '\0';  // Null-terminate incoming message

				char* client_out_fifo_path_str = buffer;
				char* command_str_ptr = strchr(buffer, '\n');

				if (command_str_ptr == NULL || *(command_str_ptr + 1) == '\0') {
					// Malformed command (no newline, or command part is empty)
					// syslog(LOG_WARNING, "Malformed/empty command from
					// client."); For simplicity, just ignore and continue. To
					// prevent blocking on a bad client indefinitely, could
					// close and reopen cmd_fifo_fd. But if client holds write
					// end open, open(O_RDONLY) won't unblock on a new client.
					// Current model: one client connects, sends, server
					// processes. If client disconnects, read gets EOF.
					close(cmd_fifo_fd);  // Close and reopen to handle bad
					                     // client or allow new one
					cmd_fifo_fd = -1;
					continue;
				}
				*command_str_ptr =
				    '\0';           // Null-terminate client_out_fifo_path_str
				command_str_ptr++;  // Move to start of actual command content

				// Remove trailing newline from command_str_ptr if present
				size_t actual_cmd_len = strlen(command_str_ptr);
				if (actual_cmd_len > 0 &&
				    command_str_ptr[actual_cmd_len - 1] == '\n') {
					command_str_ptr[actual_cmd_len - 1] = '\0';
				}
				if (strlen(command_str_ptr) ==
				    0) {  // Command is empty after stripping newline
					// syslog equivalent
					close(cmd_fifo_fd);
					cmd_fifo_fd = -1;
					continue;
				}

				// Prepare command for bash: (actual_command) > client_out_fifo
				// 2>&1 Ensure client_out_fifo_path_str is a safe path. For now,
				// trust client. Production: validate client_out_fifo_path_str
				// (e.g., ensure it's in /tmp).
				int len_needed = snprintf(
				    bash_cmd_buffer, BUFFER_SIZE, "{ %s ; } > %s 2>&1\n",
				    command_str_ptr, client_out_fifo_path_str);

				if (len_needed < 0 || len_needed >= BUFFER_SIZE) {
					// Command too long to format, log this.
					// syslog(LOG_ERR, "Formatted command for bash too long.");
					// Can't easily notify client. Best to drop.
					close(cmd_fifo_fd);  // Force client to see issue by closing
					                     // connection
					cmd_fifo_fd = -1;
					continue;
				}

				ssize_t written = write(bash_stdin_writer_fd, bash_cmd_buffer,
				                        strlen(bash_cmd_buffer));
				if (written == -1) {
					if (errno == EPIPE) {  // Bash likely exited
						                   // syslog equivalent
					} else {
						// syslog equivalent
					}
					server_running = 0;  // Stop server loop
				}
			} else if (bytes_read ==
			           0) {  // EOF on CMD_FIFO (client closed write end)
				close(cmd_fifo_fd);
				cmd_fifo_fd = -1;  // Mark for reopening (waits for new client)
			} else {               // bytes_read < 0
				if (errno == EINTR) continue;
				server_running = 0;  // Critical error
			}
		}  // end while(server_running)

		if (cmd_fifo_fd != -1) close(cmd_fifo_fd);
		close(bash_stdin_writer_fd);
		// atexit handler will manage g_bash_pid, FIFO unlinking, and lock file.
		exit(EXIT_SUCCESS);  // Normal daemon exit
	}
}

void client_cleanup_signal_handler(int sig) {
	if (s_client_out_fifo_created) {
		unlink(s_client_out_fifo_path);  // Attempt to clean up FIFO
	}
	// Default behavior for the signal (e.g., terminate)
	signal(sig, SIG_DFL);
	raise(sig);
}

void exec_client_mode(int argc, char* argv[]) {
	int cmd_fifo_fd_client;  // To write to server's CMD_FIFO
	int out_fifo_fd_client;  // To read output from client's OUT_FIFO
	char client_cmd_payload[BUFFER_SIZE];  // For command sent by client
	                                       // initially.
	char server_full_cmd[BUFFER_SIZE];     // For client_out_fifo_path + \n +
	                                       // client_cmd_payload
	char read_buf[BUFFER_SIZE];  // For reading output from out_fifo_fd_client

	// 1. Construct the actual command string to be executed
	size_t current_cmd_len = 0;
	for (int i = 2; i < argc; i++) {
		size_t arg_len = strlen(argv[i]);
		if (current_cmd_len + arg_len + (i > 2 ? 1 : 0) + 1 + 1 >=
		    sizeof(client_cmd_payload)) {  // +1 space, +1 newline, +1 null
			fprintf(stderr, "Client: Command string too long.\n");
			exit(EXIT_FAILURE);
		}
		if (i > 2) {
			client_cmd_payload[current_cmd_len++] = ' ';
		}
		strcpy(client_cmd_payload + current_cmd_len, argv[i]);
		current_cmd_len += arg_len;
	}
	if (current_cmd_len == 0) {
		fprintf(stderr, "Client: No command specified.\n");
		exit(EXIT_FAILURE);
	}
	client_cmd_payload[current_cmd_len++] = '\n';
	client_cmd_payload[current_cmd_len] = '\0';

	// 2. Create unique output FIFO for this client
	snprintf(s_client_out_fifo_path, sizeof(s_client_out_fifo_path),
	         OUT_FIFO_TEMPLATE, getpid());
	unlink(s_client_out_fifo_path);  // Remove if leftover from a previous crash
	if (mkfifo(s_client_out_fifo_path, 0666) == -1) {
		perror("Client: mkfifo for output FIFO failed");
		exit(EXIT_FAILURE);
	}
	s_client_out_fifo_created = 1;  // Mark FIFO as created for signal handler
	signal(SIGINT, client_cleanup_signal_handler);
	signal(SIGTERM, client_cleanup_signal_handler);

	// 3. Prepare the full message for the server (output_fifo_path\ncommand\n)
	size_t len_fifo_path = strlen(s_client_out_fifo_path);
	// Check total length against server's read buffer (BUFFER_SIZE)
	// current_cmd_len already includes its trailing \n.
	if (len_fifo_path + 1 + current_cmd_len >= sizeof(server_full_cmd)) {
		fprintf(
		    stderr,
		    "Client: Combined FIFO path and command too long for server.\n");
		s_client_out_fifo_created = 0;  // Unset before manual unlink
		unlink(s_client_out_fifo_path);
		exit(EXIT_FAILURE);
	}
	strcpy(server_full_cmd, s_client_out_fifo_path);
	server_full_cmd[len_fifo_path] = '\n';
	strcpy(server_full_cmd + len_fifo_path + 1, client_cmd_payload);
	size_t total_len_to_send = len_fifo_path + 1 + current_cmd_len;

	// 4. Open server's CMD_FIFO for writing
	cmd_fifo_fd_client = open(CMD_FIFO_PATH, O_WRONLY);
	if (cmd_fifo_fd_client == -1) {
		if (errno == ENOENT) {
			fprintf(stderr,
			        "Client: Failed to connect. Is headlesh server running? "
			        "(FIFO %s not found)\n",
			        CMD_FIFO_PATH);
		} else {
			perror("Client: Failed to open command FIFO for writing");
		}
		s_client_out_fifo_created = 0;
		unlink(s_client_out_fifo_path);
		exit(EXIT_FAILURE);
	}

	// 5. Write the full command (output FIFO path + actual command) to CMD_FIFO
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write errors
	ssize_t written =
	    write(cmd_fifo_fd_client, server_full_cmd, total_len_to_send);
	if (close(cmd_fifo_fd_client) ==
	    -1) { /*perror("Client: Failed to close command FIFO (write)");*/
	}  // Non-fatal for this op
	if (written == -1) {
		perror("Client: Failed to write command to server FIFO");
		s_client_out_fifo_created = 0;
		unlink(s_client_out_fifo_path);
		exit(EXIT_FAILURE);
	}
	if ((size_t)written < total_len_to_send) {
		fprintf(stderr,
		        "Client: Partial write to server FIFO (%zd of %zu bytes).\n",
		        written, total_len_to_send);
		s_client_out_fifo_created = 0;
		unlink(s_client_out_fifo_path);
		exit(EXIT_FAILURE);
	}
	// printf("Client: Command sent to server. Waiting for output on %s...\n",
	// s_client_out_fifo_path);

	// 6. Open client's output FIFO for reading (blocks until server's bash
	// redirects to it)
	out_fifo_fd_client = open(s_client_out_fifo_path, O_RDONLY);
	if (out_fifo_fd_client == -1) {
		perror("Client: Failed to open output FIFO for reading");
		s_client_out_fifo_created = 0;
		unlink(s_client_out_fifo_path);
		exit(EXIT_FAILURE);
	}
	// printf("Client: Output FIFO opened. Streaming output:\n");

	// 7. Read from output FIFO and tee to stdout
	ssize_t bytes_read_output;
	while ((bytes_read_output =
	            read(out_fifo_fd_client, read_buf, sizeof(read_buf) - 1)) > 0) {
		// Should write bytes_read_output, not assuming null term.
		if (write(STDOUT_FILENO, read_buf, bytes_read_output) !=
		    bytes_read_output) {
			perror("Client: Failed to write to stdout");
			// Continue trying to read from FIFO to let server side finish
		}
	}
	if (bytes_read_output == -1) {
		perror("Client: Error reading from output FIFO");
	}
	fflush(stdout);  // Ensure all output is flushed

	// 8. Cleanup client-side resources
	close(out_fifo_fd_client);
	s_client_out_fifo_created = 0;  // Mark as cleaned up before explicit unlink
	if (unlink(s_client_out_fifo_path) == -1) {
		// perror("Client: Failed to unlink output FIFO"); // Minor issue if
		// this fails
	}
	// printf("\nClient: Command finished and output FIFO cleaned up.\n");
	// Restore default signal handlers
	signal(SIGINT, SIG_DFL);
	signal(SIGTERM, SIG_DFL);
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
