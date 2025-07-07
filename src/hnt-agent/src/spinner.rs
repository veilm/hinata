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
        "Lining...",
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
        "Usurping...",
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
    mut rx: watch::Receiver<bool>,
) -> Result<()> {
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
                    Print(format!("{} ", message)),
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
