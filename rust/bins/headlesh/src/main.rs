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
use std::path::{Path, PathBuf};
use std::process::{exit, Command, Stdio};
use std::thread;
use tempfile::NamedTempFile;

const SESSION_DIR: &str = "/tmp/headlesh_sessions";
const HEADLESH_EXIT_CMD_PAYLOAD: &str = "__HEADLESH_INTERNAL_EXIT_CMD__";

struct FifoCleaner {
    paths: Vec<PathBuf>,
}

impl Drop for FifoCleaner {
    fn drop(&mut self) {
        for path in &self.paths {
            if path.exists() {
                if let Err(e) = fs::remove_file(path) {
                    eprintln!("Warning: failed to remove FIFO at {:?}: {}", path, e);
                }
            }
        }
    }
}

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

                    let mut shell_stdin = child.stdin.take().expect("Failed to open shell's stdin");
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
                        let mut out_fifo_path = String::new();
                        let mut err_fifo_path = String::new();
                        let mut status_fifo_path = String::new();

                        match reader.read_line(&mut out_fifo_path) {
                            Ok(0) => {
                                info!("Client disconnected without sending a command.");
                                continue 'main_loop;
                            }
                            Ok(_) => (),
                            Err(e) => {
                                error!("Error reading from FIFO: {}", e);
                                break 'main_loop;
                            }
                        }

                        match reader.read_line(&mut err_fifo_path) {
                            Ok(0) => {
                                error!("Incomplete command from client.");
                                continue 'main_loop;
                            }
                            Ok(_) => (),
                            Err(e) => {
                                error!("Error reading from FIFO: {}", e);
                                break 'main_loop;
                            }
                        }

                        match reader.read_line(&mut status_fifo_path) {
                            Ok(0) => {
                                error!("Incomplete command from client.");
                                continue 'main_loop;
                            }
                            Ok(_) => (),
                            Err(e) => {
                                error!("Error reading from FIFO: {}", e);
                                break 'main_loop;
                            }
                        }

                        let mut command_script = String::new();
                        if let Err(e) = reader.read_to_string(&mut command_script) {
                            error!("Error reading command script from FIFO: {}", e);
                            break 'main_loop;
                        }

                        let out_fifo_path = out_fifo_path.trim();
                        let err_fifo_path = err_fifo_path.trim();
                        let status_fifo_path = status_fifo_path.trim();

                        if command_script == HEADLESH_EXIT_CMD_PAYLOAD {
                            info!("Exit command received, shutting down.");
                            break 'main_loop;
                        }

                        info!("Received command, executing...");

                        let mut temp_script_file = match NamedTempFile::new() {
                            Ok(file) => file,
                            Err(e) => {
                                error!("Failed to create temp file for script: {}", e);
                                continue 'main_loop;
                            }
                        };

                        if let Err(e) = temp_script_file.write_all(command_script.as_bytes()) {
                            error!("Failed to write script to temp file: {}", e);
                            continue 'main_loop;
                        }

                        let temp_script_path = temp_script_file.path().to_string_lossy();
                        let shell_command = format!(
                            "{{ . {script_path}; EXIT_STATUS=$?; }} >{out_fifo} 2>{err_fifo}; echo $EXIT_STATUS >{status_fifo}; rm -f {script_path}\n",
                            script_path = temp_script_path,
                            out_fifo = out_fifo_path,
                            err_fifo = err_fifo_path,
                            status_fifo = status_fifo_path
                        );

                        if let Err(e) = shell_stdin.write_all(shell_command.as_bytes()) {
                            error!(
                                "Failed to write command to shell's stdin: {}. Shutting down.",
                                e
                            );
                            break 'main_loop;
                        }

                        // Check for shutdown signal after each command or connection attempt.
                        let mut shutdown_signal_received = false;
                        for signal in signals.pending() {
                            if signal == SIGTERM {
                                info!("Received SIGTERM, shutting down.");
                                shutdown_signal_received = true;
                                break;
                            }
                        }
                        if shutdown_signal_received {
                            break 'main_loop;
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
            // Generate unique paths for client FIFOs.
            let pid = std::process::id();
            let out_fifo_path = Path::new("/tmp").join(format!("headlesh_out_{}", pid));
            let err_fifo_path = Path::new("/tmp").join(format!("headlesh_err_{}", pid));
            let status_fifo_path = Path::new("/tmp").join(format!("headlesh_status_{}", pid));

            // Set up a cleaner to remove the FIFOs on exit.
            let _cleaner = FifoCleaner {
                paths: vec![
                    out_fifo_path.clone(),
                    err_fifo_path.clone(),
                    status_fifo_path.clone(),
                ],
            };

            // Create the client-side FIFOs.
            let fifo_mode = stat::Mode::S_IRWXU;
            if let Err(e) = mkfifo(&out_fifo_path, fifo_mode) {
                eprintln!("Error creating out FIFO: {}", e);
                exit(1);
            }
            if let Err(e) = mkfifo(&err_fifo_path, fifo_mode) {
                eprintln!("Error creating err FIFO: {}", e);
                exit(1);
            }
            if let Err(e) = mkfifo(&status_fifo_path, fifo_mode) {
                eprintln!("Error creating status FIFO: {}", e);
                exit(1);
            }

            // Read command from stdin.
            let mut command = String::new();
            if let Err(e) = std::io::stdin().read_to_string(&mut command) {
                eprintln!("Error reading command from stdin: {}", e);
                exit(1);
            }

            // Construct the payload with FIFO paths and the command.
            let payload = format!(
                "{}\n{}\n{}\n{}",
                out_fifo_path.display(),
                err_fifo_path.display(),
                status_fifo_path.display(),
                command
            );

            // Send the payload to the session's command FIFO.
            let fifo_path = Path::new(SESSION_DIR).join(session_id).join("cmd.fifo");
            match File::options().write(true).open(&fifo_path) {
                Ok(mut fifo_file) => {
                    if let Err(e) = fifo_file.write_all(payload.as_bytes()) {
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

            // Spawn threads to listen on out/err FIFOs and pipe to stdout/stderr.
            let out_fifo_reader = match File::open(&out_fifo_path) {
                Ok(f) => f,
                Err(e) => {
                    eprintln!("Failed to open output FIFO for reading: {}", e);
                    exit(1);
                }
            };
            let err_fifo_reader = match File::open(&err_fifo_path) {
                Ok(f) => f,
                Err(e) => {
                    eprintln!("Failed to open error FIFO for reading: {}", e);
                    exit(1);
                }
            };

            let out_handle = thread::spawn(move || {
                let mut reader = BufReader::new(out_fifo_reader);
                if let Err(e) = std::io::copy(&mut reader, &mut std::io::stdout()) {
                    eprintln!("Error streaming output: {}", e);
                }
            });

            let err_handle = thread::spawn(move || {
                let mut reader = BufReader::new(err_fifo_reader);
                if let Err(e) = std::io::copy(&mut reader, &mut std::io::stderr()) {
                    eprintln!("Error streaming error output: {}", e);
                }
            });

            out_handle.join().expect("stdout thread panicked");
            err_handle.join().expect("stderr thread panicked");

            // Read the exit status from the status FIFO.
            let mut status_str = String::new();
            let mut status_fifo_file = match File::open(&status_fifo_path) {
                Ok(f) => f,
                Err(e) => {
                    eprintln!("Failed to open status FIFO for reading: {}", e);
                    exit(1);
                }
            };
            if let Err(e) = status_fifo_file.read_to_string(&mut status_str) {
                eprintln!("Failed to read exit status: {}", e);
                exit(1);
            }

            let exit_code = status_str.trim().parse::<i32>().unwrap_or(1);
            exit(exit_code);
        }
        Commands::Exit { session_id } => {
            let payload = format!(
                "/dev/null\n/dev/null\n/dev/null\n{}",
                HEADLESH_EXIT_CMD_PAYLOAD
            );

            let fifo_path = Path::new(SESSION_DIR).join(session_id).join("cmd.fifo");
            match File::options().write(true).open(&fifo_path) {
                Ok(mut fifo_file) => {
                    if let Err(e) = fifo_file.write_all(payload.as_bytes()) {
                        eprintln!(
                            "Error sending exit command to session '{}': {}",
                            session_id, e
                        );
                        exit(1);
                    }
                    println!("Session '{}' terminated.", session_id);
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
                let session_path = entry.path();
                let lock_path = session_path.join("pid.lock");

                // Open lock file for writing. This will not truncate the file.
                let lock_file = match File::options().write(true).open(&lock_path) {
                    Ok(f) => f,
                    Err(_) => {
                        // If we can't open the lock file (e.g., doesn't exist, permissions),
                        // we can't determine session status. Treat as stale/invalid and skip.
                        continue;
                    }
                };

                match lock_file.try_lock_exclusive() {
                    Ok(_) => {
                        // Lock acquired, so the session is stale.
                        drop(lock_file); // Explicitly release lock before cleanup.

                        if session_id_str.starts_with("test-") {
                            println!("Cleaning up stale test session '{}'", session_id_str);
                            if let Err(e) = fs::remove_dir_all(&session_path) {
                                eprintln!(
                                    "Warning: failed to remove stale session directory {}: {}",
                                    session_path.display(),
                                    e
                                );
                            }
                            if let Some(data_dir) = dirs::data_dir() {
                                let log_dir = data_dir.join("hinata/headlesh").join(session_id);
                                if log_dir.exists() {
                                    if let Err(e) = fs::remove_dir_all(&log_dir) {
                                        eprintln!(
                                            "Warning: failed to remove stale session log directory {}: {}",
                                            log_dir.display(),
                                            e
                                        );
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        if e.raw_os_error() == Some(11) {
                            // EWOULDBLOCK
                            // Failed to acquire lock, session MIGHT be active.
                            // Read PID and verify process exists.
                            let pid_str = match fs::read_to_string(&lock_path) {
                                Ok(s) => s,
                                Err(_) => {
                                    // This could happen in a race condition where the session terminates
                                    // after we fail to lock but before we read.
                                    eprintln!(
                                        "Warning: session '{}' seems active but could not read pid.lock.",
                                        session_id_str
                                    );
                                    continue;
                                }
                            };

                            let pid_val = match pid_str.trim().parse::<i32>() {
                                Ok(p) => p,
                                Err(_) => {
                                    eprintln!(
                                        "Warning: malformed PID in 'pid.lock' for session '{}'.",
                                        session_id_str
                                    );
                                    continue;
                                }
                            };
                            let pid = Pid::from_raw(pid_val);

                            match kill(pid, None) {
                                Ok(_) => {
                                    // Process exists, session is active.
                                    println!("Session: {}, PID: {}", session_id_str, pid);
                                }
                                Err(Errno::ESRCH) => {
                                    // Process doesn't exist, session is stale.
                                    drop(lock_file); // Explicitly release lock before cleanup.

                                    if session_id_str.starts_with("test-") {
                                        println!(
                                            "Cleaning up stale test session '{}'",
                                            session_id_str
                                        );
                                        if let Err(e) = fs::remove_dir_all(&session_path) {
                                            eprintln!(
                                                "Warning: failed to remove stale session directory {}: {}",
                                                session_path.display(),
                                                e
                                            );
                                        }
                                        if let Some(data_dir) = dirs::data_dir() {
                                            let log_dir =
                                                data_dir.join("hinata/headlesh").join(session_id);
                                            if log_dir.exists() {
                                                if let Err(e) = fs::remove_dir_all(&log_dir) {
                                                    eprintln!(
                                                        "Warning: failed to remove stale session log directory {}: {}",
                                                        log_dir.display(),
                                                        e
                                                    );
                                                }
                                            }
                                        }
                                    }
                                }
                                Err(kill_error) => {
                                    // Another error from kill, assume active to be safe.
                                    eprintln!("Warning: could not verify process status for session '{}', assuming active: {}", session_id_str, kill_error);
                                    println!("Session: {}, PID: {}", session_id_str, pid);
                                }
                            }
                        } else {
                            // Any other error means we can't determine lock status,
                            // but we should assume it's stale and try to clean up.
                            eprintln!(
                                "Warning: An error occurred while trying to lock pid.lock for session '{}', assuming stale: {}",
                                session_id_str, e
                            );
                            drop(lock_file); // Explicitly release lock before cleanup.

                            if session_id_str.starts_with("test-") {
                                println!("Cleaning up stale test session '{}'", session_id_str);
                                if let Err(e) = fs::remove_dir_all(&session_path) {
                                    eprintln!(
                                        "Warning: failed to remove stale session directory {}: {}",
                                        session_path.display(),
                                        e
                                    );
                                }
                                if let Some(data_dir) = dirs::data_dir() {
                                    let log_dir = data_dir.join("hinata/headlesh").join(session_id);
                                    if log_dir.exists() {
                                        if let Err(e) = fs::remove_dir_all(&log_dir) {
                                            eprintln!(
                                                "Warning: failed to remove stale session log directory {}: {}",
                                                log_dir.display(),
                                                e
                                            );
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
