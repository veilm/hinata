use regex::Regex;
use std::io::{self, Read, Write};

/// Reads from a reader, escapes HNT tags by adding underscores, and writes to a writer.
///
/// This function finds opening and closing HNT tags (e.g., <hnt-user>, </hnt-user>,
/// <_hnt-assistant>, </__hnt-system>) and adds one underscore before "hnt".
///
/// # Arguments
/// * `reader` - A mutable reference to a type that implements `io::Read`.
/// * `writer` - A mutable reference to a type that implements `io::Write`.
///
/// # Returns
/// An `io::Result<()>` indicating the outcome of the operation.
pub fn escape(reader: &mut impl Read, writer: &mut impl Write) -> io::Result<()> {
    let mut content = String::new();
    reader.read_to_string(&mut content)?;

    // Pattern matches: </?_*hnt-(user|assistant|system)>
    let re = Regex::new(r"<(/?)(_*)(hnt-(user|assistant|system))>").unwrap();

    let result = re.replace_all(&content, |caps: &regex::Captures| {
        format!(
            "<{}{}_{}>",
            caps.get(1).map_or("", |m| m.as_str()), // optional /
            caps.get(2).map_or("", |m| m.as_str()), // existing underscores
            caps.get(3).map_or("", |m| m.as_str())  // hnt-role
        )
    });

    writer.write_all(result.as_bytes())?;
    Ok(())
}

/// Unescapes HNT tags by removing one underscore.
///
/// This function finds HNT tags with underscores (e.g., <_hnt-user>, </__hnt-assistant>)
/// and removes one underscore before "hnt". It is the inverse of the `escape` function.
///
/// # Arguments
/// * `input` - The string slice to unescape.
///
/// # Returns
/// A new `String` with one underscore removed from HNT tags.
pub fn unescape(input: &str) -> String {
    let re = Regex::new(r"<(/?)(_+)(hnt-(user|assistant|system))>").unwrap();

    re.replace_all(input, |caps: &regex::Captures| {
        let slash = caps.get(1).map_or("", |m| m.as_str());
        let underscores = caps.get(2).map_or("", |m| m.as_str());
        let hnt_role = caps.get(3).map_or("", |m| m.as_str());

        // Remove one underscore if present
        let new_underscores = if underscores.len() > 0 {
            &underscores[1..]
        } else {
            ""
        };

        format!("<{}{}{}>", slash, new_underscores, hnt_role)
    })
    .to_string()
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
    fn test_escape_hnt_tags() {
        assert_eq!(
            test_escape_str("<hnt-user>Hello</hnt-user>"),
            "<_hnt-user>Hello</_hnt-user>"
        );
        assert_eq!(
            test_escape_str("<hnt-assistant>Hi</hnt-assistant>"),
            "<_hnt-assistant>Hi</_hnt-assistant>"
        );
        assert_eq!(
            test_escape_str("<hnt-system>System</hnt-system>"),
            "<_hnt-system>System</_hnt-system>"
        );
    }

    #[test]
    fn test_escape_already_escaped() {
        assert_eq!(
            test_escape_str("<_hnt-user>Test</_hnt-user>"),
            "<__hnt-user>Test</__hnt-user>"
        );
        assert_eq!(
            test_escape_str("<___hnt-assistant>Multiple</___hnt-assistant>"),
            "<____hnt-assistant>Multiple</____hnt-assistant>"
        );
    }

    #[test]
    fn test_no_escape_regular_tags() {
        assert_eq!(test_escape_str("<tag>"), "<tag>");
        assert_eq!(test_escape_str("text < text"), "text < text");
        assert_eq!(test_escape_str("<div>content</div>"), "<div>content</div>");
    }

    #[test]
    fn test_escape_mixed_content() {
        let input = "Before <hnt-user>User message with <tag> inside</hnt-user> after";
        let expected = "Before <_hnt-user>User message with <tag> inside</_hnt-user> after";
        assert_eq!(test_escape_str(input), expected);
    }

    #[test]
    fn test_unescape_hnt_tags() {
        assert_eq!(
            unescape("<_hnt-user>Hello</_hnt-user>"),
            "<hnt-user>Hello</hnt-user>"
        );
        assert_eq!(
            unescape("<_hnt-assistant>Hi</_hnt-assistant>"),
            "<hnt-assistant>Hi</hnt-assistant>"
        );
        assert_eq!(
            unescape("<_hnt-system>System</_hnt-system>"),
            "<hnt-system>System</hnt-system>"
        );
    }

    #[test]
    fn test_unescape_multiple_underscores() {
        assert_eq!(
            unescape("<__hnt-user>Test</__hnt-user>"),
            "<_hnt-user>Test</_hnt-user>"
        );
        assert_eq!(
            unescape("<____hnt-assistant>Multiple</____hnt-assistant>"),
            "<___hnt-assistant>Multiple</___hnt-assistant>"
        );
    }

    #[test]
    fn test_unescape_no_underscores() {
        assert_eq!(
            unescape("<hnt-user>No underscores</hnt-user>"),
            "<hnt-user>No underscores</hnt-user>"
        );
        assert_eq!(unescape("no escaping here"), "no escaping here");
    }
}
