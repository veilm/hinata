# headlesh
a simple, efficient (no pty polling) manager of headless shell sessions

# install
```sh
git clone https://github.com/veilm/hinata
./rust/install.sh
```

# quickstart
```sh
# pick a session name. avoid special characters
$ session=hajime

# create a session. bash by default
$ headlesh create $session

# list sessions
$ headlesh list
Active sessions:
- hajime

# use other shell (must support reading command input from stdin)
# headlesh create -s /bin/sh $session

# run one or more commands
$ echo "cd /tmp" | headlesh exec $session
$ echo "msg=foo ; pwd" | headlesh exec $session
/tmp

# new lines separate commands, just like in regular shell scripts
$ echo "echo \$msg\ncat \$(date +%s)" | headlesh exec $session > /tmp/0.txt
cat: 1747092138: No such file or directory
# (writes to stdout and stderr appropriately. /tmp/0.txt contains "foo\n")

# (sets exit code appropriately)
$ echo $?
1

$ echo $msg
# (nothing is printed, of course, because $msg was only set in your headlesh session)

# use to end the session. do not `echo exit | headlesh exec`
headlesh exit $session
```
