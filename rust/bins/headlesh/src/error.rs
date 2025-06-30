use thiserror::Error;

#[derive(Error, Debug)]
pub enum Error {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Nix error: {0}")]
    Nix(#[from] nix::Error),

    #[error("Invalid session ID")]
    InvalidSessionId,

    #[error("Session already exists")]
    SessionAlreadyExists,

    #[error("Session not found")]
    SessionNotFound,
}
