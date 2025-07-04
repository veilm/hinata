/*
 * 10.c - A simple fzf-like selector.
 * Reads lines from stdin and allows selecting one with arrow keys.
 * The selected line is printed to stdout.
 * It does not use the alternate screen buffer, drawing at the bottom.
 *
 * Usage:
 *   echo "one\ntwo\nthree" | ./10
 */

#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#define MAX_LINES 4096
#define DISPLAY_HEIGHT 10

static struct termios orig_termios;
static int term_rows, term_cols;
static FILE *tty_fp = NULL;
static int tty_fd = -1;
static int interactive = 0;

static char *lines[MAX_LINES];
static int num_lines = 0;

static int selected_index = 0;
static int scroll_offset = 0;
static int display_height;

void cleanup(void) {
	if (interactive) {
		// Restore cursor to where we started, and clear the menu
		fprintf(tty_fp, "\033[u");
		for (int i = 0; i < display_height; i++) {
			fprintf(tty_fp, "\033[K\n");
		}
		fprintf(tty_fp, "\033[%dA", display_height);
		fprintf(tty_fp, "\033[?25h");  // Show cursor
		fflush(tty_fp);
		tcsetattr(tty_fd, TCSAFLUSH, &orig_termios);
	}

	if (tty_fp != NULL) {
		fclose(tty_fp);
	}

	for (int i = 0; i < num_lines; i++) {
		free(lines[i]);
	}
}

void die(const char *s) {
	// cleanup will be called by exit
	perror(s);
	exit(1);
}

void handle_sig(int sig) {
	// Let atexit handler do the cleanup
	exit(1);
}

void read_input_lines(void) {
	char *line = NULL;
	size_t len = 0;
	ssize_t read;
	while ((read = getline(&line, &len, stdin)) != -1 &&
	       num_lines < MAX_LINES) {
		if (read > 0 && line[read - 1] == '\n') {
			line[read - 1] = '\0';
		}
		lines[num_lines++] = strdup(line);
	}
	free(line);
}

void draw_menu(void) {
	fprintf(tty_fp, "\033[u");  // Restore cursor to start of menu area

	for (int i = 0; i < display_height; i++) {
		fprintf(tty_fp, "\033[K");  // Clear line
		int line_idx = scroll_offset + i;
		if (line_idx < num_lines) {
			if (line_idx == selected_index) {
				fprintf(tty_fp, "▌ \033[7m");
			} else {
				fprintf(tty_fp, "  ");
			}

			int print_len = strlen(lines[line_idx]);
			if (print_len > term_cols - 2) {
				print_len = term_cols - 2;
			}
			fwrite(lines[line_idx], 1, print_len, tty_fp);

			if (line_idx == selected_index) {
				fprintf(tty_fp, "\033[0m");  // Reset attributes
			}
		}
		if (i < display_height - 1) {
			fprintf(tty_fp, "\n\r");
		}
	}
	fflush(tty_fp);
}

void handle_input_loop(void) {
	char buf[16];
	int n;
	while ((n = read(tty_fd, buf, sizeof(buf) - 1)) >= 0) {
		if (n == 0) continue;
		buf[n] = '\0';

		if (buf[0] == '\r') {  // Enter
			return;
		} else if (strcmp(buf, "\033[A") == 0 ||  // Up
		           strcmp(buf, "\033[Z") == 0 ||  // Shift-Tab
		           (n == 1 && buf[0] == 11) ||    // Ctrl-k
		           strcmp(buf, "\033k") == 0) {   // Alt-k
			if (selected_index > 0) {
				selected_index--;
				if (selected_index < scroll_offset) {
					scroll_offset = selected_index;
				}
				draw_menu();
			}
		} else if (strcmp(buf, "\033[B") == 0 ||  // Down
		           (n == 1 && buf[0] == '\t') ||  // Tab
		           (n == 1 && buf[0] == 10) ||    // Ctrl-j
		           strcmp(buf, "\033j") == 0) {   // Alt-j
			if (selected_index < num_lines - 1) {
				selected_index++;
				if (selected_index >= scroll_offset + display_height) {
					scroll_offset = selected_index - display_height + 1;
				}
				draw_menu();
			}
		} else if ((n == 1 &&
		            (buf[0] == 3 || buf[0] == 4)) ||  // Ctrl-C, Ctrl-D
		           strcmp(buf, "\033") == 0) {        // Escape
			exit(1);
		}
	}
}

int main(int argc, char *argv[]) {
	read_input_lines();

	if (num_lines == 0) {
		return 0;
	}

	tty_fp = fopen("/dev/tty", "r+");
	if (tty_fp == NULL) {
		// Not an interactive terminal, just print first line
		printf("%s\n", lines[0]);
		for (int i = 0; i < num_lines; i++) free(lines[i]);
		return 0;
	}
	tty_fd = fileno(tty_fp);
	interactive = 1;

	atexit(cleanup);
	signal(SIGINT, handle_sig);
	signal(SIGTERM, handle_sig);

	struct termios raw;
	struct winsize ws;

	if (tcgetattr(tty_fd, &orig_termios) == -1) die("tcgetattr");

	raw = orig_termios;
	raw.c_lflag &= ~(ECHO | ICANON | IEXTEN | ISIG);
	raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
	raw.c_cflag &= ~(CSIZE | PARENB);
	raw.c_cflag |= CS8;
	raw.c_oflag &= ~(OPOST);
	raw.c_cc[VMIN] = 0;
	raw.c_cc[VTIME] = 1;  // 0.1s timeout

	if (tcsetattr(tty_fd, TCSAFLUSH, &raw) == -1) die("tcsetattr");

	if (ioctl(tty_fd, TIOCGWINSZ, &ws) == -1) {
		term_rows = 24;
		term_cols = 80;
	} else {
		term_rows = ws.ws_row;
		term_cols = ws.ws_col;
	}

	display_height = num_lines < DISPLAY_HEIGHT ? num_lines : DISPLAY_HEIGHT;
	if (term_rows < display_height + 1) {
		fprintf(stderr, "Terminal too small.\n");
		exit(1);
	}

	for (int i = 0; i < display_height; i++) {
		fprintf(tty_fp, "\n");
	}
	fprintf(tty_fp, "\033[%dA", display_height);
	fprintf(tty_fp, "\033[s");     // Save cursor
	fprintf(tty_fp, "\033[?25l");  // Hide cursor
	fflush(tty_fp);

	draw_menu();
	handle_input_loop();

	// cleanup will be called by atexit

	// Print selected line to original stdout.
	printf("%s\n", lines[selected_index]);

	return 0;
}
