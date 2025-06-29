use clap::{Args, Parser, Subcommand};
use crossterm::{
    cursor, execute, queue,
    style::{
        Attribute, Color, Print, ResetColor, SetAttribute, SetBackgroundColor, SetForegroundColor,
    },
    terminal::{self, Clear, ClearType},
};
use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use std::fs::{File, OpenOptions};
use std::io::{self, stdout, BufRead, Read, Stdout, Write};
use std::os::unix::io::AsRawFd;
use termios::{self, Termios};
use tokio::io::AsyncReadExt;
use tokio::sync::mpsc;
use vt100::Parser as TuiParser;

struct TtyWriter<'a>(&'a mut std::fs::File);

impl<'a> std::io::Write for TtyWriter<'a> {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0.write(buf)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.0.flush()
    }
}

/// Command-line arguments
#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Select an item from a list read from stdin
    Select(SelectArgs),
    /// Run a command in a new TUI pane
    Pane(PaneArgs),
}

#[derive(Args, Debug)]
struct SelectArgs {
    /// The height of the selection menu
    #[arg(long, default_value_t = 10)]
    height: usize,

    /// The color of the selected line (0-7: Black, Red, Green, Yellow, Blue, Magenta, Cyan, White)
    #[arg(long)]
    color: Option<u8>,
}

#[derive(Args, Debug)]
struct PaneArgs {
    /// The command to run in the pane.
    #[arg(required = true, trailing_var_arg = true)]
    command: Vec<String>,
}

fn map_color(c: u8) -> Color {
    match c {
        0 => Color::Black,
        1 => Color::DarkRed,
        2 => Color::DarkGreen,
        3 => Color::DarkYellow,
        4 => Color::DarkBlue,
        5 => Color::DarkMagenta,
        6 => Color::DarkCyan,
        7 => Color::Grey,
        _ => Color::White, // Should be unreachable with clap validation
    }
}

struct Tty {
    file: File,
    original_termios: Termios,
}

impl Tty {
    fn new() -> io::Result<Self> {
        let file = OpenOptions::new().read(true).write(true).open("/dev/tty")?;
        let fd = file.as_raw_fd();
        let original_termios = Termios::from_fd(fd)?;
        Ok(Tty {
            file,
            original_termios,
        })
    }

    fn enable_raw_mode(&mut self) -> io::Result<()> {
        let fd = self.file.as_raw_fd();
        let mut raw = self.original_termios;
        termios::cfmakeraw(&mut raw);
        termios::tcsetattr(fd, termios::TCSANOW, &raw)?;
        Ok(())
    }
}

impl Drop for Tty {
    fn drop(&mut self) {
        let fd = self.file.as_raw_fd();
        let _ = termios::tcsetattr(fd, termios::TCSANOW, &self.original_termios);
    }
}

struct TuiSelect {
    lines: Vec<String>,
    selected_index: usize,
    scroll_offset: usize,
    display_height: usize,
    color: Option<Color>,
    tty: Tty,
    buf: [u8; 16],
    term_cols: u16,
}

impl TuiSelect {
    fn new(lines: Vec<String>, args: &SelectArgs, tty: Tty) -> io::Result<Self> {
        let (term_cols, term_rows) = terminal::size()?;
        let num_lines = lines.len();

        let mut display_height = args.height;
        if display_height > num_lines {
            display_height = num_lines;
        }
        if (term_rows as usize).saturating_sub(1) < display_height {
            display_height = (term_rows as usize).saturating_sub(1);
        }
        if display_height == 0 && num_lines > 0 {
            return Err(io::Error::new(io::ErrorKind::Other, "Terminal too small."));
        }

        Ok(TuiSelect {
            lines,
            selected_index: 0,
            scroll_offset: 0,
            display_height,
            color: args.color.map(map_color),
            tty,
            buf: [0; 16],
            term_cols,
        })
    }

    fn run(&mut self) -> io::Result<Option<String>> {
        self.tty.enable_raw_mode()?;

        // Make space for the menu by printing newlines, then moving back up.
        execute!(
            TtyWriter(&mut self.tty.file),
            Print("\n".repeat(self.display_height))
        )?;
        execute!(
            TtyWriter(&mut self.tty.file),
            cursor::MoveUp(self.display_height as u16)
        )?;
        execute!(
            TtyWriter(&mut self.tty.file),
            cursor::SavePosition,
            cursor::Hide
        )?;

        self.draw_menu()?;

        loop {
            let n = self.tty.file.read(&mut self.buf)?;
            if n == 0 {
                continue;
            }
            let key_event = &self.buf[..n];

            let mut moved = false;
            match key_event {
                b"\r" => return Ok(Some(self.lines[self.selected_index].clone())), // Enter
                b"\x03" | b"\x04" => return Ok(None),                              // Ctrl-C, Ctrl-D

                // Move up: Up Arrow, Shift-Tab, Ctrl-K, Alt-K
                b"\x1b[A" | b"\x1b[Z" | b"\x0b" | b"\x1bk" => {
                    if self.selected_index > 0 {
                        self.selected_index -= 1;
                        if self.selected_index < self.scroll_offset {
                            self.scroll_offset = self.selected_index;
                        }
                        moved = true;
                    }
                }
                // Move down: Down Arrow, Tab, Ctrl-J, Alt-J
                b"\x1b[B" | b"\t" | b"\n" | b"\x1bj" => {
                    if self.selected_index < self.lines.len() - 1 {
                        self.selected_index += 1;
                        if self.selected_index >= self.scroll_offset + self.display_height {
                            self.scroll_offset = self.selected_index - self.display_height + 1;
                        }
                        moved = true;
                    }
                }
                // Esc to quit
                b"\x1b" => return Ok(None),
                _ => {}
            }
            if moved {
                self.draw_menu()?;
            }
        }
    }

    fn draw_menu(&mut self) -> io::Result<()> {
        execute!(TtyWriter(&mut self.tty.file), cursor::RestorePosition)?;

        for i in 0..self.display_height {
            execute!(TtyWriter(&mut self.tty.file), Clear(ClearType::CurrentLine))?;
            let line_idx = self.scroll_offset + i;

            if line_idx < self.lines.len() {
                if line_idx == self.selected_index {
                    if let Some(color) = self.color {
                        execute!(
                            TtyWriter(&mut self.tty.file),
                            SetForegroundColor(color),
                            Print("▌ "),
                            SetBackgroundColor(color),
                            SetForegroundColor(Color::Black)
                        )?;
                    } else {
                        execute!(
                            TtyWriter(&mut self.tty.file),
                            Print("▌ "),
                            SetAttribute(Attribute::Reverse)
                        )?;
                    }
                } else {
                    execute!(TtyWriter(&mut self.tty.file), Print("  "))?;
                }

                let line = &self.lines[line_idx];
                let mut truncated_line = line.as_str();
                if line.len() > self.term_cols as usize - 2 {
                    truncated_line = &line[..self.term_cols as usize - 2];
                }
                execute!(TtyWriter(&mut self.tty.file), Print(truncated_line))?;

                if line_idx == self.selected_index {
                    execute!(TtyWriter(&mut self.tty.file), ResetColor)?;
                }
            }

            if i < self.display_height - 1 {
                execute!(TtyWriter(&mut self.tty.file), Print("\n\r"))?;
            }
        }
        self.tty.file.flush()
    }
}

impl Drop for TuiSelect {
    fn drop(&mut self) {
        // It's good practice to not panic in drop, so we ignore errors.
        let _ = execute!(
            TtyWriter(&mut self.tty.file),
            cursor::RestorePosition,
            Clear(ClearType::FromCursorDown),
            cursor::Show
        );
    }
}

const PANE_HEIGHT: u16 = 20;

struct TuiPane {
    stdout: Stdout,
    should_cleanup: bool,
    pane_start_row: u16,
}

impl TuiPane {
    fn new() -> io::Result<Self> {
        let (term_cols, term_rows) = terminal::size()?;
        let (_, mut pane_start_row) = cursor::position()?;

        // Check if there is enough space to draw the pane from the current cursor row.
        // The cursor row is 0-indexed, while PANE_HEIGHT and term_rows are 1-based counts.
        // We use u32 to prevent potential overflow on the addition during the check.
        if pane_start_row as u32 + PANE_HEIGHT as u32 > term_rows as u32 {
            // Not enough space. Calculate how many lines to scroll.
            let scroll_count = (pane_start_row as u32 + PANE_HEIGHT as u32) - term_rows as u32;

            // Move cursor to the bottom and print newlines to scroll up.
            let mut stdout = stdout();
            execute!(
                stdout,
                cursor::MoveTo(0, term_rows.saturating_sub(1)),
                Print("\n".repeat(scroll_count as usize))
            )?;

            // After scrolling, update pane_start_row to be at the new bottom-most position.
            pane_start_row = term_rows.saturating_sub(PANE_HEIGHT);
        }

        let mut tui_pane = TuiPane {
            stdout: stdout(),
            should_cleanup: false,
            pane_start_row,
        };

        terminal::enable_raw_mode()?;
        tui_pane.should_cleanup = true;

        // Position pane and draw border
        execute!(
            tui_pane.stdout,
            cursor::MoveTo(0, pane_start_row),
            SetAttribute(Attribute::Reverse),
            Print("-".repeat(term_cols as usize)),
            ResetColor
        )?;

        Ok(tui_pane)
    }
}

impl Drop for TuiPane {
    fn drop(&mut self) {
        if self.should_cleanup {
            for i in 0..PANE_HEIGHT {
                let _ = execute!(
                    self.stdout,
                    cursor::MoveTo(0, self.pane_start_row + i),
                    Clear(ClearType::CurrentLine)
                );
            }
            let _ = execute!(
                self.stdout,
                cursor::MoveTo(0, self.pane_start_row),
                cursor::Show
            );
            let _ = terminal::disable_raw_mode();
        }
    }
}

fn vt100_color_to_crossterm(c: vt100::Color) -> Color {
    match c {
        vt100::Color::Default => Color::Reset,
        vt100::Color::Idx(val) => Color::AnsiValue(val),
        vt100::Color::Rgb(r, g, b) => Color::Rgb { r, g, b },
    }
}

fn draw_pane(stdout: &mut Stdout, screen: &vt100::Screen, pane_start_row: u16) -> io::Result<()> {
    queue!(stdout, cursor::Hide)?;

    let (rows, cols) = screen.size();
    for row_idx in 0..rows {
        queue!(stdout, cursor::MoveTo(0, pane_start_row + 1 + row_idx))?;

        // Reset tracked styles for each row. The terminal state is reset by ResetColor
        // at the end of the previous row, so we start fresh here.
        let mut last_style = (Color::Reset, Color::Reset, false, false, false);

        for col_idx in 0..cols {
            let cell = screen.cell(row_idx, col_idx);
            if let Some(c) = cell.as_ref() {
                if c.is_wide_continuation() {
                    continue;
                }
            }
            let (current_style, contents) = if let Some(c) = cell {
                (
                    (
                        vt100_color_to_crossterm(c.fgcolor()),
                        vt100_color_to_crossterm(c.bgcolor()),
                        c.bold(),
                        c.underline(),
                        c.inverse(),
                    ),
                    c.contents(),
                )
            } else {
                // A `None` cell is a default cell.
                (
                    (Color::Reset, Color::Reset, false, false, false),
                    String::new(),
                )
            };

            if current_style != last_style {
                queue!(stdout, ResetColor)?;
                queue!(stdout, SetForegroundColor(current_style.0))?;
                queue!(stdout, SetBackgroundColor(current_style.1))?;
                if current_style.2 {
                    queue!(stdout, SetAttribute(Attribute::Bold))?;
                }
                if current_style.3 {
                    queue!(stdout, SetAttribute(Attribute::Underlined))?;
                }
                if current_style.4 {
                    queue!(stdout, SetAttribute(Attribute::Reverse))?;
                }
                last_style = current_style;
            }

            if contents.is_empty() {
                queue!(stdout, Print(" "))?;
            } else {
                queue!(stdout, Print(contents))?;
            }
        }
        // Reset colors at the end of the row to prevent styles leaking.
        queue!(stdout, ResetColor)?;
    }

    if !screen.hide_cursor() {
        let (cursor_y, cursor_x) = screen.cursor_position();
        queue!(
            stdout,
            cursor::Show,
            cursor::MoveTo(cursor_x, pane_start_row + 1 + cursor_y)
        )?;
    } else {
        queue!(stdout, cursor::Hide)?;
    }

    stdout.flush()
}

async fn run_pane(args: &PaneArgs) -> io::Result<()> {
    let mut tui_pane = TuiPane::new()?;

    let pty_system = NativePtySystem::default();
    let (term_cols, _) = terminal::size()?;
    let pty_size = PtySize {
        rows: PANE_HEIGHT - 1,
        cols: term_cols,
        pixel_width: 0,
        pixel_height: 0,
    };

    let mut cmd = CommandBuilder::new(&args.command[0]);
    cmd.args(&args.command[1..]);
    cmd.env("TERM", "xterm-256color");

    let pair = pty_system
        .openpty(pty_size)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("openpty failed: {}", e)))?;

    let mut child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("spawn failed: {}", e)))?;

    let master = pair.master;
    let mut pty_reader = master
        .try_clone_reader()
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("clone reader failed: {}", e)))?;
    let mut pty_writer = master
        .take_writer()
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("take_writer failed: {}", e)))?;

    let mut parser = TuiParser::new(pty_size.rows, pty_size.cols, 0);

    let (tx, mut rx) = mpsc::channel::<Vec<u8>>(32);
    tokio::task::spawn_blocking(move || {
        let mut buf = [0u8; 8192];
        loop {
            match pty_reader.read(&mut buf) {
                Ok(0) | Err(_) => break, // EOF or error
                Ok(n) => {
                    if tx.blocking_send(buf[..n].to_vec()).is_err() {
                        break;
                    }
                }
            }
        }
    });

    let mut stdin = tokio::io::stdin();
    let mut input_buf = [0u8; 1024];

    let mut child_wait = tokio::task::spawn_blocking(move || child.wait());

    loop {
        tokio::select! {
            Some(output) = rx.recv() => {
                parser.process(&output);
                draw_pane(&mut tui_pane.stdout, parser.screen(), tui_pane.pane_start_row)?;
            },
            result = stdin.read(&mut input_buf) => {
                match result {
                    Ok(0) => break, // stdin closed
                    Ok(n) => {
                        pty_writer.write_all(&input_buf[..n])?;
                        pty_writer.flush()?;
                    }
                    Err(e) if e.kind() == io::ErrorKind::BrokenPipe => break,
                    Err(e) => return Err(e),
                }
            },
            _ = &mut child_wait => {
                break;
            }
        }
    }

    Ok(())
}

#[tokio::main]
async fn main() -> io::Result<()> {
    let cli = Cli::parse();
    match &cli.command {
        Commands::Select(args) => {
            if let Some(color) = args.color {
                if color > 7 {
                    eprintln!("Error: color must be between 0 and 7.");
                    return Err(io::Error::new(io::ErrorKind::InvalidInput, "Invalid color"));
                }
            }

            let lines: Vec<String> = io::stdin().lock().lines().filter_map(Result::ok).collect();
            if lines.is_empty() {
                return Ok(());
            }

            let tty = match Tty::new() {
                Ok(tty) => tty,
                Err(_) => {
                    // Not in an interactive session, so print the first line and exit.
                    if !lines.is_empty() {
                        println!("{}", lines[0]);
                    }
                    return Ok(());
                }
            };

            let selected_line = {
                let mut tui = TuiSelect::new(lines, args, tty)?;
                tui.run()?
            };

            // `tui` is dropped here, `Drop` impl runs, and the Tty's Drop impl restores
            // the original terminal settings.
            if let Some(line) = selected_line {
                // Now we can safely print the result to standard output.
                println!("{}", line);
            }
        }
        Commands::Pane(args) => {
            if args.command.is_empty() {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "No command provided for pane",
                ));
            }
            run_pane(args).await?;
        }
    }

    Ok(())
}
