# kakoune chads: start in insert mode without the placeholder instructions
# /home/oboro/src/hinata/share/hinata.kak

hook global BufCreate "/tmp/hnt-edit-.*\.md" %{
	hook global -once ClientCreate ".*" %{
		exec -with-hooks "%%c"
	}
}
