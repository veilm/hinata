# kakoune chads:
# - start in insert mode without the placeholder instructions
# - copy text on submit. maybe this is a generally sufficient solution for now
# because this matters in cases where you want to discard the LLM's response and
# just try rewording your original prompt. you can make your own UI management
# by passing a --message to hnt-edit so this is just for us

# /home/oboro/src/hinata/fmt/hinata.kak

hook global BufCreate "/tmp/hnt-edit-.*\.md" %{
	hook global -once ClientCreate ".*" %{
		exec -with-hooks "%%c"
	}
}

hook global BufClose "/tmp/hnt-edit-.*\.md" %{
	nop %sh{
		which wl-copy || exit
		which wl-paste || exit

		content=$(cat "$kak_buffile")
		[ "$content" ] || exit
		echo "$content" | grep -q "Replace this text with your instructions. Then write to this file and exit your" && exit

		# Define a newline character
		nl="$(printf '\n')"
		# Trim the very final newline from content, if any. This is what we intend to copy.
		# Using POSIX shell parameter expansion: ${string%suffix}
		# This removes the shortest match of suffix from the end of string.
		# If content is "foo\n\n", content_to_copy becomes "foo\n".
		# If content is "foo\n", content_to_copy becomes "foo".
		# If content is "foo", content_to_copy becomes "foo".
		content_to_copy="${content%"$nl"}"

		# Get current clipboard content. wl-paste should give the raw content.
		# Note: If wl-paste fails (e.g. no clipboard manager), current_clipboard_content might be empty or an error.
		# This is generally fine as comparison will likely fail, leading to a copy attempt.
		current_clipboard_content=$(wl-paste)

		# Compare the content we intend to copy with the current clipboard content.
		if [ "$content_to_copy" = "$current_clipboard_content" ]; then
			# Content is the same, abort copy and notify
			which notify-send && notify-send "Hinata: Copy Aborted" "Content already in clipboard.\nFile: $kak_buffile"
			exit # Exit the script, skipping wl-copy
		fi

		# If we reach here, the content is different, or clipboard was empty/unreadable. Proceed with copying.
		which notify-send && notify-send "Hinata: Copying" "Copying content to clipboard...\nFile: $kak_buffile"

		# Pipe the content_to_copy to wl-copy.
		# printf %s is used to avoid adding an extraneous newline.
		# This ensures that what's copied by wl-copy is exactly content_to_copy,
		# matching how current_clipboard_content would be if it was set by this script.
		printf %s "$content_to_copy" | wl-copy

		which notify-send && notify-send "Hinata: Copied" "Content copied to clipboard.\nFile: $kak_buffile"
	}
}
