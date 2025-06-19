/*
 * mini_tmux.c - A simplified tmux clone that creates a single pane
 * in the bottom 20 lines of the screen and runs a command inside it.
 *
 * Based on tmux architecture:
 * - Creates a PTY pair for the nvim process
 * - Implements a simplified control sequence parser
 * - Maintains a virtual screen (grid) for the pane
 * - Handles terminal I/O and rendering
 */

#include <errno.h>
#include <fcntl.h>
#include <pty.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

#define PANE_HEIGHT 20
#define MAX_COLS 512
#define MAX_ROWS 512

/* Cell attributes */
#define ATTR_BOLD (1 << 0)
#define ATTR_UNDERLINE (1 << 1)
#define ATTR_REVERSE (1 << 2)

/* Colour flags */
#define COLOUR_FLAG_256 (1 << 8)
#define COLOUR_FLAG_RGB (1 << 9)

static inline int colour_is_rgb(int c) { return (c & COLOUR_FLAG_RGB); }
static inline int colour_is_256(int c) { return (c & COLOUR_FLAG_256); }

static inline int colour_join_rgb(unsigned char r, unsigned char g,
                                  unsigned char b) {
	return COLOUR_FLAG_RGB | (r << 16) | (g << 8) | b;
}

static inline void colour_split_rgb(int c, unsigned char *r, unsigned char *g,
                                    unsigned char *b) {
	*r = (c >> 16) & 0xff;
	*g = (c >> 8) & 0xff;
	*b = c & 0xff;
}

#define UTF8_MAX_SIZE 4

/* UTF-8 character data */
struct utf8_char {
	char data[UTF8_MAX_SIZE];
	unsigned char size;
};

/* Virtual grid cell structure */
struct grid_cell {
	struct utf8_char uc;
	int fg;
	int bg;
	int attr;
};

/* Virtual screen grid */
struct grid {
	struct grid_cell cells[MAX_ROWS][MAX_COLS];
	int sx, sy; /* screen dimensions */
	int cx, cy; /* cursor position */
	int scroll_top;
	int scroll_bottom;
};

/* Input parser states */
enum input_state {
	INPUT_GROUND,
	INPUT_ESCAPE,
	INPUT_CSI_ENTRY,
	INPUT_CSI_PARAM,
	INPUT_CSI_INTERMEDIATE,
	INPUT_CSI_FINAL,
	INPUT_OSC_STRING,
	INPUT_DCS_STRING
};

/* Input parser context */
struct input_ctx {
	enum input_state state;
	char param_buf[64];
	int param_len;
	char intermediate_buf[8];
	int intermediate_len;
	int private_marker; /* Set if sequence starts with ? */
	struct grid *grid;
	int cur_fg;
	int cur_bg;
	int cur_attr;

	/* For UTF-8 decoding */
	struct utf8_char utf8c;
	int utf8_started; /* 0 if not in a sequence, otherwise total length */
};

/* Global state */
static struct grid pane_grid;
static struct input_ctx input_parser;
static struct termios orig_termios;
static int master_fd, slave_fd;
static pid_t child_pid;
static int term_rows, term_cols;
static int pane_start_row;

/* Function prototypes */
static void setup_terminal(void);
static void restore_terminal(void);
static int create_pty(void);
static void spawn_child(char *argv[]);
static void handle_input(void);
static void parse_control_sequence(const char *buf, int len);
static void render_pane(void);
static void move_cursor(int row, int col);
static void clear_screen(void);
static void clear_pane_area(void);
static void signal_handler(int sig);
static void resize_handler(void);

/* Initialize the virtual grid */
static void init_grid(struct grid *g, int sx, int sy) {
	int x, y;

	g->sx = sx;
	g->sy = sy;
	g->cx = 0;
	g->cy = 0;
	g->scroll_top = 0;
	g->scroll_bottom = sy - 1;

	for (y = 0; y < sy; y++) {
		for (x = 0; x < sx; x++) {
			g->cells[y][x].uc.data[0] = ' ';
			g->cells[y][x].uc.size = 1;
			g->cells[y][x].fg = 7;
			g->cells[y][x].bg = 0;
			g->cells[y][x].attr = 0;
		}
	}
}

static void grid_scroll_up(struct grid *g, int n, int fg, int bg, int attr) {
	if (n <= 0) return;
	if (g->scroll_top >= g->scroll_bottom) return;
	if (n > g->scroll_bottom - g->scroll_top + 1) {
		n = g->scroll_bottom - g->scroll_top + 1;
	}

	if (g->scroll_top + n <= g->scroll_bottom) {
		memmove(
		    &g->cells[g->scroll_top], &g->cells[g->scroll_top + n],
		    (g->scroll_bottom - g->scroll_top - n + 1) * sizeof(g->cells[0]));
	}

	for (int y = g->scroll_bottom - n + 1; y <= g->scroll_bottom; y++) {
		for (int x = 0; x < g->sx; x++) {
			g->cells[y][x].uc.data[0] = ' ';
			g->cells[y][x].uc.size = 1;
			g->cells[y][x].fg = fg;
			g->cells[y][x].bg = bg;
			g->cells[y][x].attr = attr;
		}
	}
}

static void grid_scroll_down(struct grid *g, int n, int fg, int bg, int attr) {
	if (n <= 0) return;
	if (g->scroll_top >= g->scroll_bottom) return;
	if (n > g->scroll_bottom - g->scroll_top + 1) {
		n = g->scroll_bottom - g->scroll_top + 1;
	}

	if (g->scroll_top + n <= g->scroll_bottom) {
		memmove(
		    &g->cells[g->scroll_top + n], &g->cells[g->scroll_top],
		    (g->scroll_bottom - g->scroll_top - n + 1) * sizeof(g->cells[0]));
	}

	for (int y = g->scroll_top; y < g->scroll_top + n; y++) {
		for (int x = 0; x < g->sx; x++) {
			g->cells[y][x].uc.data[0] = ' ';
			g->cells[y][x].uc.size = 1;
			g->cells[y][x].fg = fg;
			g->cells[y][x].bg = bg;
			g->cells[y][x].attr = attr;
		}
	}
}

/* Set up terminal for raw mode */
static void setup_terminal(void) {
	struct termios raw;
	struct winsize ws;

	if (tcgetattr(STDIN_FILENO, &orig_termios) == -1) {
		perror("tcgetattr");
		exit(1);
	}

	raw = orig_termios;
	raw.c_lflag &= ~(ECHO | ICANON | IEXTEN | ISIG);
	raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
	raw.c_cflag |= CS8;
	raw.c_oflag &= ~OPOST;
	raw.c_cc[VMIN] = 0;
	raw.c_cc[VTIME] = 1;

	if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) == -1) {
		perror("tcsetattr");
		exit(1);
	}

	/* Get terminal size */
	if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == -1) {
		perror("ioctl TIOCGWINSZ");
		exit(1);
	}

	term_rows = ws.ws_row;
	term_cols = ws.ws_col;
	pane_start_row = term_rows - PANE_HEIGHT;

	/* Initialize the pane grid */
	init_grid(&pane_grid, term_cols, PANE_HEIGHT);

	/* Clear screen and position pane */
	clear_screen();
	printf("\033[%d;1H", pane_start_row + 1); /* Move to pane start */
	printf("\033[7m"); /* Reverse video for pane border */
	for (int i = 0; i < term_cols; i++) {
		printf("-");
	}
	printf("\033[0m"); /* Reset attributes */
	fflush(stdout);
}

static void restore_terminal(void) {
	tcsetattr(STDIN_FILENO, TCSAFLUSH, &orig_termios);
	clear_screen();
	move_cursor(1, 1);
}

/* Create PTY pair */
static int create_pty(void) {
	struct winsize ws;

	ws.ws_row = PANE_HEIGHT - 1; /* Leave room for border */
	ws.ws_col = term_cols;
	ws.ws_xpixel = 0;
	ws.ws_ypixel = 0;

	if (openpty(&master_fd, &slave_fd, NULL, NULL, &ws) == -1) {
		perror("openpty");
		return -1;
	}

	return 0;
}

/* Spawn child process */
static void spawn_child(char *argv[]) {
	child_pid = fork();
	if (child_pid == -1) {
		perror("fork");
		exit(1);
	}

	if (child_pid == 0) {
		/* Child process */
		close(master_fd);

		/* Set up controlling terminal */
		setsid();
		if (ioctl(slave_fd, TIOCSCTTY, NULL) == -1) {
			perror("ioctl TIOCSCTTY");
			exit(1);
		}

		/* Redirect stdio */
		dup2(slave_fd, STDIN_FILENO);
		dup2(slave_fd, STDOUT_FILENO);
		dup2(slave_fd, STDERR_FILENO);
		close(slave_fd);

		/* Set TERM environment */
		setenv("TERM", "xterm-256color", 1);

		/* Execute command */
		execvp(argv[0], argv);
		perror("execvp");
		exit(1);
	}

	/* Parent process */
	close(slave_fd);
}

/* Move cursor to specific position */
static void move_cursor(int row, int col) { printf("\033[%d;%dH", row, col); }

/* Clear entire screen */
static void clear_screen(void) {
	printf("\033[2J");
	printf("\033[H");
}

/* Clear only the pane area */
static void clear_pane_area(void) {
	int row;

	for (row = pane_start_row + 1; row < term_rows; row++) {
		move_cursor(row + 1, 1);
		printf("\033[K"); /* Clear line */
	}
}

/* Parse control sequences from child process */
static void parse_control_sequence(const char *buf, int len) {
	struct input_ctx *ctx = &input_parser;
	int i;

	for (i = 0; i < len; i++) {
		unsigned char ch = buf[i];

		if (ctx->utf8_started) {
			if ((ch & 0xC0) == 0x80) { /* continuation byte */
				if (ctx->utf8c.size < UTF8_MAX_SIZE) {
					ctx->utf8c.data[ctx->utf8c.size++] = ch;
				}
				if (ctx->utf8c.size >= ctx->utf8_started) {
					/* Character complete */
					if (ctx->grid->cx < ctx->grid->sx &&
					    ctx->grid->cy < ctx->grid->sy) {
						struct grid_cell *cell =
						    &ctx->grid->cells[ctx->grid->cy][ctx->grid->cx];
						memcpy(&cell->uc, &ctx->utf8c,
						       sizeof(struct utf8_char));
						cell->fg = ctx->cur_fg;
						cell->bg = ctx->cur_bg;
						cell->attr = ctx->cur_attr;
						ctx->grid->cx++;
						if (ctx->grid->cx >= ctx->grid->sx) {
							ctx->grid->cx = 0;
							ctx->grid->cy++;
							if (ctx->grid->cy >= ctx->grid->sy) {
								ctx->grid->cy = ctx->grid->sy - 1;
							}
						}
					}
					ctx->utf8_started = 0;
				}
				continue; /* byte consumed */
			} else {
				/* invalid sequence */
				ctx->utf8_started = 0;
			}
		}

		/* any non-ground state resets utf8 */
		if (ctx->state != INPUT_GROUND) ctx->utf8_started = 0;

		switch (ctx->state) {
			case INPUT_GROUND:
				if (ch == '\033') {
					ctx->state = INPUT_ESCAPE;
				} else if (ch == '\n') {
					if (ctx->grid->cy == ctx->grid->scroll_bottom) {
						grid_scroll_up(ctx->grid, 1, 7, ctx->cur_bg, 0);
					} else {
						ctx->grid->cy++;
						if (ctx->grid->cy >= ctx->grid->sy) {
							ctx->grid->cy = ctx->grid->sy - 1;
						}
					}
				} else if (ch == '\r') {
					ctx->grid->cx = 0;
				} else if (ch == '\b') {
					/* Backspace */
					if (ctx->grid->cx > 0) {
						ctx->grid->cx--;
					}
				} else if (ch == '\t') {
					/* Tab - simple 8-space implementation */
					ctx->grid->cx = (ctx->grid->cx + 8) & ~7;
					if (ctx->grid->cx >= ctx->grid->sx) {
						ctx->grid->cx = 0;
						ctx->grid->cy++;
						if (ctx->grid->cy >= ctx->grid->sy) {
							ctx->grid->cy = ctx->grid->sy - 1;
						}
					}
				} else if (ch >= ' ' && ch <= '~') {
					/* Printable ASCII character */
					if (ctx->grid->cx < ctx->grid->sx &&
					    ctx->grid->cy < ctx->grid->sy) {
						struct grid_cell *cell =
						    &ctx->grid->cells[ctx->grid->cy][ctx->grid->cx];
						cell->uc.data[0] = ch;
						cell->uc.size = 1;
						cell->fg = ctx->cur_fg;
						cell->bg = ctx->cur_bg;
						cell->attr = ctx->cur_attr;
						ctx->grid->cx++;
						if (ctx->grid->cx >= ctx->grid->sx) {
							ctx->grid->cx = 0;
							ctx->grid->cy++;
							if (ctx->grid->cy >= ctx->grid->sy) {
								ctx->grid->cy = ctx->grid->sy - 1;
							}
						}
					}
				} else if (ch >= 0xc2 && ch <= 0xf4) {
					/* Start of a UTF-8 sequence */
					memset(&ctx->utf8c, 0, sizeof(ctx->utf8c));
					ctx->utf8c.data[0] = ch;
					ctx->utf8c.size = 1;
					if (ch <= 0xdf)
						ctx->utf8_started = 2;
					else if (ch <= 0xef)
						ctx->utf8_started = 3;
					else
						ctx->utf8_started = 4;
				}
				break;

			case INPUT_ESCAPE:
				if (ch == '[') {
					/* CSI sequence */
					ctx->state = INPUT_CSI_ENTRY;
					ctx->param_len = 0;
					ctx->intermediate_len = 0;
					ctx->private_marker = 0;
				} else if (ch == ']') {
					/* OSC sequence */
					ctx->state = INPUT_OSC_STRING;
				} else if (ch == 'P') {
					/* DCS sequence */
					ctx->state = INPUT_DCS_STRING;
				} else if (ch >= 0x30 && ch <= 0x7E) {
					/* Two-character escape sequence - consume and return to
					 * ground */
					ctx->state = INPUT_GROUND;
				} else if (ch >= 0x20 && ch <= 0x2F) {
					/* Intermediate character - stay in escape mode for one more
					 * char */
					/* Next character will be final */
				} else {
					/* Invalid or incomplete - return to ground */
					ctx->state = INPUT_GROUND;
				}
				break;

			case INPUT_CSI_ENTRY:
				if (ch == '?') {
					/* Private mode marker */
					ctx->private_marker = 1;
					ctx->state = INPUT_CSI_PARAM;
				} else if (ch >= '0' && ch <= '9') {
					if (ctx->param_len < sizeof(ctx->param_buf) - 1) {
						ctx->param_buf[ctx->param_len++] = ch;
					}
					ctx->state = INPUT_CSI_PARAM;
				} else if (ch == ';') {
					if (ctx->param_len < sizeof(ctx->param_buf) - 1) {
						ctx->param_buf[ctx->param_len++] = ch;
					}
					ctx->state = INPUT_CSI_PARAM;
				} else if (ch >= 0x20 && ch <= 0x2F) {
					/* Intermediate characters */
					if (ctx->intermediate_len <
					    sizeof(ctx->intermediate_buf) - 1) {
						ctx->intermediate_buf[ctx->intermediate_len++] = ch;
					}
					ctx->state = INPUT_CSI_INTERMEDIATE;
				} else if (ch >= 0x40 && ch <= 0x7E) {
					/* Final character */
					ctx->state = INPUT_CSI_FINAL;
					goto handle_csi_final;
				} else {
					/* Invalid - return to ground */
					ctx->state = INPUT_GROUND;
				}
				break;

			case INPUT_CSI_PARAM:
				if (ch >= '0' && ch <= '9') {
					if (ctx->param_len < sizeof(ctx->param_buf) - 1) {
						ctx->param_buf[ctx->param_len++] = ch;
					}
				} else if (ch == ';') {
					if (ctx->param_len < sizeof(ctx->param_buf) - 1) {
						ctx->param_buf[ctx->param_len++] = ch;
					}
				} else if (ch >= 0x20 && ch <= 0x2F) {
					/* Intermediate characters */
					if (ctx->intermediate_len <
					    sizeof(ctx->intermediate_buf) - 1) {
						ctx->intermediate_buf[ctx->intermediate_len++] = ch;
					}
					ctx->state = INPUT_CSI_INTERMEDIATE;
				} else if (ch >= 0x40 && ch <= 0x7E) {
					/* Final character */
					ctx->state = INPUT_CSI_FINAL;
					goto handle_csi_final;
				} else {
					/* Invalid - return to ground */
					ctx->state = INPUT_GROUND;
				}
				break;

			case INPUT_CSI_INTERMEDIATE:
				if (ch >= 0x20 && ch <= 0x2F) {
					/* More intermediate characters */
					if (ctx->intermediate_len <
					    sizeof(ctx->intermediate_buf) - 1) {
						ctx->intermediate_buf[ctx->intermediate_len++] = ch;
					}
				} else if (ch >= 0x40 && ch <= 0x7E) {
					/* Final character */
					ctx->state = INPUT_CSI_FINAL;
					goto handle_csi_final;
				} else {
					/* Invalid - return to ground */
					ctx->state = INPUT_GROUND;
				}
				break;

			case INPUT_CSI_FINAL:
			handle_csi_final:
				/* Null terminate parameters and intermediates */
				ctx->param_buf[ctx->param_len] = '\0';
				ctx->intermediate_buf[ctx->intermediate_len] = '\0';

				/* Handle the specific sequences we care about for display */
				if (!ctx->private_marker && ctx->intermediate_len == 0) {
					switch (ch) {
						case 'H':
						case 'f':
							/* Cursor position */
							if (ctx->param_len > 0) {
								int row = 1, col = 1;
								sscanf(ctx->param_buf, "%d;%d", &row, &col);
								ctx->grid->cy = row - 1;
								ctx->grid->cx = col - 1;
								if (ctx->grid->cy < 0) ctx->grid->cy = 0;
								if (ctx->grid->cx < 0) ctx->grid->cx = 0;
								if (ctx->grid->cy >= ctx->grid->sy)
									ctx->grid->cy = ctx->grid->sy - 1;
								if (ctx->grid->cx >= ctx->grid->sx)
									ctx->grid->cx = ctx->grid->sx - 1;
							} else {
								ctx->grid->cy = 0;
								ctx->grid->cx = 0;
							}
							break;

						case 'J': { /* ED - Erase in Display */
							int n = 0;
							if (ctx->param_len > 0) n = atoi(ctx->param_buf);
							int y, x;
							int fg = 7, bg = ctx->cur_bg, attr = 0;
							switch (n) {
								case 0: /* from cursor to end of screen */
									for (x = ctx->grid->cx; x < ctx->grid->sx;
									     x++) {
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.data[0] = ' ';
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.size = 1;
										ctx->grid->cells[ctx->grid->cy][x].fg =
										    fg;
										ctx->grid->cells[ctx->grid->cy][x].bg =
										    bg;
										ctx->grid->cells[ctx->grid->cy][x]
										    .attr = attr;
									}
									for (y = ctx->grid->cy + 1;
									     y < ctx->grid->sy; y++) {
										for (x = 0; x < ctx->grid->sx; x++) {
											ctx->grid->cells[y][x].uc.data[0] =
											    ' ';
											ctx->grid->cells[y][x].uc.size = 1;
											ctx->grid->cells[y][x].fg = fg;
											ctx->grid->cells[y][x].bg = bg;
											ctx->grid->cells[y][x].attr = attr;
										}
									}
									break;
								case 1: /* from cursor to beginning of screen */
									for (y = 0; y < ctx->grid->cy; y++) {
										for (x = 0; x < ctx->grid->sx; x++) {
											ctx->grid->cells[y][x].uc.data[0] =
											    ' ';
											ctx->grid->cells[y][x].uc.size = 1;
											ctx->grid->cells[y][x].fg = fg;
											ctx->grid->cells[y][x].bg = bg;
											ctx->grid->cells[y][x].attr = attr;
										}
									}
									for (x = 0; x <= ctx->grid->cx; x++) {
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.data[0] = ' ';
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.size = 1;
										ctx->grid->cells[ctx->grid->cy][x].fg =
										    fg;
										ctx->grid->cells[ctx->grid->cy][x].bg =
										    bg;
										ctx->grid->cells[ctx->grid->cy][x]
										    .attr = attr;
									}
									break;
								case 2: /* entire screen */
								case 3: /* entire screen + scrollback. we don't
								           have scrollback */
									init_grid(ctx->grid, ctx->grid->sx,
									          ctx->grid->sy);
									break;
							}
							break;
						}

						case 'K': { /* EL - Erase in Line */
							int n = 0;
							if (ctx->param_len > 0) n = atoi(ctx->param_buf);
							int x;
							int fg = 7, bg = ctx->cur_bg, attr = 0;
							switch (n) {
								case 0: /* from cursor to end of line */
									for (x = ctx->grid->cx; x < ctx->grid->sx;
									     x++) {
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.data[0] = ' ';
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.size = 1;
										ctx->grid->cells[ctx->grid->cy][x].fg =
										    fg;
										ctx->grid->cells[ctx->grid->cy][x].bg =
										    bg;
										ctx->grid->cells[ctx->grid->cy][x]
										    .attr = attr;
									}
									break;
								case 1: /* from cursor to beginning of line */
									for (x = 0; x <= ctx->grid->cx; x++) {
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.data[0] = ' ';
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.size = 1;
										ctx->grid->cells[ctx->grid->cy][x].fg =
										    fg;
										ctx->grid->cells[ctx->grid->cy][x].bg =
										    bg;
										ctx->grid->cells[ctx->grid->cy][x]
										    .attr = attr;
									}
									break;
								case 2: /* entire line */
									for (x = 0; x < ctx->grid->sx; x++) {
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.data[0] = ' ';
										ctx->grid->cells[ctx->grid->cy][x]
										    .uc.size = 1;
										ctx->grid->cells[ctx->grid->cy][x].fg =
										    fg;
										ctx->grid->cells[ctx->grid->cy][x].bg =
										    bg;
										ctx->grid->cells[ctx->grid->cy][x]
										    .attr = attr;
									}
									break;
							}
							break;
						}

						case 'A':
							/* Cursor up */
							if (ctx->param_len > 0) {
								int count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
								ctx->grid->cy -= count;
								if (ctx->grid->cy < 0) ctx->grid->cy = 0;
							} else {
								if (ctx->grid->cy > 0) ctx->grid->cy--;
							}
							break;

						case 'B':
							/* Cursor down */
							if (ctx->param_len > 0) {
								int count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
								ctx->grid->cy += count;
								if (ctx->grid->cy >= ctx->grid->sy)
									ctx->grid->cy = ctx->grid->sy - 1;
							} else {
								if (ctx->grid->cy < ctx->grid->sy - 1)
									ctx->grid->cy++;
							}
							break;

						case 'C':
							/* Cursor right */
							if (ctx->param_len > 0) {
								int count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
								ctx->grid->cx += count;
								if (ctx->grid->cx >= ctx->grid->sx)
									ctx->grid->cx = ctx->grid->sx - 1;
							} else {
								if (ctx->grid->cx < ctx->grid->sx - 1)
									ctx->grid->cx++;
							}
							break;

						case 'D':
							/* Cursor left */
							if (ctx->param_len > 0) {
								int count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
								ctx->grid->cx -= count;
								if (ctx->grid->cx < 0) ctx->grid->cx = 0;
							} else {
								if (ctx->grid->cx > 0) ctx->grid->cx--;
							}
							break;

						case '@': { /* ICH - Insert Characters */
							int count = 1;
							if (ctx->param_len > 0) {
								count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
							}
							struct grid *g = ctx->grid;
							int y = g->cy;
							if (count > g->sx - g->cx) {
								count = g->sx - g->cx;
							}
							if (count <= 0) break;
							memmove(&g->cells[y][g->cx + count],
							        &g->cells[y][g->cx],
							        (g->sx - g->cx - count) *
							            sizeof(struct grid_cell));
							for (int x = g->cx; x < g->cx + count; x++) {
								g->cells[y][x].uc.data[0] = ' ';
								g->cells[y][x].uc.size = 1;
								g->cells[y][x].fg = 7;
								g->cells[y][x].bg = ctx->cur_bg;
								g->cells[y][x].attr = 0;
							}
							break;
						}
						case 'L': { /* IL - Insert Lines */
							int count = 1;
							if (ctx->param_len > 0) {
								count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
							}
							struct grid *g = ctx->grid;
							if (g->cy < g->scroll_top ||
							    g->cy > g->scroll_bottom)
								break;
							if (count > g->scroll_bottom - g->cy + 1)
								count = g->scroll_bottom - g->cy + 1;

							for (int y = g->scroll_bottom - count; y >= g->cy;
							     y--)
								memcpy(&g->cells[y + count], &g->cells[y],
								       sizeof(g->cells[0]));

							for (int y = g->cy; y < g->cy + count; y++) {
								for (int x = 0; x < g->sx; x++) {
									g->cells[y][x].uc.data[0] = ' ';
									g->cells[y][x].uc.size = 1;
									g->cells[y][x].fg = 7;
									g->cells[y][x].bg = ctx->cur_bg;
									g->cells[y][x].attr = 0;
								}
							}
							break;
						}
						case 'M': { /* DL - Delete Lines */
							int count = 1;
							if (ctx->param_len > 0) {
								count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
							}
							struct grid *g = ctx->grid;
							if (g->cy < g->scroll_top ||
							    g->cy > g->scroll_bottom)
								break;

							if (count > g->scroll_bottom - g->cy + 1)
								count = g->scroll_bottom - g->cy + 1;

							for (int y = g->cy; y <= g->scroll_bottom - count;
							     y++)
								memcpy(&g->cells[y], &g->cells[y + count],
								       sizeof(g->cells[0]));

							for (int y = g->scroll_bottom - count + 1;
							     y <= g->scroll_bottom; y++) {
								for (int x = 0; x < g->sx; x++) {
									g->cells[y][x].uc.data[0] = ' ';
									g->cells[y][x].uc.size = 1;
									g->cells[y][x].fg = 7;
									g->cells[y][x].bg = ctx->cur_bg;
									g->cells[y][x].attr = 0;
								}
							}
							break;
						}
						case 'P': { /* DCH - Delete Characters */
							int count = 1;
							if (ctx->param_len > 0) {
								count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
							}
							struct grid *g = ctx->grid;
							int y = g->cy;
							if (count > g->sx - g->cx) {
								count = g->sx - g->cx;
							}
							if (count <= 0) break;
							memmove(&g->cells[y][g->cx],
							        &g->cells[y][g->cx + count],
							        (g->sx - g->cx - count) *
							            sizeof(struct grid_cell));
							for (int x = g->sx - count; x < g->sx; x++) {
								g->cells[y][x].uc.data[0] = ' ';
								g->cells[y][x].uc.size = 1;
								g->cells[y][x].fg = 7;
								g->cells[y][x].bg = ctx->cur_bg;
								g->cells[y][x].attr = 0;
							}
							break;
						}
						case 'S': { /* SU - Scroll Up */
							int count = 1;
							if (ctx->param_len > 0) {
								count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
							}
							grid_scroll_up(ctx->grid, count, 7, ctx->cur_bg, 0);
							break;
						}
						case 'T': { /* SD - Scroll Down */
							int count = 1;
							if (ctx->param_len > 0) {
								count = atoi(ctx->param_buf);
								if (count == 0) count = 1;
							}
							grid_scroll_down(ctx->grid, count, 7, ctx->cur_bg,
							                 0);
							break;
						}
						/* ALL other CSI sequences - just consume them */
						case 'E':
						case 'F':
						case 'G':
						case 'I':
						case 'X':
						case 'Z':
						case '`':
						case 'a':
						case 'b':
						case 'c':
						case 'd':
						case 'e':
						case 'g':
						case 'h':
						case 'i':
						case 'j':
						case 'k':
						case 'l':
						case 'n':
						case 'o':
						case 'm': { /* SGR - Select Graphic Rendition */
							if (ctx->param_len ==
							    0) {  // ESC[m is same as ESC[0m
								ctx->cur_attr = 0;
								ctx->cur_fg = 7;
								ctx->cur_bg = 0;
								break;
							}

							char params[sizeof(ctx->param_buf) + 1];
							memcpy(params, ctx->param_buf, ctx->param_len);
							params[ctx->param_len] = '\0';

							char *p = params;
							char *token;

							while ((token = strsep(&p, ";")) != NULL) {
								int n = 0;
								if (*token != '\0') {
									n = atoi(token);
								}

								switch (n) {
									case 0:
										ctx->cur_attr = 0;
										ctx->cur_fg = 7;
										ctx->cur_bg = 0;
										break;
									case 1:
										ctx->cur_attr |= ATTR_BOLD;
										break;
									case 4:
										ctx->cur_attr |= ATTR_UNDERLINE;
										break;
									case 7:
										ctx->cur_attr |= ATTR_REVERSE;
										break;
									case 22:
										ctx->cur_attr &= ~ATTR_BOLD;
										break;
									case 24:
										ctx->cur_attr &= ~ATTR_UNDERLINE;
										break;
									case 27:
										ctx->cur_attr &= ~ATTR_REVERSE;
										break;
									case 30:
									case 31:
									case 32:
									case 33:
									case 34:
									case 35:
									case 36:
									case 37:
										ctx->cur_fg = n - 30;
										break;
									case 39:
										ctx->cur_fg = 7;
										break;
									case 40:
									case 41:
									case 42:
									case 43:
									case 44:
									case 45:
									case 46:
									case 47:
										ctx->cur_bg = n - 40;
										break;
									case 49:
										ctx->cur_bg = 0;
										break;
									case 90:
									case 91:
									case 92:
									case 93:
									case 94:
									case 95:
									case 96:
									case 97:
										ctx->cur_fg = n - 90 + 8;
										break;
									case 100:
									case 101:
									case 102:
									case 103:
									case 104:
									case 105:
									case 106:
									case 107:
										ctx->cur_bg = n - 100 + 8;
										break;
									case 38:
									case 48: {
										int fgbg = n;
										int type, color, r, g, b;

										token = strsep(&p, ";");
										if (token == NULL) goto sgr_out;
										type =
										    (*token != '\0') ? atoi(token) : -1;

										if (type == 5) {
											token = strsep(&p, ";");
											if (token == NULL) goto sgr_out;
											color = (*token != '\0')
											            ? atoi(token)
											            : 0;
											if (fgbg == 38)
												ctx->cur_fg =
												    color | COLOUR_FLAG_256;
											else
												ctx->cur_bg =
												    color | COLOUR_FLAG_256;
										} else if (type == 2) {
											token = strsep(&p, ";");
											if (token == NULL) goto sgr_out;
											r = (*token != '\0') ? atoi(token)
											                     : 0;
											token = strsep(&p, ";");
											if (token == NULL) goto sgr_out;
											g = (*token != '\0') ? atoi(token)
											                     : 0;
											token = strsep(&p, ";");
											if (token == NULL) goto sgr_out;
											b = (*token != '\0') ? atoi(token)
											                     : 0;
											if (fgbg == 38)
												ctx->cur_fg =
												    colour_join_rgb(r, g, b);
											else
												ctx->cur_bg =
												    colour_join_rgb(r, g, b);
										}
										break;
									}
								}
							}
						sgr_out:
							break;
						}
						case 'p':
						case 'q':
						case 'r': { /* DECSTBM - Set top and bottom margins */
							int top = 1, bot = ctx->grid->sy;
							if (ctx->param_len > 0) {
								char params[sizeof(ctx->param_buf) + 1];
								memcpy(params, ctx->param_buf, ctx->param_len);
								params[ctx->param_len] = '\0';
								char *p = params;
								char *token = strsep(&p, ";");
								if (token != NULL && *token != '\0')
									top = atoi(token);
								token = strsep(&p, ";");
								if (token != NULL && *token != '\0')
									bot = atoi(token);
							}
							if (top < 1) top = 1;
							if (bot > ctx->grid->sy) bot = ctx->grid->sy;
							if (top >= bot) {
								ctx->grid->scroll_top = 0;
								ctx->grid->scroll_bottom = ctx->grid->sy - 1;
							} else {
								ctx->grid->scroll_top = top - 1;
								ctx->grid->scroll_bottom = bot - 1;
							}
							ctx->grid->cx = 0;
							ctx->grid->cy = 0;
							break;
						}
						case 's':
						case 't':
						case 'u':
						case 'v':
						case 'w':
						case 'x':
						case 'y':
						case 'z':
							/* All standard CSI final characters - consume */
							break;

						default:
							/* Any other final character - consume */
							break;
					}
				}
				/* All private mode sequences and sequences with intermediates
				 * are consumed */

				ctx->state = INPUT_GROUND;
				break;

			case INPUT_OSC_STRING:
				/* OSC sequences end with BEL (0x07) or ST (ESC \) */
				if (ch == 0x07) {
					/* BEL terminator */
					ctx->state = INPUT_GROUND;
				} else if (ch == 0x1B) {
					/* Potential ST - next char should be \ */
					/* For simplicity, just go to ground - real tmux would check
					 * next char */
					ctx->state = INPUT_GROUND;
				}
				/* Otherwise stay in OSC_STRING and consume everything */
				break;

			case INPUT_DCS_STRING:
				/* DCS sequences end with ST (ESC \) */
				if (ch == 0x1B) {
					/* Potential ST - next char should be \ */
					/* For simplicity, just go to ground */
					ctx->state = INPUT_GROUND;
				}
				/* Otherwise stay in DCS_STRING and consume everything */
				break;
		}
	}
}

/* Render the pane content to the terminal */
static void render_pane(void) {
	int row, col;
	int last_fg = -1, last_bg = -1, last_attr = -1;
	char sgr_buf[128];

	for (row = 0; row < pane_grid.sy; row++) {
		move_cursor(pane_start_row + 1 + row + 1, 1);
		last_fg = -1;
		last_bg = -1;
		last_attr = -1;

		for (col = 0; col < pane_grid.sx; col++) {
			struct grid_cell *cell = &pane_grid.cells[row][col];

			if (cell->fg != last_fg || cell->bg != last_bg ||
			    cell->attr != last_attr) {
				int len;
				if (cell->attr == 0 && cell->fg == 7 && cell->bg == 0) {
					len = sprintf(sgr_buf, "\033[0m");
				} else {
					len = sprintf(sgr_buf, "\033[0");

					if (cell->attr & ATTR_BOLD)
						len += sprintf(sgr_buf + len, ";1");
					if (cell->attr & ATTR_UNDERLINE)
						len += sprintf(sgr_buf + len, ";4");
					if (cell->attr & ATTR_REVERSE)
						len += sprintf(sgr_buf + len, ";7");

					int fg = cell->fg;
					int bg = cell->bg;

					if (colour_is_rgb(fg)) {
						unsigned char r, g, b;
						colour_split_rgb(fg, &r, &g, &b);
						len +=
						    sprintf(sgr_buf + len, ";38;2;%u;%u;%u", r, g, b);
					} else if (colour_is_256(fg)) {
						len += sprintf(sgr_buf + len, ";38;5;%d", fg & 0xFF);
					} else if (fg != 7) {
						if (fg < 8)
							len += sprintf(sgr_buf + len, ";%d", 30 + fg);
						else
							len += sprintf(sgr_buf + len, ";%d", 90 + (fg - 8));
					}

					if (colour_is_rgb(bg)) {
						unsigned char r, g, b;
						colour_split_rgb(bg, &r, &g, &b);
						len +=
						    sprintf(sgr_buf + len, ";48;2;%u;%u;%u", r, g, b);
					} else if (colour_is_256(bg)) {
						len += sprintf(sgr_buf + len, ";48;5;%d", bg & 0xFF);
					} else if (bg != 0) {
						if (bg < 8)
							len += sprintf(sgr_buf + len, ";%d", 40 + bg);
						else
							len +=
							    sprintf(sgr_buf + len, ";%d", 100 + (bg - 8));
					}
					len += sprintf(sgr_buf + len, "m");
				}
				fputs(sgr_buf, stdout);
			}

			if (cell->uc.size > 0) {
				if (cell->uc.size == 1 && cell->uc.data[0] == '\0') {
					putchar(' ');
				} else {
					fwrite(cell->uc.data, 1, cell->uc.size, stdout);
				}
			} else {
				putchar(' ');
			}

			last_fg = cell->fg;
			last_bg = cell->bg;
			last_attr = cell->attr;
		}

		if (last_fg != 7 || last_bg != 0 || last_attr != 0) {
			printf("\033[0m");
		}
	}

	/* Position cursor */
	move_cursor(pane_start_row + 1 + pane_grid.cy + 1, pane_grid.cx + 1);
	fflush(stdout);
}

/* Handle input from user and child process */
static void handle_input(void) {
	fd_set readfds;
	char buf[1024];
	int n;

	while (1) {
		FD_ZERO(&readfds);
		FD_SET(STDIN_FILENO, &readfds);
		FD_SET(master_fd, &readfds);

		if (select(master_fd + 1, &readfds, NULL, NULL, NULL) == -1) {
			if (errno == EINTR) continue;
			perror("select");
			break;
		}

		/* Handle user input */
		if (FD_ISSET(STDIN_FILENO, &readfds)) {
			n = read(STDIN_FILENO, buf, sizeof(buf));
			if (n > 0) {
				/* Check for exit condition (Ctrl+C) */
				if (n == 1 && buf[0] == 3) {
					break;
				}
				/* Forward to child process */
				write(master_fd, buf, n);
			}
		}

		/* Handle child output */
		if (FD_ISSET(master_fd, &readfds)) {
			n = read(master_fd, buf, sizeof(buf));
			if (n > 0) {
				parse_control_sequence(buf, n);
				render_pane();
			} else if (n == 0) {
				/* EOF - child exited */
				break;
			}
		}
	}
}

/* Signal handler for cleanup */
static void signal_handler(int sig) {
	if (child_pid > 0) {
		kill(child_pid, SIGTERM);
		waitpid(child_pid, NULL, 0);
	}
	restore_terminal();
	exit(0);
}

/* Handle terminal resize */
static void resize_handler(void) {
	struct winsize ws;

	if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) != -1) {
		term_rows = ws.ws_row;
		term_cols = ws.ws_col;
		pane_start_row = term_rows - PANE_HEIGHT;

		/* Resize the pane grid */
		init_grid(&pane_grid, term_cols, PANE_HEIGHT);

		/* Notify child of size change */
		ws.ws_row = PANE_HEIGHT - 1;
		ws.ws_col = term_cols;
		ioctl(master_fd, TIOCSWINSZ, &ws);

		/* Redraw */
		clear_screen();
		printf("\033[%d;1H", pane_start_row + 1);
		printf("\033[7m");
		for (int i = 0; i < term_cols; i++) {
			printf("-");
		}
		printf("\033[0m");
		render_pane();
	}
}

/* SIGWINCH handler */
static void sigwinch_handler(int sig) { resize_handler(); }

int main(int argc, char *argv[]) {
	if (argc < 2) {
		fprintf(stderr, "Usage: %s <command> [args...]\n", argv[0]);
		return 1;
	}

	/* Set up signal handlers */
	signal(SIGINT, signal_handler);
	signal(SIGTERM, signal_handler);
	signal(SIGWINCH, sigwinch_handler);

	/* Initialize input parser */
	input_parser.state = INPUT_GROUND;
	input_parser.param_len = 0;
	input_parser.intermediate_len = 0;
	input_parser.private_marker = 0;
	input_parser.grid = &pane_grid;
	input_parser.cur_fg = 7;
	input_parser.cur_bg = 0;
	input_parser.cur_attr = 0;
	input_parser.utf8_started = 0;

	/* Set up terminal */
	setup_terminal();

	/* Create PTY and spawn child process */
	if (create_pty() == -1) {
		restore_terminal();
		exit(1);
	}

	spawn_child(&argv[1]);

	/* Main input loop */
	handle_input();

	/* Cleanup */
	if (child_pid > 0) {
		kill(child_pid, SIGTERM);
		waitpid(child_pid, NULL, 0);
	}

	restore_terminal();
	return 0;
}