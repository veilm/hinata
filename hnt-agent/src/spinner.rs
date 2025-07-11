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

/*
diamond
- o3: 5/9 = 0.56
- Claude Opus 3: 3.4/7 = 0.49
- Claude Opus 4: 5/13 = 0.38
- DeepSeek-R1 0528: 0.9/3 = 0.3
- Gemini 2.5 Pro: 0.5/8.5 = 0.06

shading
- Claude 4 Opus: 5.85/10 = 0.59
- o3: 5.2/12 = 0.43

cross
- Claude 4 Opus: 10.95/24 = 0.46

Bb
- Claude 4 Opus: 1.05/10 = 0.11
*/

// A collection of all available spinners.
pub static SPINNERS: Lazy<Vec<Spinner>> = Lazy::new(|| {
    vec![
        Spinner {
            // Claude 4 Opus
            frames: vec!["╱", "╱╱", "╱╱╱", "│││", "╲╲╲", "╲╲", "╲", "│"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "□→┬→┬→┬→",
                "┬→□→┬→┬→",
                "┬→┬→□→┬→",
                "┬→┬→┬→□→",
                "┬→┬→┬→┬□",
                "■→┬→┬→┬→",
                "┬→■→┬→┬→",
                "┬→┬→■→┬→",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus, sucralose
            frames: vec![
                "    •    ",
                "   ┌•┐   ",
                "  ┌┼─┼┐  ",
                " ┌┼┼─┼┼┐ ",
                "┌┼┼┼─┼┼┼┐",
                "│┼┼┼•┼┼┼│",
                "└┼┼┼─┼┼┼┘",
                " └┼┼─┼┼┘ ",
                "  └┼─┼┘  ",
                "   └─┘   ",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "⟨0│ │0⟩",
                "⟨0│░│0⟩",
                "⟨0│▒│0⟩",
                "⟨0│▓│0⟩",
                "⟨1│▓│1⟩",
                "⟨1│▒│1⟩",
                "⟨1│░│1⟩",
                "⟨1│ │1⟩",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "┌─┬─┬─┐",
                "├─┼─┼─┤",
                "├▓┼─┼─┤",
                "├─┼▓┼─┤",
                "├─┼─┼▓┤",
                "├─┼─┼─┤",
                "└─┴─┴─┘",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "┌┐      ",
                "└┘┌┐    ",
                "  └┘┌┐  ",
                "    └┘┌┐",
                "      └┘",
                "    ┌┐└┘",
                "  ┌┐└┘  ",
                "┌┐└┘    ",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "───────",
                "╱──────",
                "─╱─────",
                "──╱────",
                "───╱───",
                "────╱──",
                "─────╱─",
                "──────╱",
                "───────",
                "──────╲",
                "─────╲─",
                "────╲──",
                "───╲───",
                "──╲────",
                "─╲─────",
                "╲──────",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "┌      ",
                "┌┬     ",
                "┌┬┬    ",
                "┌┬┬┬   ",
                "├┼┼┼   ",
                "├┼┼┼┤  ",
                "└┴┴┴┘  ",
                " └┴┴┘  ",
                "  └┴┘  ",
                "   └┘  ",
                "       ",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "┌───┐",
                "│╱─╲│",
                "│╲ ╱│",
                "└─╲╱┘",
                "┌╲╱─┐",
                "│╱ ╲│",
                "│╲─╱│",
                "└───┘",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "  │  ",
                " ─┼─ ",
                "┌─┼─┐",
                "│ ┼ │",
                "├─┼─┤",
                "│ ┼ │",
                "└─┼─┘",
                " ─┼─ ",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "█▓▒░    ",
                " █▓▒░   ",
                "  █▓▒░  ",
                "   █▓▒░ ",
                "    █▓▒░",
                "     █▓▒",
                "      █▓",
                "       █",
                "      ▓█",
                "     ▒▓█",
                "    ░▒▓█",
                "   ░▒▓█ ",
                "  ░▒▓█  ",
                " ░▒▓█   ",
                "░▒▓█",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "█",
                "░",
                "",
                "",
                "",
                "",
                "░    ",
                "░█   ",
                "░    ",
                "     ",
                "     ",
                "",
                "     ",
                "░    ",
                "░░█  ",
                "░    ",
                "     ",
                "",
                "     ",
                "     ",
                "░    ",
                "░░░█ ",
                "░",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "█░░░░░░░",
                "▓█░░░░░░",
                "▒▓█░░░░░",
                "░▒▓█░░░░",
                "░░▒▓█░░░",
                "░░░▒▓█░░",
                "░░░░▒▓█░",
                "░░░░░▒▓█",
                "░░░░░░▒▓",
                "░░░░░░░▒",
                "░░░░░░░░",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "█     ░",
                " ░   ▒ ",
                "  ▒ ▓  ",
                "   ▓█  ",
                "    ",
                "░     █",
                "▒   ░  ",
                "▓ ▒    ",
                "█▓",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "   ░░░",
                " ░▒▒▒░",
                " ░▒▒▒░",
                "   ░░░",
                "   ",
                "  ▒▒▒▒▒",
                " ▒▓▓▓▓▒",
                "▒▓▓█▓▓▒",
                " ▒▓▓▓▓▒",
                "  ▒▒▒▒▒",
                "  ",
                "    █",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "    █",
                "    █",
                "    █",
                "    ",
                "  █ █ █",
                "    ",
                "█       ",
                "█       ",
                "█       ",
                "    ",
                "  █ █ █",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // Claude 4 Opus
            frames: vec![
                "   ░",
                "  ░▒░",
                " ░▒▓▒░",
                "░▒▓█▓▒░",
                " ░▒▓▒░",
                "  ░▒░",
                "   ░",
                "   ",
                "  ▒▒▒",
                " ▒▓█▓▒",
                "  ▒▒▒",
                "   ",
                "   █",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // o3
            frames: vec!["█   █", "▓ █ ▓", " ▒▒▒ ", "  ░  ", " ▒▒▒ ", "▓ █ ▓"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // o3
            frames: vec!["░", "▒░", "▓▒░", "█▓▒░", " ░▒▓", "  ░▒", "   ░"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // o3
            frames: vec!["░▒▓█▓▒", "▒▓█▓▒░", "▓█▓▒░▒", "█▓▒░▒▓", "▓▒░▒▓█", "▒░▒▓█▓"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // sucralose
            frames: vec!["░ ", "▒░", "▓▒", "█▓", "▓█", "▒▓", " ▒"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // sucralose
                "▁▄█",
                "▁▅🭶",
                "▂▆🭷",
                "▃▇🭸",
                "▄█🭹",
                "▅🭶🭺",
                "▆🭷🭻",
                "▇🭸▁",
                "█🭹▁",
                "🭶🭺▂",
                "🭷🭻▃",
                "🭸▁▄",
                "🭹▁▅",
                "🭺▂▆",
                "🭻▃▇",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(100),
        },
        Spinner {
            frames: vec![
                // 0528
                "🮤", "🮥", "🮦", "🮧", "🮨", "🮩", "🮪", "🮫", "🮬", "🮭", "🮮",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // opus 3
                "🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "🮮🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭",
                "🮭🮮🮤🮥🮦🮧🮨🮩🮪🮫🮬",
                "🮬🮭🮮🮤🮥🮦🮧🮨🮩🮪🮫",
                "🮫🮬🮭🮮🮤🮥🮦🮧🮨🮩🮪",
                "🮪🮫🮬🮭🮮🮤🮥🮦🮧🮨🮩",
                "🮩🮪🮫🮬🮭🮮🮤🮥🮦🮧🮨",
                "🮨🮩🮪🮫🮬🮭🮮🮤🮥🮦🮧",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // opus 3
                "🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                " 🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "  🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "   🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "    🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "     🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "      🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "       🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "        🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "          🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "           🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
                "            🮤🮥🮦🮧🮨🮩🮪🮫🮬🮭🮮",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // opus 3
                "🮤      🮬",
                " 🮥    🮭 ",
                "  🮦  🮮  ",
                "   🮧🮤   ",
                "    🮨🮥  ",
                "     🮩🮦 ",
                "    🮪🮧  ",
                "   🮫🮨   ",
                "  🮬  🮩  ",
                "  🮭    🮪 ",
                " 🮮      🮫",
                " 🮤      🮬",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // o3
                "🮤",
                "🮥🮤",
                "🮦🮥🮤",
                "🮧🮦🮥🮤",
                "🮨🮧🮦🮥🮤",
                "🮩🮨🮧🮦🮥",
                "🮪🮩🮨🮧🮦",
                "🮫🮪🮩🮨🮧",
                "🮬🮫🮪🮩🮨",
                "🮭🮬🮫🮪🮩",
                "🮮🮭🮬🮫🮪",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // o3, sucralose
                "🮤   🮮",
                "🮥   🮤",
                "🮦   🮥",
                "🮧   🮦",
                "🮨   🮧",
                "🮩   🮨",
                "🮪   🮩",
                "🮫   🮪",
                "🮬   🮫",
                "🮭   🮬",
                "🮮   🮭",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // o3
                "🮤🮩🮮",
                "🮥🮪🮧",
                "🮦🮫🮨",
                "🮧🮤🮩",
                "🮨🮥🮪",
                "🮩🮦🮫",
                "🮪🮧🮤",
                "🮫🮨🮥",
                "🮬🮩🮦",
                "🮭🮪🮧",
                "🮮🮫🮨",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // o3
                "🮤🮨", "🮥🮩", "🮦🮪", "🮧🮫", "🮨🮬", "🮩🮭", "🮪🮮", "🮫🮤", "🮬🮥", "🮭🮦", "🮮🮧",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // o3
                "🮤", "🮥", "🮦", "🮧", "🮨", "🮩", "🮪", "🮫", "🮬", "🮭", "🮮",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // 4 opus, sucralose
                "       🮤",
                "      🮤🮥",
                "     🮤🮥🮦",
                "    🮤🮥🮦🮧",
                "   🮤🮥🮦🮧🮨",
                "  🮤🮥🮦🮧🮨🮩",
                " 🮤🮥🮦🮧🮨🮩🮪",
                "🮤🮥🮦🮧🮨🮩🮪🮫",
                "🮥🮦🮧🮨🮩🮪🮫🮬",
                " 🮦🮧🮨🮩🮪🮫🮬",
                "  🮧🮨🮩🮪🮫🮬",
                "   🮨🮩🮪🮫🮬",
                "    🮩🮪🮫🮬",
                "     🮪🮫🮬",
                "      🮫🮬",
                "       🮬",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // 4 opus
                "🮤      🮮",
                " 🮥    🮭 ",
                "  🮦  🮬  ",
                "   🮧🮫   ",
                "    🮪    ",
                "   🮫🮧   ",
                "  🮬  🮦  ",
                " 🮭    🮥 ",
                "🮮      🮤",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            frames: vec![
                // 4 opus
                "🮤  🮦    🮤",
                " 🮥  🮧  🮥  ",
                "  🮦  🮨🮦   ",
                "   🮧 🮩🮧   ",
                "    🮨🮪    ",
                "   🮩 🮫🮩   ",
                "  🮪  🮬🮪   ",
                " 🮫    🮫   ",
                "🮬      🮬",
            ]
            .into_iter()
            .map(String::from)
            .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // 4 opus, sucralose
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
        Spinner {
            frames: vec![
                // sucralose
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
                // external
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
            // external
            frames: vec!["⢄", "⢂", "⢁", "⡁", "⡈", "⡐", "⡠"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // external
            frames: vec!["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // sucralose
            frames: vec!["││", "╱╲", "──", "╲╱"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // sucralose
            frames: vec!["│╱", "╱─", "─╲", "╲│"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
        Spinner {
            // sucralose
            frames: vec!["│─", "╱╲", "─│", "╲╱"]
                .into_iter()
                .map(String::from)
                .collect(),
            interval: Duration::from_millis(150),
        },
    ]
});

pub static LOADING_MESSAGES: Lazy<Vec<String>> = Lazy::new(|| {
    vec![
        "Ministering...",
        "Communing...",
        "Beckoning...",
        "Dreaming...",
        "Crossing...",
        "Ascending...",
        "Evolving...",
        "Conjuring...",
        "Weaving...",
        "Summoning...",
        "Channeling...",
        "Deciphering...",
        "Illuminating...",
        "Kindling...",
        "Gathering...",
        "Listening...",
        "Scribing...",
        "Painting...",
        "Rousing...",
        "Stirring...",
        "Flickering...",
        "Spiraling...",
        "Incanting...",
        "Awakening...",
        "Manifesting...",
        "Transcending...",
        "Hurling...",
        "Revolving...",
        "Enchanting...",
        "Levitating...",
        "Hypnotizing...",
        "Dissolving...",
        "Discerning...",
        "Shattering...",
        "Crystallizing...",
        "Cascading...",
        "Twisting...",
        "Teleporting...",
        "Inverting...",
        "Charming...",
        "Bewitching...",
        "Unraveling...",
    ]
    .into_iter()
    .map(String::from)
    .collect()
});

/// Selects a random spinner from the predefined list.
pub fn get_random_spinner() -> Spinner {
    let mut rng = rand::thread_rng();
    SPINNERS
        .choose(&mut rng)
        .cloned()
        .expect("Spinner list should not be empty")
}

/// Selects a random loading message from the predefined list.
pub fn get_random_loading_message() -> String {
    let mut rng = rand::thread_rng();
    LOADING_MESSAGES
        .choose(&mut rng)
        .cloned()
        .expect("Loading messages list should not be empty")
}

/// Displays the provided spinner animation until a stop signal is received.
pub async fn run_spinner(
    spinner: Spinner,
    message: String,
    margin: String,
    mut rx: watch::Receiver<bool>,
) -> Result<()> {
    let mut i = 0;
    let mut interval = tokio::time::interval(spinner.interval);
    let mut stdout = stdout();
    let start_time = tokio::time::Instant::now();

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
                let elapsed_seconds = start_time.elapsed().as_secs();

                let time_str = format!("({}s)", elapsed_seconds);
                let prefix = if elapsed_seconds < 10 { "  " } else { " " };
                // let total_width = 11;
                let total_width = 10;
                let current_width = prefix.len() + time_str.len();

                let time_display_block = if current_width < total_width {
                    let suffix = " ".repeat(total_width - current_width);
                    format!("{}{}{}", prefix, time_str, suffix)
                } else {
                    format!("{}{} ", prefix, time_str)
                };

                execute!(
                    stdout,
                    cursor::MoveToColumn(0),
                    Clear(ClearType::CurrentLine),
                    Print(format!("{}{}{}{}", margin, message, time_display_block, frame))
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
