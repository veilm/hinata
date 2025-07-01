use clap::Args;
use crossterm::{
    cursor, execute, queue,
    style::{
        Attribute, Color, Print, ResetColor, SetAttribute, SetBackgroundColor, SetForegroundColor,
    },
    terminal::{self, Clear, ClearType},
};
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::io::AsRawFd;
use termios::{self, Termios};

struct TtyWriter<'a>(&'a mut std::fs::File);

impl<'a> std::io::Write for TtyWriter<'a> {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0.write(buf)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.0.flush()
    }
}

#[derive(Args, Debug)]
pub struct SelectArgs {
    /// The height of the selection menu
    #[arg(long, default_value_t = 10)]
    pub height: usize,

    /// The color of the selected line (0-7: Black, Red, Green, Yellow, Blue, Magenta, Cyan, White)
    #[arg(long)]
    pub color: Option<u8>,
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

pub struct Tty {
    file: File,
    original_termios: Termios,
}

impl Tty {
    pub fn new() -> io::Result<Self> {
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

pub struct TuiSelect {
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
    pub fn new(lines: Vec<String>, args: &SelectArgs, tty: Tty) -> io::Result<Self> {
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

    pub fn run(&mut self) -> io::Result<Option<String>> {
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
