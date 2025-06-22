use clap::{Args, Parser, Subcommand};
use crossterm::{
    cursor,
    event::{self, Event, KeyCode, KeyEvent, KeyModifiers},
    execute,
    style::{
        Attribute, Color, Print, ResetColor, SetAttribute, SetBackgroundColor, SetForegroundColor,
    },
    terminal::{self, Clear, ClearType},
    tty::IsTty,
};
use std::io::{self, stdout, BufRead, Stdout, Write};

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

struct TuiSelect {
    lines: Vec<String>,
    selected_index: usize,
    scroll_offset: usize,
    display_height: usize,
    color: Option<Color>,
    stdout: Stdout,
    should_cleanup: bool,
    term_cols: u16,
}

impl TuiSelect {
    fn new(lines: Vec<String>, args: &SelectArgs) -> io::Result<Self> {
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
            stdout: stdout(),
            should_cleanup: false,
            term_cols,
        })
    }

    fn run(&mut self) -> io::Result<Option<String>> {
        terminal::enable_raw_mode()?;
        self.should_cleanup = true;

        // Make space for the menu by printing newlines, then moving back up.
        execute!(self.stdout, Print("\n".repeat(self.display_height)))?;
        execute!(self.stdout, cursor::MoveUp(self.display_height as u16))?;
        execute!(self.stdout, cursor::SavePosition, cursor::Hide)?;

        self.draw_menu()?;

        let result = self.handle_input_loop();

        // `self` will be dropped after this function returns, and `Drop::drop` will clean up.
        result
    }

    fn draw_menu(&mut self) -> io::Result<()> {
        execute!(self.stdout, cursor::RestorePosition)?;

        for i in 0..self.display_height {
            execute!(self.stdout, Clear(ClearType::CurrentLine))?;
            let line_idx = self.scroll_offset + i;

            if line_idx < self.lines.len() {
                if line_idx == self.selected_index {
                    if let Some(color) = self.color {
                        execute!(
                            self.stdout,
                            SetForegroundColor(color),
                            Print("▌ "),
                            SetBackgroundColor(color),
                            SetForegroundColor(Color::Black)
                        )?;
                    } else {
                        execute!(self.stdout, Print("▌ "), SetAttribute(Attribute::Reverse))?;
                    }
                } else {
                    execute!(self.stdout, Print("  "))?;
                }

                let line = &self.lines[line_idx];
                let mut truncated_line = line.as_str();
                if line.len() > self.term_cols as usize - 2 {
                    truncated_line = &line[..self.term_cols as usize - 2];
                }
                execute!(self.stdout, Print(truncated_line))?;

                if line_idx == self.selected_index {
                    execute!(self.stdout, ResetColor)?;
                }
            }

            if i < self.display_height - 1 {
                execute!(self.stdout, Print("\n\r"))?;
            }
        }
        self.stdout.flush()
    }

    fn handle_input_loop(&mut self) -> io::Result<Option<String>> {
        loop {
            match event::read()? {
                // Quit without selection
                Event::Key(KeyEvent { code: KeyCode::Esc, .. })
                | Event::Key(KeyEvent {
                    code: KeyCode::Char('c'),
                    modifiers: KeyModifiers::CONTROL,
                    ..
                })
                | Event::Key(KeyEvent {
                    code: KeyCode::Char('d'),
                    modifiers: KeyModifiers::CONTROL,
                    ..
                }) => {
                    return Ok(None);
                }

                // Select and quit
                Event::Key(KeyEvent { code: KeyCode::Enter, .. }) => {
                    return Ok(Some(self.lines[self.selected_index].clone()));
                }

                // Move up
                Event::Key(KeyEvent { code: KeyCode::Up, .. })
                | Event::Key(KeyEvent { code: KeyCode::BackTab, .. }) // Shift-Tab
                | Event::Key(KeyEvent {
                    code: KeyCode::Char('k'),
                    modifiers: KeyModifiers::CONTROL, ..
                })
                | Event::Key(KeyEvent {
                    code: KeyCode::Char('k'),
                    modifiers: KeyModifiers::ALT, ..
                }) => {
                    if self.selected_index > 0 {
                        self.selected_index -= 1;
                        if self.selected_index < self.scroll_offset {
                            self.scroll_offset = self.selected_index;
                        }
                        self.draw_menu()?;
                    }
                }

                // Move down
                Event::Key(KeyEvent { code: KeyCode::Down, .. })
                | Event::Key(KeyEvent { code: KeyCode::Tab, .. })
                | Event::Key(KeyEvent {
                    code: KeyCode::Char('j'),
                    modifiers: KeyModifiers::CONTROL, ..
                })
                | Event::Key(KeyEvent {
                    code: KeyCode::Char('j'),
                    modifiers: KeyModifiers::ALT, ..
                }) => {
                    if self.selected_index < self.lines.len() - 1 {
                        self.selected_index += 1;
                        if self.selected_index >= self.scroll_offset + self.display_height {
                            self.scroll_offset = self.selected_index - self.display_height + 1;
                        }
                        self.draw_menu()?;
                    }
                }
                _ => {}
            }
        }
    }
}

impl Drop for TuiSelect {
    fn drop(&mut self) {
        if self.should_cleanup {
            // It's good practice to not panic in drop, so we ignore errors.
            let _ = execute!(
                self.stdout,
                cursor::RestorePosition,
                Clear(ClearType::FromCursorDown),
                cursor::Show
            );
            let _ = terminal::disable_raw_mode();
        }
    }
}

fn main() -> io::Result<()> {
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

            if !stdout().is_tty() {
                println!("{}", lines[0]);
                return Ok(());
            }

            let mut tui = TuiSelect::new(lines, args)?;
            let selected_line = match tui.run() {
                Ok(line) => line,
                Err(e) => {
                    // `tui` is dropped here, cleaning up the terminal before we print the error.
                    return Err(e);
                }
            };

            // `tui` is dropped here, `Drop` impl runs, terminal is restored.
            if let Some(line) = selected_line {
                // Now we can safely print the result.
                println!("{}", line);
            }
        }
    }

    Ok(())
}
