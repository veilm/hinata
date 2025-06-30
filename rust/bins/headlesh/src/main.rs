use clap::{Parser, Subcommand};
use daemonize::Daemonize;
use dirs;
use fs2::FileExt;
use log::{error, info, LevelFilter};
use nix::errno::Errno;
use nix::sys::{signal::kill, stat};
use nix::unistd::{mkfifo, Pid};
use signal_hook::{consts::SIGTERM, iterator::Signals};
use simplelog::{Config, WriteLogger};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::io::AsRawFd;
use std::path::Path;
use std::process::{exit, Command, Stdio};

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
        Commands::Create { session_id, shell } => {
            // 1. Validating the session_id to prevent path traversal.
            if session_id.contains('/') || session_id.contains("..") {
                eprintln!("Error: session_id cannot contain '/' or '..'");
                exit(1);
            }

            // 2. Creating the session directory under '/tmp/headlesh_sessions/'.
            let session_path = Path::new(SESSION_DIR).join(session_id);
            if let Err(e) = fs::create_dir_all(&session_path) {
                eprintln!(
                    "Error creating session directory {}: {}",
                    session_path.display(),
                    e
                );
                exit(1);
            }

            // Prepare log directory path
            let log_dir = match dirs::data_dir() {
                Some(path) => path.join("hinata/headlesh").join(session_id),
                None => {
                    eprintln!("Error: could not determine data directory for logs.");
                    exit(1);
                }
            };
            if let Err(e) = fs::create_dir_all(&log_dir) {
                eprintln!("Error creating log directory {}: {}", log_dir.display(), e);
                exit(1);
            }

            // 5. Using the 'daemonize' crate to fork the process into the background.
            let daemonize = Daemonize::new().working_directory(&session_path);

            println!("Starting session '{}'...", session_id);

            match daemonize.start() {
                Ok(_) => {
                    // In daemon process

                    // 4. Setting up logging to a file like '~/.local/share/hinata/headlesh/<session_id>/server.log'.
                    let log_file_path = log_dir.join("server.log");
                    let log_file = match File::create(&log_file_path) {
                        Ok(file) => file,
                        Err(_) => {
                            // Can't log, can't print, just exit.
                            exit(1);
                        }
                    };
                    if WriteLogger::init(LevelFilter::Info, Config::default(), log_file).is_err() {
                        // same problem here
                        exit(1);
                    };

                    info!("Daemon for session '{}' started.", session_id);
                    let _ = shell; // This will be used when spawning the shell

                    // 3. Creating and locking a 'pid.lock' file within the session directory. Exit if the lock is already held.
                    let lock_path = Path::new("pid.lock"); // we are in session_path
                    let mut file = match File::create(&lock_path) {
                        Ok(file) => file,
                        Err(e) => {
                            error!("Failed to create lock file: {}", e);
                            exit(1);
                        }
                    };

                    if file.try_lock_exclusive().is_err() {
                        error!("Session already running or cannot lock file. Exiting.");
                        exit(1);
                    }

                    // 6. In the daemon, writing the new PID to the 'pid.lock' file.
                    let pid = std::process::id().to_string();
                    if let Err(e) = file.write_all(pid.as_bytes()) {
                        error!("Failed to write PID to lock file: {}", e);
                        exit(1);
                    }
                    if let Err(e) = file.flush() {
                        error!("Failed to flush PID to lock file: {}", e);
                        exit(1);
                    }
                    info!("PID {} written to lock file.", pid);

                    let cmd_fifo_path = Path::new("cmd.fifo");
                    match mkfifo(cmd_fifo_path, stat::Mode::S_IRWXU) {
                        Ok(_) => info!("Command FIFO created."),
                        Err(e) => {
                            error!("Failed to create command FIFO: {}", e);
                            exit(1);
                        }
                    }

                    let shell_to_spawn = shell.as_deref().unwrap_or("bash");
                    info!("Spawning shell: {}", shell_to_spawn);

                    let log_stdout = match File::options().append(true).open(&log_file_path) {
                        Ok(f) => f,
                        Err(e) => {
                            error!("Could not reopen log file for shell stdout: {}", e);
                            exit(1);
                        }
                    };
                    let log_stderr = match log_stdout.try_clone() {
                        Ok(f) => f,
                        Err(e) => {
                            error!("Could not clone file handle for shell stderr: {}", e);
                            exit(1);
                        }
                    };

                    let mut child = match Command::new(shell_to_spawn)
                        .stdin(Stdio::piped())
                        .stdout(Stdio::from(log_stdout))
                        .stderr(Stdio::from(log_stderr))
                        .spawn()
                    {
                        Ok(child) => child,
                        Err(e) => {
                            error!("Failed to spawn shell: {}", e);
                            exit(1);
                        }
                    };

                    let _shell_stdin = child.stdin.take().expect("Failed to open shell's stdin");
                    info!("Shell process spawned with PID: {}", child.id());

                    // Set up signal handling for graceful shutdown.
                    let mut signals = match Signals::new(&[SIGTERM]) {
                        Ok(s) => s,
                        Err(e) => {
                            error!("Failed to register signal handler: {}", e);
                            exit(1);
                        }
                    };

                    info!("Entering main loop to listen on command FIFO.");
                    'main_loop: loop {
                        // This loop will block on File::open, making it unable to receive signals until a client connects.
                        // This is a known issue to be addressed later.
                        let fifo_file = match File::open(cmd_fifo_path) {
                            Ok(file) => file,
                            Err(e) => {
                                error!(
                                    "Failed to open command FIFO for reading, shutting down: {}",
                                    e
                                );
                                break 'main_loop;
                            }
                        };

                        let mut reader = BufReader::new(fifo_file);
                        let mut buffer = String::new();
                        match reader.read_line(&mut buffer) {
                            Ok(0) => {
                                // EOF, another client can connect.
                            }
                            Ok(_) => {
                                info!("Received from FIFO: {}", buffer.trim());
                                // In the future, this command will be processed.
                            }
                            Err(e) => {
                                error!("Error reading from FIFO: {}", e);
                            }
                        }

                        // Check for shutdown signal after each command or connection attempt.
                        for signal in signals.pending() {
                            if signal == SIGTERM {
                                info!("Received SIGTERM, shutting down.");
                                break 'main_loop;
                            }
                        }
                    }

                    drop(file);
                    info!("Cleaning up session directory.");
                    if let Err(e) = fs::remove_dir_all(&session_path) {
                        error!(
                            "Failed to remove session directory {}: {}",
                            session_path.display(),
                            e
                        );
                    }
                }
                Err(e) => {
                    eprintln!("Error: failed to start daemon: {}", e);
                    exit(1);
                }
            }
        }
        Commands::Exec { session_id } => {
            // 1. Read everything from stdin into a string.
            let mut command = String::new();
            if let Err(e) = std::io::stdin().read_to_string(&mut command) {
                eprintln!("Error reading command from stdin: {}", e);
                exit(1);
            }

            // 2. Construct the path to the target session's 'cmd.fifo'.
            let fifo_path = Path::new(SESSION_DIR).join(session_id).join("cmd.fifo");

            // 3. Open the FIFO for writing. If it doesn't exist, print a helpful error message.
            match File::options().write(true).open(&fifo_path) {
                Ok(mut fifo_file) => {
                    // 4. Write the string read from stdin to the FIFO.
                    if let Err(e) = fifo_file.write_all(command.as_bytes()) {
                        eprintln!("Error sending command to session '{}': {}", session_id, e);
                        exit(1);
                    }
                }
                Err(e) => {
                    eprintln!(
                        "Error connecting to session '{}': {}. Is the session running?",
                        session_id, e
                    );
                    exit(1);
                }
            }
        }
        Commands::Exit { session_id } => {
            let lock_path = Path::new(SESSION_DIR).join(session_id).join("pid.lock");

            let pid_str = match fs::read_to_string(&lock_path) {
                Ok(s) => s,
                Err(_) => {
                    eprintln!("Error: session '{}' not found.", session_id);
                    exit(1);
                }
            };

            let pid_val = match pid_str.trim().parse::<i32>() {
                Ok(p) => p,
                Err(_) => {
                    eprintln!(
                        "Error: malformed PID in lock file for session '{}'.",
                        session_id
                    );
                    exit(1);
                }
            };

            let pid = Pid::from_raw(pid_val);

            match kill(pid, nix::sys::signal::Signal::SIGTERM) {
                Ok(_) => {
                    println!("Session '{}' terminated.", session_id);
                }
                Err(Errno::ESRCH) => {
                    eprintln!(
                        "Error: session '{}' not found (stale lock file).",
                        session_id
                    );
                    exit(1);
                }
                Err(e) => {
                    eprintln!("Error terminating session '{}': {}", session_id, e);
                    exit(1);
                }
            }
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
