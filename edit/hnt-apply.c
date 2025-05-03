// Define _GNU_SOURCE to enable various extensions like strndup, realpath,
// popen, pclose Needs to be defined before including any standard headers.
#define _GNU_SOURCE
#include <errno.h>   // For errno, perror
#include <getopt.h>  // For getopt_long
#include <limits.h>  // For PATH_MAX
#include <stdint.h>  // For SIZE_MAX
#include <stdio.h>
#include <stdlib.h>  // For realpath, malloc, free, exit, EXIT_FAILURE, EXIT_SUCCESS, size_t, NULL
#include <string.h>
#include <sys/wait.h>  // For WIFEXITED, WEXITSTATUS with pclose
#include <unistd.h>    // For popen, pclose

// --- Global Flags ---
int verbose_mode = 0;  // Global flag for verbose output

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
 * finds the target section exactly once, replaces it, and writes the modified
 * content back to the file. Exits the program on any error.
 *
 * @param shared_root The shared root path obtained from llm-pack.
 * @param abs_input_paths An array of absolute paths corresponding to the CLI
 * arguments.
 * @param num_input_paths The number of paths in abs_input_paths.
 * @param rel_path The relative path parsed from the LLM block.
 * @param target The target content to search for.
 * @param replace The replacement content.
 * @return 0 on success, 1 on failure.
 */
int process_block(const char *shared_root, char **abs_input_paths,
                  int num_input_paths, const char *rel_path, const char *target,
                  const char *replace);

// --- Main Function ---

int main(int argc, char *argv[]) {
	// --- 0. Parse Command Line Options ---
	struct option long_options[] = {
	    {"verbose", no_argument, &verbose_mode, 1}, {0, 0, 0, 0}
	    // End of options
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
				        "Usage: %s [-v|--verbose] <file1> [file2] ...\n",
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
		fprintf(stderr, "Usage: %s [-v|--verbose] <file1> [file2] ...\n",
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
		printf("hnt-edit: Running: %s\n", llm_pack_cmd);
	}
	char *shared_root = run_command(llm_pack_cmd);
	if (verbose_mode) {
		printf("hnt-edit: Shared root: %s\n", shared_root);
	}
	free(llm_pack_cmd);  // Command string no longer needed

	// --- 3. Read LLM generation from stdin ---
	if (verbose_mode) {
		printf("hnt-edit: Reading LLM generation from stdin...\n");
	}
	char *stdin_content = read_stream_to_string(stdin);
	if (!stdin_content) {
		// Error reading already prints message in read_stream_to_string or
		// run_command Just ensure cleanup and exit Clean up
		free(shared_root);
		for (int i = 0; i < num_input_paths; ++i) free(abs_input_paths[i]);
		free(abs_input_paths);
		// The frees below were duplicates causing use-after-free errors.
		// The resources are already freed correctly by lines 150-152.
		return EXIT_FAILURE;
	}
	if (verbose_mode) {
		printf("hnt-edit: Finished reading stdin.\n");
	}

	// --- 4. Parse stdin and process blocks ---
	if (!verbose_mode &&
	    *stdin_content != '\0') {  // Only print if there might be blocks
		printf("hnt-edit: Processing blocks...\n");
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

		// Find start of the line *after* the opening ``` marker
		char *line_after_block_start = strchr(block_start, '\n');
		if (!line_after_block_start) {
			// Malformed block: ``` not followed by newline
			// If block_start is not NULL, it means we found ``` but no newline
			// after it. If stdin wasn't empty, this is an error. If stdin was
			// empty or only whitespace, block_start would be NULL.
			if (block_start != NULL &&
			    strlen(block_start) >
			        strlen(
			            block_marker)) {  // Check if there's content after ```
				fprintf(
				    stderr,
				    "Error: Malformed block - '%s' not followed by newline.\n",
				    block_marker);
				overall_status = EXIT_FAILURE;
				current_pos = block_start +
				              strlen(block_marker);  // Advance past the marker
				                                     // to avoid looping
				continue;  // Try to find the next block
			}
			break;  // Otherwise, assume end of input or only whitespace left
		}
		char *path_start = line_after_block_start + 1;

		// Find the end of the path line
		char *path_end = strchr(path_start, '\n');
		if (!path_end) {
			fprintf(stderr,
			        "Error: Malformed block - path line starting near '%.*s' "
			        "not terminated by newline.\n",
			        (int)MIN(20, strlen(path_start)),
			        path_start);  // Print start of path line for context
			overall_status = EXIT_FAILURE;
			current_pos = path_start;  // Advance past the point of error
			continue;
		}

		// Extract relative path
		char *relative_path = strndup(path_start, path_end - path_start);
		if (!relative_path) {
			perror("strndup failed for relative_path");
			overall_status = EXIT_FAILURE;
			current_pos = path_end;  // Advance past the point of error
			continue;
		}

		// Find TARGET marker after the path
		char *target_delim_start = strstr(path_end, target_marker);
		if (!target_delim_start) {
			fprintf(stderr, "Error: Missing '%s' after path '%s'\n",
			        target_marker, relative_path);
			free(relative_path);
			overall_status = EXIT_FAILURE;
			current_pos = path_end;  // Advance past the path line
			continue;
		}

		// Find start of target content (line after TARGET marker)
		char *target_start = strchr(target_delim_start, '\n');
		if (!target_start) {
			fprintf(stderr, "Error: Missing newline after '%s' for path '%s'\n",
			        target_marker, relative_path);
			free(relative_path);
			overall_status = EXIT_FAILURE;
			current_pos = target_delim_start +
			              strlen(target_marker);  // Advance past marker
			continue;
		}
		target_start++;  // Move past the newline

		// Find separator marker after target content
		char *separator_delim_start = strstr(target_start, separator_marker);
		if (!separator_delim_start) {
			fprintf(stderr,
			        "Error: Missing '%s' after target section for path '%s'\n",
			        separator_marker, relative_path);
			free(relative_path);
			overall_status = EXIT_FAILURE;
			// Advance past where we started searching for the separator
			current_pos = target_start;
			continue;
		}

		// Find end of target content (character before the separator line)
		char *target_end = separator_delim_start;
		// Trim trailing newline(s) before the separator marker
		while (target_end > target_start &&
		       (*(target_end - 1) == '\n' || *(target_end - 1) == '\r')) {
			target_end--;
		}
		char *target_content = strndup(target_start, target_end - target_start);
		if (!target_content) {
			perror("strndup failed for target_content");
			free(relative_path);
			overall_status = EXIT_FAILURE;
			current_pos =
			    separator_delim_start;  // Advance past separator marker
			continue;
		}

		// Find start of replace content (line after separator marker)
		char *replace_start = strchr(separator_delim_start, '\n');
		if (!replace_start) {
			fprintf(stderr, "Error: Missing newline after '%s' for path '%s'\n",
			        separator_marker, relative_path);
			free(relative_path);
			free(target_content);
			overall_status = EXIT_FAILURE;
			current_pos = separator_delim_start +
			              strlen(separator_marker);  // Advance past marker
			continue;
		}
		replace_start++;  // Move past the newline

		// Find REPLACE marker after replace content
		char *replace_delim_start = strstr(replace_start, replace_marker);
		if (!replace_delim_start) {
			fprintf(stderr,
			        "Error: Missing '%s' after replace section for path '%s'\n",
			        replace_marker, relative_path);
			free(relative_path);
			free(target_content);
			overall_status = EXIT_FAILURE;
			current_pos =
			    replace_start;  // Advance past where replace content started
			continue;
		}

		// Find end of replace content (character before the REPLACE line)
		char *replace_end = replace_delim_start;
		// Trim trailing newline(s) before the replace marker
		while (replace_end > replace_start &&
		       (*(replace_end - 1) == '\n' || *(replace_end - 1) == '\r')) {
			replace_end--;
		}
		char *replace_content =
		    strndup(replace_start, replace_end - replace_start);
		if (!replace_content) {
			perror("strndup failed for replace_content");
			free(relative_path);
			free(target_content);
			overall_status = EXIT_FAILURE;
			current_pos = replace_delim_start;  // Advance past replace marker
			continue;
		}

		// Find the closing ``` marker
		char *block_end_marker = strstr(replace_delim_start, block_marker);
		if (!block_end_marker) {
			fprintf(
			    stderr,
			    "Error: Missing closing '%s' for block related to path '%s'\n",
			    block_marker, relative_path);
			free(relative_path);
			free(target_content);
			free(replace_content);
			overall_status = EXIT_FAILURE;
			// Advance past the point where we expected the closing marker
			current_pos = replace_delim_start + strlen(replace_marker);
			continue;
		}

		block_count++;
		if (verbose_mode) {
			printf("\n--- Processing Block %d: %s ---\n", block_count,
			       relative_path);
			printf("Target:\n---\n%s\n---\n", target_content);
			printf("Replace:\n---\n%s\n---\n", replace_content);
		}

		// Process the extracted block
		int block_status =
		    process_block(shared_root, abs_input_paths, num_input_paths,
		                  relative_path, target_content, replace_content);

		// Log status and update overall status
		if (block_status != 0) {
			overall_status = EXIT_FAILURE;
			// Error message already printed by process_block
			if (!verbose_mode) {
				printf("[%d] %s: FAILED\n", block_count, relative_path);
			}
		} else {
			// Success
			if (!verbose_mode) {
				printf("[%d] %s: OK\n", block_count, relative_path);
			}
		}

		// Free memory for this block's parsed content
		free(relative_path);
		free(target_content);
		free(replace_content);

		// Advance current_pos past the end of the processed block
		current_pos = block_end_marker + strlen(block_marker);
	}

	// Final summary message
	if (verbose_mode) {
		printf("\nhnt-edit: Finished processing %d block(s).\n", block_count);
	} else if (block_count == 0 && *stdin_content != '\0' &&
	           overall_status == EXIT_SUCCESS) {
		// Only print "No valid blocks" if no errors occurred during parsing
		// attempts
		printf("\nhnt-edit: No valid blocks found to process.\n");
	} else if (overall_status != EXIT_SUCCESS) {
		fprintf(stderr,
		        "\nhnt-edit: Finished processing %d block(s) with one or more "
		        "errors.\n",
		        block_count);
	} else {
		// Successful run, non-verbose, blocks processed
		printf("\nhnt-edit: Finished processing %d block(s) successfully.\n",
		       block_count);
	}

	// --- 5. Cleanup ---
	free(stdin_content);
	free(shared_root);
	for (int i = 0; i < num_input_paths; ++i) {
		free(abs_input_paths[i]);
	}
	free(abs_input_paths);

	return overall_status;  // Return 0 if all blocks succeeded, 1 otherwise
}

// --- Helper Function Implementations ---

// (read_stream_to_string remains the same)

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
	// --- 1. Construct full path ---
	char constructed_path_buf[PATH_MAX];
	int written = snprintf(constructed_path_buf, PATH_MAX, "%s/%s", shared_root,
	                       rel_path);
	if (written < 0 || written >= PATH_MAX) {
		fprintf(stderr,
		        "Error: Constructed path exceeds PATH_MAX or snprintf error "
		        "for %s/%s\n",
		        shared_root, rel_path);
		return 1;  // Cannot proceed without a valid path
	}

	// --- 2. Get canonical absolute path for comparison ---
	// Use a buffer for realpath first to avoid allocation if it fails
	// immediately
	char canonical_path_buf[PATH_MAX];
	char *canonical_path = realpath(constructed_path_buf, canonical_path_buf);
	if (!canonical_path) {
		// If realpath fails, canonical_path is NULL, check errno
		// If realpath fails, canonical_path is NULL, check errno
		perror("Error resolving constructed path");
		fprintf(stderr, "Failed path: %s (from %s + %s)\n",
		        constructed_path_buf, shared_root, rel_path);
		// realpath doesn't allocate on failure when buffer is provided
		return 1;  // Indicate failure
	}
	// Note: canonical_path now points inside canonical_path_buf

	// --- 3. Verify against input paths ---
	int found_match = 0;
	for (int i = 0; i < num_input_paths; ++i) {
		if (strcmp(canonical_path, abs_input_paths[i]) == 0) {
			found_match = 1;
			break;
		}
	}
	if (!found_match) {
		fprintf(stderr,
		        "Error: Parsed path '%s' (from %s/%s) does not match any input "
		        "file path.\n",
		        canonical_path, shared_root, rel_path);
		fprintf(stderr, "Input paths were:\n");
		for (int i = 0; i < num_input_paths; ++i) {
			fprintf(stderr, "- %s\n", abs_input_paths[i]);
		}
		return 1;  // Indicate failure
	}

	// --- 4. Read target file content ---
	FILE *fp_read = fopen(canonical_path, "r");
	if (!fp_read) {
		perror("Error opening file for reading");
		fprintf(stderr, "File: %s\n", canonical_path);
		return 1;  // Indicate failure
	}
	char *file_content = read_stream_to_string(fp_read);
	fclose(fp_read);  // Close file immediately after reading
	if (!file_content) {
		// read_stream_to_string already printed an error
		fprintf(stderr, "Error reading content from file: %s\n",
		        canonical_path);
		// No file_content to free yet
		return 1;  // Indicate failure
	}
	long file_size =
	    strlen(file_content);  // Use strlen since read_stream null-terminates

	// --- 5. Search for target ---
	int count = 0;
	char *first_occurrence = NULL;
	char *search_start = file_content;
	size_t target_len = strlen(target);

	// Handle empty target string - treat as error? Or match everywhere?
	// Let's treat empty target as an error because replacement is ill-defined.
	// Let's treat empty target as an error because replacement is ill-defined.
	if (target_len == 0) {
		fprintf(
		    stderr,
		    "Error: Target string is empty for file %s. Cannot apply change.\n",
		    canonical_path);
		free(file_content);
		return 1;  // Indicate failure
	}

	while ((search_start = strstr(search_start, target)) != NULL) {
		count++;
		if (count == 1) {
			first_occurrence =
			    search_start;  // Store the pointer to the first match
		} else if (count > 1) {
			break;  // Found more than one, no need to continue searching
		}
		// Move search start past the current occurrence to find subsequent ones
		search_start += target_len;  // Move past the found target
		// Optimization: if target_len is 0, this would loop infinitely, hence
		// the check above.
	}

	// --- 6. Check count and perform replacement ---
	if (count == 0) {
		fprintf(stderr, "Error: Target not found in file %s\n", canonical_path);
		fprintf(stderr, "Target (length %zu):\n---\n%s\n---\n", target_len,
		        target);
		free(file_content);
		return 1;  // Indicate failure
	} else if (count > 1) {
		fprintf(
		    stderr,
		    "Error: Target found %d times (expected exactly 1) in file %s\n",
		    count, canonical_path);
		fprintf(stderr, "Target (length %zu):\n---\n%s\n---\n", target_len,
		        target);
		free(file_content);
		return 1;  // Indicate failure
	} else {
		// Found exactly once at 'first_occurrence'
		size_t replace_len = strlen(replace);
		size_t prefix_len = first_occurrence - file_content;
		// Suffix starts immediately after the target string in the original
		// content
		char *suffix_start_ptr = first_occurrence + target_len;
		// Calculate suffix length based on pointers
		size_t suffix_len = file_size - (suffix_start_ptr - file_content);

		// Calculate new total size
		// Check for potential overflow before calculating new_size
		if (prefix_len > SIZE_MAX - replace_len ||
		    prefix_len + replace_len > SIZE_MAX - suffix_len) {
			fprintf(stderr,
			        "Error: New file size calculation would overflow for %s.\n",
			        canonical_path);
			free(file_content);
			return 1;  // Indicate failure
		}
		size_t new_size = prefix_len + replace_len + suffix_len;

		// Allocate memory for the new content
		char *new_content = malloc(new_size + 1);  // +1 for null terminator
		if (!new_content) {
			perror("Failed to allocate memory for new file content");
			free(file_content);
			return 1;  // Indicate failure
		}

		// Build new content: prefix + replace + suffix
		memcpy(new_content, file_content, prefix_len);
		memcpy(new_content + prefix_len, replace, replace_len);
		memcpy(new_content + prefix_len + replace_len, suffix_start_ptr,
		       suffix_len);
		new_content[new_size] = '\0';  // Null-terminate the new content

		// --- 7. Write back to file ---
		FILE *fp_write =
		    fopen(canonical_path, "w");  // Open for writing (truncates)
		if (!fp_write) {
			perror("Error opening file for writing");
			fprintf(stderr, "File: %s\n", canonical_path);
			free(new_content);
			free(file_content);
			return 1;  // Indicate failure
		}

		size_t written = fwrite(new_content, 1, new_size, fp_write);
		if (written != new_size) {
			// Check ferror before perror for more specific error
			if (ferror(fp_write)) {
				fprintf(stderr, "Error writing to file %s: %s\n",
				        canonical_path, strerror(errno));
			} else {
				fprintf(stderr,
				        "Error writing to file %s: Incomplete write (wrote %zu "
				        "of %zu bytes).\n",
				        canonical_path, written, new_size);
			}
			fclose(fp_write);  // Attempt to close even on error
			free(new_content);
			free(file_content);
			return 1;  // Indicate failure
		}

		// Ensure data is flushed and check for errors during close
		if (fclose(fp_write) != 0) {
			perror("Error closing file after writing");
			fprintf(stderr, "File: %s\n", canonical_path);
			// Data might be partially written or corrupted
			free(new_content);
			free(file_content);
			return 1;  // Indicate failure
		}

		// Success message is now handled in main() based on verbose_mode
		// printf("Successfully applied change to %s\n", canonical_path);
		free(new_content);  // Free the buffer holding the modified content
	}

	free(file_content);  // Free the original file content buffer
	// No need to free canonical_path as it points into canonical_path_buf
	// (stack allocated)
	return 0;  // Indicate success
}
