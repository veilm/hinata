use clap::{Parser, Subcommand};

/// A simple remote shell daemon.
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Create a new session.
    Create {
        /// The ID of the session to create.
        session_id: String,
        /// The shell to use for the new session.
        #[arg(short, long)]
        shell: Option<String>,
    },
    /// Execute a command in a session.
    Exec {
        /// The ID of the session.
        session_id: String,
    },
    /// Terminate a session.
    Exit {
        /// The ID of the session to terminate.
        session_id: String,
    },
    /// List all running sessions.
    List,
}

fn main() {
    let cli = Cli::parse();

    match &cli.command {
        Commands::Create { session_id, shell } => match shell {
            Some(s) => println!(
                "'create' command called for session_id: {} with shell: {}",
                session_id, s
            ),
            None => println!(
                "'create' command called for session_id: {} with default shell",
                session_id
            ),
        },
        Commands::Exec { session_id } => {
            println!("'exec' command called for session_id: {}", session_id);
        }
        Commands::Exit { session_id } => {
            println!("'exit' command called for session_id: {}", session_id);
        }
        Commands::List => {
            println!("'list' command called");
        }
    }
}
