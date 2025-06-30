pub mod error;

use crate::error::Error;
use daemonize::Daemonize;
use dirs;
use fs2::FileExt;
use log::info;
use nix::sys::stat;
use nix::unistd::mkfifo;
use simplelog::{Config, LevelFilter, WriteLogger};
use std::env;
use std::fs::{self, File};
use std::io::Write;
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use tempfile::NamedTempFile;
use tokio::io::AsyncReadExt;

pub const SESSION_DIR: &str = "/tmp/headlesh_sessions";
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
pub struct Session {
    pub session_id: String,
}

impl Session {
    /// Performs session validation and sets up the required directory structure.
    pub async fn create(session_id: String) -> Result<Self, Error> {
        if session_id.contains('/') || session_id.contains("..") {
            return Err(Error::InvalidSessionId);
        }

        let session_path = Path::new(SESSION_DIR).join(&session_id);
        if session_path.exists() {
            let lock_path = session_path.join("pid.lock");
            if lock_path.exists() {
                let file = File::open(&lock_path)?;
                if file.try_lock_exclusive().is_err() {
                    return Err(Error::SessionAlreadyExists);
                }
            }
        }

        fs::create_dir_all(&session_path)?;

        // Create log directory.
        if let Some(data_dir) = dirs::data_dir() {
            let log_dir = data_dir.join("hinata").join("headlesh").join(&session_id);
            fs::create_dir_all(&log_dir)?;
        }

        Ok(Session { session_id })
    }

    /// Executes a command in the session.
    pub async fn exec(&self, command: &str) -> Result<std::process::ExitStatus, Error> {
        let session_path = Path::new(SESSION_DIR).join(&self.session_id);
        if !session_path.exists() {
            return Err(Error::SessionNotFound);
        }

        let pid = std::process::id();
        let out_fifo_path = Path::new("/tmp").join(format!("headlesh_out_{}", pid));
        let err_fifo_path = Path::new("/tmp").join(format!("headlesh_err_{}", pid));
        let status_fifo_path = Path::new("/tmp").join(format!("headlesh_status_{}", pid));

        let _cleaner = FifoCleaner {
            paths: vec![
                out_fifo_path.clone(),
                err_fifo_path.clone(),
                status_fifo_path.clone(),
            ],
        };

        mkfifo(&out_fifo_path, stat::Mode::S_IRWXU)?;
        mkfifo(&err_fifo_path, stat::Mode::S_IRWXU)?;
        mkfifo(&status_fifo_path, stat::Mode::S_IRWXU)?;

        let payload = format!(
            "{}\n{}\n{}\n{}",
            out_fifo_path.display(),
            err_fifo_path.display(),
            status_fifo_path.display(),
            command
        );

        let fifo_path = session_path.join("cmd.fifo");
        match File::options().write(true).open(&fifo_path) {
            Ok(mut fifo_file) => {
                fifo_file.write_all(payload.as_bytes())?;
            }
            Err(e) => return Err(Error::Io(e)),
        }

        let out_handle = tokio::spawn(async move {
            if let Ok(file) = tokio::fs::File::open(&out_fifo_path).await {
                let mut reader = tokio::io::BufReader::new(file);
                let mut stdout = tokio::io::stdout();
                let _ = tokio::io::copy(&mut reader, &mut stdout).await;
            }
        });

        let err_handle = tokio::spawn(async move {
            if let Ok(file) = tokio::fs::File::open(&err_fifo_path).await {
                let mut reader = tokio::io::BufReader::new(file);
                let mut stderr = tokio::io::stderr();
                let _ = tokio::io::copy(&mut reader, &mut stderr).await;
            }
        });

        out_handle.await.unwrap();
        err_handle.await.unwrap();

        let mut status_str = String::new();
        let mut status_fifo_file = tokio::fs::File::open(&status_fifo_path).await?;
        status_fifo_file.read_to_string(&mut status_str).await?;

        let exit_code = status_str.trim().parse::<i32>().unwrap_or(1);
        Ok(std::process::ExitStatus::from_raw(exit_code))
    }

    /// Sends a termination signal to the session.
    pub async fn exit(&self) -> Result<(), Error> {
        let payload = format!(
            "/dev/null\n/dev/null\n/dev/null\n{}",
            HEADLESH_EXIT_CMD_PAYLOAD
        );

        let fifo_path = Path::new(SESSION_DIR)
            .join(&self.session_id)
            .join("cmd.fifo");
        if !fifo_path.exists() {
            return Err(Error::SessionNotFound);
        }

        match File::options().write(true).open(&fifo_path) {
            Ok(mut fifo_file) => {
                fifo_file.write_all(payload.as_bytes())?;
            }
            Err(e) => return Err(Error::Io(e)),
        }

        Ok(())
    }

    /// Spawns the daemon process for the session.
    pub async fn spawn(&self, shell: Option<String>) -> Result<(), error::Error> {
        let initial_cwd = env::current_dir()?;

        let session_path = Path::new(SESSION_DIR).join(&self.session_id);

        let daemonize = Daemonize::new().working_directory(session_path);
        match daemonize.start() {
            Ok(_) => {
                // In child, run the daemon.
                if let Err(e) = run_daemon(self.session_id.clone(), shell, initial_cwd) {
                    eprintln!("[headlesh daemon] exiting with error: {}", e);
                    std::process::exit(1);
                }
                std::process::exit(0);
            }
            Err(e) => Err(Error::Io(std::io::Error::new(std::io::ErrorKind::Other, e))),
        }
    }
}

fn run_daemon(
    session_id: String,
    shell: Option<String>,
    initial_cwd: PathBuf,
) -> Result<(), Error> {
    use std::fs::OpenOptions;
    use std::io::{Read, Write};
    use std::thread;

    let mut f = OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/headlesh_debug.log")
        .unwrap();
    writeln!(f, "Daemon started for session: {}", session_id).unwrap();
    if let Some(data_dir) = dirs::data_dir() {
        let log_dir = data_dir.join("hinata").join("headlesh").join(&session_id);
        fs::create_dir_all(&log_dir)?;

        let log_path = log_dir.join("server.log");
        let log_file = File::create(log_path)?;

        WriteLogger::init(LevelFilter::Info, Config::default(), log_file)
            .expect("Failed to initialize headlesh logger");
    }

    if let Err(e) = env::set_current_dir(&initial_cwd) {
        info!(
            "[headlesh daemon] Failed to set CWD to {}: {}",
            initial_cwd.display(),
            e
        );
        return Err(e.into());
    }

    let session_path = Path::new(SESSION_DIR).join(&session_id);

    let lock_path = session_path.join("pid.lock");
    // Hold this file handle for the lifetime of the daemon to keep the lock.
    let _lock_file = {
        let file = File::create(&lock_path)?;
        file.lock_exclusive()?;
        file
    };

    let fifo_path = session_path.join("cmd.fifo");
    if fifo_path.exists() {
        fs::remove_file(&fifo_path)?;
    }
    mkfifo(&fifo_path, stat::Mode::S_IRWXU)?;

    loop {
        // This is a blocking read on a named pipe. It will wait until a writer connects.
        let mut cmd_fifo_file = File::open(&fifo_path)?;
        let mut payload_str = String::new();
        cmd_fifo_file.read_to_string(&mut payload_str)?;

        if payload_str.is_empty() {
            continue;
        }

        let mut lines = payload_str.lines();
        let out_fifo_path = PathBuf::from(lines.next().unwrap_or("/dev/null"));
        let err_fifo_path = PathBuf::from(lines.next().unwrap_or("/dev/null"));
        let status_fifo_path = PathBuf::from(lines.next().unwrap_or("/dev/null"));
        let command = lines.collect::<Vec<_>>().join("\n");

        if command == HEADLESH_EXIT_CMD_PAYLOAD {
            break;
        }

        let shell_to_use = shell.clone().unwrap_or_else(|| "sh".to_string());

        thread::spawn(move || {
            let res: Result<(), std::io::Error> = (|| {
                let mut tmp_script = NamedTempFile::new()?;
                tmp_script.write_all(command.as_bytes())?;

                let shell_cmd = format!(
                    // Execute the script, redirecting stdout/stderr. Then, capture its
                    // exit code and write it to the status FIFO.
                    "{{ . \"{}\"; }} > \"{}\" 2> \"{}\"; ec=$?; echo $ec > \"{}\"",
                    tmp_script.path().display(),
                    out_fifo_path.display(),
                    err_fifo_path.display(),
                    status_fifo_path.display()
                );

                let mut child = std::process::Command::new(shell_to_use)
                    .arg("-c")
                    .arg(shell_cmd)
                    .spawn()?;

                let status = child.wait()?;
                if !status.success() {
                    eprintln!(
                        "[headlesh daemon] Shell command execution failed with status: {}",
                        status
                    );
                }

                // The temp file is automatically removed when `tmp_script` is dropped.
                Ok(())
            })();

            if let Err(e) = res {
                eprintln!("[headlesh daemon] Error executing command: {}", e);
                // Attempt to write an error code to the status fifo to unblock the client.
                if let Ok(mut status_fifo) = OpenOptions::new().write(true).open(&status_fifo_path)
                {
                    if let Err(write_err) = status_fifo.write_all(b"127") {
                        eprintln!(
                            "[headlesh daemon] Failed to write error code to status fifo: {}",
                            write_err
                        );
                    }
                }
            }
        });
    }

    let _ = fs::remove_file(&fifo_path);
    let _ = fs::remove_file(&lock_path);

    Ok(())
}

/// Lists all active sessions.
pub async fn list() -> Result<Vec<String>, Error> {
    let session_dir = Path::new(SESSION_DIR);
    if !session_dir.exists() {
        return Ok(vec![]);
    }
    let mut sessions = Vec::new();
    let entries = fs::read_dir(session_dir)?;

    for entry in entries {
        let entry = entry?;
        if !entry.file_type()?.is_dir() {
            continue;
        }

        let session_id = entry.file_name();
        let session_id_str = session_id.to_string_lossy().to_string();
        let session_path = entry.path();
        let lock_path = session_path.join("pid.lock");

        if !lock_path.exists() {
            continue;
        }

        let lock_file = match File::open(&lock_path) {
            Ok(f) => f,
            Err(_) => continue,
        };

        if lock_file.try_lock_exclusive().is_err() {
            // Couldn't get a lock, so the session is likely active.
            sessions.push(session_id_str);
        }
        // If we get a lock, the session is stale. We do nothing, and the lock is
        // released when `lock_file` goes out of scope.
    }

    Ok(sessions)
}
