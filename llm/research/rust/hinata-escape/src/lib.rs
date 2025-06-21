const SPECIAL_TAGS: &[&str] = &["hnt-system", "hnt-user", "hnt-assistant"];

/// Private helper function to process special tags for escaping or unescaping.
/// It iterates through the input string, identifies special tags, and applies a transformation
/// using a character-by-character state machine.
fn _process(input: &str, is_escape: bool) -> String {
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    enum State {
        Normal,
        SeenLt,
        SeenSlash,
        ParsingTag,
    }

    let mut result = String::with_capacity(input.len());
    let mut state = State::Normal;

    let mut buffer = String::new();
    let mut tag_name_buf = String::new();
    let mut is_closing = false;

    for c in input.chars() {
        match state {
            State::Normal => {
                if c == '<' {
                    state = State::SeenLt;
                    buffer.push(c);
                } else {
                    result.push(c);
                }
            }
            State::SeenLt => {
                buffer.push(c);
                if c == '/' {
                    is_closing = true;
                    state = State::SeenSlash;
                } else if c.is_alphanumeric() || c == '_' {
                    is_closing = false;
                    tag_name_buf.push(c);
                    state = State::ParsingTag;
                } else if c == '<' {
                    // A `<<` sequence. Flush the first `<` to the result, and restart
                    // the FSM for the second `<` by leaving it in the buffer.
                    result.push(buffer.remove(0));
                } else {
                    // Not a valid tag character sequence (e.g., `< `).
                    result.push_str(&buffer);
                    buffer.clear();
                    state = State::Normal;
                }
            }
            State::SeenSlash => {
                buffer.push(c);
                if c.is_alphanumeric() || c == '_' {
                    tag_name_buf.push(c);
                    state = State::ParsingTag;
                } else {
                    // Not a valid tag character sequence (e.g., `</ ` or `</>`).
                    result.push_str(&buffer);
                    buffer.clear();
                    is_closing = false; // Reset as we are aborting.
                    state = State::Normal;
                }
            }
            State::ParsingTag => {
                buffer.push(c);
                if c == '>' {
                    // End of a potential tag.
                    let mut temp_name = tag_name_buf.as_str();
                    let mut underscore_count = 0;
                    while temp_name.starts_with('_') {
                        temp_name = &temp_name[1..];
                        underscore_count += 1;
                    }

                    if SPECIAL_TAGS.iter().any(|&tag| tag == temp_name) {
                        // It is a special tag, process it.
                        if is_escape {
                            result.push('<');
                            if is_closing {
                                result.push('/');
                            }
                            result.push('_');
                            result.push_str(&tag_name_buf);
                            result.push('>');
                        } else {
                            // Unescape
                            if underscore_count > 0 {
                                result.push('<');
                                if is_closing {
                                    result.push('/');
                                }
                                result.push_str(&tag_name_buf[1..]);
                                result.push('>');
                            } else {
                                let tag_content = if is_closing {
                                    format!("/{}", tag_name_buf)
                                } else {
                                    tag_name_buf.clone()
                                };
                                eprintln!(
                                    "warning: tag '<{}>' found with no leading underscore during unescape",
                                    tag_content
                                );
                                result.push_str(&buffer);
                            }
                        }
                    } else {
                        // Not a special tag, so append the buffered original text.
                        result.push_str(&buffer);
                    }

                    // Reset for the next characters.
                    state = State::Normal;
                    buffer.clear();
                    tag_name_buf.clear();
                    is_closing = false;
                } else if c.is_alphanumeric() || c == '_' || c == '-' {
                    // A valid character for a tag name.
                    tag_name_buf.push(c);
                } else {
                    // Invalid character for a tag name, so this is not a tag we should process.
                    result.push_str(&buffer);

                    state = State::Normal;
                    buffer.clear();
                    tag_name_buf.clear();
                    is_closing = false;
                }
            }
        }
    }

    // If the input ends while inside a tag, flush the buffer.
    if !buffer.is_empty() {
        result.push_str(&buffer);
    }

    result
}

/// Escapes special hinata tags by adding a leading underscore.
///
/// For example, `<hnt-user>` becomes `<_hnt-user>`, and `</_hnt-assistant>`
/// becomes `</__hnt-assistant>`.
pub fn escape(input: &str) -> String {
    _process(input, true)
}

/// Unescapes special hinata tags by removing a leading underscore.
///
/// For example, `</__hnt-system>` becomes `</_hnt-system>`.
/// If a tag is found that has no leading underscores (e.g., `<hnt-user>`),
/// it prints a warning to stderr and leaves the tag unchanged.
pub fn unescape(input: &str) -> String {
    _process(input, false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_escape() {
        assert_eq!(escape("<hnt-user>"), "<_hnt-user>");
        assert_eq!(escape("</hnt-user>"), "</_hnt-user>");
        assert_eq!(escape("<_hnt-user>"), "<__hnt-user>");
        assert_eq!(escape("</_hnt-user>"), "</__hnt-user>");
        assert_eq!(escape("foo<hnt-system>bar"), "foo<_hnt-system>bar");
        assert_eq!(
            escape("<hnt-user> and </hnt-assistant>"),
            "<_hnt-user> and </_hnt-assistant>"
        );
        assert_eq!(
            escape("<hnt-user><hnt-assistant>"),
            "<_hnt-user><_hnt-assistant>"
        );
        assert_eq!(escape("not a tag <hnt-usr>"), "not a tag <hnt-usr>");
        assert_eq!(escape("incomplete <hnt-user"), "incomplete <hnt-user");
        assert_eq!(escape("<<hnt-user>"), "<<_hnt-user>");
        assert_eq!(escape("<hnt-user/>"), "<hnt-user/>");
    }

    #[test]
    fn test_unescape() {
        assert_eq!(unescape("<_hnt-user>"), "<hnt-user>");
        assert_eq!(unescape("</_hnt-user>"), "</hnt-user>");
        assert_eq!(unescape("<__hnt-user>"), "<_hnt-user>");
        assert_eq!(unescape("</__hnt-user>"), "</_hnt-user>");
        assert_eq!(unescape("foo<_hnt-system>bar"), "foo<hnt-system>bar");
        assert_eq!(
            unescape("<__hnt-user> and </_hnt-assistant>"),
            "<_hnt-user> and </hnt-assistant>"
        );
        assert_eq!(unescape("not a tag <_hnt-usr>"), "not a tag <_hnt-usr>");
        assert_eq!(
            unescape("incomplete <_hnt-user"),
            "incomplete <_hnt-user"
        );
        assert_eq!(unescape("<<_hnt-user>"), "<<hnt-user>");
    }

    #[test]
    fn test_unescape_warning() {
        // Here we just check that the string remains unchanged.
        // Capturing stderr is possible but more complex than needed for this test.
        assert_eq!(unescape("<hnt-user>"), "<hnt-user>");
        assert_eq!(unescape("</hnt-assistant>"), "</hnt-assistant>");
        assert_eq!(
            unescape("<hnt-user> and </hnt-assistant>"),
            "<hnt-user> and </hnt-assistant>"
        );
    }

    #[test]
    fn test_no_op() {
        assert_eq!(escape("nothing to do"), "nothing to do");
        assert_eq!(unescape("nothing to do"), "nothing to do");
        assert_eq!(escape(""), "");
        assert_eq!(unescape(""), "");
        assert_eq!(escape("text with < and > but no tags"), "text with < and > but no tags");
        assert_eq!(unescape("text with < and > but no tags"), "text with < and > but no tags");
    }

    #[test]
    fn test_mixed_tags() {
        let original = "<p>Here is a user message: <hnt-user>Hello!</hnt-user></p>";
        let escaped = "<p>Here is a user message: <_hnt-user>Hello!</_hnt-user></p>";
        assert_eq!(escape(original), escaped);
        assert_eq!(unescape(escaped), original);
    }
}