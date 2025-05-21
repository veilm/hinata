// Define _GNU_SOURCE to enable various extensions like strndup, realpath,
// popen, pclose Needs to be defined before including any standard headers.
#define _GNU_SOURCE
#include <errno.h>    // For errno, perror
#include <getopt.h>   // For getopt_long
#include <libgen.h>   // For dirname
#include <limits.h>   // For PATH_MAX
#include <stdbool.h>  // For bool type used in process_block
#include <stdint.h>   // For SIZE_MAX
#include <stdio.h>
#include <stdlib.h>  // For realpath, malloc, free, exit, EXIT_FAILURE, EXIT_SUCCESS, size_t, NULL
#include <string.h>
#include <sys/stat.h>   // For mkdir, mode_t
#include <sys/types.h>  // For mode_t (often included by sys/stat.h anyway)
#include <sys/wait.h>   // For WIFEXITED, WEXITSTATUS with pclose
#include <unistd.h>     // For popen, pclose

// --- Global Flags ---
int verbose_mode = 0;            // Global flag for verbose output
int disallow_creating_flag = 0;  // Global flag for disallowing file creation

#ifndef MIN  // Define MIN if not already defined (e.g., by sys/param.h)
#define MIN(a, b) (((a) < (b)) ? (a) : (b))
#endif

// --- Forward Declarations ---

/**
 * @brief Reads the entire content from a FILE stream into a dynamically
 * allocated string.
 * @param stream The FILE stream to read from (e.g., stdin, or a file pointer).
 * @return A dynamically allocated string containing the stream's content,
 * or NULL on error (errno will be set). The caller must free the returned
 * string.
 */
char *read_stream_to_string(FILE *stream);

/**
 * @brief Runs a shell command and captures its standard output.
 * @param cmd The command string to execute.
 * @return A dynamically allocated string containing the command's stdout.
 * Exits the program on error (e.g., popen failure, command non-zero exit).
 * The caller must free the returned string.
 */
char *run_command(const char *cmd);

/**
 * @brief Processes a single LLM change block.
 *
 * Constructs the full path, verifies it against input files, reads the file,
 * find the target section exactly once, replaces it, and writes the modified
 * content back to the file. If the target is empty and the file does not
 * exist (and --disallow-creating is not set), it creates the file.
 * Exits the program on some errors, returns status code for others.
 *
 * @param shared_root The shared root path obtained from llm-pack.
 * @param abs_input_paths An array of absolute paths corresponding to the CLI
 * arguments.
 * @param num_input_paths The number of paths in abs_input_paths.
 * @param rel_path The relative path parsed from the LLM block.
 * @param target The target content to search for.
 * @param replace The replacement content.
 * @return 0 on success (file modified), 1 on failure, 2 on success (file
 * created).
 */
int process_block(const char *shared_root, char **abs_input_paths,
                  int num_input_paths, const char *rel_path, const char *target,
                  const char *replace);

// Helper function to create directories recursively like mkdir -p
// This function is specifically for ensuring the parent directory of a file
// exists.
static int ensure_directory_exists(const char *file_path, mode_t mode) {
	char *path_copy = strdup(file_path);
	if (!path_copy) {
		perror("strdup in ensure_directory_exists (for path_copy)");
		return -1;
	}

	char *dir_name = dirname(path_copy);  // dirname might modify path_copy
	// dirname might return "." or a pointer to input or static storage.
	// Create a mutable copy of the directory path itself.
	char *dir_to_create = strdup(dir_name);
	free(path_copy);  // Done with path_copy

	if (!dir_to_create) {
		perror("strdup in ensure_directory_exists (for dir_to_create)");
		return -1;
	}

	// If dir_name is "." (file in current dir) or "/" (file in root), no
	// directory needs to be created.
	if (strcmp(dir_to_create, ".") == 0 || strcmp(dir_to_create, "/") == 0) {
		free(dir_to_create);
		return 0;
	}

	char *p = dir_to_create;
	// If absolute path, skip the first '/'
	if (*p == '/') {
		p++;
	}

	while (*p) {  // Iterate through the path string
		if (*p == '/') {
			*p = '\0';  // Temporarily null-terminate to make a directory
			            // component
			if (mkdir(dir_to_create, mode) == -1 && errno != EEXIST) {
				// perror("mkdir intermediate in ensure_directory_exists"); //
				// Let caller provide context
				free(dir_to_create);
				return -1;
			}
			*p = '/';  // Restore the slash
		}
		p++;
	}

	// Create the final component of the directory path
	if (mkdir(dir_to_create, mode) == -1 && errno != EEXIST) {
		// perror("mkdir final in ensure_directory_exists"); // Let caller
		// provide context
		free(dir_to_create);
		return -1;
	}

	free(dir_to_create);
	return 0;
}

/**
 * @brief Finds a line in a string that exactly matches `exact_line_content`.
 *
 * Iterates line by line from `search_ptr`. A line matches if its content
 * (excluding the newline character) is identical to `exact_line_content`.
 *
 * @param search_ptr Pointer to the current position in the string to search
 * from.
 * @param exact_line_content The exact string the line should contain.
 * @param p_start_of_next_line Output: If the marker is found, this pointer is
 * updated to point to the start of the line immediately following the marker
 * line (or the null terminator if the marker line is the last line).
 * @param stop_marker_content Optional: If not NULL, this is another exact
 * string. If a line matching `stop_marker_content` is found before
 * `exact_line_content`, the search stops.
 * @param p_found_stop_marker_line Output: If `stop_marker_content` is provided
 * and found before `exact_line_content`, this pointer is updated to point to
 * the start of the line containing `stop_marker_content`.
 * @return Pointer to the start of the line containing `exact_line_content` if
 * found. Returns `NULL` if `exact_line_content` is not found (either EOF is
 * reached, or `stop_marker_content` was found first).
 */
static char *find_line_with_exact_content(char *search_ptr,
                                          const char *exact_line_content,
                                          char **p_start_of_next_line,
                                          const char *stop_marker_content,
                                          char **p_found_stop_marker_line) {
	if (p_start_of_next_line) *p_start_of_next_line = NULL;
	if (p_found_stop_marker_line) *p_found_stop_marker_line = NULL;

	if (!search_ptr || !exact_line_content) return NULL;

	size_t exact_len = strlen(exact_line_content);
	size_t stop_len = stop_marker_content ? strlen(stop_marker_content) : 0;

	while (*search_ptr) {
		char *line_start = search_ptr;
		char *line_end_char = strchr(search_ptr, '\n');  // Find newline
		char *next_search_start_after_this_line;
		size_t current_line_content_len;

		if (line_end_char) {  // Newline found
			current_line_content_len = line_end_char - line_start;
			next_search_start_after_this_line = line_end_char + 1;
		} else {  // No newline, this is potentially the last line
			current_line_content_len = strlen(line_start);
			next_search_start_after_this_line =
			    line_start + current_line_content_len;  // Points to '\0'
		}

		// Check for stop_marker first (if provided)
		if (stop_marker_content && current_line_content_len == stop_len) {
			if (strncmp(line_start, stop_marker_content, stop_len) == 0) {
				if (p_found_stop_marker_line)
					*p_found_stop_marker_line = line_start;
				return NULL;  // Stop marker found before exact_line_content
			}
		}

		// Check for exact_line_content
		if (current_line_content_len == exact_len) {
			if (strncmp(line_start, exact_line_content, exact_len) == 0) {
				if (p_start_of_next_line)
					*p_start_of_next_line = next_search_start_after_this_line;
				return line_start;  // Exact marker line found
			}
		}

		if (!line_end_char)
			break;  // End of string if no newline was found on this last
			        // checkable line
		search_ptr = next_search_start_after_this_line;
	}
	return NULL;  // Reached end of string without finding exact_line_content
}

// --- Main Function ---

int main(int argc, char *argv[]) {
	// --- 0. Parse Command Line Options ---
	struct option long_options[] = {
	    {"verbose", no_argument, &verbose_mode, 1},
	    {"disallow-creating", no_argument, &disallow_creating_flag, 1},
	    {0, 0, 0, 0}  // End of options
	};
	int opt;
	int option_index = 0;

	// Keep parsing options until there are no more
	// `getopt_long` permutes argv so that non-option arguments are at the end
	while ((opt = getopt_long(argc, argv, "v", long_options, &option_index)) !=
	       -1) {
		switch (opt) {
			case 'v':
				verbose_mode = 1;
				break;
			case 0:  // For long options that set a flag
				// If the option sets a flag variable, getopt_long returns 0
				// 'verbose_mode' is already set by the option definition
				break;
			case '?':  // Unknown option or missing argument
				// Error message is printed by getopt_long
				fprintf(stderr,
				        "Usage: %s [-v|--verbose] [--disallow-creating] "
				        "<file1> [file2] ...\n",
				        argv[0]);
				fprintf(
				    stderr,
				    "Learn more at "
				    "https://github.com/michaelskyba/hinata/tree/main/edit\n");
				return EXIT_FAILURE;
			default:
				// Should not happen
				abort();
		}
	}

	// Check if any file paths were provided after options
	if (optind >= argc) {
		fprintf(stderr,
		        "Usage: %s [-v|--verbose] [--disallow-creating] <file1> "
		        "[file2] ...\n",
		        argv[0]);
		fprintf(stderr, "Error: No input files specified.\n");
		fprintf(stderr,
		        "Learn more at "
		        "https://github.com/michaelskyba/hinata/tree/main/edit\n");
		return EXIT_FAILURE;
	}

	// --- 1. Resolve absolute paths for input files ---
	// File paths start at argv[optind]
	int num_input_paths = argc - optind;
	char **abs_input_paths = malloc(num_input_paths * sizeof(char *));
	if (!abs_input_paths) {
		perror("Failed to allocate memory for absolute paths");
		return EXIT_FAILURE;
	}

	size_t cmd_len = strlen("llm-pack -p") + 1;  // Base command + space
	for (int i = 0; i < num_input_paths; ++i) {
		// Access files using argv[optind + i]
		abs_input_paths[i] = realpath(argv[optind + i], NULL);
		if (!abs_input_paths[i]) {
			perror("Error resolving input path");
			fprintf(stderr, "Failed path: %s\n", argv[optind + i]);
			// Clean up already resolved paths before exiting
			for (int j = 0; j < i; ++j) {
				free(abs_input_paths[j]);
			}
			free(abs_input_paths);
			return EXIT_FAILURE;
		}
		// Add length for path + space (or null terminator later)
		cmd_len += strlen(abs_input_paths[i]) + 1;
	}

	// --- 2. Run llm-pack to get shared root path ---
	char *llm_pack_cmd = malloc(cmd_len);
	if (!llm_pack_cmd) {
		perror("Failed to allocate memory for llm-pack command");
		// Clean up absolute paths
		for (int i = 0; i < num_input_paths; ++i) free(abs_input_paths[i]);
		free(abs_input_paths);
		return EXIT_FAILURE;
	}

	strcpy(llm_pack_cmd, "llm-pack -p");
	for (int i = 0; i < num_input_paths; ++i) {
		strcat(llm_pack_cmd, " ");
		strcat(llm_pack_cmd, abs_input_paths[i]);
	}

	if (verbose_mode) {
		printf("hnt-apply: Running: %s\n", llm_pack_cmd);
	}
	char *shared_root = run_command(llm_pack_cmd);
	if (verbose_mode) {
		printf("hnt-apply: Shared root: %s\n", shared_root);
	}
	free(llm_pack_cmd);  // Command string no longer needed

	// --- 3. Read LLM generation from stdin ---
	if (verbose_mode) {
		printf("hnt-apply: Reading LLM generation from stdin...\n");
	}
	char *stdin_content = read_stream_to_string(stdin);
	if (!stdin_content) {
		// Error reading already prints message in read_stream_to_string or
		// run_command Just ensure cleanup and exit Clean up
		free(shared_root);
		for (int i = 0; i < num_input_paths; ++i) free(abs_input_paths[i]);
		free(abs_input_paths);
		return EXIT_FAILURE;
	}
	if (verbose_mode) {
		printf("hnt-apply: Finished reading stdin.\n");
	}

	// --- 4. Parse stdin and process blocks ---
	if (!verbose_mode &&
	    *stdin_content != '\0') {  // Only print if there might be blocks
		printf("hnt-apply: Processing blocks...\n");
	}
	char *current_pos = stdin_content;
	const char *block_marker = "```";
	const char *target_marker = "<<<<<<< TARGET";
	const char *separator_marker = "=======";
	const char *replace_marker = ">>>>>>> REPLACE";
	int block_count = 0;
	int overall_status = EXIT_SUCCESS;  // Track if any block fails

	while (1) {
		char *block_start = strstr(current_pos, block_marker);
		if (!block_start) break;  // No more blocks found

		char *line_after_block_start = strchr(block_start, '\n');
		if (!line_after_block_start) {
			if (strlen(block_start) > strlen(block_marker)) {
				fprintf(
				    stdout,
				    "Error: Malformed block - '%s' not followed by newline.\n",
				    block_marker);
				overall_status = EXIT_FAILURE;
			}
			current_pos = block_start + strlen(block_marker);
			continue;
		}
		char *path_start = line_after_block_start + 1;

		char *path_end_newline = strchr(path_start, '\n');
		if (!path_end_newline) {
			fprintf(stdout,
			        "Error: Malformed block - path line starting near '%.*s' "
			        "not terminated by newline.\n",
			        (int)MIN(20, strlen(path_start)), path_start);
			overall_status = EXIT_FAILURE;
			current_pos = path_start;
			continue;
		}

		char *relative_path =
		    strndup(path_start, path_end_newline - path_start);
		if (!relative_path) {
			perror("strndup failed for relative_path");
			overall_status = EXIT_FAILURE;
			current_pos = path_end_newline + 1;
			continue;
		}

		char *content_scan_ptr =
		    path_end_newline + 1;  // Start scanning for markers after path line
		char *target_marker_line = NULL;
		char *target_content_starts_here = NULL;
		char *found_block_end_instead = NULL;

		target_marker_line = find_line_with_exact_content(
		    content_scan_ptr, target_marker, &target_content_starts_here,
		    block_marker,  // Stop if "```" is found first
		    &found_block_end_instead);

		if (!target_marker_line) {
			if (verbose_mode) {
				printf(
				    "hnt-apply: Skipping non-TARGET/REPLACE block associated "
				    "with path '%s'. Reason: '%s' marker not found or "
				    "misplaced before block end.\n",
				    relative_path, target_marker);
			}
			free(relative_path);
			if (found_block_end_instead) {  // "```" was found, ending this
				                            // non-TARGET block
				char *end_of_fence_line = strchr(found_block_end_instead, '\n');
				current_pos =
				    end_of_fence_line
				        ? (end_of_fence_line + 1)
				        : (found_block_end_instead + strlen(block_marker));
			} else {  // EOF or other issue before TARGET or "```"
				current_pos = content_scan_ptr +
				              strlen(content_scan_ptr);  // Advance to end of
				                                         // current scan area
			}
			continue;
		}

		// TARGET marker found. target_content_starts_here points to the line
		// after it.
		char *separator_marker_line = NULL;
		char *replace_content_starts_here = NULL;
		char *found_block_end_before_separator = NULL;

		separator_marker_line = find_line_with_exact_content(
		    target_content_starts_here, separator_marker,
		    &replace_content_starts_here,
		    NULL,  // Allow "```" within TARGET content
		    &found_block_end_before_separator);

		if (!separator_marker_line) {
			fprintf(stdout,
			        "Error: Missing '%s' after target section for path '%s'. ",
			        separator_marker, relative_path);
			// With stop_marker_content as NULL,
			// found_block_end_before_separator will not be set by finding
			// block_marker. So, the 'else' branch is more likely.
			if (found_block_end_before_separator) {  // This condition would now
				                                     // only be true if
				                                     // stop_marker was
				                                     // something else
				fprintf(stdout,
				        "'%s' found instead (unexpected stop marker).\n",
				        block_marker /* or actual stop marker */);
				current_pos = found_block_end_before_separator;
			} else {
				fprintf(stdout,
				        "End of block content reached before finding it.\n");
				current_pos =
				    target_content_starts_here;  // Advance past TARGET line
			}
			free(relative_path);
			overall_status = EXIT_FAILURE;
			continue;
		}

		// Extract target content
		char *actual_target_content_end = separator_marker_line;
		while (actual_target_content_end > target_content_starts_here &&
		       (*(actual_target_content_end - 1) == '\n' ||
		        *(actual_target_content_end - 1) == '\r')) {
			actual_target_content_end--;
		}
		char *target_content_str =
		    strndup(target_content_starts_here,
		            actual_target_content_end - target_content_starts_here);
		if (!target_content_str) {
			perror("strndup failed for target_content");
			free(relative_path);
			overall_status = EXIT_FAILURE;
			current_pos =
			    replace_content_starts_here;  // Advance past separator line
			continue;
		}

		// Find REPLACE marker
		char *replace_marker_line = NULL;
		char *after_replace_marker_content_area = NULL;
		char *found_block_end_before_replace = NULL;

		replace_marker_line = find_line_with_exact_content(
		    replace_content_starts_here, replace_marker,
		    &after_replace_marker_content_area,
		    NULL,  // Allow "```" within REPLACE content
		    &found_block_end_before_replace);

		if (!replace_marker_line) {
			fprintf(stdout,
			        "Error: Missing '%s' after replace section for path '%s'. ",
			        replace_marker, relative_path);
			// With stop_marker_content as NULL, found_block_end_before_replace
			// will not be set by finding block_marker. So, the 'else' branch is
			// more likely.
			if (found_block_end_before_replace) {  // This condition would now
				                                   // only be true if
				                                   // stop_marker was something
				                                   // else
				fprintf(stdout,
				        "'%s' found instead (unexpected stop marker).\n",
				        block_marker /* or actual stop marker */);
				current_pos = found_block_end_before_replace;
			} else {
				fprintf(stdout,
				        "End of block content reached before finding it.\n");
				current_pos =
				    replace_content_starts_here;  // Advance past SEPARATOR line
			}
			free(relative_path);
			free(target_content_str);
			overall_status = EXIT_FAILURE;
			continue;
		}

		// Extract replace content
		char *actual_replace_content_end = replace_marker_line;
		while (actual_replace_content_end > replace_content_starts_here &&
		       (*(actual_replace_content_end - 1) == '\n' ||
		        *(actual_replace_content_end - 1) == '\r')) {
			actual_replace_content_end--;
		}
		char *replace_content_str =
		    strndup(replace_content_starts_here,
		            actual_replace_content_end - replace_content_starts_here);
		if (!replace_content_str) {
			perror("strndup failed for replace_content");
			free(relative_path);
			free(target_content_str);
			overall_status = EXIT_FAILURE;
			current_pos =
			    after_replace_marker_content_area;  // Advance past replace
			                                        // marker line
			continue;
		}

		// Find closing block_marker "```"
		char *closing_block_marker_line = NULL;
		char *after_closing_block_marker =
		    NULL;  // This will be the new current_pos for the main loop.
		char *dummy_found_stop_marker = NULL;

		closing_block_marker_line = find_line_with_exact_content(
		    after_replace_marker_content_area, block_marker,
		    &after_closing_block_marker,
		    NULL,  // No specific stop marker, just looking for "```"
		    &dummy_found_stop_marker);

		if (!closing_block_marker_line) {
			fprintf(
			    stdout,
			    "Error: Missing closing '%s' for block related to path '%s'\n",
			    block_marker, relative_path);
			free(relative_path);
			free(target_content_str);
			free(replace_content_str);
			overall_status = EXIT_FAILURE;
			current_pos =
			    after_replace_marker_content_area;  // Advance past where
			                                        // REPLACE content ended
			continue;
		}

		block_count++;
		if (verbose_mode) {
			printf("\n--- Processing Block %d: %s ---\n", block_count,
			       relative_path);
			printf("Target:\n---\n%s\n---\n", target_content_str);
			printf("Replace:\n---\n%s\n---\n", replace_content_str);
		}

		int block_status = process_block(
		    shared_root, abs_input_paths, num_input_paths, relative_path,
		    target_content_str, replace_content_str);

		if (block_status == 1) {
			overall_status = EXIT_FAILURE;
			if (!verbose_mode) {
				printf("[%d] %s: FAILED\n", block_count, relative_path);
			}
		} else if (block_status == 2) {
			if (!verbose_mode) {
				printf("[%d] %s: OK (CREATED)\n", block_count, relative_path);
			}
		} else {
			if (!verbose_mode) {
				printf("[%d] %s: OK\n", block_count, relative_path);
			}
		}

		free(relative_path);
		free(target_content_str);
		free(replace_content_str);

		current_pos = after_closing_block_marker;  // Advance current_pos past
		                                           // the processed block
	}

	// Final summary message
	if (verbose_mode) {
		printf("\nhnt-apply: Finished processing %d block(s).\n", block_count);
	} else if (block_count == 0 && *stdin_content != '\0' &&
	           overall_status == EXIT_SUCCESS) {
		printf("\nhnt-apply: No valid blocks found to process.\n");
	} else if (overall_status != EXIT_SUCCESS) {
		fprintf(stderr,
		        "\nhnt-apply: Finished processing %d block(s) with one or more "
		        "errors.\n",
		        block_count);
	} else {
		printf("\nhnt-apply: Finished processing %d block(s) successfully.\n",
		       block_count);
	}

	// --- 5. Cleanup ---
	free(stdin_content);
	free(shared_root);
	for (int i = 0; i < num_input_paths; ++i) {
		free(abs_input_paths[i]);
	}
	free(abs_input_paths);

	return overall_status;
}

// --- Helper Function Implementations ---

char *read_stream_to_string(FILE *stream) {
	size_t capacity = 4096;  // Initial capacity
	size_t size = 0;
	char *buffer = malloc(capacity);
	if (!buffer) {
		perror("Failed to allocate buffer for stream reading");
		return NULL;  // errno should be set by malloc
	}

	size_t bytes_read;
	while ((bytes_read = fread(buffer + size, 1, capacity - size - 1, stream)) >
	       0) {
		size += bytes_read;
		if (size + 1 >= capacity) {
			// Double capacity, check for overflow
			if (capacity > SIZE_MAX / 2) {
				fprintf(stderr,
				        "Error: Exceeded maximum buffer size while reading "
				        "stream.\n");
				free(buffer);
				errno = EOVERFLOW;  // Indicate overflow
				return NULL;
			}
			capacity *= 2;
			char *new_buffer = realloc(buffer, capacity);
			if (!new_buffer) {
				perror("Failed to realloc buffer for stream reading");
				free(buffer);
				return NULL;  // errno set by realloc
			}
			buffer = new_buffer;
		}
	}

	if (ferror(stream)) {
		// Don't use perror here as it might overwrite ferror's specific error
		fprintf(stderr, "Error reading from stream: %s\n", strerror(errno));
		free(buffer);
		return NULL;
	}

	buffer[size] = '\0';  // Null-terminate
	return buffer;
}

char *run_command(const char *cmd) {
	FILE *pipe = popen(cmd, "r");
	if (!pipe) {
		perror("popen failed");
		fprintf(stderr, "Command: %s\n", cmd);
		exit(EXIT_FAILURE);  // Exit on failure to start command
	}

	char *output = read_stream_to_string(pipe);

	int status = pclose(pipe);
	if (status == -1) {
		perror("pclose failed");
		free(output);  // output might be NULL if read_stream failed, free(NULL)
		               // is safe
		exit(EXIT_FAILURE);
	} else if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
		fprintf(stderr, "Command failed with status %d: %s\n",
		        WEXITSTATUS(status), cmd);
		fprintf(stderr, "Output: %s\n", output ? output : "(null)");
		free(output);
		exit(EXIT_FAILURE);
	} else if (!WIFEXITED(status)) {
		fprintf(stderr, "Command terminated abnormally (e.g., by signal): %s\n",
		        cmd);
		free(output);
		exit(EXIT_FAILURE);
	}

	if (!output) {
		// This case occurs if read_stream_to_string failed but pclose
		// succeeded.
		fprintf(stderr, "Failed to read output from command: %s\n", cmd);
		exit(EXIT_FAILURE);
	}

	// Trim trailing newline if present (often added by command output)
	size_t len = strlen(output);
	if (len > 0 && output[len - 1] == '\n') {
		output[len - 1] = '\0';
	}

	return output;
}

// Implementation for process_block
int process_block(const char *shared_root, char **abs_input_paths,
                  int num_input_paths, const char *rel_path, const char *target,
                  const char *replace) {
	// Mark unused parameters to avoid compiler warnings/errors
	(void)abs_input_paths;
	(void)num_input_paths;

	// --- 1. Construct full path ---
	char constructed_path_buf[PATH_MAX];
	int written = snprintf(constructed_path_buf, PATH_MAX, "%s/%s", shared_root,
	                       rel_path);
	if (written < 0 || written >= PATH_MAX) {
		fprintf(stdout,  // ERROR to stdout
		        "Error: Constructed path exceeds PATH_MAX or snprintf error "
		        "for %s/%s\n",
		        shared_root, rel_path);
		return 1;  // Cannot proceed without a valid path
	}

	// --- 2. Get canonical absolute path for comparison ---
	char canonical_path_buf[PATH_MAX];  // Buffer for realpath result
	char *resolved_path_str =
	    realpath(constructed_path_buf, canonical_path_buf);
	char *path_to_operate_on;  // This will point to either resolved_path_str or
	                           // constructed_path_buf

	size_t target_len = strlen(target);
	char *file_content = NULL;  // Initialize to NULL
	long file_size = 0;

	if (!resolved_path_str) {   // realpath failed
		if (errno == ENOENT) {  // File or path component does not exist
			// Condition for creation: target is empty AND creation is allowed
			if (target_len == 0 && !disallow_creating_flag) {
				if (verbose_mode) {
					printf(
					    "hnt-apply: File %s does not exist. Attempting to "
					    "create.\n",
					    constructed_path_buf);
				}

				// Ensure parent directory exists
				if (ensure_directory_exists(constructed_path_buf, 0755) != 0) {
					perror("Error creating parent directories");  // To stderr
					fprintf(stdout,
					        "Failed to create parent directories for: %s "
					        "(Error: %s)\n",
					        constructed_path_buf,
					        strerror(errno));  // To stdout
					return 1;                  // Failure
				}

				// Create and write to the new file
				FILE *fp_write = fopen(constructed_path_buf, "w");
				if (!fp_write) {
					perror("Error opening new file for writing");  // To stderr
					fprintf(stdout, "Failed creating file: %s (Error: %s)\n",
					        constructed_path_buf,
					        strerror(errno));  // To stdout
					return 1;                  // Failure
				}

				size_t replace_len = strlen(replace);
				if (fwrite(replace, 1, replace_len, fp_write) != replace_len) {
					if (ferror(fp_write)) {  // To stderr
						fprintf(stderr, "Error writing to new file %s: %s\n",
						        constructed_path_buf, strerror(errno));
					} else {  // To stderr
						fprintf(
						    stderr,
						    "Error writing to new file %s: Incomplete write.\n",
						    constructed_path_buf);
					}
					fclose(fp_write);
					// Optionally, remove partially written file here:
					// remove(constructed_path_buf);
					return 1;  // Failure
				}

				if (fclose(fp_write) != 0) {
					perror(
					    "Error closing new file after writing");  // To stderr
					fprintf(
					    stdout, "Failed closing created file: %s (Error: %s)\n",
					    constructed_path_buf, strerror(errno));  // To stdout
					return 1;                                    // Failure
				}

				if (verbose_mode) {
					printf("hnt-apply: Successfully created and wrote to %s\n",
					       constructed_path_buf);
				}
				return 2;  // Special success code for CREATED

			} else {  // File not found, but conditions for creation not met
				perror("Error resolving constructed path");  // To stderr (e.g.,
				                                             // "No such file or
				                                             // directory")
				fprintf(
				    stdout,
				    "Failed path resolution: %s (from %s + %s)\n",  // To stdout
				    constructed_path_buf, shared_root, rel_path);
				if (target_len != 0) {  // To stdout
					fprintf(stdout,
					        "File does not exist and target is not empty. "
					        "Cannot create.\n");
				}
				if (disallow_creating_flag && target_len == 0) {  // To stdout
					fprintf(stdout,
					        "File creation is disallowed by "
					        "--disallow-creating flag.\n");
				}
				return 1;  // Failure
			}
		} else {  // realpath failed for other reasons (e.g., permission denied
			      // for a component)
			perror("Error resolving constructed path");  // To stderr
			fprintf(stdout,
			        "Failed path resolution: %s (from %s + %s)\n",  // To stdout
			        constructed_path_buf, shared_root, rel_path);
			return 1;  // Failure
		}
	} else {  // realpath succeeded, file exists
		path_to_operate_on = resolved_path_str;  // resolved_path_str points
		                                         // into canonical_path_buf

		// File exists. Proceed to read and edit without checking against input
		// file paths. The original check against abs_input_paths for existing
		// files has been removed as per the updated requirements.

		// --- 4. Read target file content ---
		FILE *fp_read = fopen(path_to_operate_on, "r");
		if (!fp_read) {
			perror("Error opening file for reading");  // Use perror for system
			                                           // error (goes to stderr)
			fprintf(stdout,  // ERROR to stdout (context message only)
			        "Failed opening file for reading: %s\n",
			        path_to_operate_on);
			return 1;  // Indicate failure
		}
		file_content = read_stream_to_string(fp_read);
		fclose(fp_read);  // Close file immediately after reading
		if (!file_content) {
			// read_stream_to_string likely printed a system error via perror
			// (stderr)
			fprintf(stdout,  // ERROR to stdout (context message only)
			        "Failed reading content from file: %s\n",
			        path_to_operate_on);
			return 1;  // Indicate failure
		}
		file_size = strlen(file_content);
	}

	// --- 5. Search for target (if file existed and was read) ---
	// Note: if file was created, we returned '2' already.
	// This section is for modifying an existing file.

	// --- 5b. Handle empty target string for existing files ---
	if (target_len == 0) {
		// File exists (we are in the 'else' of realpath check).
		// If target is empty, only proceed if the file is also effectively
		// empty.
		bool file_is_effectively_empty =
		    (file_size == 0) || (file_size == 1 && file_content[0] == '\n');

		if (file_is_effectively_empty) {
			if (verbose_mode) {
				printf(
				    "hnt-apply: Applying replace content to effectively empty "
				    "file %s\n",
				    path_to_operate_on);
			}
			// Proceed to write replace content (same as normal replacement but
			// with empty prefix/suffix)
		} else {
			fprintf(stdout,  // ERROR to stdout
			        "Error: Target string is empty, but existing file %s is "
			        "not effectively empty (size %ld). Cannot apply change.\n",
			        path_to_operate_on, file_size);
			free(file_content);
			return 1;  // Indicate failure
		}
		// If effectively empty, the general replacement logic below will handle
		// it correctly by finding an empty target at the beginning of an empty
		// file_content. No, the general logic will find it MANY times in an
		// empty file. The original "empty target" logic should run here if
		// target_len == 0 AND file_content was loaded. Reuse the original logic
		// block for empty target replacement:
		size_t replace_len = strlen(replace);
		FILE *fp_write =
		    fopen(path_to_operate_on, "w");  // Open for writing (truncates)
		if (!fp_write) {
			perror(
			    "Error opening file for writing (empty target case on existing "
			    "file)");
			fprintf(stderr, "File: %s\n", path_to_operate_on);
			free(file_content);
			return 1;
		}
		if (fwrite(replace, 1, replace_len, fp_write) != replace_len) {
			if (ferror(fp_write)) {
				fprintf(stderr,
				        "Error writing replace content to file %s: %s\n",
				        path_to_operate_on, strerror(errno));
			} else {
				fprintf(stderr,
				        "Error writing replace content to file %s: Incomplete "
				        "write.\n",
				        path_to_operate_on);
			}
			fclose(fp_write);
			free(file_content);
			return 1;
		}
		if (fclose(fp_write) != 0) {
			perror(
			    "Error closing file after writing (empty target case on "
			    "existing file)");
			fprintf(stderr, "File: %s\n", path_to_operate_on);
			free(file_content);
			return 1;
		}
		free(file_content);
		return 0;  // Success
	}

	// --- 5c. Search for non-empty target in existing file content ---
	int count = 0;
	char *first_occurrence = NULL;
	char *search_start = file_content;

	while ((search_start = strstr(search_start, target)) != NULL) {
		count++;
		if (count == 1) {
			first_occurrence = search_start;
		} else if (count > 1) {
			break;
		}
		search_start += target_len;
		if (target_len == 0)
			break;  // Avoid infinite loop on empty target if logic changes
	}

	// --- 6. Check count and perform replacement ---
	if (count == 0) {
		fprintf(stdout,  // ERROR to stdout
		        "Error: Target not found in file %s\n", path_to_operate_on);
		fprintf(stdout, "Target (length %zu):\n---\n%s\n---\n", target_len,
		        target);  // ERROR to stdout
		free(file_content);
		return 1;  // Indicate failure
	} else if (count > 1) {
		fprintf(
		    stdout,  // ERROR to stdout
		    "Error: Target found %d times (expected exactly 1) in file %s\n",
		    count, path_to_operate_on);
		fprintf(stdout, "Target (length %zu):\n---\n%s\n---\n", target_len,
		        target);  // ERROR to stdout
		free(file_content);
		return 1;  // Indicate failure
	} else {
		// Found exactly once at 'first_occurrence'
		size_t replace_len = strlen(replace);
		size_t prefix_len = first_occurrence - file_content;
		char *suffix_start_ptr = first_occurrence + target_len;
		size_t suffix_len =
		    file_size -
		    (prefix_len + target_len);  // Corrected suffix_len calculation

		if (prefix_len > SIZE_MAX - replace_len ||
		    prefix_len + replace_len > SIZE_MAX - suffix_len) {
			fprintf(stderr,
			        "Error: New file size calculation would overflow for %s.\n",
			        path_to_operate_on);
			free(file_content);
			return 1;
		}
		size_t new_size = prefix_len + replace_len + suffix_len;

		char *new_content = malloc(new_size + 1);
		if (!new_content) {
			perror("Failed to allocate memory for new file content");
			free(file_content);
			return 1;
		}

		memcpy(new_content, file_content, prefix_len);
		memcpy(new_content + prefix_len, replace, replace_len);
		memcpy(new_content + prefix_len + replace_len, suffix_start_ptr,
		       suffix_len);
		new_content[new_size] = '\0';

		// --- 7. Write back to file ---
		FILE *fp_write = fopen(path_to_operate_on, "w");
		if (!fp_write) {
			perror("Error opening file for writing");
			fprintf(stderr, "File: %s\n", path_to_operate_on);
			free(new_content);
			free(file_content);
			return 1;
		}

		size_t written_bytes = fwrite(new_content, 1, new_size, fp_write);
		if (written_bytes != new_size) {
			if (ferror(fp_write)) {
				fprintf(stderr, "Error writing to file %s: %s\n",
				        path_to_operate_on, strerror(errno));
			} else {
				fprintf(stderr,
				        "Error writing to file %s: Incomplete write (wrote %zu "
				        "of %zu bytes).\n",
				        path_to_operate_on, written_bytes, new_size);
			}
			fclose(fp_write);
			free(new_content);
			free(file_content);
			return 1;
		}

		if (fclose(fp_write) != 0) {
			perror("Error closing file after writing");
			fprintf(stderr, "File: %s\n", path_to_operate_on);
			free(new_content);
			free(file_content);
			return 1;
		}
		free(new_content);
	}

	free(file_content);  // Free the original file content buffer if it was read
	// resolved_path_str points into stack buffer canonical_path_buf, no free
	// needed for it.
	return 0;  // Indicate success for modification
}
