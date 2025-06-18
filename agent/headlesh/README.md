# headlesh
a simple, efficient (no bl*at pty polling) manager of headless shell sessions

# quickstart
```sh
# compile (no deps)
git clone https://github.com/veilm/hinata
cd hinata/agent/headlesh
./build

# pick a session name. avoid special characters
s=hajime

# create a session. bash by default
headlesh create $s

# list sessions
headlesh list
# > Active headlesh sessions:
# > - hajime (PID: 3274953)

# use other shell. must support reading command input from stdin
# headlesh create $s /bin/sh

# run one or more commands
echo "cd" | headlesh exec $s
echo "f=5 ; pwd" | headlesh exec $s
# > /home/oboro

# new lines separate commands, just like in regular shell scripts
echo "echo \$f\ncat \$(date +%s)" | headlesh exec $s > /tmp/0
# > cat: 1747092138: No such file or directory
# (writes to stdout and stderr appropriately)

echo $?
# > 1
# (sets exit code appropriately)

cat /tmp/0
# > 5

echo $f
# >
# (nothing is printed, of course, because f was only set in your headlesh session)

# use to end the session. do not `echo exit | headlesh exec`
headlesh exit $s
```

# Shrine Note

> Turn back if you value you life.

> You can't behead the headless.

> Our swords and pikes did nothing.

![headless by celest c. from defrec1747092671](https://cdn.donmai.us/sample/b1/52/__headless_sekiro_shadows_die_twice_drawn_by_celest_c__sample-b152e1cda121797f807297636a890be7.jpg)
