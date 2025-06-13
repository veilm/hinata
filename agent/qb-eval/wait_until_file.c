#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/select.h>
#include <unistd.h>

void print_usage(const char *prog_name) {
	fprintf(stderr, "Usage: %s <file_path> [max_wait_seconds]\n", prog_name);
}

int main(int argc, char *argv[]) {
	if (argc < 2 || argc > 3) {
		print_usage(argv[0]);
		return 3;  // bad arguments
	}

	const char *path = argv[1];
	long max_wait = -1;

	if (argc == 3) {
		char *endptr;
		max_wait = strtol(argv[2], &endptr, 10);
		if (*endptr != '\0' || max_wait < 0) {
			fprintf(stderr, "Error: Invalid max_wait_seconds value.\n");
			print_usage(argv[0]);
			return 3;
		}
	}

	if (access(path, F_OK) == 0) {
		return 1;
	}

	// dirname and basename can modify the input string, so we must use copies.
	char *path_copy_for_dirname = strdup(path);
	if (!path_copy_for_dirname) {
		perror("strdup");
		return 4;
	}
	char *dir = dirname(path_copy_for_dirname);

	char *path_copy_for_basename = strdup(path);
	if (!path_copy_for_basename) {
		perror("strdup");
		free(path_copy_for_dirname);
		return 4;
	}
	char *base = basename(path_copy_for_basename);

	int inotify_fd = inotify_init1(IN_CLOEXEC);
	if (inotify_fd == -1) {
		perror("inotify_init1");
		free(path_copy_for_dirname);
		free(path_copy_for_basename);
		return 4;
	}

	// Watch for file creation or moves into the directory.
	int watch_descriptor =
	    inotify_add_watch(inotify_fd, dir, IN_CREATE | IN_MOVED_TO);
	if (watch_descriptor == -1) {
		fprintf(stderr, "Error adding inotify watch on directory '%s': %s\n",
		        dir, strerror(errno));
		close(inotify_fd);
		free(path_copy_for_dirname);
		free(path_copy_for_basename);
		return 4;
	}

	// Race condition: check again after setting up the watch.
	if (access(path, F_OK) == 0) {
		inotify_rm_watch(inotify_fd, watch_descriptor);
		close(inotify_fd);
		free(path_copy_for_dirname);
		free(path_copy_for_basename);
		return 1;
	}

	struct timeval timeout;
	struct timeval *timeout_ptr = NULL;

	if (max_wait >= 0) {
		timeout.tv_sec = max_wait;
		timeout.tv_usec = 0;
		timeout_ptr = &timeout;
	}

	while (1) {
		fd_set read_fds;
		FD_ZERO(&read_fds);
		FD_SET(inotify_fd, &read_fds);

		int retval = select(inotify_fd + 1, &read_fds, NULL, NULL, timeout_ptr);

		if (retval == -1) {
			if (errno == EINTR) {
				continue;
			}
			perror("select");
			inotify_rm_watch(inotify_fd, watch_descriptor);
			close(inotify_fd);
			free(path_copy_for_dirname);
			free(path_copy_for_basename);
			return 4;
		}

		if (retval == 0) {
			fprintf(stderr,
			        "Timeout of %ld seconds exceeded waiting for file '%s'\n",
			        max_wait, path);
			inotify_rm_watch(inotify_fd, watch_descriptor);
			close(inotify_fd);
			free(path_copy_for_dirname);
			free(path_copy_for_basename);
			return 2;
		}

		char buffer[4096]
		    __attribute__((aligned(__alignof__(struct inotify_event))));
		ssize_t len = read(inotify_fd, buffer, sizeof(buffer));

		if (len <= 0) {
			if (len < 0 && errno == EINTR) {
				continue;
			}
			perror("read from inotify_fd");
			inotify_rm_watch(inotify_fd, watch_descriptor);
			close(inotify_fd);
			free(path_copy_for_dirname);
			free(path_copy_for_basename);
			return 4;
		}

		ssize_t i = 0;
		while (i < len) {
			struct inotify_event *event = (struct inotify_event *)&buffer[i];
			if (event->len > 0) {
				if ((event->mask & IN_CREATE) || (event->mask & IN_MOVED_TO)) {
					if (strcmp(event->name, base) == 0) {
						inotify_rm_watch(inotify_fd, watch_descriptor);
						close(inotify_fd);
						free(path_copy_for_dirname);
						free(path_copy_for_basename);
						return 1;
					}
				}
			}
			i += sizeof(struct inotify_event) + event->len;
		}
	}

	// Unreachable
	return 4;
}