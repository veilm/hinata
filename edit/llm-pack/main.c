// Define required for realpath on some systems
#define _XOPEN_SOURCE 500

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libgen.h> // For dirname
#include <limits.h> // For PATH_MAX
#include <errno.h>  // For errno
#include <unistd.h> // For getopt, realpath (sometimes in stdlib.h)
#include <stdbool.h> // For bool type

#ifndef PATH_MAX
#define PATH_MAX 4096 // Define PATH_MAX if not available
#endif

// Function to find the longest common directory prefix of two absolute paths
static void find_common_prefix(char *prefix, const char *path2_dir) {
    int len1 = strlen(prefix);
    int len2 = strlen(path2_dir);
    int min_len = len1 < len2 ? len1 : len2;
    int diff_idx = -1;

    // Find the first differing character index
    for (int i = 0; i < min_len; ++i) {
        if (prefix[i] != path2_dir[i]) {
            diff_idx = i;
            break;
        }
    }

    // Handle cases where one path is a prefix of the other directory path
    if (diff_idx == -1 && len1 != len2) {
        if (len1 < len2) { // prefix is shorter, e.g., /a/b vs /a/b/c
            // Check character in path2_dir immediately after the common part
            if (path2_dir[len1] != '/') {
                // Not a directory boundary, e.g. /a/b vs /a/bc
                // Difference starts after the common part; backtrack needed
                diff_idx = len1;
            }
            // If it is '/', prefix is already the correct common directory path.
            // No change needed to prefix.
        } else { // len2 < len1, path2_dir is shorter, e.g., /a/b/c vs /a/b
            // Check character in prefix immediately after the common part
            if (prefix[len2] != '/') {
                // Not a directory boundary, e.g. /a/bc vs /a/b
                // Difference starts after the common part; backtrack needed
                diff_idx = len2;
            } else {
                // path2_dir is the common directory path. Truncate prefix.
                // e.g. prefix=/a/b/c, path2_dir=/a/b -> prefix becomes /a/b
                prefix[len2] = '\0';
            }
        }
    }

    // If a difference was found (either initially or because paths diverged after common string)
    if (diff_idx != -1) {
        // Backtrack in prefix to the last '/' before or at the difference point
        int last_slash = -1;
        // Start search from diff_idx - 1, as diff_idx is the first differing char index
        for (int i = diff_idx - 1; i >= 0; --i) {
            if (prefix[i] == '/') {
                last_slash = i;
                break;
            }
        }

        // Determine the common root based on the last slash found
        if (last_slash == 0) { // Common root is "/"
            prefix[1] = '\0';
        } else if (last_slash > 0) {
            // Truncate prefix at the last slash found before the difference
            prefix[last_slash] = '\0';
        } else {
             // No '/' found before the difference.
             // This implies paths like "foo" and "bar" (shouldn't happen with realpath)
             // or "/foo" and "/bar". The common root should be "/".
             if (prefix[0] == '/') {
                 prefix[1] = '\0'; // Set to "/"
             } else {
                 // Should not happen with absolute paths from realpath
                 fprintf(stderr, "Error: Cannot determine common root directory for non-absolute-like paths.\n");
                 // Set prefix to empty string or handle error appropriately?
                 prefix[0] = '\0'; // Indicate no common root found?
                 // Consider exiting or returning an error code if this state is critical
                 // exit(EXIT_FAILURE);
             }
        }
    }
    // No need for final '/' cleanup, the logic above should handle it.
}


// Function to print the content of a file to stdout
// Returns 1 if the content ended with a newline, 0 otherwise.
static int print_file_content(const char *path) {
    FILE *file = fopen(path, "rb"); // Use binary mode for arbitrary file content
    if (!file) {
        fprintf(stderr, "Warning: Could not open file %s: %s. Skipping content.\n", path, strerror(errno));
        printf("<!-- Error reading file %s: %s -->", path, strerror(errno));
        return 0; // Indicate error / unknown ending
    }

    char buffer[4096];
    size_t bytes_read;
    int last_byte = -1; // Track the last byte successfully written

    while ((bytes_read = fread(buffer, 1, sizeof(buffer), file)) > 0) {
        // Write exactly the bytes read to stdout
        if (fwrite(buffer, 1, bytes_read, stdout) != bytes_read) {
             fprintf(stderr, "Warning: Error writing content of file %s to output: %s.\n", path, strerror(errno));
             printf("<!-- Error writing file %s -->", path);
             fclose(file);
             return 0; // Indicate error / unknown ending on write error
        }
        // Update last_byte with the last byte actually written in this chunk
        if (bytes_read > 0) {
             last_byte = buffer[bytes_read - 1];
        }
    }

    if (ferror(file)) {
        fprintf(stderr, "Warning: Error reading file %s: %s.\n", path, strerror(errno));
        printf("<!-- Error during reading file %s -->", path);
        // Continue to return based on last byte written, even if there was a read error after some writes
    }

    fclose(file);

    // Return true (1) if the last byte written was a newline, false (0) otherwise
    // Handles empty files correctly (last_byte remains -1, returns 0)
    return (last_byte == '\n');
}

int main(int argc, char *argv[]) {
    bool print_code_fences = true;
    bool print_common_root_only = false; // Flag for -p option
    int opt;

    // Parse command-line options
    // Add 'p' to the list of valid options
    while ((opt = getopt(argc, argv, "np")) != -1) {
        switch (opt) {
            case 'n':
                print_code_fences = false;
                break;
            case 'p':
                print_common_root_only = true;
                break;
            default: /* '?' */
                // Update usage message
                fprintf(stderr, "Usage: %s [-n] [-p] <file1> [file2] ...\n", argv[0]);
                return EXIT_FAILURE;
        }
    }

    // Check if any file arguments were provided after options
    if (optind >= argc) {
        // Update usage message
        fprintf(stderr, "Usage: %s [-n] [-p] <file1> [file2] ...\n", argv[0]);
        fprintf(stderr, "Error: No input files specified.\n");
        return EXIT_FAILURE;
    }

    int num_files = argc - optind; // Number of files is remaining arguments
    char **abs_paths = malloc(num_files * sizeof(char *));
    char **rel_paths = malloc(num_files * sizeof(char *));
    char common_root[PATH_MAX] = "";
    char path_copy[PATH_MAX]; // For dirname manipulation
    char dir_buffer[PATH_MAX]; // For dirname result

    if (!abs_paths || !rel_paths) {
        perror("Failed to allocate memory for paths");
        free(abs_paths);
        free(rel_paths);
        return EXIT_FAILURE;
    }

    // Allocate space for each path string
    for (int i = 0; i < num_files; ++i) {
        abs_paths[i] = malloc(PATH_MAX);
        rel_paths[i] = malloc(PATH_MAX);
        if (!abs_paths[i] || !rel_paths[i]) {
            perror("Failed to allocate memory for path string");
            // Free already allocated memory before exiting
            for (int j = 0; j <= i; ++j) {
                free(abs_paths[j]);
                free(rel_paths[j]);
            }
            free(abs_paths);
            free(rel_paths);
            return EXIT_FAILURE;
        }
    }

    // 1. Get absolute paths and find common root directory
    for (int i = 0; i < num_files; ++i) {
        // Use optind to get the correct file argument index
        if (realpath(argv[optind + i], abs_paths[i]) == NULL) {
            fprintf(stderr, "Error resolving path %s: %s\n", argv[optind + i], strerror(errno));
            // Cleanup allocated memory
             for (int j = 0; j < num_files; ++j) {
                free(abs_paths[j]);
                free(rel_paths[j]);
            }
            free(abs_paths);
            free(rel_paths);
            return EXIT_FAILURE;
        }

        // Use dirname on a copy to find the directory
        strncpy(path_copy, abs_paths[i], PATH_MAX - 1);
        path_copy[PATH_MAX - 1] = '\0'; // Ensure null termination
        char *current_dir = dirname(path_copy);
        strncpy(dir_buffer, current_dir, PATH_MAX -1); // Copy result of dirname
        dir_buffer[PATH_MAX - 1] = '\0';


        if (i == 0) {
            // Initialize common_root with the directory of the first file
            strncpy(common_root, dir_buffer, PATH_MAX -1);
            common_root[PATH_MAX - 1] = '\0';
             // Ensure common_root doesn't end with '/' unless it's just "/"
            int root_len = strlen(common_root);
            if (root_len > 1 && common_root[root_len - 1] == '/') {
                common_root[root_len - 1] = '\0';
            }
        } else {
            // Update common_root by finding common prefix with the current file's directory
            find_common_prefix(common_root, dir_buffer);
        }
    }

    // If -p was specified, print the common root and exit
    if (print_common_root_only) {
        printf("%s\n", common_root);
        // Free allocated memory before exiting
        for (int i = 0; i < num_files; ++i) {
            free(abs_paths[i]);
            free(rel_paths[i]);
        }
        free(abs_paths);
        free(rel_paths);
        return EXIT_SUCCESS;
    }

    // 2. Calculate relative paths
    size_t root_len = strlen(common_root); // Use size_t for length
    // Offset is 1 character after the root path string, unless root is "/"
    // Cast root_len to int for arithmetic if needed, or ensure offset calculation is safe
    int offset = (int)root_len + (strcmp(common_root, "/") == 0 ? 0 : 1);

    for (int i = 0; i < num_files; ++i) {
        if (strlen(abs_paths[i]) > root_len) { // Now comparing size_t with size_t
             // Check if abs_path actually starts with common_root + '/'
             // Use root_len (size_t) directly with strncmp
             if (strncmp(abs_paths[i], common_root, root_len) == 0 &&
                 (root_len == 1 || abs_paths[i][root_len] == '/')) // root_len is size_t here
             {
                 // Ensure offset is not out of bounds, though realpath should guarantee structure
                 // if common_root logic is correct.
                 strcpy(rel_paths[i], abs_paths[i] + offset);
             } else {
                 // This might happen if common root calculation is imperfect or paths are strange
                 // As a fallback, maybe just use the filename? Or the full absolute path?
                 // Let's use the absolute path minus the leading '/' for now if root is '/'
                 // Or just the filename as a simpler fallback.
                 fprintf(stderr, "Warning: Path %s does not seem to be under calculated root %s. Using filename only.\n", abs_paths[i], common_root);
                 strncpy(path_copy, abs_paths[i], PATH_MAX - 1);
                 path_copy[PATH_MAX - 1] = '\0';
                 strcpy(rel_paths[i], basename(path_copy));
             }

        } else if (strcmp(abs_paths[i], common_root) == 0) {
             // Path is the common root itself? Unlikely for files. Use basename.
             fprintf(stderr, "Warning: Path %s is the same as the calculated root %s. Using filename only.\n", abs_paths[i], common_root);
             strncpy(path_copy, abs_paths[i], PATH_MAX - 1);
             path_copy[PATH_MAX - 1] = '\0';
             strcpy(rel_paths[i], basename(path_copy));
        } else {
             // Absolute path is shorter than root? Should not happen.
             fprintf(stderr, "Error: Absolute path %s is shorter than calculated root %s.\n", abs_paths[i], common_root);
             // Cleanup allocated memory
             for (int j = 0; j < num_files; ++j) {
                free(abs_paths[j]);
                free(rel_paths[j]);
            }
            free(abs_paths);
            free(rel_paths);
            return EXIT_FAILURE;
        }
    }

    // 3. Print XML structure (conditionally with code fences)
    if (print_code_fences) {
        printf("```\n");
    }
    printf("<file_paths>\n");
    for (int i = 0; i < num_files; ++i) {
        printf("%s\n", rel_paths[i]);
    }
    printf("</file_paths>\n");

    // Separator before the first file content block
    printf("\n");

    for (int i = 0; i < num_files; ++i) {
        // Print opening tag for the current file
        printf("<%s>\n", rel_paths[i]);

        // Print file content and check if it ends with a newline
        // Use optind to get the correct file argument index
        int ends_with_newline = print_file_content(argv[optind + i]); // Use original path

        // Print closing tag, adding a newline only if the content didn't end with one
        // Also check file is not empty before potentially adding a newline
        FILE *check_file = fopen(argv[optind + i], "rb");
        long file_size = -1;
        if (check_file) {
            fseek(check_file, 0, SEEK_END);
            file_size = ftell(check_file);
            fclose(check_file);
        }

        if (!ends_with_newline && file_size > 0) {
             printf("\n");
        }
        printf("</%s>", rel_paths[i]);

        // Print separator for the *next* file block, if there is one
        // This creates one blank line between </file1> and <file2>
        if (i < num_files - 1) {
            printf("\n\n");
        }
    }
    printf("\n"); // Final newline before potential fence

    if (print_code_fences) {
        printf("```\n"); // Final code fence at the end of output
    }

    // 4. Free memory
    for (int i = 0; i < num_files; ++i) {
        free(abs_paths[i]);
        free(rel_paths[i]);
    }
    free(abs_paths);
    free(rel_paths);

    return EXIT_SUCCESS;
}
