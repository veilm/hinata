use clap::{Parser, Subcommand};
use headlesh::{error::Error as HeadleshError, list, Session};
use std::io::{self, Read};
use std::process::exit;

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
    let rt = tokio::runtime::Runtime::new().unwrap();
    let cli = Cli::parse();

    match &cli.command {
        Commands::Create { session_id, shell } => {
            let result = rt.block_on(async {
                let session = Session::create(session_id.clone()).await?;
                session.spawn(shell.clone()).await
            });
            match result {
                Ok(()) => {
                    println!("Successfully created and spawned session '{}'.", session_id);
                }
                Err(e) => {
                    eprintln!("Error creating or spawning session '{}': {}", session_id, e);
                    exit(1);
                }
            }
        }
        Commands::Exec { session_id } => {
            let session = Session {
                session_id: session_id.clone(),
            };

            let mut command = String::new();
            if let Err(e) = io::stdin().read_to_string(&mut command) {
                eprintln!("Error reading command from stdin: {}", e);
                exit(1);
            }

            match rt.block_on(session.exec(&command)) {
                Ok(status) => {
                    exit(status.code().unwrap_or(1));
                }
                Err(e) => {
                    if let HeadleshError::SessionNotFound = e {
                        eprintln!("Error: session '{}' not found. Is it running?", session_id);
                    } else {
                        eprintln!("Error executing command in session '{}': {}", session_id, e);
                    }
                    exit(1);
                }
            }
        }
        Commands::Exit { session_id } => {
            let session = Session {
                session_id: session_id.clone(),
            };
            match rt.block_on(session.exit()) {
                Ok(_) => {
                    println!("Termination signal sent to session '{}'.", session_id);
                }
                Err(e) => {
                    if let HeadleshError::SessionNotFound = e {
                        eprintln!(
                            "Error connecting to session '{}': {}. Is the session running?",
                            session_id, e
                        );
                    } else {
                        eprintln!("Error terminating session '{}': {}", session_id, e);
                    }
                    exit(1);
                }
            }
        }
        Commands::List => match rt.block_on(list()) {
            Ok(sessions) => {
                if sessions.is_empty() {
                    println!("No active sessions found.");
                } else {
                    println!("Active sessions:");
                    for session in sessions {
                        println!("  - {}", session);
                    }
                }
            }
            Err(e) => {
                eprintln!("Error listing sessions: {}", e);
                exit(1);
            }
        },
    }
}
