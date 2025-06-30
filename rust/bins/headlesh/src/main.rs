use clap::{Parser, Subcommand};
use nix::errno::Errno;
use nix::sys::signal::kill;
use nix::unistd::Pid;
use std::fs;
use std::path::Path;

const SESSION_DIR: &str = "/tmp/headlesh_sessions";

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
            let session_dir = Path::new(SESSION_DIR);
            let entries = match fs::read_dir(session_dir) {
                Ok(entries) => entries,
                Err(ref e) if e.kind() == std::io::ErrorKind::NotFound => {
                    // Directory doesn't exist, so there are no sessions. This is a clean exit.
                    return;
                }
                Err(e) => {
                    eprintln!("Error reading session directory {}: {}", SESSION_DIR, e);
                    return;
                }
            };

            for entry in entries {
                let entry = match entry {
                    Ok(e) => e,
                    Err(e) => {
                        eprintln!(
                            "Warning: skipping unreadable entry in session directory: {}",
                            e
                        );
                        continue;
                    }
                };

                if !entry.file_type().map_or(false, |ft| ft.is_dir()) {
                    continue; // We only care about directories
                }

                let session_id = entry.file_name();
                let session_id_str = session_id.to_string_lossy();
                let pid_path = entry.path().join("pid.lock");

                let pid_str = match fs::read_to_string(&pid_path) {
                    Ok(s) => s,
                    Err(_) => {
                        eprintln!(
                            "Warning: unreadable 'pid.lock' for session '{}'. Skipping.",
                            session_id_str
                        );
                        continue;
                    }
                };

                let pid_val = match pid_str.trim().parse::<i32>() {
                    Ok(p) => p,
                    Err(_) => {
                        eprintln!(
                            "Warning: malformed PID in 'pid.lock' for session '{}'. Skipping.",
                            session_id_str
                        );
                        continue;
                    }
                };

                let pid = Pid::from_raw(pid_val);
                match kill(pid, None) {
                    Ok(_) => {
                        println!("Session: {}, PID: {}", session_id_str, pid);
                    }
                    Err(Errno::ESRCH) => {
                        // Stale session, process is dead. Do nothing.
                    }
                    Err(e) => {
                        eprintln!(
                            "Error checking status of session '{}': {}",
                            session_id_str, e
                        );
                    }
                }
            }
        }
    }
}
