#!/usr/bin/env python3
import os, ctypes, ctypes.util, struct, select, sys, errno

# ----------------------------------------------------------------------
# 1. Load libc + declare the 3 syscalls we need
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# int inotify_init1(int flags);
libc.inotify_init1.argtypes  = [ctypes.c_int]
libc.inotify_init1.restype   = ctypes.c_int

# int inotify_add_watch(int fd, const char *pathname, uint32_t mask);
libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
libc.inotify_add_watch.restype  = ctypes.c_int

# int inotify_rm_watch(int fd, int wd);
libc.inotify_rm_watch.argtypes  = [ctypes.c_int, ctypes.c_int]
libc.inotify_rm_watch.restype   = ctypes.c_int

# ----------------------------------------------------------------------
# 2. Constants from <sys/inotify.h>
IN_CREATE   = 0x00000100   # file/dir *created* in watched dir
IN_MOVED_TO = 0x00000080   # moved/renamed into watched dir
IN_ONLYDIR  = 0x01000000   # (optional) refuse to watch non-dirs
IN_NONBLOCK = 0x00008000   # for inotify_init1()
EVENT_MASK  = IN_CREATE | IN_MOVED_TO

# ----------------------------------------------------------------------
# 3. Create the inotify FD (blocking so select() can sleep)
fd = libc.inotify_init1(0)
if fd == -1:
    raise OSError(ctypes.get_errno(), "inotify_init1 failed")

# 4. Add a watch on *this* directory
watch_dir = b'.'
wd = libc.inotify_add_watch(fd, watch_dir, EVENT_MASK)
if wd == -1:
    raise OSError(ctypes.get_errno(), "inotify_add_watch failed")

target_name = b"foo.txt"         # what we’re waiting for

print("Waiting for foo.txt to appear …")
try:
    while True:
        # block here until the kernel has something to say
        select.select([fd], [], [])

        # when we get here, at least one event is ready
        buffer = os.read(fd, 4096)
        i = 0
        # Process events byte-by-byte according to the struct definition
        while i + 16 <= len(buffer): # While there's at least room for the fixed header
            # struct inotify_event { int wd; uint32_t mask, cookie, len; char name[]; }
            # Unpack the fixed-size header (16 bytes: i, I, I, I)
            wd_evt, mask, cookie, length = struct.unpack_from('iIII', buffer, i)

            # Calculate the total size of this event (header + name)
            # The 'length' field includes the size of the name including null bytes.
            event_size = 16 + length

            # Check we have the full event in the buffer (should normally be true)
            if i + event_size > len(buffer):
                print(f"Warning: Partial event read (need {event_size}, have {len(buffer)-i}). Breaking.", file=sys.stderr)
                break

            # Extract the name bytes. The name starts after the 16-byte header.
            name_bytes = buffer[i + 16 : i + event_size]
            # The name buffer might have trailing null bytes for padding, remove them.
            name = name_bytes.rstrip(b'\0')

            # Check if this event matches our criteria
            if name == target_name and mask & EVENT_MASK:
                print("✓  foo.txt created!")
                sys.exit(0)

            # Move the offset to the start of the next event
            i += event_size
finally:
    libc.inotify_rm_watch(fd, wd)
    os.close(fd)
