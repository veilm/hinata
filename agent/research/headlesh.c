#include <errno.h>
#include <fcntl.h>
#include <limits.h>  // For PATH_MAX
#include <signal.h>
#include <stdarg.h>   // For variadic functions like robust_open
#include <stdbool.h>  // For bool, true, false
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>  // For daemon logging timestamp
#include <unistd.h>

// --- Configuration ---
#define SERVER_PID_FILE "/tmp/headlesh_server.pid"
#define SERVER_CMD_FIFO "/tmp/headlesh_server_cmd.fifo"
#define BASH_STDIN_FIFO "/tmp/headlesh_bash_stdin.fifo"
#define CLIENT_RESP_FIFO_PATTERN "/tmp/headlesh_client_resp_%d.fifo"
#define DAEMON_LOG_FILE "/tmp/headlesh_server.log"

#define MAX_CMD_LEN 4096
#define MAX_LINE_LEN \
	2048  // Increased for potentially long lines + delimiter + exit code
#define BUFFER_SIZE 4096
#define DELIMITER_BASE "HEADLESH_CMD_DELIMITER_v1_"

// --- Globals (mostly for signal handling and cleanup) ---
volatile sig_atomic_t server_running = 1;
pid_t g_bash_child_pid = -1;
char g_server_cmd_fifo_path[PATH_MAX] = SERVER_CMD_FIFO;
char g_bash_stdin_fifo_path[PATH_MAX] = BASH_STDIN_FIFO;
char g_pid_file_path[PATH_MAX] = SERVER_PID_FILE;
FILE* g_log_fp = NULL;

// --- Utility Function Declarations ---
void print_error_and_exit(const char* context_msg);
void server_log(const char* format, ...);
void daemonize();
void create_pid_file(const char* path, pid_t pid);
void remove_pid_file(const char* path);
void cleanup_server_resources(void);
void server_signal_handler(int sig);
void setup_server_signal_handlers(void);
ssize_t read_line_from_fd(int fd, char* buffer, size_t buffer_size);
void client_cleanup_resources(void);

char g_client_resp_fifo_path[PATH_MAX];  // For client atexit cleanup

// --- Server Function Declarations ---
void server_mode(int argc, char* argv[]);

// --- Client Function Declarations ---
void client_mode(int argc, char* argv[]);

// --- Main ---
int main(int argc, char* argv[]) {
	if (argc < 2) {
		fprintf(stderr, "Usage: headlesh <start|exec ...>\n");
		return EXIT_FAILURE;
	}

	if (strcmp(argv[1], "start") == 0) {
		server_mode(argc, argv);
	} else if (strcmp(argv[1], "exec") == 0) {
		if (argc < 3) {
			fprintf(stderr, "Usage: headlesh exec <command> [args...]\n");
			return EXIT_FAILURE;
		}
		client_mode(argc, argv);
	} else {
		fprintf(stderr, "Unknown command: %s\n", argv[1]);
		fprintf(stderr, "Usage: headlesh <start|exec ...>\n");
		return EXIT_FAILURE;
	}

	return EXIT_SUCCESS;
}

// --- Utility Function Implementations ---

void print_error_and_exit(const char* context_msg) {
	char error_buf[256];
	snprintf(error_buf, sizeof(error_buf), "headlesh ERROR: %s", context_msg);
	perror(error_buf);
	if (g_log_fp) {
		server_log("FATAL: %s: %s", context_msg, strerror(errno));
		fclose(g_log_fp);
		g_log_fp = NULL;
	}
	exit(EXIT_FAILURE);
}

void server_log(const char* format, ...) {
	if (!g_log_fp) return;

	time_t now;
	time(&now);
	char time_buf[30];
	strftime(time_buf, sizeof(time_buf), "%Y-%m-%d %H:%M:%S", localtime(&now));

	fprintf(g_log_fp, "[%s] ", time_buf);

	va_list args;
	va_start(args, format);
	vfprintf(g_log_fp, format, args);
	va_end(args);

	fprintf(g_log_fp, "\n");
	fflush(g_log_fp);
}

void daemonize() {
	pid_t pid;

	pid = fork();
	if (pid < 0) print_error_and_exit("fork (1) failed");
	if (pid > 0) exit(EXIT_SUCCESS);  // Parent exits

	if (setsid() < 0) print_error_and_exit("setsid failed");

	// Fork again to ensure daemon cannot acquire a controlling terminal
	pid = fork();
	if (pid < 0) print_error_and_exit("fork (2) failed");
	if (pid > 0) exit(EXIT_SUCCESS);  // First child exits

	umask(0);  // Set file mode creation mask to 0

	if (chdir("/") < 0) print_error_and_exit("chdir / failed");

	// Close standard file descriptors
	close(STDIN_FILENO);
	close(STDOUT_FILENO);
	close(STDERR_FILENO);

	// Redirect standard file descriptors to /dev/null (optional, but good
	// practice)
	int fd_dev_null = open("/dev/null", O_RDWR);
	if (fd_dev_null != -1) {
		dup2(fd_dev_null, STDIN_FILENO);
		dup2(fd_dev_null, STDOUT_FILENO);
		dup2(fd_dev_null, STDERR_FILENO);
		if (fd_dev_null > STDERR_FILENO) close(fd_dev_null);
	}

	g_log_fp = fopen(DAEMON_LOG_FILE, "a");
	if (!g_log_fp) {  // Can't use print_error_and_exit as it might rely on
		              // g_log_fp
		perror("headlesh ERROR: fopen daemon log failed");
		exit(EXIT_FAILURE);
	}
	setlinebuf(g_log_fp);  // Line buffer log for easier debugging
	server_log("Daemon initialized. PID: %d", getpid());
}

void create_pid_file(const char* path, pid_t pid) {
	FILE* f = fopen(path, "w");
	if (!f) {
		server_log("Failed to create PID file %s", path);
		print_error_and_exit("fopen PID file for write");
	}
	fprintf(f, "%d\n", pid);
	fclose(f);
	server_log("PID file %s created with PID %d", path, pid);
}

void remove_pid_file(const char* path) {
	if (unlink(path) == 0) {
		server_log("PID file %s removed.", path);
	} else if (errno !=
	           ENOENT) {  // ENOENT means file doesn't exist, which is fine
		server_log("Warning: Failed to remove PID file %s: %s", path,
		           strerror(errno));
	}
}

void cleanup_server_resources(void) {
	server_log("Server shutting down...");
	if (g_bash_child_pid > 0) {
		server_log("Sending SIGTERM to bash child PID %d", g_bash_child_pid);
		kill(g_bash_child_pid, SIGTERM);
		int status;
		waitpid(g_bash_child_pid, &status, 0);  // Wait for bash to exit
		server_log("Bash child process reaped.");
		g_bash_child_pid = -1;
	}
	unlink(g_server_cmd_fifo_path);  // Use global paths
	unlink(g_bash_stdin_fifo_path);
	remove_pid_file(g_pid_file_path);
	if (g_log_fp) {
		server_log("Server shutdown complete.");
		fclose(g_log_fp);
		g_log_fp = NULL;
	}
}

void server_signal_handler(int sig) {
	server_log("Caught signal %d. Initiating shutdown.", sig);
	server_running = 0;  // This will break the main server loop
	// Cleanup will be handled by atexit
}

void setup_server_signal_handlers(void) {
	struct sigaction sa;
	memset(&sa, 0, sizeof(sa));
	sa.sa_handler = server_signal_handler;
	sigemptyset(&sa.sa_mask);  // Do not block other signals during handler
	sa.sa_flags = 0;  // No SA_RESTART, so syscalls like read are interrupted

	if (sigaction(SIGINT, &sa, NULL) == -1)
		print_error_and_exit("sigaction SIGINT");
	if (sigaction(SIGTERM, &sa, NULL) == -1)
		print_error_and_exit("sigaction SIGTERM");
	if (sigaction(SIGHUP, &sa, NULL) == -1)
		print_error_and_exit(
		    "sigaction SIGHUP");  // Treat SIGHUP as shutdown for now

	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE globally for the server
}

ssize_t read_line_from_fd(int fd, char* buffer, size_t buffer_size) {
	ssize_t total_bytes_read = 0;
	char ch;
	ssize_t n;

	if (buffer_size == 0) return -1;  // No space to store anything

	while (total_bytes_read < (ssize_t)buffer_size - 1) {
		n = read(fd, &ch, 1);
		if (n == 1) {
			buffer[total_bytes_read++] = ch;
			if (ch == '\n') {
				break;
			}
		} else if (n == 0) {                      // EOF
			if (total_bytes_read == 0) return 0;  // EOF and no data read
			break;                                // EOF after some data
		} else {                                  // n == -1 (error)
			if (errno == EINTR) continue;  // Interrupted by signal, try again
			return -1;                     // Other read error
		}
	}
	buffer[total_bytes_read] = '\0';
	return total_bytes_read;
}

// --- Server Mode Implementation ---
void server_mode(int argc, char* argv[]) {
	// 1. Check if server is already running
	FILE* pid_f = fopen(SERVER_PID_FILE, "r");
	if (pid_f) {
		int existing_pid;
		if (fscanf(pid_f, "%d", &existing_pid) == 1) {
			// Check if process with existing_pid is actually running
			if (kill(existing_pid, 0) == 0 || errno != ESRCH) {
				fprintf(stderr,
				        "Server already running with PID %d (found in %s).\n",
				        existing_pid, SERVER_PID_FILE);
				fclose(pid_f);
				exit(EXIT_FAILURE);
			}
		}
		fclose(pid_f);
		// PID file exists but process is not running, okay to proceed
		remove_pid_file(SERVER_PID_FILE);  // Clean up stale PID file
	}

	// 2. Daemonize
	daemonize();  // This also sets up g_log_fp

	// 3. Create PID file
	create_pid_file(SERVER_PID_FILE, getpid());
	strncpy(g_pid_file_path, SERVER_PID_FILE,
	        PATH_MAX - 1);  // Store for cleanup

	// 4. Setup signal handlers and atexit cleanup
	setup_server_signal_handlers();
	if (atexit(cleanup_server_resources) != 0) {
		server_log("Failed to register atexit cleanup function.");
		print_error_and_exit("atexit failed");
	}

	// 5. Create FIFOs
	strncpy(g_server_cmd_fifo_path, SERVER_CMD_FIFO, PATH_MAX - 1);
	strncpy(g_bash_stdin_fifo_path, BASH_STDIN_FIFO, PATH_MAX - 1);

	// Clean up pre-existing FIFOs if any (best effort)
	unlink(SERVER_CMD_FIFO);
	unlink(BASH_STDIN_FIFO);

	if (mkfifo(SERVER_CMD_FIFO, 0660) == -1)
		print_error_and_exit("mkfifo SERVER_CMD_FIFO failed");
	server_log("Created FIFO: %s", SERVER_CMD_FIFO);
	if (mkfifo(BASH_STDIN_FIFO, 0660) == -1)
		print_error_and_exit("mkfifo BASH_STDIN_FIFO failed");
	server_log("Created FIFO: %s", BASH_STDIN_FIFO);

	// 6. Fork and exec bash
	int bash_stdout_pipe[2];  // Server reads from [0], bash writes to [1]
	// We won't use a separate stderr pipe for bash; commands will redirect
	// their stderr to stdout. However, bash's own errors (not command specific)
	// would go to its original stderr, which is /dev/null after daemonization
	// if not handled. For simplicity, we'll focus on command output.

	if (pipe(bash_stdout_pipe) == -1)
		print_error_and_exit("pipe for bash stdout failed");

	g_bash_child_pid = fork();
	if (g_bash_child_pid == -1) print_error_and_exit("fork for bash failed");

	if (g_bash_child_pid == 0) {  // --- Bash Child Process ---
		// Redirect stdin from BASH_STDIN_FIFO
		int fifo_fd_child = open(BASH_STDIN_FIFO, O_RDONLY);
		if (fifo_fd_child == -1) {
			// Cannot use server_log here. Send to daemon's /dev/null
			// effectively.
			perror("Bash Child: Failed to open BASH_STDIN_FIFO for reading");
			exit(EXIT_FAILURE);
		}
		if (dup2(fifo_fd_child, STDIN_FILENO) == -1) {
			perror("Bash Child: dup2 stdin failed");
			exit(EXIT_FAILURE);
		}
		close(fifo_fd_child);

		// Redirect stdout to pipe
		close(bash_stdout_pipe[0]);  // Close read end
		if (dup2(bash_stdout_pipe[1], STDOUT_FILENO) == -1) {
			perror("Bash Child: dup2 stdout failed");
			exit(EXIT_FAILURE);
		}
		// Redirect stderr to the same pipe as stdout
		if (dup2(bash_stdout_pipe[1], STDERR_FILENO) == -1) {
			perror("Bash Child: dup2 stderr failed");
			exit(EXIT_FAILURE);
		}
		close(bash_stdout_pipe[1]);

		// To make bash unbuffered (or line-buffered) for more responsive
		// output: Requires GNU stdbuf, if available. execlp("stdbuf", "stdbuf",
		// "-i0", "-o0", "-e0", "bash", "--norc", "--noprofile", "-i", NULL);
		// For simplicity, let's run bash directly. Interactive mode can source
		// profiles. Using --noprofile and --norc for a cleaner environment.
		// "-i" for interactive can be useful, but also can cause issues if not
		// handled well. Let's start with a non-interactive bash, which is
		// simpler.
		execlp("bash", "bash", "--noprofile", "--norc", NULL);
		perror("Bash Child: execlp bash failed");  // Only returns on error
		exit(EXIT_FAILURE);
	} else {                         // --- Server Parent Process ---
		close(bash_stdout_pipe[1]);  // Close write end for parent
		int bash_stdout_read_fd = bash_stdout_pipe[0];
		// Make bash_stdout_read_fd non-blocking for select
		fcntl(bash_stdout_read_fd, F_SETFL, O_NONBLOCK);

		// Open BASH_STDIN_FIFO for writing (blocks until child opens for
		// reading)
		int bash_stdin_write_fd = open(BASH_STDIN_FIFO, O_WRONLY);
		if (bash_stdin_write_fd == -1) {
			server_log(
			    "Failed to open BASH_STDIN_FIFO for writing from server.");
			print_error_and_exit("open BASH_STDIN_FIFO for writing");
		}
		server_log("Bash process started (PID: %d). Server ready for commands.",
		           g_bash_child_pid);

		// Server main loop
		fd_set read_fds;
		int max_fd;
		char client_resp_fifo_path[PATH_MAX];
		char command_from_client[MAX_CMD_LEN];
		char current_delimiter[128];
		int current_client_output_fd = -1;

		// Buffer for reading from bash, to find delimiter and exit code
		char bash_output_line_buffer[MAX_LINE_LEN];
		int line_buffer_idx = 0;

		bool processing_client_request = false;
		bool waiting_for_delimiter_line = false;
		bool waiting_for_exit_code_line = false;
		unsigned long cmd_counter = 0;  // For unique delimiters

		// This FD will be reopened each time select indicates activity on the
		// FIFO path
		int server_cmd_fifo_fd = -1;

		while (server_running) {
			FD_ZERO(&read_fds);

			// Always try to open server_cmd_fifo for reading if not processing
			// a request This is tricky as FIFOs need to be reopened after
			// client disconnects.
			if (!processing_client_request && server_cmd_fifo_fd == -1) {
				// Open non-blocking to avoid hanging here if no client connects
				server_cmd_fifo_fd =
				    open(SERVER_CMD_FIFO, O_RDONLY | O_NONBLOCK);
				if (server_cmd_fifo_fd == -1 &&
				    errno != ENXIO) {  // ENXIO (No such device or address) can
					                   // happen before client opens write end
					server_log("Error opening SERVER_CMD_FIFO: %s. Retrying.",
					           strerror(errno));
					sleep(1);  // Avoid busy-looping on persistent errors
					continue;
				} else if (server_cmd_fifo_fd != -1) {
					server_log("Opened SERVER_CMD_FIFO for reading commands.");
				}
			}

			if (server_cmd_fifo_fd != -1 && !processing_client_request) {
				FD_SET(server_cmd_fifo_fd, &read_fds);
			}
			FD_SET(bash_stdout_read_fd, &read_fds);

			max_fd = bash_stdout_read_fd;
			if (server_cmd_fifo_fd > max_fd) max_fd = server_cmd_fifo_fd;

			int activity = select(max_fd + 1, &read_fds, NULL, NULL, NULL);

			if (activity == -1) {
				if (errno == EINTR && !server_running)
					break;  // Interrupted by our signal handler for shutdown
				if (errno == EINTR) continue;  // Other signal, try again
				server_log("select() error: %s", strerror(errno));
				break;  // Exit loop on other select errors
			}

			if (!server_running)
				break;  // Check server_running flag again after select

			// 1. Check for new client request
			if (server_cmd_fifo_fd != -1 &&
			    FD_ISSET(server_cmd_fifo_fd, &read_fds) &&
			    !processing_client_request) {
				ssize_t path_len = read_line_from_fd(
				    server_cmd_fifo_fd, client_resp_fifo_path, PATH_MAX);
				if (path_len > 0 && client_resp_fifo_path[path_len - 1] == '\n')
					client_resp_fifo_path[path_len - 1] = '\0';

				ssize_t cmd_len = 0;
				if (path_len > 0) {  // Got path, try to read command
					cmd_len = read_line_from_fd(
					    server_cmd_fifo_fd, command_from_client, MAX_CMD_LEN);
					if (cmd_len > 0 && command_from_client[cmd_len - 1] == '\n')
						command_from_client[cmd_len - 1] = '\0';
				}

				if (path_len > 0 && cmd_len > 0) {
					server_log("Received request. Client FIFO: %s, Command: %s",
					           client_resp_fifo_path, command_from_client);
					processing_client_request = true;
					waiting_for_delimiter_line = true;
					waiting_for_exit_code_line = false;
					line_buffer_idx = 0;  // Reset line buffer
					cmd_counter++;
					snprintf(current_delimiter, sizeof(current_delimiter),
					         "%s%lu", DELIMITER_BASE, cmd_counter);

					current_client_output_fd =
					    open(client_resp_fifo_path, O_WRONLY);
					if (current_client_output_fd == -1) {
						server_log(
						    "Failed to open client response FIFO %s: %s. "
						    "Aborting request.",
						    client_resp_fifo_path, strerror(errno));
						processing_client_request = false;  // Abort
					} else {
						char full_bash_cmd[MAX_CMD_LEN + 256];
						// Command structure: ( actual_command ) 2>&1; __EC=$?;
						// echo "DELIMITER"; echo $__EC
						snprintf(
						    full_bash_cmd, sizeof(full_bash_cmd),
						    "(%s) 2>&1; __EC=$?; echo \"%s\"; echo \"$__EC\"\n",
						    command_from_client, current_delimiter);

						server_log(
						    "Sending to bash: %s",
						    full_bash_cmd);  // Log the exact command being sent
						if (write(bash_stdin_write_fd, full_bash_cmd,
						          strlen(full_bash_cmd)) == -1) {
							server_log(
							    "Write to bash_stdin_write_fd failed: %s. "
							    "Aborting request.",
							    strerror(errno));
							close(current_client_output_fd);
							current_client_output_fd = -1;
							processing_client_request = false;
						}
					}
				} else if (path_len == 0 ||
				           cmd_len == 0) {  // EOF on SERVER_CMD_FIFO or
					                        // incomplete read
					server_log(
					    "EOF or incomplete data on SERVER_CMD_FIFO. Closing "
					    "and will reopen.");
					close(server_cmd_fifo_fd);
					server_cmd_fifo_fd = -1;  // Mark to reopen
				} else {  // path_len < 0 or cmd_len < 0 (read errors)
					server_log(
					    "Error reading from SERVER_CMD_FIFO: %s. Closing and "
					    "will reopen.",
					    strerror(errno));
					close(server_cmd_fifo_fd);
					server_cmd_fifo_fd = -1;  // Mark to reopen
				}
			}

			// 2. Check for output from bash
			if (FD_ISSET(bash_stdout_read_fd, &read_fds) &&
			    processing_client_request) {
				char read_buf[BUFFER_SIZE];
				ssize_t n_read =
				    read(bash_stdout_read_fd, read_buf, BUFFER_SIZE - 1);

				if (n_read > 0) {
					read_buf[n_read] =
					    '\0';  // Null terminate for string operations
					// server_log("RAW BASH OUT: %s", read_buf); // For
					// debugging, can be very verbose

					char* current_pos = read_buf;
					while (current_pos < read_buf + n_read) {
						char ch = *current_pos++;
						if (line_buffer_idx < MAX_LINE_LEN - 1) {
							bash_output_line_buffer[line_buffer_idx++] = ch;
						} else {
							// Line too long, flush what we have and reset
							bash_output_line_buffer[MAX_LINE_LEN - 1] = '\0';
							if (current_client_output_fd != -1 &&
							    !waiting_for_delimiter_line &&
							    !waiting_for_exit_code_line) {
								write(current_client_output_fd,
								      bash_output_line_buffer, line_buffer_idx);
							}
							server_log(
							    "Warning: Line from bash exceeded "
							    "MAX_LINE_LEN.");
							line_buffer_idx = 0;
							bash_output_line_buffer[line_buffer_idx++] =
							    ch;  // Start new line with current char
						}

						if (ch == '\n') {
							bash_output_line_buffer[line_buffer_idx] = '\0';
							// server_log("PROCESS LINE: %s",
							// bash_output_line_buffer); // Debug parsed line

							if (waiting_for_exit_code_line) {
								// This line is the exit code
								int exit_code = atoi(bash_output_line_buffer);
								server_log(
								    "Command executed. Delimiter: %s. Exit "
								    "code: %d",
								    current_delimiter, exit_code);
								// Client doesn't get exit code explicitly via
								// FIFO in this version. Client exec will exit
								// 0. To send exit code:
								// write(current_client_output_fd,
								// bash_output_line_buffer, line_buffer_idx);

								// Request finished
								if (current_client_output_fd != -1) {
									close(current_client_output_fd);
									current_client_output_fd = -1;
								}
								processing_client_request = false;
								waiting_for_delimiter_line = false;
								waiting_for_exit_code_line = false;
								line_buffer_idx = 0;
								break;  // Stop processing this batch of
								        // read_buf, new state
							} else if (waiting_for_delimiter_line) {
								// Check if this line (excluding newline) is the
								// delimiter
								if (line_buffer_idx > 0 &&
								    bash_output_line_buffer[line_buffer_idx -
								                            1] == '\n') {
									bash_output_line_buffer[line_buffer_idx -
									                        1] =
									    '\0';  // Temporarily remove newline for
									           // strcmp
								}
								if (strcmp(bash_output_line_buffer,
								           current_delimiter) == 0) {
									waiting_for_exit_code_line = true;
									server_log("Delimiter '%s' found.",
									           current_delimiter);
								} else {  // Not the delimiter, so it's command
									      // output
									if (line_buffer_idx > 0 &&
									    bash_output_line_buffer
									            [line_buffer_idx - 1] ==
									        '\0') {  // Put newline back if
										             // removed
										bash_output_line_buffer
										    [line_buffer_idx - 1] = '\n';
									}
									if (current_client_output_fd != -1) {
										if (write(current_client_output_fd,
										          bash_output_line_buffer,
										          line_buffer_idx) == -1 &&
										    errno == EPIPE) {
											server_log(
											    "Client closed pipe. Aborting "
											    "send for current command.");
											close(current_client_output_fd);
											current_client_output_fd = -1;
											processing_client_request = false;
											waiting_for_delimiter_line = false;
											waiting_for_exit_code_line = false;
										}
									}
								}
								if (line_buffer_idx > 0 &&
								    bash_output_line_buffer[line_buffer_idx -
								                            1] ==
								        '\0') {  // In case it wasn't put back
									bash_output_line_buffer[line_buffer_idx -
									                        1] =
									    '\n';  // Restore for next char if any
								}
							}
							line_buffer_idx = 0;  // Reset for next line
						}
					}
					if (!server_running || !processing_client_request)
						break;             // Break outer loop if state changed
						                   // mid-processing
				} else if (n_read == 0) {  // EOF from bash_stdout_read_fd
					server_log(
					    "EOF on bash_stdout_read_fd. Bash process likely "
					    "exited.");
					server_running = 0;  // Trigger server shutdown
					break;
				} else if (n_read == -1 && errno != EAGAIN &&
				           errno != EWOULDBLOCK) {
					server_log("Error reading from bash_stdout_read_fd: %s",
					           strerror(errno));
					server_running = 0;  // Trigger server shutdown
					break;
				}
				// EAGAIN/EWOULDBLOCK means no data now, loop and select again
			} else if (FD_ISSET(bash_stdout_read_fd, &read_fds) &&
			           !processing_client_request) {
				// Bash is outputting stuff but we are not processing a client
				// request This could be initial prompts, or output after a
				// client request finished. For now, just drain it to avoid
				// blocking bash.
				char drain_buf[256];
				ssize_t drained =
				    read(bash_stdout_read_fd, drain_buf, sizeof(drain_buf) - 1);
				if (drained > 0) {
					drain_buf[drained] = '\0';
					server_log("Drained unsolicited bash output: %s",
					           drain_buf);
				} else if (drained == 0) {  // EOF from bash
					server_log(
					    "EOF on bash_stdout_read_fd (draining). Bash process "
					    "likely exited.");
					server_running = 0;
					break;
				} else if (drained < 0 && errno != EAGAIN &&
				           errno != EWOULDBLOCK) {
					server_log("Error draining bash_stdout_read_fd: %s",
					           strerror(errno));
					server_running = 0;
					break;
				}
			}
		}  // end server_running loop

		server_log("Server main loop exited.");
		if (bash_stdin_write_fd != -1) close(bash_stdin_write_fd);
		if (bash_stdout_read_fd != -1) close(bash_stdout_read_fd);
		if (server_cmd_fifo_fd != -1) close(server_cmd_fifo_fd);
		if (current_client_output_fd != -1) close(current_client_output_fd);
		// atexit handler (cleanup_server_resources) will do the rest
	}
}

// --- Client Mode Implementation ---

void client_cleanup_resources(void) {
	if (strlen(g_client_resp_fifo_path) > 0) {
		unlink(g_client_resp_fifo_path);
		// Optional: log client-side cleanup if needed
		// printf("Client: cleaned up %s\n", g_client_resp_fifo_path);
	}
}

void client_mode(int argc, char* argv[]) {
	// 1. Construct full command string
	char full_command_string[MAX_CMD_LEN] = "";
	size_t current_len = 0;
	for (int i = 2; i < argc; i++) {
		size_t arg_len = strlen(argv[i]);
		if (current_len + arg_len + (i > 2 ? 1 : 0) < MAX_CMD_LEN - 1) {
			if (i > 2) {
				strcat(full_command_string, " ");
				current_len++;
			}
			strcat(full_command_string, argv[i]);
			current_len += arg_len;
		} else {
			fprintf(stderr, "Client: Command string too long.\n");
			exit(EXIT_FAILURE);
		}
	}

	// 2. Create client response FIFO
	pid_t client_pid = getpid();
	snprintf(g_client_resp_fifo_path, PATH_MAX, CLIENT_RESP_FIFO_PATTERN,
	         client_pid);

	// Clean up pre-existing FIFO just in case (e.g. from a crashed previous
	// client with same PID, unlikely)
	unlink(g_client_resp_fifo_path);
	if (mkfifo(g_client_resp_fifo_path, 0600) == -1) {
		perror("Client: mkfifo for response failed");
		exit(EXIT_FAILURE);
	}
	atexit(client_cleanup_resources);

	// 3. Open server command FIFO for writing
	int server_cmd_fd = open(SERVER_CMD_FIFO, O_WRONLY);
	if (server_cmd_fd == -1) {
		if (errno == ENOENT) {
			fprintf(stderr,
			        "Client: Server command FIFO %s does not exist. Is server "
			        "running?\n",
			        SERVER_CMD_FIFO);
		} else {
			perror("Client: open server command FIFO failed");
		}
		exit(EXIT_FAILURE);
	}

	// 4. Send response FIFO path and command to server
	char msg_to_server[PATH_MAX + MAX_CMD_LEN + 2];  // +2 for newlines
	snprintf(msg_to_server, sizeof(msg_to_server), "%s\n%s\n",
	         g_client_resp_fifo_path, full_command_string);

	if (write(server_cmd_fd, msg_to_server, strlen(msg_to_server)) == -1) {
		perror("Client: write to server command FIFO failed");
		close(server_cmd_fd);
		exit(EXIT_FAILURE);
	}
	close(server_cmd_fd);  // Close quickly to signal server

	// 5. Open client response FIFO for reading (blocks until server opens it
	// for writing)
	int client_read_fd = open(g_client_resp_fifo_path, O_RDONLY);
	if (client_read_fd == -1) {
		perror("Client: open response FIFO for reading failed");
		exit(EXIT_FAILURE);
	}

	// 6. Read output from response FIFO and print to stdout
	char buffer[BUFFER_SIZE];
	ssize_t bytes_read;
	while ((bytes_read = read(client_read_fd, buffer, BUFFER_SIZE - 1)) > 0) {
		buffer[bytes_read] =
		    '\0';  // Not strictly necessary if writing raw bytes
		if (write(STDOUT_FILENO, buffer, bytes_read) != bytes_read) {
			perror("Client: write to STDOUT_FILENO failed");
			// Continue trying to read the rest from FIFO to let server finish
		}
	}
	if (bytes_read == -1) {
		perror("Client: read from response FIFO failed");
	}
	// EOF (bytes_read == 0) is the normal termination.

	close(client_read_fd);
	// atexit handler will unlink the FIFO.
	// Client exit code is 0 if communication succeeded, not necessarily if
	// command succeeded.
}