const SPECIAL_TAGS: &[&str] = &["hnt-system", "hnt-user", "hnt-assistant"];

/// Private helper function to process special tags for escaping or unescaping.
/// It iterates through the input string, identifies special tags, and applies a transformation.
fn _process(input: &str, is_escape: bool) -> String {
    let mut result = String::with_capacity(input.len());
    let mut last_end = 0;

    for (start_bracket, _) in input.match_indices('<') {
        result.push_str(&input[last_end..start_bracket]);

        let remaining = &input[start_bracket..];

        if let Some(end_bracket_offset) = remaining.find('>') {
            let tag_with_brackets = &remaining[..=end_bracket_offset];
            let tag_content = &tag_with_brackets[1..tag_with_brackets.len() - 1];

            let (tag_name_part, is_closing) = if let Some(stripped) = tag_content.strip_prefix('/') {
                (stripped, true)
            } else {
                (tag_content, false)
            };

            let mut temp_name = tag_name_part;
            let mut underscore_count = 0;
            while temp_name.starts_with('_') {
                temp_name = &temp_name[1..];
                underscore_count += 1;
            }

            let mut is_special_tag = false;
            for &tag in SPECIAL_TAGS {
                if temp_name == tag {
                    is_special_tag = true;
                    break;
                }
            }

            if is_special_tag {
                if is_escape {
                    // escape: add one leading underscore
                    result.push('<');
                    if is_closing {
                        result.push('/');
                    }
                    result.push('_');
                    result.push_str(tag_name_part);
                    result.push('>');
                } else {
                    // unescape: remove one leading underscore
                    if underscore_count > 0 {
                        result.push('<');
                        if is_closing {
                            result.push('/');
                        }
                        result.push_str(&tag_name_part[1..]);
                        result.push('>');
                    } else {
                        // no leading underscores, print warning and leave as is.
                        eprintln!(
                            "warning: tag '<{}>' found with no leading underscore during unescape",
                            tag_content
                        );
                        result.push_str(tag_with_brackets);
                    }
                }
                last_end = start_bracket + tag_with_brackets.len();
            } else {
                // Not a special tag, so treat '<' literally.
                result.push('<');
                last_end = start_bracket + 1;
            }
        } else {
            // No matching '>', so treat '<' literally.
            result.push('<');
            last_end = start_bracket + 1;
        }
    }

    if last_end < input.len() {
        result.push_str(&input[last_end..]);
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