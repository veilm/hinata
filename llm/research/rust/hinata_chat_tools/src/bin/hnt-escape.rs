use clap::Parser;
use std::io::{self, Read, Write};

/// Escape or unescape stdin content using hinata_escape.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Unescape the input instead of escaping.
    #[arg(short, long)]
    unescape: bool,
}

fn main() -> io::Result<()> {
    let args = Args::parse();

    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;

    let output = if args.unescape {
        hinata_chat_tools::unescape(&input)
    } else {
        hinata_chat_tools::escape(&input)
    };

    io::stdout().write_all(output.as_bytes())?;

    Ok(())
}