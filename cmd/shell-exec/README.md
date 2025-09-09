# Limitations
- The order of stdout writing relative to stderr is not preserved
	- e.g. `echo "cd /tmp ; pwd ; cat /does/not/exist ; pwd" | ./shell-exec`
	- The command above will write `/tmp\n/tmp\n` to stdout and `cat: /does/not/exist: No such file or directory\n` to stderr. But visually in the terminal output, you'll see both `/tmp`s first, then the `cat` error.
	- For automated use cases this is usually negligible
- Defined shell functions are not preserved in state
- Internal background process / job control is only somewhat supported
	- e.g. `echo "bash -c 'sleep 5 ; echo foo' & echo bar" | ./shell-exec`
	- The command above will write "bar\nfoo\n" to stdout, after five seconds. It would hang indefinitely with no output, if the sleep 5 ran forever
