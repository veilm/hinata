#define _POSIX_C_SOURCE 200809L  // For kill, ftruncate, etc.

#include <dirent.h>  // For opendir, readdir, closedir for list command
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

#define HEADLESH_SESSIONS_DIR "/tmp/headlesh_sessions"
#define SESSION_CMD_FIFO_NAME "cmd.fifo"
#define SESSION_LOCK_FILE_NAME "pid.lock"
#define SESSION_LOG_DIR_NAME_COMPONENT "headlesh"  // Component under hinata
#define SESSION_LOG_FILE_NAME "server.log"

#define OUT_FIFO_TEMPLATE "/tmp/headlesh_out_%d"  // %d for client PID
#define BUFFER_SIZE 4096  // For general I/O and command construction
#define HEADLESH_EXIT_CMD_PAYLOAD "__HEADLESH_INTERNAL_EXIT_CMD__"

// Globals for server cleanup - specific to one daemon instance
static char g_session_dir_path[PATH_MAX];
static char g_session_cmd_fifo_path[PATH_MAX];
static char g_session_lock_file_path[PATH_MAX];
int g_lock_fd = -1;     // File descriptor for the session's lock file
pid_t g_bash_pid = -1;  // PID of the bash process for this session

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
	// This function's printf statements will go to the session's log file if
	// daemonized.
	fprintf(
	    stdout,
	    "Session Server: Cleaning up resources for session...\n");  // To log
	if (g_bash_pid > 0) {
		fprintf(stdout,
		        "Session Server: Terminating bash process (PID: %d)...\n",
		        g_bash_pid);  // To log
		kill(g_bash_pid, SIGTERM);
		sleep(1);  // Give bash a moment to terminate
		int status;
		if (waitpid(g_bash_pid, &status, WNOHANG) ==
		    0) {  // Check if terminated
			fprintf(stdout,
			        "Session Server: Bash process did not terminate "
			        "gracefully, sending SIGKILL.\n");  // To log
			kill(g_bash_pid, SIGKILL);
			waitpid(g_bash_pid, NULL, 0);  // Wait for SIGKILL to be processed
		} else {
			fprintf(stdout,
			        "Session Server: Bash process terminated.\n");  // To log
		}
		g_bash_pid = -1;
	}

	if (g_session_cmd_fifo_path[0] != '\0') {
		if (unlink(g_session_cmd_fifo_path) == -1 && errno != ENOENT) {
			perror(
			    "Session Server cleanup: unlink command FIFO failed");  // To
			                                                            // log
			                                                            // via
			                                                            // stderr
		} else {
			fprintf(stdout,
			        "Session Server cleanup: Unlinked command FIFO %s.\n",
			        g_session_cmd_fifo_path);  // To log
		}
	}

	if (g_lock_fd != -1) {
		// flock is advisory and lock is released on close.
		if (close(g_lock_fd) == -1) {
			perror(
			    "Session Server cleanup: close lock_fd failed");  // To log via
			                                                      // stderr
		}
		g_lock_fd = -1;  // Mark as closed
		if (g_session_lock_file_path[0] != '\0') {
			if (unlink(g_session_lock_file_path) == -1 && errno != ENOENT) {
				perror(
				    "Session Server cleanup: unlink lock file failed");  // To
				                                                         // log
				                                                         // via
				                                                         // stderr
			} else {
				fprintf(stdout,
				        "Session Server cleanup: Unlinked lock file %s.\n",
				        g_session_lock_file_path);  // To log
			}
		}
	}

	// Attempt to remove the session directory itself if it's empty
	if (g_session_dir_path[0] != '\0') {
		if (rmdir(g_session_dir_path) == -1 && errno != ENOENT &&
		    errno != ENOTEMPTY) {
			// ENOTEMPTY is possible if e.g. log files are unexpectedly there or
			// other issues. ENOENT means it's already gone.
			perror(
			    "Session Server cleanup: rmdir session directory failed");  // To log
		} else {
			fprintf(stdout,
			        "Session Server cleanup: Removed session directory %s (if "
			        "empty).\n",
			        g_session_dir_path);  // To log
		}
	}
	fflush(stdout);
}

void server_signal_handler(int sig) {
	(void)sig;  // Mark as unused to prevent compiler warnings
	// printf("\nServer: Caught signal %d, initiating shutdown...\n", sig);
	// atexit handler (cleanup_server_resources) will be called.
	exit(EXIT_FAILURE);  // Trigger atexit
}

// Helper function to ensure a directory path exists, creating it if necessary.
// Similar to mkdir -p. Returns 0 on success, -1 on failure.
static int ensure_directory_exists(const char* path) {
	char tmp[PATH_MAX];
	char* p = NULL;
	size_t len;

	snprintf(tmp, sizeof(tmp), "%s", path);
	len = strlen(tmp);
	if (len == 0) return -1;     // Empty path
	if (tmp[len - 1] == '/') {   // Remove trailing slash
		if (len == 1) return 0;  // Path is just "/"
		tmp[len - 1] = 0;
	}

	// Iterate through path components and create them
	for (p = tmp + 1; *p;
	     p++) {  // Start after the first char (e.g. skip root '/')
		if (*p == '/') {
			*p = 0;  // Temporarily terminate string at this slash
			if (mkdir(tmp, S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH) == -1) {
				if (errno != EEXIST) {
					fprintf(stderr, "Error creating directory %s: %s\n", tmp,
					        strerror(errno));
					return -1;
				}
			}
			*p = '/';  // Restore slash
		}
	}
	// Create the final component
	if (mkdir(tmp, S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH) == -1) {
		if (errno != EEXIST) {
			fprintf(stderr, "Error creating directory %s: %s\n", tmp,
			        strerror(errno));
			return -1;
		}
	}
	return 0;
}

// Helper function to construct the session-specific log file path
// Returns 0 on success, -1 on error.
// path_buffer will contain the log file path on success.
static int construct_session_log_file_path(char* path_buffer,
                                           size_t buffer_size,
                                           const char* session_id) {
	const char* xdg_data_home_val = getenv("XDG_DATA_HOME");
	const char* home_dir_val;
	char base_log_dir[PATH_MAX];
	char session_log_dir[PATH_MAX];

	if (xdg_data_home_val && xdg_data_home_val[0] != '\0') {
		snprintf(base_log_dir, sizeof(base_log_dir), "%s/hinata",
		         xdg_data_home_val);
	} else {
		home_dir_val = getenv("HOME");
		if (home_dir_val && home_dir_val[0] != '\0') {
			snprintf(base_log_dir, sizeof(base_log_dir),
			         "%s/.local/share/hinata", home_dir_val);
		} else {
			fprintf(stderr,
			        "Error: Neither XDG_DATA_HOME nor HOME set. Cannot "
			        "determine log directory base.\n");
			return -1;
		}
	}

	// base_log_dir is now like ".../hinata"
	// Append "headlesh/<session_id>" to it for the session-specific log
	// directory
	int written =
	    snprintf(session_log_dir, sizeof(session_log_dir), "%s/%s/%s",
	             base_log_dir, SESSION_LOG_DIR_NAME_COMPONENT, session_id);
	if (written < 0 || (size_t)written >= sizeof(session_log_dir)) {
		fprintf(stderr, "Error: Session log directory path too long.\n");
		return -1;
	}

	// Ensure this session-specific log directory exists
	if (ensure_directory_exists(session_log_dir) != 0) {
		// ensure_directory_exists prints its own error
		return -1;
	}

	// Construct the full log file path
	written = snprintf(path_buffer, buffer_size, "%s/%s", session_log_dir,
	                   SESSION_LOG_FILE_NAME);
	if (written < 0 || (size_t)written >= buffer_size) {
		fprintf(stderr,
		        "Error: Full log file path too long or snprintf error.\n");
		return -1;
	}
	return 0;  // Success
}

void start_server_mode(const char* session_id) {
	int bash_stdin_pipe[2];
	int cmd_fifo_fd = -1;      // FD for the session's command FIFO
	char buffer[BUFFER_SIZE];  // For reading commands from session's CMD_FIFO
	char bash_cmd_buffer[BUFFER_SIZE];    // For formatting commands to bash
	char daemon_log_file_path[PATH_MAX];  // For the session's log path

	// 0. Setup session paths and directories
	// Ensure base sessions directory exists
	if (ensure_directory_exists(HEADLESH_SESSIONS_DIR) != 0) {
		fprintf(stderr,
		        "Session Server (%s): Failed to create base sessions directory "
		        "%s. Aborting.\n",
		        session_id, HEADLESH_SESSIONS_DIR);
		exit(EXIT_FAILURE);
	}

	int base_path_len;  // Length of g_session_dir_path string (excluding null
	                    // terminator)

	// Construct and validate g_session_dir_path
	base_path_len = snprintf(g_session_dir_path, PATH_MAX, "%s/%s",
	                         HEADLESH_SESSIONS_DIR, session_id);
	if (base_path_len < 0 || (size_t)base_path_len >= PATH_MAX) {
		// snprintf error or path too long (would be truncated if base_path_len
		// == PATH_MAX-1, or overflow if >= PATH_MAX)
		fprintf(stderr,
		        "Session Server (%s): Session directory path is too long or "
		        "snprintf error. Base: '%s', ID: '%s'. Attempted string length "
		        "%d, buffer capacity %d (max string length %d).\n",
		        session_id, HEADLESH_SESSIONS_DIR, session_id, base_path_len,
		        PATH_MAX, PATH_MAX - 1);
		exit(EXIT_FAILURE);
	}

	// Construct g_session_cmd_fifo_path
	int cmd_fifo_written_len;
	cmd_fifo_written_len =
	    snprintf(g_session_cmd_fifo_path,
	             sizeof g_session_cmd_fifo_path, /* истинный размер буфера */
	             "%s/%s", g_session_dir_path, SESSION_CMD_FIFO_NAME);
	if (cmd_fifo_written_len < 0 || /* ошибка snprintf */
	    (size_t)cmd_fifo_written_len >=
	        sizeof g_session_cmd_fifo_path /* усечение */) {
		fprintf(stderr,
		        "Session Server (%s): Failed to construct command-FIFO path "
		        "(too long or snprintf error).\n",
		        session_id);
		exit(EXIT_FAILURE);
	}

	// Construct g_session_lock_file_path
	int lock_file_written_len;
	lock_file_written_len =
	    snprintf(g_session_lock_file_path,
	             sizeof g_session_lock_file_path, /* истинный размер буфера */
	             "%s/%s", g_session_dir_path, SESSION_LOCK_FILE_NAME);
	if (lock_file_written_len < 0 || /* ошибка snprintf */
	    (size_t)lock_file_written_len >=
	        sizeof g_session_lock_file_path /* усечение */) {
		fprintf(stderr,
		        "Session Server (%s): Failed to construct lock-file path (too "
		        "long or snprintf error).\n",
		        session_id);
		exit(EXIT_FAILURE);
	}

	// Create the specific session directory
	if (ensure_directory_exists(g_session_dir_path) != 0) {
		fprintf(stderr,
		        "Session Server (%s): Failed to create session directory %s. "
		        "Aborting.\n",
		        session_id, g_session_dir_path);
		exit(EXIT_FAILURE);
	}
	printf("Session Server (%s): Session directory created/ensured: %s\n",
	       session_id, g_session_dir_path);

	// Determine log file path first (uses session_id). Errors go to current
	// stderr.
	if (construct_session_log_file_path(daemon_log_file_path,
	                                    sizeof(daemon_log_file_path),
	                                    session_id) != 0) {
		fprintf(stderr,
		        "Session Server (%s): Failed to initialize log file path. "
		        "Aborting.\n",
		        session_id);
		exit(EXIT_FAILURE);
	}
	printf("Session Server (%s): Logging will be to: %s\n", session_id,
	       daemon_log_file_path);

	// 1. Setup session lock file (before daemonizing fork, so errors are
	// visible)
	g_lock_fd = open(g_session_lock_file_path, O_CREAT | O_RDWR, 0666);
	if (g_lock_fd == -1) {
		char err_msg[PATH_MAX + 100];
		snprintf(err_msg, sizeof(err_msg),
		         "Session Server (%s): Failed to open/create lock file %s",
		         session_id, g_session_lock_file_path);
		print_error_and_exit(err_msg);
	}
	if (flock(g_lock_fd, LOCK_EX | LOCK_NB) == -1) {
		if (errno == EWOULDBLOCK) {
			fprintf(stderr,
			        "Session Server (%s): Another instance for this session is "
			        "already running (lock held on %s).\n",
			        session_id, g_session_lock_file_path);
		} else {
			char err_msg[PATH_MAX + 100];
			snprintf(err_msg, sizeof(err_msg),
			         "Session Server (%s): flock on %s failed", session_id,
			         g_session_lock_file_path);
			perror(err_msg);
		}
		close(g_lock_fd);
		g_lock_fd = -1;  // Reset g_lock_fd as it's not validly held
		// Do not unlink here as another process might own it.
		exit(EXIT_FAILURE);
	}
	printf(
	    "Session Server (%s): Lock acquired: %s. Daemon PID will be written to "
	    "this file.\n",
	    session_id, g_session_lock_file_path);

	// 2. Create session CMD_FIFO (before daemonizing fork)
	unlink(g_session_cmd_fifo_path);  // Remove if it already exists
	if (mkfifo(g_session_cmd_fifo_path, 0666) == -1) {
		char err_msg[PATH_MAX + 100];
		snprintf(err_msg, sizeof(err_msg),
		         "Session Server (%s): mkfifo for command FIFO %s failed",
		         session_id, g_session_cmd_fifo_path);
		print_error_and_exit(err_msg);
	}
	printf("Session Server (%s): Command FIFO created: %s\n", session_id,
	       g_session_cmd_fifo_path);

	// 3. Daemonize
	printf("Session Server (%s): Daemonizing...\n", session_id);
	fflush(stdout);  // Ensure messages are printed before fork

	pid_t pid = fork();  // First fork
	if (pid < 0) {
		print_error_and_exit("Session Server: fork (1) failed");
	}
	if (pid > 0) {  // Parent of first fork
		printf(
		    "Session Server (%s): Daemonizing process initiated. Daemon PID "
		    "will be in %s.\n",
		    session_id, g_session_lock_file_path);
		exit(EXIT_SUCCESS);  // Parent exits, child continues
	}

	// ---- Child Process 1 (continues to become daemon) ----
	if (setsid() < 0) {
		print_error_and_exit("Session Server: setsid failed");
	}

	signal(SIGHUP,
	       SIG_IGN);  // Ignore SIGHUP often sent when session leader exits

	pid = fork();  // Second fork
	if (pid < 0) {
		print_error_and_exit("Session Server: fork (2) failed");
	}
	if (pid > 0) {  // Parent of second fork (session leader) exits
		exit(EXIT_SUCCESS);
	}

	// ---- Grandchild Process (Actual Daemon for the session) ----
	if (chdir("/") < 0) {
		print_error_and_exit("Session Server: chdir failed");
	}
	umask(0);

	// Redirect standard file descriptors for the daemon
	int log_fd =
	    open(daemon_log_file_path, O_WRONLY | O_CREAT | O_APPEND, 0644);
	if (log_fd == -1) {
		char err_msg_buf[PATH_MAX + 100];
		snprintf(err_msg_buf, sizeof(err_msg_buf),
		         "Session Server: Failed to open log file %s",
		         daemon_log_file_path);
		print_error_and_exit(
		    err_msg_buf);  // Error to original stderr if possible
	}

	// Redirect stdout to the log file
	if (close(STDOUT_FILENO) == -1) {
		dprintf(log_fd, "Session Server: Failed to close STDOUT_FILENO: %s\n",
		        strerror(errno));
	}
	if (dup2(log_fd, STDOUT_FILENO) == -1) {
		dprintf(log_fd, "Sessopm Server: Failed to dup2 STDOUT_FILENO: %s\n",
		        strerror(errno));
		close(log_fd);
		exit(EXIT_FAILURE);
	}

	// Redirect stderr to the log file
	if (close(STDERR_FILENO) == -1) {
		fprintf(stdout, "Session Server: Failed to close STDERR_FILENO: %s\n",
		        strerror(errno));  // To log file
	}
	if (dup2(log_fd, STDERR_FILENO) == -1) {
		fprintf(stdout, "Session Server: Failed to dup2 STDERR_FILENO: %s\n",
		        strerror(errno));  // To log file
		if (log_fd != STDOUT_FILENO) close(log_fd);
		exit(EXIT_FAILURE);
	}

	if (log_fd != STDOUT_FILENO && log_fd != STDERR_FILENO) {
		close(
		    log_fd);  // Close original log_fd if not same as STDOUT/STDERR now
	}
	// At this point, STDOUT and STDERR are directed to the session's log file.

	// Redirect stdin to /dev/null
	if (close(STDIN_FILENO) == -1) {
		perror("Session Server: Failed to close STDIN_FILENO");  // Goes to log
		                                                         // file
	}
	int fd_stdin = open("/dev/null", O_RDWR);
	if (fd_stdin == -1) {
		perror(
		    "Session Server: Failed to open /dev/null for STDIN");  // Goes to
		                                                            // log file
		exit(EXIT_FAILURE);
	}
	if (dup2(fd_stdin, STDIN_FILENO) == -1) {
		perror(
		    "Session Server: Failed to dup2 STDIN_FILENO");  // Goes to log file
		if (fd_stdin != STDIN_FILENO) close(fd_stdin);
		exit(EXIT_FAILURE);
	}
	if (fd_stdin != STDIN_FILENO) {
		close(fd_stdin);
	}

	// End of FD redirection. Log daemon startup.
	fprintf(stdout,
	        "Session Server (%s) daemon starting. PID: %d. Logging to %s.\n",
	        session_id, getpid(), daemon_log_file_path);
	fflush(stdout);

	// Write daemon's PID to the session lock file
	if (ftruncate(g_lock_fd, 0) == -1) {  // Truncate before writing PID
		perror("Session Server: ftruncate lock_fd failed");  // To log file
		// cleanup_server_resources(); // Risky before atexit registered,
		// globals might be partially set
		exit(EXIT_FAILURE);  // Exit, let OS clean FDs. Lock file may remain.
	}
	char pid_str[32];
	snprintf(pid_str, sizeof(pid_str), "%d\n", getpid());
	if (write(g_lock_fd, pid_str, strlen(pid_str)) == -1) {
		perror("Session Server: write PID to lock_fd failed");  // To log file
		// cleanup_server_resources();
		exit(EXIT_FAILURE);
	}
	// Note: g_lock_fd (for the session lock file) remains open and locked.

	// Register cleanup and signal handlers *IN THE DAEMON PROCESS*
	if (atexit(cleanup_server_resources) != 0) {
		perror("Session Server: atexit registration failed");  // To log file
		// Attempt manual cleanup as a fallback, though paths might not be fully
		// set. This is a best-effort. A more robust solution might involve a
		// different cleanup trigger. For now, rely on OS for unclosed FDs/FIFOs
		// if this path is hit. unlink(g_session_cmd_fifo_path); if (g_lock_fd
		// != -1) close(g_lock_fd); unlink(g_session_lock_file_path);
		exit(EXIT_FAILURE);
	}
	signal(SIGINT, server_signal_handler);
	signal(SIGTERM, server_signal_handler);
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write() errors instead

	// 4. Create pipe for bash's stdin
	if (pipe(bash_stdin_pipe) == -1) {
		print_error_and_exit(
		    "Session Server: pipe for bash_stdin failed");  // Exits, calls
		                                                    // atexit
	}

	// 5. Fork bash process for this session
	g_bash_pid = fork();
	if (g_bash_pid == -1) {
		print_error_and_exit(
		    "Session Server: fork for bash process failed");  // Exits, calls
		                                                      // atexit
	}

	if (g_bash_pid == 0) {          // Child process (bash)
		close(bash_stdin_pipe[1]);  // Close write end
		if (dup2(bash_stdin_pipe[0], STDIN_FILENO) == -1) {
			// Cannot reliably log here to session log as FDs are not inherited
			// in the same state. perror("Bash child: dup2 stdin failed");
			_exit(EXIT_FAILURE);  // Use _exit, not exit, to bypass atexit
			                      // handlers
		}
		close(bash_stdin_pipe[0]);

		if (g_lock_fd != -1)
			close(g_lock_fd);  // Bash doesn't need session lock file FD

		// cmd_fifo_fd would be -1 here (not opened by bash child)
		// No need to close cmd_fifo_fd for the session.

		execlp("bash", "bash", NULL);
		// If execlp returns, it's an error
		// perror("Bash child: execlp bash failed");
		_exit(EXIT_FAILURE);
	} else {  // Parent process (session daemon server logic)
		close(bash_stdin_pipe[0]);  // Close read end
		int bash_stdin_writer_fd = bash_stdin_pipe[1];

		fprintf(stdout,
		        "Session Server (%s): Bash process forked with PID %d. "
		        "Entering command loop.\n",
		        session_id, g_bash_pid);
		fflush(stdout);

		int server_running = 1;
		while (server_running) {
			int status;
			pid_t result = waitpid(g_bash_pid, &status, WNOHANG);
			if (result == g_bash_pid) {  // Bash exited
				fprintf(stdout,
				        "Session Server (%s): Bash process (PID %d) exited.\n",
				        session_id, g_bash_pid);
				fflush(stdout);
				g_bash_pid = -1;     // Mark as exited
				server_running = 0;  // Stop server loop
				break;
			} else if (result == -1 &&
			           errno != ECHILD) {  // ECHILD means bash_pid was invalid
				                           // (e.g. already reaped)
				perror(
				    "Session Server: waitpid for bash process failed");  // To
				                                                         // log
				                                                         // file
				fflush(stdout);
				g_bash_pid = -1;
				server_running = 0;
				break;
			}

			// If session CMD_FIFO (cmd_fifo_fd) not open, try to open it
			// (blocking) This is the main blocking point for new client
			// connections to the FIFO
			if (cmd_fifo_fd == -1) {
				cmd_fifo_fd = open(g_session_cmd_fifo_path, O_RDONLY);
				if (cmd_fifo_fd == -1) {
					if (errno == EINTR)
						continue;  // Interrupted by signal, retry
					perror(
					    "Session Server: Failed to open command FIFO for "
					    "reading in loop");  // To log file
					fflush(stdout);
					server_running =
					    0;  // Critical error, cannot accept commands
					break;
				}
				fprintf(stdout,
				        "Session Server (%s): Opened command FIFO %s for "
				        "reading.\n",
				        session_id, g_session_cmd_fifo_path);
				fflush(stdout);
			}

			ssize_t bytes_read = read(cmd_fifo_fd, buffer, BUFFER_SIZE - 1);
			if (bytes_read > 0) {
				// buffer[bytes_read] = '\0'; // Null-terminate incoming message
				// - not safe if buffer full
				char* newline_pos = memchr(buffer, '\n', bytes_read);

				if (newline_pos == NULL) {
					fprintf(stdout,
					        "Session Server (%s): Malformed message (no "
					        "newline for FIFO path).\n",
					        session_id);
					fflush(stdout);
					// Close and reopen to reset state and wait for a new,
					// well-formed client message.
					close(cmd_fifo_fd);
					cmd_fifo_fd = -1;
					continue;
				}

				size_t client_out_fifo_path_len = newline_pos - buffer;
				char client_out_fifo_path_str[256];
				if (client_out_fifo_path_len >=
				    sizeof(client_out_fifo_path_str)) {
					fprintf(stdout,
					        "Session Server (%s): Client FIFO path too long in "
					        "message.\n",
					        session_id);
					fflush(stdout);
					close(cmd_fifo_fd);
					cmd_fifo_fd = -1;
					continue;
				}
				memcpy(client_out_fifo_path_str, buffer,
				       client_out_fifo_path_len);
				client_out_fifo_path_str[client_out_fifo_path_len] = '\0';

				char* command_script_content = newline_pos + 1;
				size_t command_script_len =
				    bytes_read - (client_out_fifo_path_len + 1);

				if (command_script_len == strlen(HEADLESH_EXIT_CMD_PAYLOAD) &&
				    strncmp(command_script_content, HEADLESH_EXIT_CMD_PAYLOAD,
				            command_script_len) == 0) {
					fprintf(stdout,
					        "Session Server (%s): Received exit command (via "
					        "%s). Shutting down.\n",
					        session_id, client_out_fifo_path_str);
					fflush(stdout);
					server_running = 0;  // Signal server to stop
					// cmd_fifo_fd will be closed outside loop, no need to
					// close/reopen here
					continue;  // Go to top of loop, which will then exit based
					           // on server_running
				}

				if (command_script_len == 0) {
					fprintf(stdout,
					        "Session Server (%s): Received empty command "
					        "script for client FIFO %s.\n",
					        session_id, client_out_fifo_path_str);
					fflush(stdout);
				}

				char tmp_script_path_template[] =
				    "/tmp/headlesh_cmd_script_XXXXXX";
				int tmp_script_fd = mkstemp(tmp_script_path_template);
				if (tmp_script_fd == -1) {
					perror(
					    "Session Server: mkstemp for command script failed");  // Logged
					// Cannot notify client easily. Drop connection to signal
					// issue by closing FIFO.
					close(cmd_fifo_fd);
					cmd_fifo_fd = -1;
					continue;
				}

				ssize_t written_to_script = write(
				    tmp_script_fd, command_script_content, command_script_len);
				// Note: close can be interrupted by a signal (EINTR). A robust
				// solution would retry.
				if (close(tmp_script_fd) == -1) {
					perror(
					    "Session Server: close temp script fd failed");  // Logged
				}

				if (written_to_script == -1 ||
				    (size_t)written_to_script < command_script_len) {
					perror(
					    "Session Server: Failed to write full command to "
					    "temporary script file");      // Logged
					unlink(tmp_script_path_template);  // Clean up
					close(cmd_fifo_fd);
					cmd_fifo_fd = -1;
					continue;
				}

				int len_needed =
				    snprintf(bash_cmd_buffer, BUFFER_SIZE,
				             "{ . %s ; } > %s 2>&1 ; rm -f %s\n",
				             tmp_script_path_template, client_out_fifo_path_str,
				             tmp_script_path_template);

				if (len_needed < 0 || len_needed >= BUFFER_SIZE) {
					fprintf(stdout,
					        "Session Server (%s): Formatted command for bash "
					        "too long. Temp script: '%s', Client FIFO: '%s'\n",
					        session_id, tmp_script_path_template,
					        client_out_fifo_path_str);
					fflush(stdout);
					unlink(tmp_script_path_template);
					close(cmd_fifo_fd);
					cmd_fifo_fd = -1;
					continue;
				}

				fprintf(stdout,
				        "Session Server (%s): Sending command to bash: { . %s "
				        "; } > %s 2>&1 ; rm -f %s\n",
				        session_id, tmp_script_path_template,
				        client_out_fifo_path_str, tmp_script_path_template);
				fflush(stdout);

				ssize_t written_to_bash =
				    write(bash_stdin_writer_fd, bash_cmd_buffer,
				          strlen(bash_cmd_buffer));
				if (written_to_bash == -1) {
					if (errno == EPIPE) {  // Bash likely exited
						fprintf(stdout,
						        "Session Server (%s): Write to bash failed "
						        "(EPIPE), bash may have exited.\n",
						        session_id);
						fflush(stdout);
					} else {
						perror(
						    "Session Server: Write to bash_stdin_writer_fd "
						    "failed");  // To log
						fflush(stdout);
					}
					server_running =
					    0;  // Stop server loop, bash is gone or pipe broken
					// No need to unlink tmp_script_path_template, bash command
					// includes `rm -f`
				}
				// Successfully processed one command. The current cmd_fifo_fd
				// for the session remains open. Client specific FIFOs
				// (client_out_fifo_path_str) are handled by clients and the
				// bash command.
			} else if (bytes_read ==
			           0) {  // EOF on session's CMD_FIFO (all writers closed)
				fprintf(stdout,
				        "Session Server (%s): Detected EOF on command FIFO %s. "
				        "Reopening for next client connection.\n",
				        session_id, g_session_cmd_fifo_path);
				fflush(stdout);
				close(cmd_fifo_fd);
				cmd_fifo_fd = -1;  // Mark for reopening (waits for new client
				                   // to open for writing)
			} else {               // bytes_read < 0 (error)
				if (errno == EINTR)
					continue;  // Interrupted by signal, retry read
				perror(
				    "Session Server: read from command FIFO failed");  // To log
				fflush(stdout);
				server_running = 0;  // Critical error on session command FIFO
			}
		}  // end while(server_running)

		if (cmd_fifo_fd != -1) close(cmd_fifo_fd);
		close(bash_stdin_writer_fd);  // Close write end of pipe to bash
		fprintf(stdout,
		        "Session Server (%s): Daemon shutting down gracefully.\n",
		        session_id);
		fflush(stdout);
		// atexit handler (cleanup_server_resources) will manage g_bash_pid,
		// session FIFO unlinking, session lock file, and session dir.
		exit(EXIT_SUCCESS);  // Normal daemon exit for this session
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

void exec_client_mode(const char* session_id) {
	int session_cmd_fifo_fd_client;  // To write to the specific session's
	                                 // CMD_FIFO
	int out_fifo_fd_client;          // To read output from this client's unique
	                                 // OUT_FIFO
	char client_cmd_payload[BUFFER_SIZE];  // Buffer for command read from stdin

	char server_full_cmd[BUFFER_SIZE];  // For: client_out_fifo_path + \n +
	                                    // client_cmd_payload
	char read_buf[BUFFER_SIZE];  // For reading output from out_fifo_fd_client
	char target_session_cmd_fifo_path[PATH_MAX];  // Path to the target
	                                              // session's command FIFO

	// Construct path to the target session's command FIFO
	snprintf(target_session_cmd_fifo_path, sizeof(target_session_cmd_fifo_path),
	         "%s/%s/%s", HEADLESH_SESSIONS_DIR, session_id,
	         SESSION_CMD_FIFO_NAME);

	// 1. Read the command from stdin
	size_t total_bytes_read_stdin = 0;
	ssize_t last_read_size = 0;  // Initialize to avoid uninitialized read in
	                             // `if` condition below for some paths

	// Reading from stdin first
	while (total_bytes_read_stdin < BUFFER_SIZE - 1) {
		last_read_size =
		    read(STDIN_FILENO, client_cmd_payload + total_bytes_read_stdin,
		         BUFFER_SIZE - 1 - total_bytes_read_stdin);
		if (last_read_size == -1) {
			if (errno == EINTR) continue;
			perror("Client: Read from stdin failed");
			exit(EXIT_FAILURE);
		}
		if (last_read_size == 0) {  // EOF
			break;
		}
		total_bytes_read_stdin += last_read_size;
	}
	client_cmd_payload[total_bytes_read_stdin] = '\0';

	// Check if input was truncated: buffer is full, and the last read operation
	// was successful (not EOF or error)
	if (total_bytes_read_stdin == BUFFER_SIZE - 1 && last_read_size > 0) {
		char dummy_buf[1];
		ssize_t peek = read(STDIN_FILENO, dummy_buf, 1);
		if (peek > 0) {
			fprintf(
			    stderr,
			    "Client: Command from stdin too long (exceeds %zu bytes).\n",
			    (size_t)BUFFER_SIZE - 1);
			exit(EXIT_FAILURE);
		} else if (peek == -1 &&
		           errno !=
		               EINTR) {  // EINTR on peek is fine, means we couldn't
			                     // check but won't assume too long.
			perror("Client: Error checking for oversized stdin command");
			exit(EXIT_FAILURE);
		}
		// If peek == 0 (EOF) or peek == -1 && errno == EINTR, command fit
		// exactly or check was interrupted.
	}

	size_t current_cmd_len = total_bytes_read_stdin;
	// An empty command (current_cmd_len == 0) is allowed. Server will handle
	// it.

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

	// 3. Prepare the full message for the server
	// (output_fifo_path\ncommand_payload)
	size_t len_fifo_path = strlen(s_client_out_fifo_path);
	// current_cmd_len is strlen(client_cmd_payload) effectively (length of data
	// read from stdin) Check total length against server's read buffer and our
	// client-side send buffer. total_len_to_send = len_fifo_path + 1 ('\n') +
	// current_cmd_len. This must be < BUFFER_SIZE for server to process
	// correctly.
	if (len_fifo_path + 1 + current_cmd_len >= BUFFER_SIZE) {
		fprintf(stderr,
		        "Client (session %s): Combined FIFO path and command too long "
		        "for server buffer.\n",
		        session_id);
		unlink(
		    s_client_out_fifo_path);  // Manually clean up client's output FIFO
		s_client_out_fifo_created = 0;
		exit(EXIT_FAILURE);
	}
	strcpy(server_full_cmd, s_client_out_fifo_path);
	server_full_cmd[len_fifo_path] = '\n';
	// client_cmd_payload contains the command script read from stdin.
	// current_cmd_len is its length. It's already null-terminated.
	// Use memcpy to copy exactly current_cmd_len bytes of script content.
	memcpy(server_full_cmd + len_fifo_path + 1, client_cmd_payload,
	       current_cmd_len);  // current_cmd_len ensures we don't copy potential
	                          // garbage if payload was null
	size_t total_len_to_send = len_fifo_path + 1 + current_cmd_len;

	// 4. Open the target session's CMD_FIFO for writing
	session_cmd_fifo_fd_client = open(target_session_cmd_fifo_path, O_WRONLY);
	if (session_cmd_fifo_fd_client == -1) {
		if (errno == ENOENT) {
			fprintf(stderr,
			        "Client (session %s): Failed to connect. Is headlesh "
			        "session '%s' running? (FIFO %s not found)\n",
			        session_id, session_id, target_session_cmd_fifo_path);
		} else {
			char err_msg[PATH_MAX + 100];
			snprintf(err_msg, sizeof(err_msg),
			         "Client (session %s): Failed to open command FIFO %s for "
			         "writing",
			         session_id, target_session_cmd_fifo_path);
			perror(err_msg);
		}
		unlink(s_client_out_fifo_path);  // Clean up client's output FIFO
		s_client_out_fifo_created = 0;
		exit(EXIT_FAILURE);
	}

	// 5. Write the full command (output FIFO path + actual command) to the
	// session's CMD_FIFO
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write errors
	ssize_t written =
	    write(session_cmd_fifo_fd_client, server_full_cmd, total_len_to_send);

	if (close(session_cmd_fifo_fd_client) == -1) {
		// perror("Client: Failed to close session command FIFO (after write)");
		// // Minor, non-fatal for client op
	}

	if (written == -1) {
		perror("Client: Failed to write command to session FIFO");
		unlink(s_client_out_fifo_path);  // Clean up client's output FIFO
		s_client_out_fifo_created = 0;
		exit(EXIT_FAILURE);
	}
	if ((size_t)written < total_len_to_send) {
		fprintf(stderr,
		        "Client (session %s): Partial write to session FIFO %s (%zd of "
		        "%zu bytes).\n",
		        session_id, target_session_cmd_fifo_path, written,
		        total_len_to_send);
		unlink(s_client_out_fifo_path);  // Clean up client's output FIFO
		s_client_out_fifo_created = 0;
		exit(EXIT_FAILURE);
	}
	// printf("Client: Command sent to server. Waiting for output on %s...\n",
	// s_client_out_fifo_path);

	// 6. Open client's output FIFO for reading (blocks until server's bash
	// redirects to it)
	out_fifo_fd_client = open(s_client_out_fifo_path, O_RDONLY);
	if (out_fifo_fd_client == -1) {
		perror("Client: Failed to open output FIFO for reading");
		unlink(s_client_out_fifo_path);  // Manually clean up
		s_client_out_fifo_created = 0;
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
	unlink(s_client_out_fifo_path);
	s_client_out_fifo_created = 0;  // Mark as cleaned up
	// printf("\nClient: Command for session %s finished and output FIFO cleaned
	// up.\n", session_id); Restore default signal handlers
	signal(SIGINT, SIG_DFL);
	signal(SIGTERM, SIG_DFL);
}

// Function for the client to send an exit command to a specific session server
void send_exit_command(const char* session_id) {
	char client_out_fifo_path[256];  // Dummy path, not actually used by server
	                                 // for exit
	char server_full_cmd[BUFFER_SIZE];
	int session_cmd_fifo_fd_client;
	char target_session_cmd_fifo_path[PATH_MAX];

	// Construct path to the target session's command FIFO
	snprintf(target_session_cmd_fifo_path, sizeof(target_session_cmd_fifo_path),
	         "%s/%s/%s", HEADLESH_SESSIONS_DIR, session_id,
	         SESSION_CMD_FIFO_NAME);

	// 1. Create a "dummy" client output FIFO path string.
	// The server expects this format for all commands, but won't use the path
	// for an exit command.
	snprintf(client_out_fifo_path, sizeof(client_out_fifo_path),
	         "/tmp/headlesh_exit_dummy_for_session_%s_%d", session_id,
	         getpid());

	// 2. Prepare the full message for the server
	// (dummy_fifo_path\nexit_payload)
	size_t len_fifo_path = strlen(client_out_fifo_path);
	size_t len_exit_payload = strlen(HEADLESH_EXIT_CMD_PAYLOAD);

	if (len_fifo_path + 1 + len_exit_payload >= BUFFER_SIZE) {
		fprintf(stderr,
		        "Client (exit for session %s): Internal error - exit command "
		        "message too long.\n",
		        session_id);
		exit(EXIT_FAILURE);
	}
	strcpy(server_full_cmd, client_out_fifo_path);
	server_full_cmd[len_fifo_path] = '\n';
	memcpy(server_full_cmd + len_fifo_path + 1, HEADLESH_EXIT_CMD_PAYLOAD,
	       len_exit_payload);
	// server_full_cmd[len_fifo_path + 1 + len_exit_payload] = '\0'; //
	// Implicitly null-terminated by buffer size for safety, but length sent is
	// key
	size_t total_len_to_send = len_fifo_path + 1 + len_exit_payload;

	// 3. Open the target session's CMD_FIFO for writing
	session_cmd_fifo_fd_client = open(target_session_cmd_fifo_path, O_WRONLY);
	if (session_cmd_fifo_fd_client == -1) {
		if (errno == ENOENT) {
			fprintf(stderr,
			        "Client (exit for session %s): Failed to connect. Is "
			        "headlesh session '%s' running? (FIFO %s not found)\n",
			        session_id, session_id, target_session_cmd_fifo_path);
		} else {
			char err_msg[PATH_MAX + 100];
			snprintf(err_msg, sizeof(err_msg),
			         "Client (exit for session %s): Failed to open command "
			         "FIFO %s for writing",
			         session_id, target_session_cmd_fifo_path);
			perror(err_msg);
		}
		exit(EXIT_FAILURE);
	}

	// 4. Write the exit command
	signal(SIGPIPE, SIG_IGN);  // Ignore SIGPIPE, check write errors
	ssize_t written =
	    write(session_cmd_fifo_fd_client, server_full_cmd, total_len_to_send);

	if (close(session_cmd_fifo_fd_client) == -1) {
		// perror("Client (exit): Failed to close session command FIFO"); //
		// Minor, non-fatal
	}

	if (written == -1) {
		perror("Client (exit): Failed to write exit command to session FIFO");
		exit(EXIT_FAILURE);
	}
	if ((size_t)written < total_len_to_send) {
		fprintf(stderr,
		        "Client (exit for session %s): Partial write of exit command "
		        "to session FIFO %s (%zd of %zu bytes).\n",
		        session_id, target_session_cmd_fifo_path, written,
		        total_len_to_send);
		exit(EXIT_FAILURE);
	}

	printf("Exit command sent to headlesh session '%s'.\n", session_id);
	exit(EXIT_SUCCESS);
}

void list_sessions_mode() {
	DIR* d;
	struct dirent* dir;
	d = opendir(HEADLESH_SESSIONS_DIR);
	if (!d) {
		if (errno == ENOENT) {  // Base directory doesn't exist -> no sessions
			printf(
			    "No active headlesh sessions found (session directory %s does "
			    "not exist).\n",
			    HEADLESH_SESSIONS_DIR);
			exit(EXIT_SUCCESS);
		}
		perror("list: Failed to open sessions directory");
		exit(EXIT_FAILURE);
	}

	printf("Active headlesh sessions:\n");
	int active_sessions_found = 0;

	while ((dir = readdir(d)) != NULL) {
		// Skip . and .. entries first, as they are not session directories.
		if (strcmp(dir->d_name, ".") == 0 || strcmp(dir->d_name, "..") == 0) {
			continue;
		}

		int is_directory = 0;  // Flag to indicate if the entry is a directory

#if defined(DT_DIR) && defined(DT_UNKNOWN)
		// Method 1: Use d_type if available and the macros DT_DIR/DT_UNKNOWN
		// are defined.
		if (dir->d_type == DT_DIR) {
			is_directory = 1;
		} else if (dir->d_type == DT_UNKNOWN) {
			// If d_type is DT_UNKNOWN, filesystem doesn't tell us the type.
			// Fall back to stat() to determine if it's a directory.
			char path[PATH_MAX];
			snprintf(path, sizeof(path), "%s/%s", HEADLESH_SESSIONS_DIR,
			         dir->d_name);
			struct stat st;
			if (stat(path, &st) == 0) {
				if (S_ISDIR(st.st_mode)) {
					is_directory = 1;
				}
			} else {
				// Optional: Log stat failure. For robust listing, silently skip
				// if stat fails. perror("stat in list_sessions_mode (DT_UNKNOWN
				// fallback)");
				continue;  // Skip this entry if stat fails
			}
		}
		// If dir->d_type is something else (e.g., DT_REG, DT_LNK), it's not a
		// directory for our purposes.
#else
		// Method 2: Fallback if DT_DIR or DT_UNKNOWN are not defined (e.g., on
		// some systems). Always use stat() to determine if it's a directory.
		// This is also hit if struct dirent doesn't have d_type field (less
		// common on modern POSIX).
		char path[PATH_MAX];
		snprintf(path, sizeof(path), "%s/%s", HEADLESH_SESSIONS_DIR,
		         dir->d_name);
		struct stat st;
		if (stat(path, &st) == 0) {
			if (S_ISDIR(st.st_mode)) {
				is_directory = 1;
			}
		} else {
			// Optional: Log stat failure.
			// perror("stat in list_sessions_mode (DT_DIR undefined fallback)");
			continue;  // Skip this entry if stat fails
		}
#endif  // defined(DT_DIR) && defined(DT_UNKNOWN)

		if (is_directory) {
			// This entry is confirmed to be a directory. Process it as a
			// potential session.
			char session_id[NAME_MAX + 1];
			strncpy(session_id, dir->d_name, NAME_MAX);
			session_id[NAME_MAX] = '\0';  // Ensure null termination

			char lock_file_path[PATH_MAX];
			snprintf(lock_file_path, sizeof(lock_file_path), "%s/%s/%s",
			         HEADLESH_SESSIONS_DIR, session_id, SESSION_LOCK_FILE_NAME);

			FILE* lock_fp = fopen(lock_file_path, "r");
			if (lock_fp) {
				pid_t pid = -1;
				if (fscanf(lock_fp, "%d", &pid) == 1) {
					if (pid > 0) {
						// Check if process is active
						if (kill(pid, 0) == 0) {
							printf("- %s (PID: %d)\n", session_id, pid);
							active_sessions_found++;
						} else if (errno == ESRCH) {
							// Process doesn't exist, stale lock file.
							fprintf(stderr,
							        "  (Stale session '%s': PID %d not "
							        "running, lock file: %s)\n",
							        session_id, pid, lock_file_path);
						} else {
							// Other error with kill (e.g. EPERM)
							// Consider it active or status unclear if kill
							// doesn't say ESRCH.
							printf("- %s (PID: %d, status unclear: %s)\n",
							       session_id, pid, strerror(errno));
							active_sessions_found++;
						}
					}
				}  // else: could not read PID from lock file
				fclose(lock_fp);
			}  // else: lock file not found or not readable for this session dir
		}
	}
	closedir(d);

	if (active_sessions_found == 0) {
		printf("No active headlesh sessions found.\n");
	}
	exit(EXIT_SUCCESS);
}

int main(int argc, char* argv[]) {
	if (argc < 2) {
		fprintf(stderr, "Usage: %s <command> [args...]\n", argv[0]);
		fprintf(stderr, "Commands:\n");
		fprintf(stderr,
		        "  create <session_id>                      : Create and start "
		        "a new session daemon.\n");
		fprintf(stderr,
		        "  exec <session_id>                        : Execute command "
		        "(from stdin) in a session.\n");
		fprintf(stderr,
		        "  exit <session_id>                        : Terminate a "
		        "session daemon.\n");
		fprintf(stderr,
		        "  list                                     : List active "
		        "sessions.\n");
		return EXIT_FAILURE;
	}

	const char* command = argv[1];

	if (strcmp(command, "create") == 0) {
		if (argc != 3) {
			fprintf(stderr, "Usage: %s create <session_id>\n", argv[0]);
			return EXIT_FAILURE;
		}
		const char* session_id = argv[2];
		// Basic validation for session_id (e.g., not empty, no slashes)
		if (strlen(session_id) == 0 || strchr(session_id, '/') != NULL) {
			fprintf(
			    stderr,
			    "Error: Invalid session_id. Cannot be empty or contain '/'.\n");
			return EXIT_FAILURE;
		}
		start_server_mode(
		    session_id);  // This function will daemonize and then call exit()
	} else if (strcmp(command, "exec") == 0) {
		if (argc != 3) {
			fprintf(stderr,
			        "Usage: %s exec <session_id> (command read from stdin)\n",
			        argv[0]);
			return EXIT_FAILURE;
		}
		const char* session_id = argv[2];
		exec_client_mode(session_id);
	} else if (strcmp(command, "exit") == 0) {
		if (argc != 3) {
			fprintf(stderr, "Usage: %s exit <session_id>\n", argv[0]);
			return EXIT_FAILURE;
		}
		const char* session_id = argv[2];
		send_exit_command(session_id);
	} else if (strcmp(command, "list") == 0) {
		if (argc != 2) {
			fprintf(stderr, "Usage: %s list\n", argv[0]);
			return EXIT_FAILURE;
		}
		list_sessions_mode();
	} else {
		fprintf(stderr, "Unknown command: %s\n", command);
		// Print usage again
		fprintf(stderr, "Usage: %s <command> [args...]\n", argv[0]);
		fprintf(stderr, "Commands:\n");
		fprintf(stderr, "  create <session_id>\n");
		fprintf(stderr, "  exec <session_id> (command from stdin)\n");
		fprintf(stderr, "  exit <session_id>\n");
		fprintf(stderr, "  list\n");
		return EXIT_FAILURE;
	}

	return EXIT_SUCCESS;  // Should be unreachable for 'create' if successful
}
