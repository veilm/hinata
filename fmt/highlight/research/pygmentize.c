#define _POSIX_C_SOURCE 200809L // For fdopen, dprintf if needed, although not strictly used here
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <errno.h>
#include <stddef.h> // For size_t

#define READ_CHUNK_SIZE 4096
#define OUTPUT_CHUNK_SIZE 4096

// Structure to hold dynamically growing buffer
typedef struct {
    char *data;
    size_t len;
    size_t capacity;
} buffer_t;

// Initialize a buffer
void buffer_init(buffer_t *buf) {
    buf->data = NULL;
    buf->len = 0;
    buf->capacity = 0;
}

// Append data to a buffer, reallocating if necessary
int buffer_append(buffer_t *buf, const char *data, size_t len) {
    if (buf->len + len > buf->capacity) {
        size_t new_capacity = buf->capacity ? buf->capacity * 2 : READ_CHUNK_SIZE;
        while (new_capacity < buf->len + len) {
            new_capacity *= 2;
        }
        char *new_data = realloc(buf->data, new_capacity);
        if (!new_data) {
            perror("realloc failed in buffer_append");
            return 0; // Failure
        }
        buf->data = new_data;
        buf->capacity = new_capacity;
    }
    memcpy(buf->data + buf->len, data, len);
    buf->len += len;
    return 1; // Success
}

// Free buffer memory
void buffer_free(buffer_t *buf) {
    free(buf->data);
    buffer_init(buf); // Reset state
}

// Function to run pygmentize and capture its output
// Returns a dynamically allocated string with the output (must be freed by caller)
// Returns NULL on failure
char* run_pygmentize(const char *input_data, size_t input_len, size_t *output_len) {
    int stdin_pipe[2]; // Pipe for sending data to pygmentize's stdin
    int stdout_pipe[2]; // Pipe for receiving data from pygmentize's stdout
    pid_t pid;

    if (pipe(stdin_pipe) == -1 || pipe(stdout_pipe) == -1) {
        perror("pipe failed");
        // Close any pipes that were opened successfully
        if (stdin_pipe[0] != -1) close(stdin_pipe[0]);
        if (stdin_pipe[1] != -1) close(stdin_pipe[1]);
        if (stdout_pipe[0] != -1) close(stdout_pipe[0]);
        if (stdout_pipe[1] != -1) close(stdout_pipe[1]);
        return NULL;
    }

    pid = fork();
    if (pid == -1) {
        perror("fork failed");
        close(stdin_pipe[0]);
        close(stdin_pipe[1]);
        close(stdout_pipe[0]);
        close(stdout_pipe[1]);
        return NULL;
    }

    if (pid == 0) { // Child process
        // Close unused pipe ends
        close(stdin_pipe[1]);  // Close write end of stdin pipe
        close(stdout_pipe[0]); // Close read end of stdout pipe

        // Redirect stdin to read from the stdin pipe
        if (dup2(stdin_pipe[0], STDIN_FILENO) == -1) {
            perror("dup2 stdin failed");
            _exit(EXIT_FAILURE); // Use _exit in child after fork
        }
        close(stdin_pipe[0]); // Close original fd

        // Redirect stdout to write to the stdout pipe
        if (dup2(stdout_pipe[1], STDOUT_FILENO) == -1) {
            perror("dup2 stdout failed");
            _exit(EXIT_FAILURE);
        }
        close(stdout_pipe[1]); // Close original fd

        // Prepare arguments for pygmentize
        const char *args[] = {"pygmentize", "-l", "markdown", NULL};

        // Execute pygmentize
        execvp(args[0], (char *const *)args);

        // If execvp returns, it failed
        perror("execvp pygmentize failed");
        fprintf(stderr, "Ensure 'pygmentize' is installed and in your PATH.\n");
        _exit(EXIT_FAILURE);

    } else { // Parent process
        buffer_t output_buffer;
        buffer_init(&output_buffer);
        char read_buf[OUTPUT_CHUNK_SIZE];
        ssize_t bytes_read_from_child;
        ssize_t total_written = 0;
        ssize_t bytes_written;

        // Close unused pipe ends
        close(stdin_pipe[0]);  // Close read end of stdin pipe
        close(stdout_pipe[1]); // Close write end of stdout pipe

        // Write input data to pygmentize's stdin
        // Loop to handle potential partial writes
        while (total_written < input_len) {
             bytes_written = write(stdin_pipe[1], input_data + total_written, input_len - total_written);
             if (bytes_written <= 0) {
                 if (bytes_written == -1 && errno != EPIPE) { // Ignore broken pipe, it means child exited potentially
                     perror("write to child stdin failed");
                 }
                 // Might happen if child exits early due to error or short input
                 break;
             }
             total_written += bytes_written;
        }
        close(stdin_pipe[1]); // Close write end - signals EOF to child's stdin

        // Read output from pygmentize's stdout
        while ((bytes_read_from_child = read(stdout_pipe[0], read_buf, sizeof(read_buf))) > 0) {
            if (!buffer_append(&output_buffer, read_buf, bytes_read_from_child)) {
                // Error appending (likely memory allocation failure)
                buffer_free(&output_buffer);
                close(stdout_pipe[0]);
                waitpid(pid, NULL, 0); // Clean up zombie process
                return NULL;
            }
        }
        close(stdout_pipe[0]); // Close read end

        if (bytes_read_from_child == -1) {
             perror("read from child stdout failed");
             buffer_free(&output_buffer);
             waitpid(pid, NULL, 0);
             return NULL;
        }


        // Wait for child process to terminate and check status
        int status;
        waitpid(pid, &status, 0);
        if (!(WIFEXITED(status) && WEXITSTATUS(status) == 0)) {
             fprintf(stderr, "Warning: pygmentize process did not exit cleanly (status %d).\n", WEXITSTATUS(status));
             // Continue anyway, maybe got partial output
        }

        // Null-terminate the buffer data (important!)
        if (!buffer_append(&output_buffer, "\0", 1)) {
             fprintf(stderr, "Failed to null-terminate output buffer.\n");
             buffer_free(&output_buffer);
             return NULL;
        }

        *output_len = output_buffer.len - 1; // Store length excluding null terminator
        return output_buffer.data; // Return ownership of the buffer data
    }
}

int main() {
    buffer_t input_buf;
    buffer_init(&input_buf);

    char *prev_output = NULL;
    size_t prev_output_len = 0;

    int first_run = 1;
    char *line = NULL;       // Buffer for getline
    size_t line_capacity = 0; // Capacity of the buffer
    ssize_t line_len;        // Length of the line read

    // Read from stdin line by line using getline
    while ((line_len = getline(&line, &line_capacity, stdin)) != -1) {
        // Append the line (which includes the newline, if present) to the input buffer
        if (!buffer_append(&input_buf, line, line_len)) {
            fprintf(stderr, "Error appending stdin line to input buffer.\n");
            buffer_free(&input_buf);
            free(prev_output);
            free(line); // Free getline buffer before exiting
            return EXIT_FAILURE;
        }

        // Run pygmentize with the current complete input buffer
        size_t current_output_len = 0;
        char *current_output = run_pygmentize(input_buf.data, input_buf.len, &current_output_len);

        if (!current_output) {
            fprintf(stderr, "Error running pygmentize.\n");
            buffer_free(&input_buf);
            free(prev_output);
            free(line); // Free getline buffer before exiting
            return EXIT_FAILURE;
        }

        // Compare and write output
        if (first_run) {
            // First time, write the whole output
            ssize_t written = write(STDOUT_FILENO, current_output, current_output_len);
            if (written < 0 || (size_t)written != current_output_len) {
                 perror("Failed to write initial output");
                 // Consider if we should exit here or just warn
            }
            first_run = 0;
        } else {
            // Subsequent times, find the difference
            if (prev_output && current_output_len >= prev_output_len &&
                memcmp(current_output, prev_output, prev_output_len) == 0)
            {
                // The new output starts with the previous output, print only the suffix
                size_t diff_len = current_output_len - prev_output_len;
                if (diff_len > 0) {
                    ssize_t written = write(STDOUT_FILENO, current_output + prev_output_len, diff_len);
                     if (written < 0 || (size_t)written != diff_len) {
                         perror("Failed to write diff output");
                         // Consider if we should exit here or just warn
                     }
                }
            } else {
                // Output doesn't start with previous, or shrunk.
                // This can happen if edits remove ANSI sequences or change structure significantly.
                // Safest bet is to clear screen (if interactive) and rewrite the whole thing.
                // For simplicity, just rewrite without clearing.
                // Optionally add a clear screen sequence: write(STDOUT_FILENO, "\033[H\033[J", 6);
                fprintf(stderr, "\nWarning: Pygmentize output inconsistency detected or structural change. Rewriting full output.\n");
                 ssize_t written = write(STDOUT_FILENO, current_output, current_output_len);
                 if (written < 0 || (size_t)written != current_output_len) {
                     perror("Failed to rewrite full output");
                 }
            }
        }
        fflush(stdout); // Ensure output is flushed immediately

        // Update previous output
        free(prev_output); // Free the old previous output
        prev_output = current_output; // Take ownership of the new output
        prev_output_len = current_output_len;
        // Do NOT free current_output here, it's now prev_output

        // The 'line' buffer is automatically reused or reallocated by getline in the next iteration.
    } // End while loop reading stdin with getline

    // Check for errors after the loop (getline returns -1 on EOF or error)
    if (ferror(stdin)) {
        perror("Error reading from stdin using getline");
        // Decide on exit strategy if needed
    }

    // Clean up the buffer allocated by getline
    free(line);

    // Clean up
    buffer_free(&input_buf);
    free(prev_output);

    return EXIT_SUCCESS;
}
