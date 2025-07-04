use std::io::{self, Read, Write};

/// Reads from a reader, escapes specific characters ('<'), and writes to a writer.
///
/// This function processes data in a streaming fashion, avoiding loading the
/// entire content into memory.
///
/// # Arguments
/// * `reader` - A mutable reference to a type that implements `io::Read`.
/// * `writer` - A mutable reference to a type that implements `io::Write`.
///
/// # Returns
/// An `io::Result<()>` indicating the outcome of the operation.
pub fn escape(reader: &mut impl Read, writer: &mut impl Write) -> io::Result<()> {
    // Using a buffer for efficiency is better than byte-by-byte.
    let mut buffer = [0; 8192];

    loop {
        let bytes_read = reader.read(&mut buffer)?;
        if bytes_read == 0 {
            break; // End of stream
        }

        let chunk = &buffer[..bytes_read];
        let mut last_pos = 0;

        for (i, &byte) in chunk.iter().enumerate() {
            if byte == b'<' {
                // Write segment before the special character
                if i > last_pos {
                    writer.write_all(&chunk[last_pos..i])?;
                }
                // Write the escaped version
                writer.write_all(b"\\<")?;
                last_pos = i + 1;
            }
        }

        // Write any remaining part of the chunk
        if last_pos < chunk.len() {
            writer.write_all(&chunk[last_pos..])?;
        }
    }

    Ok(())
}

/// Unescapes specific character sequences in a string slice.
///
/// This function specifically replaces instances of "\\<" with "<".
/// It is the inverse of the `escape` function.
///
/// # Arguments
/// * `input` - The string slice to unescape.
///
/// # Returns
/// A new `String` with the character sequences unescaped.
pub fn unescape(input: &str) -> String {
    input.replace("\\<", "<")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn test_escape_str(input: &str) -> String {
        let mut reader = Cursor::new(input);
        let mut writer = Vec::new();
        escape(&mut reader, &mut writer).unwrap();
        String::from_utf8(writer).unwrap()
    }

    #[test]
    fn test_escape() {
        assert_eq!(test_escape_str("<tag>"), "\\<tag>");
        assert_eq!(test_escape_str("text < text"), "text \\< text");
    }

    #[test]
    fn test_no_op() {
        assert_eq!(test_escape_str("hello world"), "hello world");
    }

    #[test]
    fn test_mixed_tags() {
        let input = "<outer><inner></inner></outer>";
        let expected = "\\<outer>\\<inner>\\</inner>\\</outer>";
        assert_eq!(test_escape_str(input), expected);
    }

    #[test]
    fn test_unescape() {
        assert_eq!(unescape("\\<tag>"), "<tag>");
        assert_eq!(unescape("text \\< text"), "text < text");
        assert_eq!(unescape("no escaping here"), "no escaping here");
        assert_eq!(
            unescape("\\<outer>\\<inner>\\</inner>\\</outer>"),
            "<outer><inner></inner></outer>"
        );
    }
}
