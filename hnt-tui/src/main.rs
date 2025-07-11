use clap::{Args, Parser, Subcommand};
use crossterm::{
    cursor, execute, queue,
    style::{
        Attribute, Color, Print, ResetColor, SetAttribute, SetBackgroundColor, SetForegroundColor,
    },
    terminal::{self, Clear, ClearType},
};
use hnt_tui::{SelectArgs, Tty, TuiSelect};
use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use std::io::{self, stdout, BufRead, Read, Stdout, Write};
use tokio::sync::mpsc;
use vt100::Parser as TuiParser;

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
struct PaneArgs {
    /// The command to run in the pane.
    #[arg(required = true, trailing_var_arg = true)]
    command: Vec<String>,
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

    pub fn cleanup(&mut self) -> io::Result<()> {
        if self.should_cleanup {
            for i in 0..PANE_HEIGHT {
                execute!(
                    self.stdout,
                    cursor::MoveTo(0, self.pane_start_row + i),
                    Clear(ClearType::CurrentLine)
                )?;
            }
            execute!(
                self.stdout,
                cursor::MoveTo(0, self.pane_start_row),
                cursor::Show
            )?;
            terminal::disable_raw_mode()?;
            self.should_cleanup = false;
        }
        Ok(())
    }
}

impl Drop for TuiPane {
    fn drop(&mut self) {
        if self.should_cleanup {
            // We can't propagate errors from drop, so we ignore the result.
            // The cleanup function will set should_cleanup to false on success.
            let _ = self.cleanup();
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

    // PTY reader task: reads from PTY and sends to the main event loop.
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

    // Stdin reader task: reads from stdin and sends to the main event loop.
    let (stdin_tx, mut stdin_rx) = mpsc::channel(32);
    let stdin_task_handle = tokio::task::spawn_blocking(move || {
        let stdin = std::io::stdin();
        let mut handle = stdin.lock();
        let mut buf = [0u8; 1024];
        loop {
            match handle.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    if stdin_tx.blocking_send(buf[..n].to_vec()).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    let (exit_tx, mut exit_rx) = mpsc::channel(1);
    tokio::task::spawn_blocking(move || {
        let _ = child.wait();
        let _ = exit_tx.blocking_send(());
    });

    loop {
        tokio::select! {
            output = rx.recv() => {
                match output {
                    Some(data) => {
                        parser.process(&data);
                        draw_pane(&mut tui_pane.stdout, parser.screen(), tui_pane.pane_start_row)?;
                    }
                    None => {
                        // PTY closed
                        break;
                    }
                }
            },
            input = stdin_rx.recv() => {
                match input {
                    Some(data) => {
                        pty_writer.write_all(&data)?;
                        pty_writer.flush()?;
                    }
                    None => {
                        // Stdin closed
                        break;
                    }
                }
            },
            _ = exit_rx.recv() => {
                break;
            },
        }
    }

    stdin_task_handle.abort();
    tui_pane.cleanup()?;
    std::process::exit(0);
}

#[tokio::main]
async fn main() -> io::Result<()> {
    let cli = Cli::parse();
    match &cli.command {
        Commands::Select(args) => {
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
