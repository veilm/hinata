#define _GNU_SOURCE     // Needed for strdup
#include <ctype.h>      // For isspace
#include <curl/curl.h>  // Requires libcurl development library
#include <errno.h>      // For errno
#include <getopt.h>     // For getopt_long
#include <jansson.h>    // Requires jansson development library
#include <libgen.h>     // For dirname
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>  // For mkdir
#include <sys/wait.h>  // For pclose status checking (WIFEXITED, etc.)
#include <termios.h>   // For tcgetattr, tcsetattr
#include <unistd.h>    // For isatty(), STDIN_FILENO, read(), write()
#include <wordexp.h>   // For wordexp

#define VERSION_STRING "hnt-llm 0.05"

#define HINATA_CONFIG_DIR_SUBPATH "/hinata"
#define HINATA_DATA_DIR_SUBPATH "/hinata"
#define KEYS_FILENAME "/keys"
#define LOCAL_KEY_FILENAME "/.local_key"
#define DIR_PERMS 0700
#define KEY_FILE_PERMS 0600
#define LOCAL_KEY_LENGTH 32

// Structure for a single message in the conversation
typedef struct Message {
	char* role;
	char* content;
	struct Message* next;
} Message;

// Structure to store the start and end positions of XML tags to remove
typedef struct XmlRange {
	char* start;
	char* end;  // Points to the character *after* the closing '>'
} XmlRange;

// Global flag for debug mode
static int debug_mode = 0;
// Global flag for --include-reasoning
static int include_reasoning_flag = 0;
// Global flag to track if an API error was detected in the response
static int api_error_occurred = 0;

// Define API endpoints
#define OPENAI_API_URL "https://api.openai.com/v1/chat/completions"
#define OPENROUTER_API_URL "https://openrouter.ai/api/v1/chat/completions"
#define DEEPSEEK_API_URL "https://api.deepseek.com/chat/completions"
#define GOOGLE_COMPAT_API_URL \
	"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"  // Google OpenAI-Compatible Endpoint
#define READ_CHUNK_SIZE 4096  // Size for reading stdin chunks

// Structure to hold unprocessed stream data
// Enum for output phase tracking when --include-reasoning is active
typedef enum { PHASE_INIT, PHASE_THINKING, PHASE_RESPONDING } OutputPhase;

struct StreamData {
	char* buffer;
	size_t buffer_size;
	size_t data_len;
	// Flags and state for --include-reasoning
	int include_reasoning_mode;
	OutputPhase current_output_phase;
	int think_tag_printed;
};

// Function to process a single SSE data payload (JSON string) - handles
// different provider formats
static void process_sse_data(const char* json_data, struct StreamData* sd) {
	json_t* root_resp = NULL;
	json_error_t error;

	// Check for the special [DONE] message
	if (strcmp(json_data, "[DONE]") == 0) {
		// If --include-reasoning is active and <think> was opened but not
		// closed, close it now.
		if (sd->include_reasoning_mode && sd->think_tag_printed) {
			printf("</think>\n");
			fflush(stdout);
			sd->think_tag_printed = 0;  // Reset for this stream context
		}
		return;
	}

	root_resp = json_loads(json_data, 0, &error);
	if (!root_resp) {
		fprintf(stderr,
		        "\nError parsing JSON chunk: on line %d: %s\nData: %s\n",
		        error.line, error.text, json_data);
		return;  // Skip this chunk
	}

	// Try parsing as OpenAI/OpenRouter/DeepSeek format first
	json_t* choices_array = json_object_get(root_resp, "choices");
	if (choices_array && json_is_array(choices_array) &&
	    json_array_size(choices_array) > 0) {
		// --- OpenAI/OpenRouter/DeepSeek Format ---
		json_t* first_choice = json_array_get(choices_array, 0);
		if (json_is_object(first_choice)) {
			json_t* delta_obj = json_object_get(first_choice, "delta");
			if (json_is_object(delta_obj)) {
				if (!sd->include_reasoning_mode) {
					// Default behavior: only process "content"
					json_t* content_str_obj =
					    json_object_get(delta_obj, "content");
					if (content_str_obj && json_is_string(content_str_obj)) {
						const char* content =
						    json_string_value(content_str_obj);
						// Print only if content is non-empty, to match new
						// behavior style
						if (content && strlen(content) > 0) {
							printf("%s", content);
							fflush(stdout);
						}
					}
				} else {
					// --include-reasoning behavior
					json_t* j_content = json_object_get(delta_obj, "content");
					json_t* j_reasoning =
					    json_object_get(delta_obj, "reasoning");
					json_t* j_reasoning_content =
					    json_object_get(delta_obj, "reasoning_content");

					const char* text_reasoning = NULL;
					if (j_reasoning_content &&
					    json_is_string(j_reasoning_content)) {
						text_reasoning = json_string_value(j_reasoning_content);
					} else if (j_reasoning && json_is_string(j_reasoning)) {
						text_reasoning = json_string_value(j_reasoning);
					}

					const char* text_content = NULL;
					if (j_content && json_is_string(j_content)) {
						text_content = json_string_value(j_content);
					}

					int has_reasoning_token =
					    (text_reasoning && strlen(text_reasoning) > 0);
					int has_content_token =
					    (text_content && strlen(text_content) > 0);

					// A chunk signals a transition to the content phase if and
					// only if it contains actual content tokens. An empty
					// content string ("") or a null content field does not
					// count as an actual content token.
					int is_transitioning_to_content = has_content_token;

					if (sd->current_output_phase == PHASE_INIT) {
						if (has_reasoning_token) {
							printf("<think>");
							fflush(stdout);
							sd->think_tag_printed = 1;
							sd->current_output_phase = PHASE_THINKING;
							printf("%s", text_reasoning);
							fflush(stdout);
						} else if (is_transitioning_to_content) {
							// Started directly with content (no prior
							// reasoning)
							sd->current_output_phase = PHASE_RESPONDING;
							if (has_content_token) {
								printf("%s", text_content);
								fflush(stdout);
							}
						}
					} else if (sd->current_output_phase == PHASE_THINKING) {
						if (is_transitioning_to_content) {
							if (sd->think_tag_printed) {
								printf("</think>\n");
								fflush(stdout);
								sd->think_tag_printed = 0;
							}
							sd->current_output_phase = PHASE_RESPONDING;
							if (has_content_token) {
								printf("%s", text_content);
								fflush(stdout);
							}
						} else if (has_reasoning_token) {
							// Still in reasoning phase
							printf("%s", text_reasoning);
							fflush(stdout);
						}
						// If no reasoning token and not transitioning, it might
						// be an empty reasoning chunk or metadata. Do nothing.
					} else if (sd->current_output_phase == PHASE_RESPONDING) {
						if (has_content_token) {
							printf("%s", text_content);
							fflush(stdout);
						}
					}
				}
			}
		}
	} else {
		// --- Handle potential errors or unknown formats ---
		json_t* error_obj = json_object_get(root_resp, "error");
		if (json_is_object(error_obj)) {
			json_t* message_str = json_object_get(error_obj, "message");
			if (json_is_string(message_str)) {
				// Remove leading/trailing \n
				fprintf(stderr, "API Error: %s",
				        json_string_value(message_str));
			} else {
				// Remove leading/trailing \n
				fprintf(stderr, "API Error: (Could not parse error message)");
			}
			api_error_occurred =
			    1;           // Set the flag indicating an API error was found
			fflush(stderr);  // Ensure error appears immediately
		} else {
			// Only print unknown format error if it wasn't the [DONE] marker
			if (strcmp(json_data, "[DONE]") != 0) {
				// Remove leading \n, keep trailing \n for the data dump
				fprintf(stderr,
				        "Warning: Received chunk in unknown format or without "
				        "content/choices.\nData: %s\n",
				        json_data);
				fflush(stderr);  // Ensure warning appears immediately
			}
		}
	}

	json_decref(root_resp);  // Free the parsed JSON object
}

// Helper function to read all data from stdin into a buffer
static char* read_stdin_all(size_t* out_len) {
	char* buffer = NULL;
	size_t capacity = 0;
	size_t len = 0;
	size_t nread;

	do {
		if (len + READ_CHUNK_SIZE + 1 > capacity) {
			size_t new_capacity =
			    (capacity == 0) ? READ_CHUNK_SIZE + 1 : capacity * 2;
			if (new_capacity < len + READ_CHUNK_SIZE + 1) {
				new_capacity = len + READ_CHUNK_SIZE + 1;
			}
			char* new_buffer = realloc(buffer, new_capacity);
			if (!new_buffer) {
				fprintf(stderr,
				        "Error: Failed to allocate buffer for stdin: %s\n",
				        strerror(errno));
				free(buffer);
				return NULL;
			}
			buffer = new_buffer;
			capacity = new_capacity;
		}
		nread = fread(buffer + len, 1, READ_CHUNK_SIZE, stdin);
		if (nread < READ_CHUNK_SIZE && ferror(stdin)) {
			fprintf(stderr, "Error reading from stdin: %s\n", strerror(errno));
			free(buffer);
			return NULL;
		}
		len += nread;
	} while (nread > 0);

	if (buffer) {
		buffer[len] = '\0';  // Null-terminate
	} else {
		// Handle case where stdin is empty - return an empty, null-terminated
		// string
		buffer = malloc(1);
		if (!buffer) {
			fprintf(stderr,
			        "Error: Failed to allocate buffer for empty stdin: %s\n",
			        strerror(errno));
			return NULL;
		}
		buffer[0] = '\0';
		len = 0;
	}

	*out_len = len;
	return buffer;
}

// Callback function for libcurl to handle incoming stream data
// Callback function for libcurl to handle incoming stream data
static size_t WriteStreamCallback(void* contents, size_t size, size_t nmemb,
                                  void* userp) {
	size_t realsize = size * nmemb;
	struct StreamData* stream_data = (struct StreamData*)userp;
	const char* data_prefix = "data: ";
	size_t prefix_len = strlen(data_prefix);
	json_t* root_direct = NULL;
	json_error_t error_direct;
	int standalone_error_found =
	    0;  // Flag to indicate if we handled a direct JSON error

	if (debug_mode) {
		fprintf(stderr, "DEBUG: Raw incoming chunk (%zu bytes):\n", realsize);
		fwrite(contents, 1, realsize, stderr);
		fwrite(contents, 1, realsize, stderr);
		fprintf(stderr, "\n");
	}

	// --- Attempt to parse the entire chunk as JSON directly (for potential
	// standalone errors) ---
	root_direct = json_loadb(contents, realsize, 0, &error_direct);
	if (root_direct) {
		// Successfully parsed the chunk directly as JSON. Check for error
		// structures.
		json_t* error_obj = NULL;
		const char* error_message = NULL;

		if (json_is_object(root_direct)) {
			error_obj = json_object_get(root_direct, "error");
			if (json_is_object(error_obj)) {
				json_t* message_str = json_object_get(error_obj, "message");
				if (json_is_string(message_str)) {
					error_message = json_string_value(message_str);
				}
				standalone_error_found = 1;  // Mark as handled
			}
		} else if (json_is_array(root_direct)) {
			size_t i;
			json_t* value;
			json_array_foreach(root_direct, i, value) {
				if (json_is_object(value)) {
					error_obj = json_object_get(value, "error");
					if (json_is_object(error_obj)) {
						json_t* message_str =
						    json_object_get(error_obj, "message");
						if (json_is_string(message_str)) {
							error_message = json_string_value(
							    message_str);  // Take the first one found
							break;  // Stop after finding the first error in the
							        // array
						}
					}
				}
			}
			if (error_message) {
				standalone_error_found = 1;  // Mark as handled
			}
		}

		if (standalone_error_found) {
			if (error_message) {
				fprintf(stderr, "API Error (standalone chunk): %s",
				        error_message);
			} else {
				// Error structure found, but couldn't extract message string
				char* dump = json_dumps(error_obj ? error_obj : root_direct,
				                        JSON_INDENT(2));
				// Keep the newline after the message but remove the leading
				// one. Add a newline after the JSON dump for readability.
				fprintf(
				    stderr,
				    "API Error (standalone chunk, structure found but message "
				    "parsing failed):\n%s\n",
				    dump ? dump : "(Could not dump error JSON)");
				if (dump) free(dump);
			}
			api_error_occurred =
			    1;           // Set the flag indicating an API error was found
			fflush(stderr);  // Ensure error appears immediately
		}

		json_decref(root_direct);  // Clean up the parsed JSON

		// If we found and handled a standalone error, consume the chunk and
		// return. Otherwise, proceed to appending/buffering for standard SSE
		// processing.
		if (standalone_error_found) {
			return realsize;  // Tell curl we handled this many bytes
		}
		// If no error structure was found, fall through to standard
		// buffering...
	} else {
		// json_loadb failed. This chunk is likely not a standalone JSON error.
		// Proceed with the standard SSE buffering logic below.
		if (debug_mode) {
			// Check if the beginning of the chunk looks like "data: "
			if (realsize < prefix_len ||
			    memcmp(contents, data_prefix, prefix_len) != 0) {
				fprintf(
				    stderr,
				    "DEBUG: Chunk did not parse as standalone JSON and doesn't "
				    "start with '%s'. Error (if any): %s (L%d C%d P%d). "
				    "Proceeding "
				    "with buffering.\n",
				    data_prefix, error_direct.text, error_direct.line,
				    error_direct.column, error_direct.position);
			} else {
				fprintf(
				    stderr,
				    "DEBUG: Chunk did not parse as standalone JSON, but starts "
				    "with '%s'. Proceeding with buffering.\n",
				    data_prefix);
			}
		}
	}

	// --- 1. Append new data to buffer (Only if not handled as a standalone
	// error) ---
	size_t needed_size =
	    stream_data->data_len + realsize + 1;  // +1 for null terminator
	if (stream_data->buffer == NULL || needed_size > stream_data->buffer_size) {
		size_t new_size = (stream_data->buffer_size == 0)
		                      ? 1024
		                      : stream_data->buffer_size * 2;
		if (new_size < needed_size)
			new_size = needed_size;  // Ensure enough space

		char* new_buffer = realloc(stream_data->buffer, new_size);
		if (new_buffer == NULL) {
			fprintf(stderr, "Error: Failed to reallocate stream buffer\n");
			return 0;  // Signal error to curl
		}
		stream_data->buffer = new_buffer;
		stream_data->buffer_size = new_size;
	}
	memcpy(stream_data->buffer + stream_data->data_len, contents, realsize);
	stream_data->data_len += realsize;
	stream_data->buffer[stream_data->data_len] = '\0';  // Null-terminate

	// --- 2. Process complete SSE messages in the buffer ---
	char* message_start = stream_data->buffer;
	char* message_end;

	// --- Add hex dump ---
	if (debug_mode && stream_data->data_len > 0) {
		fprintf(stderr, "DEBUG: Checking last bytes of buffer (max 10): ");
		size_t start_idx =
		    (stream_data->data_len > 10) ? stream_data->data_len - 10 : 0;
		for (size_t i = start_idx; i < stream_data->data_len; ++i) {
			fprintf(stderr, "%02X ", (unsigned char)stream_data->buffer[i]);
		}
		fprintf(stderr, "\n");
	}
	// --- End hex dump ---

	while (1) {  // Loop indefinitely until break
		char* separator_rn = strstr(message_start, "\r\n\r\n");
		char* separator_n = strstr(message_start, "\n\n");
		size_t separator_len = 0;

		// Determine which separator comes first, or if none found
		if (separator_rn && (!separator_n || separator_rn < separator_n)) {
			message_end = separator_rn;
			separator_len = 4;  // "\r\n\r\n"
			if (debug_mode)
				fprintf(stderr,
				        "DEBUG: Found '\\r\\n\\r\\n' separator. Processing "
				        "message block.\n");
		} else if (separator_n) {
			message_end = separator_n;
			separator_len = 2;  // "\n\n"
			if (debug_mode)
				fprintf(stderr,
				        "DEBUG: Found '\\n\\n' separator. Processing "
				        "message block.\n");
		} else {
			// No complete message separator found in the current buffer
			break;  // Exit the while loop
		}

		// Found a potential message boundary
		// size_t message_len = message_end - message_start; // Unused variable

		// Process lines within this message block
		char* line_start = message_start;
		char* line_end;
		while (line_start < message_end &&
		       (line_end = memchr(line_start, '\n',
		                          message_end - line_start)) != NULL) {
			// Check if the line starts with "data: "
			// Cast pointer difference to size_t for comparison
			if (((size_t)(line_end - line_start) > prefix_len) &&
			    memcmp(line_start, data_prefix, prefix_len) == 0) {
				// Extract the JSON payload part
				char* json_start = line_start + prefix_len;
				// size_t json_len = line_end - json_start; // Unused variable

				// Temporarily null-terminate the JSON string for processing
				char original_char = *line_end;
				*line_end = '\0';
				process_sse_data(json_start, stream_data);
				*line_end = original_char;  // Restore original character
			}
			// Move to the next line
			line_start = line_end + 1;
		}
		// Check the last part of the message block if it didn't end with \n
		if (line_start < message_end) {
			// Cast pointer difference to size_t for comparison
			if (((size_t)(message_end - line_start) > prefix_len) &&
			    memcmp(line_start, data_prefix, prefix_len) == 0) {
				char* json_start = line_start + prefix_len;
				// size_t json_len = message_end - json_start; // Unused
				// variable
				char original_char = *message_end;
				*message_end = '\0';
				process_sse_data(json_start, stream_data);
				*message_end = original_char;
			}
		}

		// Move past the processed message (including the separator)
		message_start =
		    message_end + separator_len;  // Use determined separator length
	}

	// --- 3. Remove processed data from the buffer ---
	if (message_start > stream_data->buffer) {
		size_t remaining_len =
		    stream_data->data_len - (message_start - stream_data->buffer);
		memmove(stream_data->buffer, message_start, remaining_len);
		stream_data->data_len = remaining_len;
		stream_data->buffer[stream_data->data_len] = '\0';  // Re-null-terminate
	}

	return realsize;  // Tell curl we processed all received bytes
}

// Function to create a new message node
static Message* create_message(const char* role, const char* content) {
	Message* new_message = malloc(sizeof(Message));
	if (!new_message) {
		perror("Failed to allocate memory for message");
		return NULL;
	}

	// Use strdup to allocate and copy the content
	new_message->content = strdup(content);
	if (!new_message->content) {
		perror("Failed to duplicate message content");
		free(new_message);
		return NULL;
	}

	// Role can be a static string, no need to copy unless modifying
	new_message->role =
	    (char*)role;  // Cast away const, assuming role is static literal
	new_message->next = NULL;

	return new_message;
}

// Function to free the message linked list
static void free_message_list(Message* head) {
	Message* current = head;
	Message* next;
	while (current != NULL) {
		next = current->next;
		free(current->content);  // Free the duplicated content
		// Do not free role if it points to static literals
		free(current);
		current = next;
	}
}

// Function to convert message linked list to Jansson JSON array
static json_t* messages_to_json_array(Message* head) {
	json_t* messages_array = json_array();
	if (!messages_array) {
		fprintf(stderr, "Error: Failed to create messages JSON array.\n");
		return NULL;
	}

	Message* current = head;
	while (current != NULL) {
		json_t* message_obj = json_object();
		if (!message_obj) {
			fprintf(stderr, "Error: Failed to create message JSON object.\n");
			json_decref(messages_array);  // Clean up partially created array
			return NULL;
		}
		if (json_object_set_new(message_obj, "role",
		                        json_string(current->role)) != 0 ||
		    json_object_set_new(message_obj, "content",
		                        json_string(current->content)) != 0) {
			fprintf(stderr,
			        "Error: Failed to set message properties in JSON.\n");
			json_decref(message_obj);
			json_decref(messages_array);
			return NULL;
		}
		if (json_array_append_new(messages_array, message_obj) != 0) {
			fprintf(stderr,
			        "Error: Failed to append message to messages array.\n");
			// message_obj is now owned by messages_array or freed if append
			// failed
			json_decref(messages_array);
			return NULL;
		}
		current = current->next;
	}

	return messages_array;
}

// Helper function to trim leading and trailing whitespace from a string
// (modifies the string in place)
static char* trim_whitespace(char* str) {
	if (!str) return NULL;  // Handle NULL input defensively
	char* end;

	// Trim leading space
	while (isspace((unsigned char)*str)) str++;

	if (*str == 0)  // All spaces?
		return str;

	// Trim trailing space
	end = str + strlen(str) - 1;
	while (end > str && isspace((unsigned char)*end)) end--;

	// Write new null terminator character
	end[1] = '\0';

	return str;
}

// Function to add a message to the list (centralized for convenience)
static int add_message_to_list(Message** head, Message** tail, const char* role,
                               const char* content) {
	Message* new_msg = create_message(role, content);
	if (!new_msg) {
		// create_message prints error
		return 0;  // Error
	}
	if (*tail) {
		(*tail)->next = new_msg;
		*tail = new_msg;
	} else {
		*head = new_msg;
		*tail = new_msg;
	}
	return 1;  // Success
}

/******************************************************************************
 * API Key Management
 ******************************************************************************/

// A simple XOR encryption/decryption function.
void xor_crypt(const char* key, size_t key_len, char* data, size_t data_len) {
	for (size_t i = 0; i < data_len; ++i) {
		data[i] ^= key[i % key_len];
	}
}

// Ensures that a directory exists at the given path, creating it recursively
// if necessary. Does not support tilde expansion.
static int ensure_dir_exists_recursive(char* path) {
	struct stat st = {0};

	// Check if the directory already exists.
	if (stat(path, &st) == 0 && S_ISDIR(st.st_mode)) {
		return 0;
	}

	// dirname() can modify its argument, so we must pass it a copy.
	char* path_copy = strdup(path);
	if (!path_copy) {
		perror("ensure_dir_exists_recursive strdup");
		return -1;
	}

	// Recursively create the parent directory.
	char* parent_dir = dirname(path_copy);
	if (strcmp(parent_dir, ".") != 0 && strcmp(parent_dir, "/") != 0) {
		ensure_dir_exists_recursive(parent_dir);
	}
	free(path_copy);

	// Create the target directory.
	if (mkdir(path, DIR_PERMS) != 0 && errno != EEXIST) {
		fprintf(stderr, "Error: Cannot create directory '%s': %s\n", path,
		        strerror(errno));
		return -1;
	}
	return 0;
}

// Resolves an XDG directory path (e.g., for config or data).
// It gets the base path from an environment variable like `xdg_env_var`. If the
// env var is not set, it uses `fallback_home_subdir`. Then, it appends the
// hinata-specific subpath. The function ensures the full path exists, creating
// it recursively if needed. Returns a malloc'd string that the caller must
// free.
char* get_hinata_dir(const char* xdg_env_var,
                     const char* fallback_home_subdir) {
	const char* base_path = getenv(xdg_env_var);
	wordexp_t p;

	const char* path_to_expand =
	    (base_path && *base_path) ? base_path : fallback_home_subdir;

	if (wordexp(path_to_expand, &p, 0) != 0) {
		fprintf(stderr, "Error expanding path: %s\n", path_to_expand);
		return NULL;
	}

	if (p.we_wordc == 0) {
		fprintf(stderr, "Error: wordexp resulted in zero words for path: %s\n",
		        path_to_expand);
		wordfree(&p);
		return NULL;
	}

	// Using HINATA_CONFIG_DIR_SUBPATH, as both config and data are the same.
	size_t len = strlen(p.we_wordv[0]) + strlen(HINATA_CONFIG_DIR_SUBPATH) + 1;
	char* full_path = malloc(len);
	if (!full_path) {
		perror("malloc for hinata dir path");
		wordfree(&p);
		return NULL;
	}
	snprintf(full_path, len, "%s%s", p.we_wordv[0], HINATA_CONFIG_DIR_SUBPATH);
	wordfree(&p);

	if (ensure_dir_exists_recursive(full_path) != 0) {
		free(full_path);
		return NULL;
	}

	return full_path;
}

// Checks if the local encryption key exists. If not, generates a new one.
void ensure_local_key(const char* key_path) {
	struct stat st;
	if (stat(key_path, &st) == 0) {
		return;  // Key already exists
	}

	FILE* urandom = fopen("/dev/urandom", "r");
	if (!urandom) {
		perror("Failed to open /dev/urandom");
		exit(1);
	}

	char key[LOCAL_KEY_LENGTH];
	if (fread(key, 1, LOCAL_KEY_LENGTH, urandom) != LOCAL_KEY_LENGTH) {
		fprintf(stderr, "Failed to read from /dev/urandom\n");
		fclose(urandom);
		exit(1);
	}
	fclose(urandom);

	FILE* key_file = fopen(key_path, "w");
	if (!key_file) {
		perror("Failed to create local key file");
		exit(1);
	}

	if (fwrite(key, 1, LOCAL_KEY_LENGTH, key_file) != LOCAL_KEY_LENGTH) {
		fprintf(stderr, "Failed to write to local key file\n");
		fclose(key_file);
		exit(1);
	}
	fclose(key_file);

	if (chmod(key_path, KEY_FILE_PERMS) != 0) {
		perror("Failed to set permissions on local key file");
		exit(1);
	}
}

// Reads the local encryption key from a file.
char* read_local_key(const char* key_path, size_t* key_len) {
	FILE* f = fopen(key_path, "r");
	if (!f) return NULL;

	fseek(f, 0, SEEK_END);
	long size = ftell(f);
	fseek(f, 0, SEEK_SET);

	if (size <= 0) {
		fclose(f);
		return NULL;
	}

	char* key = malloc(size);
	if (!key) {
		perror("malloc for local key");
		fclose(f);
		return NULL;
	}

	if (fread(key, 1, size, f) != (size_t)size) {
		fprintf(stderr, "Failed to read local key\n");
		free(key);
		fclose(f);
		return NULL;
	}

	fclose(f);
	*key_len = size;
	return key;
}

// Command handler for `save-key`.
void handle_save_key(int argc, char* argv[]) {
	if (argc < 3) {
		fprintf(stderr, "Usage: %s save-key <KEY_NAME>\n", argv[0]);
		exit(1);
	}
	const char* key_name = argv[2];

	char* config_dir = get_hinata_dir("XDG_CONFIG_HOME", "~/.config");
	char* data_dir = get_hinata_dir("XDG_DATA_HOME", "~/.local/share");
	if (!config_dir || !data_dir) exit(1);

	// Ensure .gitignore exists and contains `.*` to hide the local key
	char gitignore_path[1024];
	snprintf(gitignore_path, sizeof(gitignore_path), "%s/.gitignore", data_dir);
	FILE* gitignore_file = fopen(gitignore_path, "w");
	if (gitignore_file) {
		fprintf(gitignore_file, ".*\n");
		fclose(gitignore_file);
	}

	char local_key_path[1024];
	snprintf(local_key_path, sizeof(local_key_path), "%s%s", data_dir,
	         LOCAL_KEY_FILENAME);
	ensure_local_key(local_key_path);

	printf("Enter API key value for %s: ", key_name);
	fflush(stdout);

	struct termios oldt, newt;
	tcgetattr(STDIN_FILENO, &oldt);
	newt = oldt;
	newt.c_lflag &= ~ECHO;
	tcsetattr(STDIN_FILENO, TCSANOW, &newt);

	char api_key_value[1024];
	if (!fgets(api_key_value, sizeof(api_key_value), stdin)) {
		api_key_value[0] = '\0';
	}
	// remove trailing newline
	api_key_value[strcspn(api_key_value, "\n")] = 0;

	tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
	printf("\n");

	if (strlen(api_key_value) == 0) {
		fprintf(stderr, "API key cannot be empty.\n");
		exit(1);
	}

	size_t local_key_len;
	char* local_key = read_local_key(local_key_path, &local_key_len);
	if (!local_key) {
		fprintf(stderr, "Error reading local key.\n");
		exit(1);
	}

	// Read existing keys
	char keys_path[1024];
	snprintf(keys_path, sizeof(keys_path), "%s%s", config_dir, KEYS_FILENAME);
	FILE* keys_file = fopen(keys_path, "r");

	char temp_keys_path[1024];
	int snprintf_len =
	    snprintf(temp_keys_path, sizeof(temp_keys_path), "%s.tmp", keys_path);
	if (snprintf_len < 0 || (size_t)snprintf_len >= sizeof(temp_keys_path)) {
		fprintf(stderr, "Error creating temp path.\n");
		exit(1);
	}
	FILE* temp_file = fopen(temp_keys_path, "w");
	if (!temp_file) {
		perror("Could not open temp file for writing keys");
		exit(1);
	}
	int key_found = 0;

	if (keys_file) {
		char* line = NULL;
		size_t len = 0;
		ssize_t read;
		while ((read = getline(&line, &len, keys_file)) != -1) {
			char* eq = strchr(line, '=');
			if (eq) {
				*eq = '\0';
				if (strcmp(line, key_name) == 0) {
					// This is the key we're updating, skip it
					key_found = 1;
				} else {
					// Write other keys back
					*eq = '=';
					fputs(line, temp_file);
				}
			}
		}
		free(line);
		fclose(keys_file);
	}

	// Encrypt new key and add it
	char* new_key_val_encrypted = strdup(api_key_value);
	size_t new_key_len = strlen(new_key_val_encrypted);
	xor_crypt(local_key, local_key_len, new_key_val_encrypted, new_key_len);
	fprintf(temp_file, "%s=", key_name);
	fwrite(new_key_val_encrypted, 1, new_key_len, temp_file);
	fprintf(temp_file, "\n");
	free(new_key_val_encrypted);

	fclose(temp_file);
	rename(temp_keys_path, keys_path);
	chmod(keys_path, KEY_FILE_PERMS);
	free(local_key);
	free(config_dir);
	free(data_dir);

	printf("Successfully %s key '%s'.\n", key_found ? "updated" : "saved",
	       key_name);
}

// Command handler for `list-keys`
void handle_list_keys(int argc, char* argv[]) {
	(void)argc;
	(void)argv;
	char* config_dir = get_hinata_dir("XDG_CONFIG_HOME", "~/.config");
	if (!config_dir) exit(1);
	char keys_path[1024];
	snprintf(keys_path, sizeof(keys_path), "%s%s", config_dir, KEYS_FILENAME);
	free(config_dir);

	FILE* f = fopen(keys_path, "r");
	if (!f) {
		// It's not an error if the file doesn't exist, just means no keys are
		// stored.
		if (errno != ENOENT) {
			perror("Error opening keys file");
		}
		return;
	}

	char* line = NULL;
	size_t len = 0;
	while (getline(&line, &len, f) != -1) {
		char* eq = strchr(line, '=');
		if (eq) {
			*eq = '\0';
			printf("%s\n", line);
		}
	}
	free(line);
	fclose(f);
}

// Command handler for `delete-key`.
void handle_delete_key(int argc, char* argv[]) {
	if (argc < 3) {
		fprintf(stderr, "Usage: %s delete-key <KEY_NAME>\n", argv[0]);
		exit(1);
	}
	const char* key_name_to_delete = argv[2];

	char* config_dir = get_hinata_dir("XDG_CONFIG_HOME", "~/.config");
	if (!config_dir) exit(1);

	char keys_path[1024];
	snprintf(keys_path, sizeof(keys_path), "%s%s", config_dir, KEYS_FILENAME);
	FILE* keys_file = fopen(keys_path, "r");
	if (!keys_file) {
		fprintf(stderr, "No keys file found, nothing to delete.\n");
		free(config_dir);
		exit(0);
	}

	char temp_keys_path[1024];
	int snprintf_len =
	    snprintf(temp_keys_path, sizeof(temp_keys_path), "%s.tmp", keys_path);
	if (snprintf_len < 0 || (size_t)snprintf_len >= sizeof(temp_keys_path)) {
		fprintf(stderr, "Error creating temp path.\n");
		exit(1);
	}
	FILE* temp_file = fopen(temp_keys_path, "w");
	if (!temp_file) {
		perror("Could not open temp file for writing keys");
		fclose(keys_file);
		free(config_dir);
		exit(1);
	}

	int key_found = 0;
	char* line = NULL;
	size_t len = 0;
	while (getline(&line, &len, keys_file) != -1) {
		char* line_copy = strdup(line);
		char* eq = strchr(line_copy, '=');
		if (eq) {
			*eq = '\0';
			if (strcmp(line_copy, key_name_to_delete) == 0) {
				key_found = 1;
				// Skip writing this line
			} else {
				fputs(line, temp_file);
			}
		}
		free(line_copy);
	}
	free(line);
	fclose(keys_file);
	fclose(temp_file);

	if (key_found) {
		rename(temp_keys_path, keys_path);
		printf("Deleted key '%s'.\n", key_name_to_delete);
	} else {
		remove(temp_keys_path);
		printf("Key '%s' not found.\n", key_name_to_delete);
	}
	free(config_dir);
}

// Retrieves an API key from the local store, decrypting it.
char* get_api_key_from_store(const char* key_name) {
	char* config_dir = get_hinata_dir("XDG_CONFIG_HOME", "~/.config");
	char* data_dir = get_hinata_dir("XDG_DATA_HOME", "~/.local/share");
	if (!config_dir || !data_dir) return NULL;

	char local_key_path[1024];
	snprintf(local_key_path, sizeof(local_key_path), "%s%s", data_dir,
	         LOCAL_KEY_FILENAME);
	size_t local_key_len;
	char* local_key = read_local_key(local_key_path, &local_key_len);
	if (!local_key) {
		// No local key means no encrypted keys can exist.
		free(config_dir);
		free(data_dir);
		return NULL;
	}

	char keys_path[1024];
	snprintf(keys_path, sizeof(keys_path), "%s%s", config_dir, KEYS_FILENAME);
	FILE* f = fopen(keys_path, "r");
	if (!f) {
		free(config_dir);
		free(data_dir);
		free(local_key);
		return NULL;
	}

	char* found_api_key = NULL;
	char* line = NULL;
	size_t len = 0;
	ssize_t read;
	while ((read = getline(&line, &len, f)) != -1) {
		char* eq = strchr(line, '=');
		if (eq) {
			*eq = '\0';
			if (strcmp(line, key_name) == 0) {
				char* value = eq + 1;
				// remove trailing newline
				value[strcspn(value, "\n")] = 0;
				size_t value_len = strlen(value);
				found_api_key = strdup(value);
				xor_crypt(local_key, local_key_len, found_api_key, value_len);
				break;  // Found it
			}
		}
	}
	free(line);
	fclose(f);
	free(local_key);
	free(config_dir);
	free(data_dir);

	return found_api_key;
}

/******************************************************************************
 * Provider Configuration
 ******************************************************************************/

typedef struct {
	const char* name;
	const char* api_url;
	const char* env_var;
	const char** extra_headers;
} Provider;

static const char* openrouter_extra_headers[] = {
    "HTTP-Referer: https://github.com/veilm/hinata/", "X-Title: hinata", NULL};

static Provider providers[] = {
    {"openai", OPENAI_API_URL, "OPENAI_API_KEY", NULL},
    {"openrouter", OPENROUTER_API_URL, "OPENROUTER_API_KEY",
     openrouter_extra_headers},
    {"deepseek", DEEPSEEK_API_URL, "DEEPSEEK_API_KEY", NULL},
    {"google", GOOGLE_COMPAT_API_URL, "GEMINI_API_KEY", NULL},
};
static const int num_providers = sizeof(providers) / sizeof(providers[0]);

// Gets an API key for a provider, checking environment variables first,
// then falling back to the local key store. Returns a malloc'd string.
char* get_provider_api_key(const Provider* p) {
	const char* key = getenv(p->env_var);
	if (key && *key) {
		if (debug_mode)
			fprintf(stderr, "DEBUG: Found API key in environment variable %s\n",
			        p->env_var);
		return strdup(key);
	}
	if (debug_mode)
		fprintf(stderr, "DEBUG: API key not in env, checking store for %s\n",
		        p->env_var);
	char* stored_key = get_api_key_from_store(p->env_var);
	if (stored_key) {
		if (debug_mode)
			fprintf(stderr, "DEBUG: Found API key for %s in local store\n",
			        p->name);
	}
	return stored_key;
}

// Helper function to run hnt-escape -u on content via a temporary file
// Returns a new dynamically allocated string with the unescaped content,
// or NULL on error. Caller must free the returned string.
static char* unescape_message_content(const char* original_content) {
	char temp_filename[] = "/tmp/hnt-llm-unescape-XXXXXX";
	int fd = -1;
	FILE* temp_fp = NULL;
	FILE* pipe_fp = NULL;
	char* command = NULL;
	char* output_buffer = NULL;
	size_t output_capacity = 0;
	size_t output_len = 0;
	char read_buf[4096];
	size_t bytes_read;
	int pclose_status;
	char* final_output = NULL;

	// 1. Create and write to temporary file
	fd = mkstemp(temp_filename);
	if (fd == -1) {
		perror("Failed to create temporary file for unescaping");
		return NULL;  // Indicate error
	}
	// Need a FILE* to easily write the string
	temp_fp = fdopen(fd, "w");
	if (!temp_fp) {
		perror("Failed to fdopen temporary file");
		close(fd);              // Close the file descriptor
		unlink(temp_filename);  // Clean up temp file
		return NULL;
	}
	if (fputs(original_content, temp_fp) == EOF) {
		fprintf(stderr, "Error writing to temporary file: %s\n",
		        strerror(errno));
		fclose(temp_fp);  // This also closes fd
		unlink(temp_filename);
		return NULL;
	}
	// Ensure data is written before the child process reads it
	if (fclose(temp_fp) != 0) {  // fclose also closes fd
		perror("Failed to close temporary file after writing");
		unlink(temp_filename);
		return NULL;
	}
	temp_fp = NULL;  // Avoid double close
	fd = -1;         // Avoid double close

	// 2. Construct command
	// Ensure hnt-escape is found via PATH or specify full path if needed
	const char* escape_cmd = "hnt-escape -u";
	size_t command_len =
	    strlen(escape_cmd) + strlen(" < ") + strlen(temp_filename) + 1;
	command = malloc(command_len);
	if (!command) {
		perror("Failed to allocate memory for unescape command");
		unlink(temp_filename);
		return NULL;
	}
	snprintf(command, command_len, "%s < %s", escape_cmd, temp_filename);

	// 3. Run command with popen
	pipe_fp = popen(command, "r");
	free(command);  // Free command string now
	command = NULL;
	if (!pipe_fp) {
		perror("Failed to popen hnt-escape command");
		unlink(temp_filename);
		return NULL;
	}

	// 4. Read output from the pipe
	output_capacity = 1024;  // Initial capacity
	output_buffer = malloc(output_capacity);
	if (!output_buffer) {
		perror("Failed to allocate buffer for unescape output");
		pclose(pipe_fp);
		unlink(temp_filename);
		return NULL;
	}
	output_len = 0;

	while ((bytes_read = fread(read_buf, 1, sizeof(read_buf), pipe_fp)) > 0) {
		if (output_len + bytes_read + 1 > output_capacity) {
			size_t new_capacity = output_capacity * 2;
			if (new_capacity < output_len + bytes_read + 1) {
				new_capacity = output_len + bytes_read + 1;
			}
			char* new_buffer = realloc(output_buffer, new_capacity);
			if (!new_buffer) {
				perror("Failed to reallocate buffer for unescape output");
				free(output_buffer);
				pclose(pipe_fp);
				unlink(temp_filename);
				return NULL;
			}
			output_buffer = new_buffer;
			output_capacity = new_capacity;
		}
		memcpy(output_buffer + output_len, read_buf, bytes_read);
		output_len += bytes_read;
	}
	output_buffer[output_len] = '\0';  // Null-terminate

	// Check for read errors
	if (ferror(pipe_fp)) {
		fprintf(stderr, "Error reading from hnt-escape pipe: %s\n",
		        strerror(errno));
		free(output_buffer);
		pclose(pipe_fp);
		unlink(temp_filename);
		return NULL;
	}

	// 5. Close the pipe and check status
	pclose_status = pclose(pipe_fp);
	pipe_fp = NULL;  // Avoid double close
	if (pclose_status == -1) {
		perror("Failed to pclose hnt-escape pipe");
		free(output_buffer);
		unlink(temp_filename);
		return NULL;
	} else if (WIFEXITED(pclose_status) && WEXITSTATUS(pclose_status) != 0) {
		fprintf(stderr, "Error: hnt-escape command exited with status %d\n",
		        WEXITSTATUS(pclose_status));
		free(output_buffer);
		unlink(temp_filename);
		return NULL;  // Indicate command execution error
	} else if (!WIFEXITED(pclose_status)) {
		fprintf(stderr,
		        "Error: hnt-escape command terminated abnormally (signal %d)\n",
		        WTERMSIG(pclose_status));
		free(output_buffer);
		unlink(temp_filename);
		return NULL;  // Indicate command execution error
	}

	// 6. Clean up temporary file
	if (unlink(temp_filename) != 0) {
		// Use __func__ for function name in C99+
		fprintf(stderr,
		        "Warning (%s): Failed to delete temporary file '%s': %s\n",
		        __func__, temp_filename, strerror(errno));
		// Continue, as we have the output, but warn the user
	}

	// 7. Return the captured output (caller must free)
	// Attempt to reallocate to the exact size + null terminator.
	final_output = realloc(output_buffer, output_len + 1);

	if (!final_output) {
		// Realloc failed. The original output_buffer is still valid and
		// contains the correct data. Print a warning and return the original
		// (potentially oversized) buffer.
		fprintf(stderr,
		        "Warning (%s): Failed to realloc unescape buffer to final size "
		        "(%zu bytes). Returning original buffer.\n",
		        __func__, output_len + 1);
		return output_buffer;  // Original buffer is returned, no free occurs
		                       // here.
	}

	// Realloc succeeded. final_output points to the new (or possibly same)
	// buffer. The original output_buffer pointer is now potentially invalid IF
	// realloc moved the memory. Return the new pointer.
	return final_output;
}

int main(int argc, char* argv[]) {
	if (argc > 1) {
		if (strcmp(argv[1], "save-key") == 0 ||
		    strcmp(argv[1], "set-key") == 0) {
			handle_save_key(argc, argv);
			exit(0);
		} else if (strcmp(argv[1], "list-keys") == 0) {
			handle_list_keys(argc, argv);
			exit(0);
		} else if (strcmp(argv[1], "delete-key") == 0) {
			handle_delete_key(argc, argv);
			exit(0);
		}
	}

	CURL* curl_handle = NULL;  // Initialize curl_handle to NULL
	CURLcode res = CURLE_OK;   // Initialize res
	struct StreamData stream_data = {
	    NULL, 0, 0, 0, PHASE_INIT, 0};  // Initialize stream data struct
	struct curl_slist* headers = NULL;
	char* api_key = NULL;
	char auth_header[1097];  // Buffer for the Authorization header
	char* stdin_content = NULL;
	size_t stdin_len = 0;
	Message* message_list_head = NULL;  // Head of the conversation message list
	Message* message_list_tail = NULL;  // Tail for efficient appending
	json_t* root_payload = NULL;
	json_t* messages_array = NULL;  // To hold the generated JSON array
	char* post_data_dynamic = NULL;
	// Variables for XML parsing and remaining content
	XmlRange* ranges_to_remove = NULL;
	size_t ranges_count = 0;
	size_t ranges_capacity = 0;
	char* remaining_content_buffer = NULL;
	const char* DEFAULT_MODEL_FALLBACK =
	    "openrouter/deepseek/deepseek-chat-v3-0324:free";  // Fallback if
	                                                       // --model and
	                                                       // HINATA_LLM_MODEL
	                                                       // are not set.
	const char* model_arg =
	    DEFAULT_MODEL_FALLBACK;  // Effective model to be used. Will be updated
	                             // if --model or HINATA_LLM_MODEL is used.
	const char* api_url_base = NULL;  // Base URL or format string
	char final_api_url[1024];         // Buffer for the final formatted URL
	const Provider* provider = NULL;
	const char* model_name_to_send = NULL;
	const char* system_prompt = NULL;  // Variable to store the system prompt

	// --- 1. Parse Command Line Arguments ---
	int opt;
	// Define long options
#define INCLUDE_REASONING_OPT_CODE 256  // Arbitrary value for long-only option

	// Use model_arg to store the argument value, default or from -m
	// Use system_prompt to store the system prompt argument
	// Use 'd' internally for the debug flag, no short option exposed to user
	// Use 'V' for version flag
	// include_reasoning_flag is set directly by getopt_long

	// Note: getopt_long will set include_reasoning_flag to 1 if
	// --include-reasoning is present.
	// We don't need a specific case for it in the switch if we use the flag
	// pointer method.
	// However, to keep the style consistent or if we needed to parse an
	// argument for it, we'd use a char code. For a simple flag, letting
	// getopt_long set it is fine. Let's use a char code for consistency for
	// now. Reverting the direct flag setting to use a char code.
	static struct option long_options_revised[] = {
	    {"model", required_argument, 0, 'm'},
	    {"system", required_argument, 0, 's'},
	    {"version", no_argument, 0, 'V'},
	    {"debug-unsafe", no_argument, 0, 'd'},
	    {"include-reasoning", no_argument, 0, INCLUDE_REASONING_OPT_CODE},
	    {0, 0, 0, 0}};

	while ((opt = getopt_long(argc, argv, "m:s:V", long_options_revised,
	                          NULL)) != -1) {
		switch (opt) {
			case 'V':  // Handle version flag
				printf("%s\n", VERSION_STRING);
				exit(0);  // Exit successfully after printing version
			case 'm':
				model_arg = optarg;
				break;
			case 'd':  // Handle debug flag
				debug_mode = 1;
				break;
			case 's':  // Handle system prompt argument
				system_prompt = optarg;
				break;
			case INCLUDE_REASONING_OPT_CODE:
				include_reasoning_flag = 1;
				break;
			case '?':
				// getopt_long already printed an error message.
				fprintf(
				    stderr,
				    "Model format: provider/model_name (e.g., openai/gpt-4o, "
				    "openrouter/some/model)\n");
				fprintf(
				    stderr,
				    "Usage: %s [-m provider/model_name] [-s system_prompt] "
				    "[--version|-V] [--debug-unsafe] [--include-reasoning]\n",
				    argv[0]);
				return 1;
			default:
				abort();  // Should not happen
		}
	}

	// --- 1a. Determine effective model (CLI > Env Var > Fallback) ---
	if (model_arg ==
	    DEFAULT_MODEL_FALLBACK) {  // True if --model CLI argument was NOT used
		const char* env_model = getenv("HINATA_LLM_MODEL");
		if (env_model != NULL &&
		    *env_model != '\0') {   // If HINATA_LLM_MODEL is set and not empty
			model_arg = env_model;  // Use environment variable
			if (debug_mode) {
				fprintf(stderr,
				        "DEBUG: Using model from HINATA_LLM_MODEL environment "
				        "variable: %s\n",
				        model_arg);
			}
		} else {  // HINATA_LLM_MODEL not set, empty, or -m was not used and
			      // HINATA_LLM_MODEL is not suitable
			// model_arg remains DEFAULT_MODEL_FALLBACK (the hardcoded one)
			if (debug_mode) {
				if (env_model == NULL) {
					fprintf(stderr,
					        "DEBUG: HINATA_LLM_MODEL environment variable not "
					        "set. Using hardcoded fallback model: %s\n",
					        model_arg);
				} else {  // *env_model == '\0'
					fprintf(
					    stderr,
					    "DEBUG: HINATA_LLM_MODEL environment variable is set "
					    "but empty. Using hardcoded fallback model: %s\n",
					    model_arg);
				}
			}
		}
	} else {  // --model CLI argument was used, model_arg was updated by
		      // getopt_long
		if (debug_mode) {
			fprintf(stderr,
			        "DEBUG: Using model from --model CLI argument: %s\n",
			        model_arg);
		}
	}

	// --- Debug: Print Arguments ---
	if (debug_mode) {
		fprintf(stderr, "<hnt-llm-argv>\n");
		for (int i = 0; i < argc; ++i) {
			fprintf(stderr, "  <arg index=\"%d\">%s</arg>\n", i, argv[i]);
		}
		fprintf(stderr, "</hnt-llm-argv>\n");
	}

	// Check for non-option arguments (currently none expected)
	if (optind < argc) {
		fprintf(stderr, "Error: Unexpected non-option arguments found.\n");
		fprintf(stderr,
		        "Model format: provider/model_name (e.g., openai/gpt-4o, "
		        "openrouter/some/model)\n");
		fprintf(stderr,
		        "Usage: %s [-m provider/model_name] [-s system_prompt] "
		        "[--version|-V] [--debug-unsafe] [--include-reasoning]\n",
		        argv[0]);
		return 1;
	}

	// --- 2. Parse Model Argument and Select Provider ---
	const char* separator = strchr(model_arg, '/');
	if (separator == NULL) {
		fprintf(
		    stderr,
		    "Error: Invalid model format. Expected 'provider/model_name', got "
		    "'%s'\n",
		    model_arg);
		return 1;
	}

	size_t provider_len = separator - model_arg;
	for (int i = 0; i < num_providers; i++) {
		if (strlen(providers[i].name) == provider_len &&
		    strncmp(model_arg, providers[i].name, provider_len) == 0) {
			provider = &providers[i];
			break;
		}
	}

	if (!provider) {
		char* provider_str = malloc(provider_len + 1);
		if (!provider_str) {
			fprintf(stderr,
			        "Error: Memory allocation failed for provider string.\n");
			return 1;
		}
		strncpy(provider_str, model_arg, provider_len);
		provider_str[provider_len] = '\0';
		fprintf(stderr,
		        "Error: Unsupported provider '%s' in model '%s'. Use 'openai', "
		        "'openrouter', 'deepseek', or 'google'.\n",
		        provider_str, model_arg);
		free(provider_str);
		return 1;
	}

	model_name_to_send = separator + 1;
	if (*model_name_to_send == '\0') {
		fprintf(stderr, "Error: Missing model name after '/' in '%s'.\n",
		        model_arg);
		return 1;
	}

	api_url_base = provider->api_url;
	if (provider->extra_headers) {
		for (int i = 0; provider->extra_headers[i]; i++) {
			headers = curl_slist_append(headers, provider->extra_headers[i]);
		}
	}

	// --- 3. Initialize stream data buffer ---
	// --- 4. Get API Key ---
	api_key = get_provider_api_key(provider);
	if (api_key == NULL) {
		fprintf(stderr,
		        "Error: API key for %s not found.\nSet the %s environment "
		        "variable or save it using:\nhnt-llm save-key %s\n",
		        provider->name, provider->env_var, provider->env_var);
		free(stream_data.buffer);
		return 1;
	}

	// Prepare Authorization header (used by all providers now)
	snprintf(auth_header, sizeof(auth_header), "Authorization: Bearer %s",
	         api_key);

	// --- 4a. Read content from stdin ---
	// Inform user only if stdin is a terminal
	if (isatty(STDIN_FILENO)) {
		fprintf(stderr, "Reading prompt from stdin...\n");
	}
	stdin_content = read_stdin_all(&stdin_len);
	if (stdin_content == NULL) {
		fprintf(stderr, "Error reading from stdin.\n");
		free(stream_data.buffer);  // Free stream buffer if allocated
		// No need to free api_key, it's from getenv
		return 1;
	}
	// fprintf(stderr, "Read %zu bytes from stdin.\n", stdin_len); // Confirm
	// bytes read

	// --- Debug: Print Stdin ---
	if (debug_mode) {
		fprintf(stderr, "<hnt-llm-stdin>");
		// Use fwrite for potentially large/binary stdin
		fwrite(stdin_content, 1, stdin_len, stderr);
		fprintf(stderr, "</hnt-llm-stdin>\n");
	}

	// --- 5. Parse Stdin for XML Tags and Build Message List ---
	message_list_head = NULL;  // Initialize message list
	message_list_tail = NULL;

	// 5.1 Add system message from CLI argument first, if provided
	if (system_prompt != NULL) {
		if (!add_message_to_list(&message_list_head, &message_list_tail,
		                         "system", system_prompt)) {
			// Error already printed by create_message/add_message_to_list
			goto cleanup;
		}
		if (debug_mode) fprintf(stderr, "DEBUG: Added CLI system prompt.\n");
	}

	// 5.2 Parse XML tags from stdin_content
	char* current_pos = stdin_content;
	remaining_content_buffer = NULL;  // Initialize here
	ranges_to_remove = NULL;          // Initialize here
	ranges_count = 0;
	ranges_capacity = 0;

	const char* tags[][2] = {// {tag_name, role}
	                         {"hnt-system", "system"},
	                         {"hnt-user", "user"},
	                         {"hnt-assistant", "assistant"}};
	const int num_tags = sizeof(tags) / sizeof(tags[0]);

	if (debug_mode)
		fprintf(stderr, "DEBUG: Starting XML tag parsing in stdin.\n");

	while (current_pos != NULL && *current_pos != '\0') {
		char* next_tag_start = NULL;
		int found_tag_index = -1;
		char open_tag[50];  // Buffer for "<tag_name>"

		// Find the earliest occurrence of any known opening tag
		for (int i = 0; i < num_tags; ++i) {
			snprintf(open_tag, sizeof(open_tag), "<%s>", tags[i][0]);
			char* found_pos = strstr(current_pos, open_tag);
			if (found_pos) {
				if (next_tag_start == NULL || found_pos < next_tag_start) {
					next_tag_start = found_pos;
					found_tag_index = i;
				}
			}
		}

		if (next_tag_start == NULL) {
			// No more known tags found in the rest of the string
			if (debug_mode)
				fprintf(stderr, "DEBUG: No more known XML tags found.\n");
			break;
		}

		// Found a tag, now find its corresponding closing tag
		const char* tag_name = tags[found_tag_index][0];
		const char* role = tags[found_tag_index][1];
		size_t open_tag_len = strlen(tag_name) + 2;  // Length of "<tag_name>"
		char close_tag[50];                          // Buffer for "</tag_name>"
		snprintf(close_tag, sizeof(close_tag), "</%s>", tag_name);
		size_t close_tag_len = strlen(close_tag);

		char* content_start = next_tag_start + open_tag_len;
		char* close_tag_start = strstr(content_start, close_tag);

		if (!close_tag_start) {
			fprintf(stderr,
			        "Error: Malformed XML in stdin. Found opening tag '<%s>' "
			        "starting at offset %ld but no closing tag '</%s>'.\n",
			        tag_name, (long)(next_tag_start - stdin_content), tag_name);
			// ranges_to_remove and remaining_content_buffer cleanup handled in
			// 'cleanup' block
			goto cleanup;  // Malformed XML
		}

		// Extract content
		size_t content_len = close_tag_start - content_start;
		char* content = malloc(content_len + 1);
		if (!content) {
			perror("Failed to allocate memory for tag content");
			goto cleanup;
		}
		memcpy(content, content_start, content_len);
		content[content_len] = '\0';
		if (debug_mode)
			fprintf(stderr,
			        "DEBUG: Found tag: <%s>, Role: %s, Content: \"%.*s...\"\n",
			        tag_name, role, content_len > 20 ? 20 : (int)content_len,
			        content);

		// Add message to list
		if (!add_message_to_list(&message_list_head, &message_list_tail, role,
		                         content)) {
			free(content);
			goto cleanup;  // Error
		}
		free(content);  // Content is duplicated by create_message

		// Record the range to remove (from start of opening tag to end of
		// closing tag)
		if (ranges_count >= ranges_capacity) {
			ranges_capacity = (ranges_capacity == 0) ? 8 : ranges_capacity * 2;
			XmlRange* new_ranges =
			    realloc(ranges_to_remove, ranges_capacity * sizeof(XmlRange));
			if (!new_ranges) {
				perror("Failed to reallocate memory for XML ranges");
				// Old ranges_to_remove is still valid if realloc fails, cleanup
				// will handle it
				goto cleanup;
			}
			ranges_to_remove = new_ranges;
		}
		ranges_to_remove[ranges_count].start = next_tag_start;
		ranges_to_remove[ranges_count].end =
		    close_tag_start + close_tag_len;  // Point *after* closing tag '>'
		ranges_count++;

		// Move current_pos past the processed tag
		current_pos = ranges_to_remove[ranges_count - 1].end;
	}
	if (debug_mode)
		fprintf(stderr, "DEBUG: Finished XML tag parsing. Found %zu tags.\n",
		        ranges_count);

	// 5.3 Construct remaining content string (excluding removed ranges)
	remaining_content_buffer = malloc(stdin_len + 1);  // Max possible size
	if (!remaining_content_buffer) {
		perror("Failed to allocate memory for remaining content buffer");
		goto cleanup;
	}

	char* write_ptr = remaining_content_buffer;
	char* read_ptr = stdin_content;
	size_t current_range_idx = 0;

	while (read_ptr != NULL && *read_ptr != '\0') {
		// Check if the current read_ptr is within a range to be removed
		int in_remove_range = 0;
		if (current_range_idx < ranges_count &&
		    read_ptr >= ranges_to_remove[current_range_idx].start) {
			// We assume ranges are sorted by start pointer as they are found
			// sequentially
			if (read_ptr < ranges_to_remove[current_range_idx].end) {
				in_remove_range = 1;
				// Advance read_ptr to the end of this range
				read_ptr = ranges_to_remove[current_range_idx].end;
				current_range_idx++;  // Move to check the next range
			} else {
				// This case means read_ptr is exactly at or after the end of
				// the current range. This can happen if ranges are adjacent or
				// if read_ptr somehow landed here. We should just advance the
				// range index and re-evaluate the *same* read_ptr against the
				// *next* range in the next loop iteration.
				current_range_idx++;
				continue;  // Re-evaluate same read_ptr against next range (if
				           // any)
			}
		}

		if (!in_remove_range && read_ptr != NULL &&
		    *read_ptr != '\0') {  // Check *read_ptr again after potential jump
			*write_ptr++ = *read_ptr++;
		} else if (read_ptr == NULL || *read_ptr == '\0') {
			// Reached end after jumping past a range or original string ended
			break;
		}
		// If in_remove_range is true, read_ptr was already advanced, loop
		// continues
	}
	*write_ptr = '\0';  // Null-terminate the remaining content
	size_t remaining_content_len = write_ptr - remaining_content_buffer;
	free(ranges_to_remove);   // No longer needed
	ranges_to_remove = NULL;  // Avoid double free in cleanup

	if (debug_mode)
		fprintf(
		    stderr,
		    "DEBUG: Remaining content after XML removal (%zu bytes): \"%s\"\n",
		    remaining_content_len, remaining_content_buffer);

	// 5.4 Add remaining content as a final user message if not empty/whitespace
	char* trimmed_remaining =
	    trim_whitespace(remaining_content_buffer);  // Modifies buffer in-place
	if (trimmed_remaining && *trimmed_remaining != '\0') {
		if (debug_mode)
			fprintf(stderr,
			        "DEBUG: Adding trimmed remaining content as final user "
			        "message: "
			        "\"%s\"\n",
			        trimmed_remaining);
		if (!add_message_to_list(&message_list_head, &message_list_tail, "user",
		                         trimmed_remaining)) {
			// free(remaining_content_buffer); // Don't free here, cleanup
			// handles it
			goto cleanup;  // Error
		}
	} else {
		if (debug_mode)
			fprintf(stderr,
			        "DEBUG: Trimmed remaining content is empty, not adding "
			        "final user message.\n");
	}
	// Free the buffer used for remaining content construction AFTER it's
	// potentially added to the list (it's duplicated by create_message)
	free(remaining_content_buffer);
	remaining_content_buffer = NULL;  // Avoid double free in cleanup

	// --- 5.5 Unescape message content ---
	if (debug_mode)
		fprintf(stderr,
		        "DEBUG: Unescaping message content using hnt-escape...\n");
	Message* current_msg = message_list_head;
	while (current_msg != NULL) {
		if (debug_mode)
			fprintf(stderr, "DEBUG: Unescaping content for role '%s'...\n",
			        current_msg->role);
		char* original_content =
		    current_msg->content;  // Keep pointer to free later
		char* unescaped_content = unescape_message_content(original_content);

		if (!unescaped_content) {
			fprintf(stderr,
			        "Error: Failed to unescape content for role '%s'. Original "
			        "content:\n%s\n",
			        current_msg->role,
			        original_content ? original_content : "(null)");
			// Abort if unescaping fails
			goto cleanup;  // Use existing cleanup mechanism
		}

		// Check if content actually changed to avoid unnecessary free/strdup
		// Note: create_message uses strdup, so original_content is always
		// allocated unless it was NULL initially (which shouldn't happen here).
		if (strcmp(original_content, unescaped_content) != 0) {
			if (debug_mode)
				fprintf(stderr, "DEBUG: Content changed after unescaping.\n");
			free(original_content);  // Free the old content
			current_msg->content =
			    unescaped_content;  // Assign the new (we own it now)
		} else {
			if (debug_mode)
				fprintf(stderr, "DEBUG: Content unchanged after unescaping.\n");
			free(unescaped_content);  // Free the buffer returned by helper if
			                          // unchanged
			// current_msg->content remains the original pointer
		}

		current_msg = current_msg->next;
	}
	if (debug_mode)
		fprintf(stderr, "DEBUG: Finished unescaping message content.\n");

	// --- 5b. Construct Final API URL ---
	// URL is now fixed for all providers, API key always goes in header
	strncpy(final_api_url, api_url_base, sizeof(final_api_url) - 1);
	final_api_url[sizeof(final_api_url) - 1] = '\0';  // Ensure null termination

	if (debug_mode) {
		fprintf(stderr, "DEBUG: Request URL: %s\n", final_api_url);
	}

	// --- 6. Initialize libcurl ---
	curl_global_init(CURL_GLOBAL_ALL);
	curl_handle = curl_easy_init();
	if (!curl_handle) {
		fprintf(stderr, "Error: Failed to initialize curl handle.\n");
		free(stdin_content);
		free(stream_data.buffer);
		curl_global_cleanup();
		return 1;
	}

	// --- 7. Prepare JSON Payload using Jansson ---
	root_payload = json_object();
	if (!root_payload) {
		fprintf(stderr, "Error: Failed to create root JSON object.\n");
		goto cleanup;  // Use goto for centralized cleanup
	}

	// --- Standard OpenAI/Compatible Payload Structure (used for all providers
	// now) ---

	// Add model
	if (json_object_set_new(root_payload, "model",
	                        json_string(model_name_to_send)) != 0) {
		fprintf(stderr, "Error: Failed to set model '%s' in JSON.\n",
		        model_name_to_send);
		goto cleanup;
	}

	// Convert message linked list to JSON array
	messages_array = messages_to_json_array(message_list_head);
	if (!messages_array) {
		// Error message printed inside messages_to_json_array
		goto cleanup;
	}

	// Add the generated messages array to the root payload
	if (json_object_set_new(root_payload, "messages", messages_array) != 0) {
		fprintf(stderr, "Error: Failed to add messages array to root JSON.\n");
		// messages_array will be decref'd by the cleanup of root_payload if it
		// was successfully added If set_new fails, we might need to decref
		// messages_array explicitly? Jansson docs say set_new consumes
		// reference on success. If it fails, the reference count isn't changed,
		// so we still need to decref it.
		json_decref(messages_array);  // Decref here if set_new failed
		messages_array = NULL;        // Avoid double free in cleanup
		goto cleanup;
	}
	// messages_array is now owned by root_payload

	// Add stream parameter
	if (json_object_set_new(root_payload, "stream", json_true()) != 0) {
		fprintf(stderr, "Error: Failed to set stream parameter in JSON.\n");
		goto cleanup;
	}

	// Dump the JSON object to a string
	post_data_dynamic = json_dumps(root_payload, JSON_COMPACT);
	if (!post_data_dynamic) {
		fprintf(stderr, "Error: Failed to dump JSON to string.\n");
		goto cleanup;
	}
	if (debug_mode) {
		fprintf(stderr, "DEBUG: Request Payload: %s\n", post_data_dynamic);
	}
	// fprintf(stderr, "Payload: %s\n", post_data_dynamic); // Debug: Print
	// payload

	// --- 8. Set libcurl options ---
	// Set URL (using the final constructed URL)
	curl_easy_setopt(curl_handle, CURLOPT_URL, final_api_url);

	// Set POST data (using the dynamically generated string)
	curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDS, post_data_dynamic);

	// Set Headers
	headers = curl_slist_append(headers, "Content-Type: application/json");
	headers = curl_slist_append(
	    headers, auth_header);  // Add Authorization header (always needed now)
	curl_easy_setopt(curl_handle, CURLOPT_HTTPHEADER, headers);

	if (debug_mode) {
		struct curl_slist* hdr = headers;
		fprintf(stderr, "DEBUG: Request Headers:\n");
		while (hdr) {
			fprintf(stderr, "  %s\n", hdr->data);
			hdr = hdr->next;
		}
	}

	// Set callback function to handle stream response
	curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, WriteStreamCallback);
	curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, (void*)&stream_data);

	// Set user agent (good practice)
	curl_easy_setopt(curl_handle, CURLOPT_USERAGENT, "libcurl-agent/1.0");

	// Enable POST request
	curl_easy_setopt(curl_handle, CURLOPT_POST, 1L);

	// Optional: Enable verbose output for debugging curl issues
	// curl_easy_setopt(curl_handle, CURLOPT_VERBOSE, 1L);

	// --- Initialize stream state for --include-reasoning ---
	stream_data.include_reasoning_mode = include_reasoning_flag;
	stream_data.current_output_phase = PHASE_INIT;
	stream_data.think_tag_printed = 0;

	// --- 9. Perform the request ---
	res = curl_easy_perform(curl_handle);

	// --- 10. Check for errors ---
	if (res != CURLE_OK) {
		// Avoid printing extra newline if stream already printed one before
		// error. Also, if <think> was opened, ensure it's closed on error.
		if (stream_data.include_reasoning_mode &&
		    stream_data.think_tag_printed) {
			printf("</think>\n");  // Close tag on error if it was opened
			fflush(stdout);
			// No need to reset think_tag_printed here as we are exiting.
		} else if (stream_data.data_len == 0 && !api_error_occurred) {
			// Only print newline if no data was streamed and no API error
			// (which prints its own newlines)
			printf("\n");
		}
		fprintf(stderr, "curl_easy_perform() failed: %s\n",
		        curl_easy_strerror(res));
	} else {
		// --- 11. Processing is done in the callback, including [DONE] handling
		// --- Ensure a final newline after streaming is complete, if not
		// already handled by an API error or the stream itself. The callback
		// for [DONE] might close </think>, or normal output might end with a
		// newline. If an API error occurred, it likely printed a newline. If no
		// data was streamed at all (e.g. empty response before [DONE]), and no
		// API error, then print a newline.
		if (!api_error_occurred && stream_data.data_len == 0 &&
		    (include_reasoning_flag ? !stream_data.think_tag_printed : 1)) {
			// The above condition for data_len might be tricky if [DONE] was
			// the only thing, which clears buffer. A simple printf("\n") here
			// is generally safe if the LLM doesn't guarantee final newlines.
			// The original code had printf("\n"); here. Let's keep it for now,
			// as LLM outputs might not always end with one.
			printf("\n");
		}
	}

	// --- 12. Cleanup ---
cleanup:  // Label for centralized cleanup
	if (api_key) free(api_key);
	if (post_data_dynamic)
		free(post_data_dynamic);  // Free dynamically generated JSON string
	if (root_payload)
		json_decref(root_payload);  // Free jansson object structure (this will
		                            // decref messages_array if it was added)
	else if (messages_array)
		json_decref(messages_array);  // Decref messages_array if root_payload
		                              // creation failed or set_new failed
	free_message_list(message_list_head);    // Free the message linked list
	if (stdin_content) free(stdin_content);  // Free stdin buffer
	if (curl_handle) curl_easy_cleanup(curl_handle);  // Cleanup curl handle
	free(stream_data.buffer);                         // Free stream buffer
	curl_slist_free_all(headers);                     // Free headers list
	// --- Add cleanup for new allocations ---
	if (ranges_to_remove)
		free(ranges_to_remove);  // In case of early exit via goto
	if (remaining_content_buffer)
		free(remaining_content_buffer);  // In case of early exit via goto
	// --- End added cleanup ---
	curl_global_cleanup();  // Global curl cleanup

	// Check curl success, payload creation, non-empty messages, AND our API
	// error flag.
	int success = (res == CURLE_OK && post_data_dynamic != NULL &&
	               message_list_head != NULL &&
	               !api_error_occurred);  // Check the API error flag

	if (!success && message_list_head == NULL && res == CURLE_OK &&
	    !api_error_occurred) {
		// Specific case: No messages provided (empty stdin, no -s, or only
		// whitespace after XML removal), and no other errors occurred (curl ok,
		// no API error). We don't treat this as an error needing a message if
		// the curl call itself didn't fail and no API error reported. Allow
		// sending empty messages list if API supports it? For now, treat as
		// non-success. Let's print an info message but still return 1, as
		// nothing was sent.
		if (debug_mode)
			fprintf(stderr,
			        "DEBUG: No messages were generated to send (empty "
			        "stdin/result?).\n");
		// No need to print another error if curl failed, it was already
		// printed.
	}

	return success ? 0 : 1;
}
