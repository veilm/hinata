/*
 * 10.c - A simple fzf-like line selector.
 * Reads lines from stdin, displays a navigable menu,
 * and prints the selected line to stdout.
 *
 * Usage: some_command | ./10
 */

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#define UI_HEIGHT 10

/* Globals */
static struct termios orig_termios;
static char **lines = NULL;
static int num_lines = 0;
static int capacity = 0;
static int selection = 0;
static int scroll_offset = 0;
static int term_rows, term_cols;
static int ui_height = 0;

/* Function prototypes */
static void restore_terminal(void);
static void setup_terminal(void);
static void read_input_lines(void);
static void run_ui(void);

static void die(const char *s) {
	perror(s);
	exit(1);
}

static void restore_terminal(void) {
	tcsetattr(STDIN_FILENO, TCSAFLUSH, &orig_termios);
}

static void setup_terminal(void) {
	if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO)) {
		fprintf(stderr, "This program must be run in a terminal.\n");
		exit(1);
	}

	if (tcgetattr(STDIN_FILENO, &orig_termios) == -1) die("tcgetattr");
	atexit(restore_terminal);

	struct termios raw = orig_termios;
	raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
	raw.c_oflag &= ~(OPOST);
	raw.c_cflag |= (CS8);
	raw.c_lflag &= ~(ECHO | ICANON | IEXTEN | ISIG);
	raw.c_cc[VMIN] = 0;
	raw.c_cc[VTIME] = 1;

	if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) == -1) die("tcsetattr");
}

static void get_terminal_size(void) {
	struct winsize ws;
	if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == -1 || ws.ws_col == 0) {
		term_rows = 24;
		term_cols = 80;
	} else {
		term_rows = ws.ws_row;
		term_cols = ws.ws_col;
	}
}

static void read_input_lines(void) {
	char *line = NULL;
	size_t len = 0;
	ssize_t read;

	while ((read = getline(&line, &len, stdin)) != -1) {
		if (num_lines >= capacity) {
			capacity = capacity == 0 ? 8 : capacity * 2;
			lines = realloc(lines, capacity * sizeof(char *));
			if (!lines) die("realloc");
		}
		if (read > 0 && line[read - 1] == '\n') {
			line[read - 1] = '\0';
		}
		lines[num_lines++] = strdup(line);
	}
	free(line);
}

static void run_ui(void) {
	get_terminal_size();
	ui_height = num_lines < UI_HEIGHT ? num_lines : UI_HEIGHT;
	if (ui_height >= term_rows) ui_height = term_rows - 1;

	/* Make space for the UI */
	for (int i = 0; i < ui_height; i++) {
		printf("\n");
	}

	int first_draw = 1;
	while (1) {
		if (first_draw) {
			printf("\033[%dA", ui_height);
			first_draw = 0;
		} else {
			printf("\033[%dA", ui_height - 1);
		}

		for (int i = 0; i < ui_height; i++) {
			printf("\033[K");
			int line_idx = scroll_offset + i;
			if (line_idx < num_lines) {
				if (line_idx == selection) {
					printf("\033[7m> %.*s\033[m", term_cols - 2,
					       lines[line_idx]);
				} else {
					printf("  %.*s", term_cols - 2, lines[line_idx]);
				}
			}
			if (i < ui_height - 1) printf("\n");
		}
		fflush(stdout);

		char c;
		int nread = read(STDIN_FILENO, &c, 1);
		if (nread == -1 && errno != EAGAIN) die("read");

		if (nread == 1) {
			if (c == '\x1b') {
				char seq[3];
				if (read(STDIN_FILENO, &seq[0], 1) != 1) continue;
				if (read(STDIN_FILENO, &seq[1], 1) != 1) continue;

				if (seq[0] == '[') {
					if (seq[1] == 'A') { /* Up arrow */
						if (selection > 0) selection--;
					} else if (seq[1] == 'B') { /* Down arrow */
						if (selection < num_lines - 1) selection++;
					}
				}
				if (selection < scroll_offset) {
					scroll_offset = selection;
				} else if (selection >= scroll_offset + ui_height) {
					scroll_offset = selection - ui_height + 1;
				}
			} else if (c == '\r' || c == '\n') {
				break;
			} else if (c == 3 || c == 4) { /* Ctrl-C or Ctrl-D */
				selection = -1;
				break;
			}
		}
	}

	/* Clear UI */
	if (first_draw) { /* Nothing was drawn */
		printf("\033[%dA", ui_height);
	} else {
		printf("\033[%dA", ui_height - 1);
	}
	printf("\033[J"); /* Clear from cursor to end of screen */
}

int main(int argc, char *argv[]) {
	read_input_lines();

	if (num_lines > 0) {
		setup_terminal();
		run_ui();
	}

	if (selection >= 0 && selection < num_lines) {
		printf("%s\n", lines[selection]);
	}

	for (int i = 0; i < num_lines; i++) {
		free(lines[i]);
	}
	free(lines);

	return selection >= 0 ? 0 : 1;
}