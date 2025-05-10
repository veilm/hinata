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
		content=$(cat "$kak_buffile")
		[ "$content" ] || exit
		echo "$content" | grep -q "Replace this text with your instructions. Then write to this file and exit your" && exit

		which notify-send && notify-send "copying from $kak_buffile"

		# Define a newline character
		nl="$(printf '\n')"
		# Trim the very final newline from content, if any
		# Using POSIX shell parameter expansion: ${string%suffix}
		# This removes the shortest match of suffix from the end of string.
		# If content is "foo\n\n", trimmed_content becomes "foo\n".
		# If content is "foo\n", trimmed_content becomes "foo".
		# If content is "foo", trimmed_content becomes "foo".
		trimmed_content="${content%"$nl"}"
		# Pipe the trimmed content to wl-copy.
		# printf %s is used to avoid adding an extraneous newline.
		printf %s "$trimmed_content" | wl-copy

		which notify-send && notify-send "done copying from $kak_buffile"
	}
}
