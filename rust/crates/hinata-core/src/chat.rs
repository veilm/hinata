use crate::escaping;
use anyhow::{Context, Result};
use chrono::Utc;
use std::cmp::Ordering;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::thread;
use std::time::Duration;
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    User,
    Assistant,
    System,
    AssistantReasoning,
}

impl fmt::Display for Role {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            Role::User => "user",
            Role::Assistant => "assistant",
            Role::System => "system",
            Role::AssistantReasoning => "assistant-reasoning",
        };
        write!(f, "{}", s)
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
#[error("Unknown role: {0}")]
pub struct ParseRoleError(String);

impl FromStr for Role {
    type Err = ParseRoleError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "user" => Ok(Role::User),
            "assistant" => Ok(Role::Assistant),
            "system" => Ok(Role::System),
            "assistant-reasoning" => Ok(Role::AssistantReasoning),
            _ => Err(ParseRoleError(s.to_string())),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChatMessage {
    pub path: PathBuf,
    pub timestamp: i64,
    pub role: Role,
}

impl Ord for ChatMessage {
    fn cmp(&self, other: &Self) -> Ordering {
        self.timestamp.cmp(&other.timestamp)
    }
}

impl PartialOrd for ChatMessage {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[derive(Error, Debug)]
pub enum ChatError {
    #[error("Could not determine a valid home directory.")]
    HomeDirNotFound,
    #[error("Could not create the required directory: {0}")]
    DirectoryCreation(PathBuf),
    #[error("Invalid role: {0}")]
    InvalidRole(String),
}

/// Determines the base directory for storing all conversations, ensuring it exists.
///
/// Follows the XDG Base Directory Specification:
/// 1. Uses \`$XDG_DATA_HOME/hinata/chat/conversations\`.
/// 2. Defaults to \`$HOME/.local/share/hinata/chat/conversations\` if \`$XDG_DATA_HOME\` is not set.
///
/// # Returns
/// A \`Result\` containing the \`PathBuf\` to the conversations directory.
///
/// # Errors
/// - \`ChatError::HomeDirNotFound\` if the home directory cannot be determined.
/// - \`ChatError::DirectoryCreation\` if the directory cannot be created.
pub fn get_conversations_dir() -> Result<PathBuf> {
    let data_dir = match dirs_next::data_dir() {
        Some(path) => path,
        None => {
            // Fallback for systems where data_dir might not be available, though home_dir should be.
            dirs_next::home_dir()
                .ok_or(ChatError::HomeDirNotFound)?
                .join(".local/share")
        }
    };

    let conversations_dir = data_dir.join("hinata/chat/conversations");

    if !conversations_dir.exists() {
        std::fs::create_dir_all(&conversations_dir).with_context(|| {
            format!(
                "Failed to create conversation directory at {:?}",
                conversations_dir
            )
        })?;
    }

    Ok(conversations_dir)
}

/// Creates a new unique conversation directory within the given base directory.
///
/// The new directory is named using the current nanosecond timestamp.
/// The function handles potential collisions by retrying after a short, random delay.
///
/// # Arguments
/// * `base_dir` - The directory in which to create the new conversation directory.
///
/// # Returns
/// A `Result` containing the `PathBuf` to the newly created directory.
pub fn create_new_conversation(base_dir: &Path) -> Result<PathBuf> {
    loop {
        // Note: timestamp_nanos() is deprecated, but timestamp_nanos_opt() is correct.
        // The unwrap is safe here as we don't expect dates outside the representable range.
        let timestamp_ns = Utc::now().timestamp_nanos_opt().unwrap();
        let new_conv_path = base_dir.join(timestamp_ns.to_string());

        match fs::create_dir(&new_conv_path) {
            Ok(_) => return Ok(new_conv_path),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {
                // Collision is extremely unlikely but handled defensively.
                thread::sleep(Duration::from_millis(1));
                continue;
            }
            Err(e) => {
                return Err(e).with_context(|| {
                    format!(
                        "Failed to create new conversation directory at {:?}",
                        new_conv_path
                    )
                });
            }
        }
    }
}

/// Finds the most recent conversation directory in the base conversations directory.
/// "Latest" is determined by the lexicographically largest directory name, which corresponds
/// to the largest timestamp.
///
/// # Arguments
/// * `base_dir` - The directory to search within.
///
/// # Returns
/// An `Ok(Some(PathBuf))` if a latest directory is found, `Ok(None)` if there are no
/// valid subdirectories, and an `Err` if there's a problem reading the directory.
pub fn find_latest_conversation(base_dir: &Path) -> Result<Option<PathBuf>> {
    if !base_dir.exists() {
        return Ok(None);
    }

    let subdirs = fs::read_dir(base_dir)?
        .filter_map(Result::ok) // Ignore entries that cause errors
        .map(|entry| entry.path())
        .filter(|path| path.is_dir())
        .collect::<Vec<PathBuf>>();

    Ok(subdirs.into_iter().max())
}

/// Writes a message content to a new file within a given conversation directory.
///
/// The filename is generated using a nanosecond timestamp and the message role,
/// e.g., `<timestamp>-<role>.md`.
///
/// # Arguments
/// * `conv_dir` - The path to the conversation directory.
/// * `role` - The `Role` of the message author.
/// * `content` - The string content of the message.
///
/// # Returns
/// A `Result` containing the relative `PathBuf` of the newly created file.
pub fn write_message_file(conv_dir: &Path, role: Role, content: &str) -> Result<PathBuf> {
    // Note: timestamp_nanos() is deprecated, but timestamp_nanos_opt() is correct.
    // The unwrap is safe here as we don't expect dates outside the representable range.
    let timestamp_ns = Utc::now().timestamp_nanos_opt().unwrap();
    let filename = format!("{}-{}.md", timestamp_ns, role);
    let file_path = conv_dir.join(&filename);

    if file_path.exists() {
        // Extremely unlikely, but handle defensively.
        return Err(anyhow::anyhow!(
            "File collision detected for path: {:?}",
            file_path
        ));
    }

    fs::write(&file_path, content)
        .with_context(|| format!("Failed to write message to file at {:?}", file_path))?;

    Ok(PathBuf::from(filename))
}

/// Scans a conversation directory and returns a sorted list of valid message files.
///
/// It parses filenames like `<timestamp>-<role>.md`, ignoring any files that do not
/// match this pattern. The returned list is sorted chronologically by timestamp.
///
/// # Arguments
/// * `conv_dir` - The path to the conversation directory to scan.
///
/// # Returns
/// A `Result` containing a sorted `Vec<ChatMessage>`.
pub fn list_messages(conv_dir: &Path) -> Result<Vec<ChatMessage>> {
    let mut messages = Vec::new();

    for entry in fs::read_dir(conv_dir)? {
        let entry = entry?;
        let path = entry.path();

        if !path.is_file() {
            continue;
        }

        let extension = path.extension().and_then(|s| s.to_str());
        if extension != Some("md") {
            continue;
        }

        if let Some(file_stem) = path.file_stem().and_then(|s| s.to_str()) {
            let parts: Vec<&str> = file_stem.splitn(2, '-').collect();
            if parts.len() == 2 {
                if let Ok(timestamp) = parts[0].parse::<i64>() {
                    if let Ok(role) = Role::from_str(parts[1]) {
                        messages.push(ChatMessage {
                            path,
                            timestamp,
                            role,
                        });
                    }
                }
            }
        }
    }

    messages.sort(); // Relies on the Ord implementation for ChatMessage

    Ok(messages)
}

/// Packs messages from a conversation directory into a specified writer.
///
/// It lists all messages, reads each one, escapes its content using the `hinata_core::escaping`
/// module, wraps it in role-specific tags, and writes it to the output.
///
/// # Arguments
/// * `conv_dir` - The path to the conversation directory.
/// * `writer` - A mutable reference to a type that implements `io::Write`, where the
///              packed output will be written.
pub fn pack_conversation(conv_dir: &Path, writer: &mut impl io::Write) -> Result<()> {
    let messages = list_messages(conv_dir)?;

    for msg in messages {
        writer.write_all(format!("<hnt-{}>", msg.role).as_bytes())?;

        let mut file = fs::File::open(&msg.path)
            .with_context(|| format!("Failed to open message file: {:?}", msg.path))?;

        // Use the core escaping function to process the content directly.
        escaping::escape(&mut file, writer)?;

        writer.write_all(format!("</hnt-{}>\n", msg.role).as_bytes())?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use tempfile::tempdir;

    #[test]
    fn test_get_conversations_dir_xdg_set() {
        let tmp_dir = tempdir().unwrap();
        let xdg_data_home = tmp_dir.path();
        env::set_var("XDG_DATA_HOME", xdg_data_home.as_os_str());

        let expected_path = xdg_data_home.join("hinata/chat/conversations");
        let result_path = get_conversations_dir().unwrap();

        assert_eq!(result_path, expected_path);
        assert!(expected_path.exists());

        env::remove_var("XDG_DATA_HOME");
    }

    #[test]
    fn test_get_conversations_dir_xdg_not_set() {
        // This test is a bit tricky as it depends on the actual home dir.
        // We'll just verify it doesn't fail and returns a path that makes sense.
        // Unset XDG_DATA_HOME to be sure
        env::remove_var("XDG_DATA_HOME");

        let result = get_conversations_dir();
        assert!(result.is_ok());
        let path = result.unwrap();

        let home_dir = dirs_next::home_dir().unwrap();
        let default_path = home_dir.join(".local/share/hinata/chat/conversations");
        let another_possible_path = dirs_next::data_dir()
            .unwrap()
            .join("hinata/chat/conversations");

        // The result should be one of the standard locations
        assert!(path == default_path || path == another_possible_path);
        assert!(path.exists());
    }

    #[test]
    fn test_create_and_find_latest_conversation() {
        let tmp_dir = tempdir().unwrap();
        let base_dir = tmp_dir.path();

        // Initially, there should be no conversations
        let latest = find_latest_conversation(base_dir).unwrap();
        assert!(latest.is_none());

        // Create a few conversations
        let conv1_path = create_new_conversation(base_dir).unwrap();
        thread::sleep(Duration::from_millis(10)); // Ensure timestamps are different
        let conv2_path = create_new_conversation(base_dir).unwrap();
        thread::sleep(Duration::from_millis(10));
        let conv3_path = create_new_conversation(base_dir).unwrap();

        assert!(conv1_path.exists() && conv1_path.is_dir());
        assert!(conv2_path.exists() && conv2_path.is_dir());
        assert!(conv3_path.exists() && conv3_path.is_dir());

        // Find the latest one
        let latest = find_latest_conversation(base_dir).unwrap();
        assert_eq!(latest, Some(conv3_path));
    }

    #[test]
    fn test_find_latest_with_non_dir_files() {
        let tmp_dir = tempdir().unwrap();
        let base_dir = tmp_dir.path();

        fs::create_dir(base_dir.join("100")).unwrap();
        fs::create_dir(base_dir.join("300")).unwrap();
        fs::write(base_dir.join("a_file.txt"), "hello").unwrap(); // should be ignored
        fs::create_dir(base_dir.join("200")).unwrap();

        let latest = find_latest_conversation(base_dir).unwrap();
        assert_eq!(latest.unwrap().file_name().unwrap(), "300");
    }

    #[test]
    fn test_write_message_file() {
        let tmp_dir = tempdir().unwrap();
        let conv_dir = tmp_dir.path();
        let role = Role::User;
        let content = "Hello, world!";

        let relative_path = write_message_file(conv_dir, role, content).unwrap();
        let full_path = conv_dir.join(&relative_path);

        assert!(full_path.exists());
        let read_content = fs::read_to_string(full_path).unwrap();
        assert_eq!(read_content, content);

        let filename = relative_path.file_name().unwrap().to_str().unwrap();
        assert!(filename.ends_with("-user.md"));
    }

    #[test]
    fn test_list_messages() {
        let tmp_dir = tempdir().unwrap();
        let conv_dir = tmp_dir.path();

        // Create some message files, ensuring a bit of delay for unique timestamps
        let path1 = write_message_file(conv_dir, Role::User, "First").unwrap();
        thread::sleep(Duration::from_millis(2));
        let path2 = write_message_file(conv_dir, Role::Assistant, "Second").unwrap();
        thread::sleep(Duration::from_millis(2));
        let path3 = write_message_file(conv_dir, Role::User, "Third").unwrap();

        // Create a file that should be ignored
        fs::write(conv_dir.join("ignore.txt"), "not a message").unwrap();
        fs::write(conv_dir.join("123-invalidrole.md"), "bad role").unwrap();

        let messages = list_messages(conv_dir).unwrap();
        assert_eq!(messages.len(), 3);
        assert_eq!(messages[0].role, Role::User);
        assert_eq!(messages[1].role, Role::Assistant);
        assert_eq!(messages[2].role, Role::User);

        // Check that paths are correct
        assert_eq!(
            messages[0].path.file_name().unwrap(),
            path1.file_name().unwrap()
        );
        assert_eq!(
            messages[1].path.file_name().unwrap(),
            path2.file_name().unwrap()
        );
        assert_eq!(
            messages[2].path.file_name().unwrap(),
            path3.file_name().unwrap()
        );

        // Check if sorted correctly
        assert!(messages[0].timestamp < messages[1].timestamp);
        assert!(messages[1].timestamp < messages[2].timestamp);
    }

    #[test]
    fn test_pack_conversation() {
        let tmp_dir = tempdir().unwrap();
        let conv_dir = tmp_dir.path();

        write_message_file(conv_dir, Role::User, "Hello").unwrap();
        thread::sleep(Duration::from_millis(2));
        write_message_file(conv_dir, Role::Assistant, "Hi! <tag>").unwrap();

        let mut output_buffer = Vec::new();
        pack_conversation(conv_dir, &mut output_buffer).unwrap();

        let packed_string = String::from_utf8(output_buffer).unwrap();

        let mut lines = packed_string.lines();
        let first_line = lines.next().unwrap();
        let second_line = lines.next().unwrap();

        assert_eq!(first_line, "<hnt-user>Hello</hnt-user>");
        assert_eq!(second_line, "<hnt-assistant>Hi! \\<tag></hnt-assistant>");
    }
}
