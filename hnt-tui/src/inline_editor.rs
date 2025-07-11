use anyhow::{Context, Result};
use ratatui::crossterm::event::{self, Event, KeyCode, KeyModifiers};
use ratatui::crossterm::{cursor, execute, terminal};
use ratatui::widgets::{Block, Borders};
use ratatui::{self, TerminalOptions, Viewport};
use std::cmp::min;
use std::io::{self, Write};
use tui_textarea::{Input, TextArea};

/// Renders an inline TUI text editor and returns the user's input.
///
/// This function is designed to work within a terminal without taking over the full screen.
/// It correctly handles terminal scrolling and ensures the UI is properly cleaned up
/// on both normal exit (Esc, Ctrl+D) and interrupt (Ctrl+C).
pub fn prompt_for_input() -> Result<Option<String>> {
    const TUI_HEIGHT: u16 = 10;

    io::stdout().flush()?;
    let (start_col, initial_pane_top) = cursor::position()?;

    // Predict how many lines Ratatui will scroll to fit the pane.
    let (_, rows) = terminal::size()?;
    let spare = rows.saturating_sub(initial_pane_top); // rows remaining below cursor
    let delta = TUI_HEIGHT.saturating_sub(spare); // lines that will be scrolled (0 if enough room)
    let pane_top = initial_pane_top.saturating_sub(delta); // true pane top after the implicit scroll

    let mut terminal = ratatui::init_with_options(TerminalOptions {
        viewport: Viewport::Inline(TUI_HEIGHT),
    });

    let mut textarea = TextArea::default();
    textarea.set_block(
        Block::default()
            .borders(Borders::ALL)
            .title("Enter Instructions (Esc or Ctrl+D to submit, Ctrl+C to abort)"),
    );

    let (instruction, aborted) = loop {
        terminal.draw(|f| {
            f.render_widget(&textarea, f.area());
        })?;
        match event::read().context("Failed to read TUI event")? {
            Event::Key(key) => match key.code {
                KeyCode::Esc => break (textarea.into_lines().join("\n"), false),
                KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    break (textarea.into_lines().join("\n"), false);
                }
                KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    break (String::new(), true);
                }
                _ => {
                    textarea.input(Input::from(key));
                }
            },
            Event::Resize(_, _) => {
                terminal.autoresize()?;
            }
            _ => {}
        }
    };

    ratatui::restore();
    let mut out = io::stdout();
    out.write_all(b"\x1b[?6l\x1b[r")?; // DECOM off, scroll region reset
    let (_, rows) = terminal::size()?;
    let real_height = min(TUI_HEIGHT, rows.saturating_sub(pane_top));
    for y in 0..real_height {
        execute!(
            out,
            cursor::MoveTo(0, pane_top + y),
            terminal::Clear(terminal::ClearType::CurrentLine)
        )?;
    }
    execute!(out, cursor::MoveTo(start_col, pane_top))?;

    if aborted || instruction.trim().is_empty() {
        Ok(None)
    } else {
        Ok(Some(instruction))
    }
}
