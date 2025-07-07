use anyhow::Result;
use crossterm::{
    cursor,
    terminal::{Clear, ClearType},
};
use crossterm::{execute, style::Print};
use once_cell::sync::Lazy;
use rand::seq::SliceRandom;
use std::io::{stdout, Write};
use std::time::Duration;

use tokio::sync::watch;

#[derive(Debug, Clone)]
pub struct Spinner {
    pub frames: Vec<String>,
    pub interval: Duration,
}

// A collection of all available spinners.
pub static SPINNERS: Lazy<Vec<Spinner>> = Lazy::new(|| {
    vec![
        Spinner {
            frames: vec![
                "🮤🮥🮦🮧🮨",
                " 🮥🮦🮧🮨🮩",
                "  🮦🮧🮨🮩🮪",
                "   🮧🮨🮩🮪🮫",
                "    🮨🮩🮪🮫🮬",
                "     🮩🮪🮫🮬🮭",
                "      🮪🮫🮬🮭🮮",
                "       🮫🮬🮭🮮🮤",
                "        🮬🮭🮮🮤🮥",
                "         🮭🮮🮤🮥🮦",
                "          🮮🮤🮥🮦🮧",
                "           🮤🮥🮦🮧🮨",
                "            🮥🮦🮧🮨🮩",
                "             🮦🮧🮨🮩🮪",
                "              🮧🮨🮩🮪🮫",
                "               🮨🮩🮪🮫🮬",
                "                🮩🮪🮫🮬🮭",
                "                 🮪🮫🮬🮭🮮",
                "                  🮫🮬🮭🮮🮤",
                "                   🮬🮭🮮🮤🮥",
                "                    🮭🮮🮤🮥🮦",
                "                     🮮🮤🮥🮦🮧",
                "🮤                     🮤🮥🮦🮧",
                "🮤🮥                     🮥🮦🮧",
                "🮤🮥🮦                     🮦🮧",
                "🮤🮥🮦🮧                     🮧",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(100),
        },
        // Spinner {
        //     frames: vec![
        //      "🯚🯚🯚",
        //      "🭯🯚🯚",
        //      "🯚🭯🯚",
        //      "🯚🯚🭯",
        //      "🯚🯚🯚🭈",
        //      "🯚🯚🯚🭇🭄",
        //      "🯚🯚🯚🭇🭄",
        //      "🯚🯚🯚🭈",
        //      "🯚🯚🭯",
        //      "🯚🭯🯚",
        //      "🭯🯚🯚",
        //      "🯚🯚🯚",
        //     ]
        //     .into_iter()
        //     .map(String::from)
        //     .collect(),
        //     interval: Duration::from_millis(150),
        // },
        Spinner {
            frames: vec![
                "╶╀┼╴",
                "╶┾┽╴",
                "╶┼╁╴",
                "╶┼┾╸",
                "╶┼╀╴",
                "╶┾┽╴",
                "╶╁┼╴",
                "╺┽┼╴",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                "⢀⠀", "⡀⠀", "⠄⠀", "⢂⠀", "⡂⠀", "⠅⠀", "⢃⠀", "⡃⠀", "⠍⠀", "⢋⠀", "⡋⠀", "⠍⠁", "⢋⠁", "⡋⠁",
                "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙", "⠉⠙", "⠉⠩", "⠈⢙", "⠈⡙", "⢈⠩", "⡀⢙", "⠄⡙", "⢂⠩", "⡂⢘", "⠅⡘",
                "⢃⠨", "⡃⢐", "⠍⡐", "⢋⠠", "⡋⢀", "⠍⡁", "⢋⠁", "⡋⠁", "⠍⠉", "⠋⠉", "⠋⠉", "⠉⠙", "⠉⠙", "⠉⠩",
                "⠈⢙", "⠈⡙", "⠈⠩", "⠀⢙", "⠀⡙", "⠀⠩", "⠀⢘", "⠀⡘", "⠀⠨", "⠀⢐", "⠀⡐", "⠀⠠", "⠀⢀", "⠀⡀",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec!["⢄", "⢂", "⢁", "⡁", "⡈", "⡐", "⡠"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec!["🌑 ", "🌒 ", "🌓 ", "🌔 ", "🌕 ", "🌖 ", "🌗 ", "🌘 "]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec!["░", "▒", "▓", "█", "▓", "▒", " "]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec!["||", "/\\", "--", "\\/"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec!["|/", "/-", "-\\", "\\|"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec!["|-", "/\\", "-|", "\\/"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                "  ", "▁▁", "▂▂", "▃▃", "▄▄", "▅▅", "▆▆", "▇▇", "██", "🭶🭶", "🭷🭷", "🭸🭸", "🭹🭹", "🭺🭺",
                "🭻🭻",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(100),
        },
    ]
});

/// Selects a random spinner from the predefined list.
pub fn get_random_spinner() -> Spinner {
    let mut rng = rand::thread_rng();
    SPINNERS
        .choose(&mut rng)
        .cloned()
        .expect("Spinner list should not be empty")
}

/// Displays the provided spinner animation until a stop signal is received.
pub async fn run_spinner(spinner: Spinner, mut rx: watch::Receiver<bool>) -> Result<()> {
    let mut i = 0;
    let mut interval = tokio::time::interval(spinner.interval);
    let mut stdout = stdout();

    execute!(stdout, cursor::Hide)?;
    stdout.flush()?;

    loop {
        tokio::select! {
            res = rx.changed() => {
                if res.is_err() || *rx.borrow() {
                    break;
                }
            },
            _ = interval.tick() => {
                let frame = &spinner.frames[i];
                execute!(
                    stdout,
                    cursor::MoveToColumn(0),
                    Clear(ClearType::CurrentLine),
                    Print("Executing... "),
                    Print(frame)
                )?;

                stdout.flush()?;
                i = (i + 1) % spinner.frames.len();
            }
        }
    }

    // Cleanup
    execute!(
        stdout,
        cursor::MoveToColumn(0),
        Clear(ClearType::CurrentLine),
        cursor::Show
    )?;
    stdout.flush()?;

    Ok(())
}
