#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h> // Requires libcurl development library
#include <jansson.h>   // Requires jansson development library
#include <errno.h>     // For errno
#include <unistd.h>    // For isatty() and STDIN_FILENO
#include <getopt.h>    // For getopt_long

// Global flag for debug mode
static int debug_mode = 0;

// API Providers Enum
enum ApiProvider {
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    PROVIDER_DEEPSEEK,
    PROVIDER_GOOGLE
};

// Define API endpoints
#define OPENAI_API_URL "https://api.openai.com/v1/chat/completions"
#define OPENROUTER_API_URL "https://openrouter.ai/api/v1/chat/completions"
#define DEEPSEEK_API_URL "https://api.deepseek.com/chat/completions"
#define GOOGLE_COMPAT_API_URL "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions" // Google OpenAI-Compatible Endpoint
#define READ_CHUNK_SIZE 4096 // Size for reading stdin chunks

// Structure to hold unprocessed stream data
struct StreamData {
    char *buffer;
    size_t buffer_size;
    size_t data_len;
};

// Function to process a single SSE data payload (JSON string) - handles different provider formats
static void process_sse_data(const char *json_data) {
    json_t *root_resp = NULL;
    json_error_t error;

    // Check for the special [DONE] message
    if (strcmp(json_data, "[DONE]") == 0) {
        // End of stream detected
        // printf("\n[STREAM DONE]\n"); // Optional: indicate stream end
        return;
    }

    root_resp = json_loads(json_data, 0, &error);
    if (!root_resp) {
        fprintf(stderr, "\nError parsing JSON chunk: on line %d: %s\nData: %s\n", error.line, error.text, json_data);
        return; // Skip this chunk
    }

    // Try parsing as OpenAI/OpenRouter/DeepSeek format first
    json_t *choices_array = json_object_get(root_resp, "choices");
    if (choices_array && json_is_array(choices_array) && json_array_size(choices_array) > 0) {
        // --- OpenAI/OpenRouter/DeepSeek Format ---
        json_t *first_choice = json_array_get(choices_array, 0);
        if (json_is_object(first_choice)) {
            json_t *delta_obj = json_object_get(first_choice, "delta");
            if (json_is_object(delta_obj)) {
                json_t *content_str = json_object_get(delta_obj, "content");
                if (json_is_string(content_str)) {
                    const char *content = json_string_value(content_str);
                    printf("%s", content);
                    fflush(stdout);
                }
            }
            // Check for finish reason (optional)
            // json_t *finish_reason = json_object_get(first_choice, "finish_reason");
            // Check for finish reason (optional)
            // json_t *finish_reason = json_object_get(first_choice, "finish_reason");
            // if (json_is_string(finish_reason)) { ... }
        }
    } else {
        // --- Handle potential errors or unknown formats ---
        json_t *error_obj = json_object_get(root_resp, "error");
        if (json_is_object(error_obj)) {
            json_t *message_str = json_object_get(error_obj, "message");
            if (json_is_string(message_str)) {
                fprintf(stderr, "\nAPI Error: %s\n", json_string_value(message_str));
            } else {
                fprintf(stderr, "\nAPI Error: (Could not parse error message)\n");
            }
        } else {
             // Only print unknown format error if it wasn't the [DONE] marker
             if (strcmp(json_data, "[DONE]") != 0) {
                fprintf(stderr, "\nWarning: Received chunk in unknown format or without content/choices.\nData: %s\n", json_data);
             }
        }
    }

    json_decref(root_resp); // Free the parsed JSON object
}

// Helper function to read all data from stdin into a buffer
static char* read_stdin_all(size_t *out_len) {
    char *buffer = NULL;
    size_t capacity = 0;
    size_t len = 0;
    size_t nread;

    do {
        if (len + READ_CHUNK_SIZE + 1 > capacity) {
            size_t new_capacity = (capacity == 0) ? READ_CHUNK_SIZE + 1 : capacity * 2;
            if (new_capacity < len + READ_CHUNK_SIZE + 1) {
                new_capacity = len + READ_CHUNK_SIZE + 1;
            }
            char *new_buffer = realloc(buffer, new_capacity);
            if (!new_buffer) {
                fprintf(stderr, "Error: Failed to allocate buffer for stdin: %s\n", strerror(errno));
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
        buffer[len] = '\0'; // Null-terminate
    } else {
        // Handle case where stdin is empty - return an empty, null-terminated string
        buffer = malloc(1);
        if (!buffer) {
             fprintf(stderr, "Error: Failed to allocate buffer for empty stdin: %s\n", strerror(errno));
             return NULL;
        }
        buffer[0] = '\0';
        len = 0;
    }


    *out_len = len;
    return buffer;
}


// Callback function for libcurl to handle incoming stream data
static size_t WriteStreamCallback(void *contents, size_t size, size_t nmemb, void *userp) {
    size_t realsize = size * nmemb;
    struct StreamData *stream_data = (struct StreamData *)userp;
    const char *data_prefix = "data: ";
    size_t prefix_len = strlen(data_prefix);

    if (debug_mode) {
        fprintf(stderr, "DEBUG: Raw incoming chunk (%zu bytes):\n", realsize);
        fwrite(contents, 1, realsize, stderr);
        fprintf(stderr, "\n");
    }

    // --- 1. Append new data to buffer ---
    size_t needed_size = stream_data->data_len + realsize + 1; // +1 for null terminator
    if (stream_data->buffer == NULL || needed_size > stream_data->buffer_size) {
        size_t new_size = (stream_data->buffer_size == 0) ? 1024 : stream_data->buffer_size * 2;
        if (new_size < needed_size) new_size = needed_size; // Ensure enough space

        char *new_buffer = realloc(stream_data->buffer, new_size);
        if (new_buffer == NULL) {
            fprintf(stderr, "Error: Failed to reallocate stream buffer\n");
            return 0; // Signal error to curl
        }
        stream_data->buffer = new_buffer;
        stream_data->buffer_size = new_size;
    }
    memcpy(stream_data->buffer + stream_data->data_len, contents, realsize);
    stream_data->data_len += realsize;
    stream_data->buffer[stream_data->data_len] = '\0'; // Null-terminate

    // --- 2. Process complete SSE messages in the buffer ---
    char *message_start = stream_data->buffer;
    char *message_end;

    // --- Add hex dump ---
    if (debug_mode && stream_data->data_len > 0) {
        fprintf(stderr, "DEBUG: Checking last bytes of buffer (max 10): ");
        size_t start_idx = (stream_data->data_len > 10) ? stream_data->data_len - 10 : 0;
        for (size_t i = start_idx; i < stream_data->data_len; ++i) {
            fprintf(stderr, "%02X ", (unsigned char)stream_data->buffer[i]);
        }
        fprintf(stderr, "\n");
    }
    // --- End hex dump ---

    while (1) { // Loop indefinitely until break
        char *separator_rn = strstr(message_start, "\r\n\r\n");
        char *separator_n = strstr(message_start, "\n\n");
        size_t separator_len = 0;

        // Determine which separator comes first, or if none found
        if (separator_rn && (!separator_n || separator_rn < separator_n)) {
            message_end = separator_rn;
            separator_len = 4; // "\r\n\r\n"
            if (debug_mode) fprintf(stderr, "DEBUG: Found '\\r\\n\\r\\n' separator. Processing message block.\n");
        } else if (separator_n) {
            message_end = separator_n;
            separator_len = 2; // "\n\n"
            if (debug_mode) fprintf(stderr, "DEBUG: Found '\\n\\n' separator. Processing message block.\n");
        } else {
            // No complete message separator found in the current buffer
            break; // Exit the while loop
        }

        // Found a potential message boundary
        // size_t message_len = message_end - message_start; // Unused variable

        // Process lines within this message block
        char *line_start = message_start;
        char *line_end;
        while (line_start < message_end && (line_end = memchr(line_start, '\n', message_end - line_start)) != NULL) {
             // Check if the line starts with "data: "
             // Cast pointer difference to size_t for comparison
            if (((size_t)(line_end - line_start) > prefix_len) && memcmp(line_start, data_prefix, prefix_len) == 0) {
                // Extract the JSON payload part
                char *json_start = line_start + prefix_len;
                // size_t json_len = line_end - json_start; // Unused variable

                // Temporarily null-terminate the JSON string for processing
                char original_char = *line_end;
                *line_end = '\0';
                process_sse_data(json_start);
                *line_end = original_char; // Restore original character
            }
            // Move to the next line
            line_start = line_end + 1;
        }
         // Check the last part of the message block if it didn't end with \n
        if (line_start < message_end) {
             // Cast pointer difference to size_t for comparison
             if (((size_t)(message_end - line_start) > prefix_len) && memcmp(line_start, data_prefix, prefix_len) == 0) {
                char *json_start = line_start + prefix_len;
                // size_t json_len = message_end - json_start; // Unused variable
                char original_char = *message_end;
                *message_end = '\0';
                process_sse_data(json_start);
                *message_end = original_char;
            }
        }


        // Move past the processed message (including the separator)
        message_start = message_end + separator_len; // Use determined separator length
    }

    // --- 3. Remove processed data from the buffer ---
    if (message_start > stream_data->buffer) {
        size_t remaining_len = stream_data->data_len - (message_start - stream_data->buffer);
        memmove(stream_data->buffer, message_start, remaining_len);
        stream_data->data_len = remaining_len;
        stream_data->buffer[stream_data->data_len] = '\0'; // Re-null-terminate
    }

    return realsize; // Tell curl we processed all received bytes
}


int main(int argc, char *argv[]) {
  CURL *curl_handle = NULL; // Initialize curl_handle to NULL
  CURLcode res = CURLE_OK; // Initialize res
  struct StreamData stream_data = {NULL, 0, 0}; // Initialize stream data struct
  struct curl_slist *headers = NULL;
  char *api_key = NULL;
  char auth_header[1024]; // Buffer for the Authorization header
  char *stdin_content = NULL;
  size_t stdin_len = 0;
  json_t *root_payload = NULL;
  char *post_data_dynamic = NULL;
  const char *model_arg = "openrouter/deepseek/deepseek-chat-v3-0324:free"; // Default model argument
  const char *api_url_base = NULL; // Base URL or format string
  char final_api_url[1024]; // Buffer for the final formatted URL
  const char *api_key_env_var = NULL;
  const char *model_name_to_send = NULL;
  const char *system_prompt = NULL; // Variable to store the system prompt

  // --- 1. Parse Command Line Arguments ---
  int opt;
  // Define long options
  static struct option long_options[] = {
      {"model",        required_argument, 0, 'm'},
      {"system",       required_argument, 0, 's'},
      {"debug-unsafe", no_argument,       0, 'd'}, // Added debug flag (using 'd' internally)
      {0, 0, 0, 0} // End of options marker
  };

  // Use model_arg to store the argument value, default or from -m
  // Use system_prompt to store the system prompt argument
  // Use 'd' internally for the debug flag, no short option exposed to user
  while ((opt = getopt_long(argc, argv, "m:s:", long_options, NULL)) != -1) {
      switch (opt) {
          case 'm':
              model_arg = optarg;
              break;
          case 'd': // Handle debug flag
              debug_mode = 1;
              break;
          case 's': // Handle system prompt argument
              system_prompt = optarg;
              break;
          case '?':
              // getopt_long already printed an error message.
              fprintf(stderr, "Model format: provider/model_name (e.g., openai/gpt-4o, openrouter/some/model)\n");
              fprintf(stderr, "Usage: %s [-m provider/model_name] [-s system_prompt]\n", argv[0]);
              return 1;
          default:
              abort(); // Should not happen
      }
  }

  // Check for non-option arguments (currently none expected)
  if (optind < argc) {
      fprintf(stderr, "Error: Unexpected non-option arguments found.\n");
      fprintf(stderr, "Model format: provider/model_name (e.g., openai/gpt-4o, openrouter/some/model)\n");
      fprintf(stderr, "Usage: %s [-m provider/model_name] [-s system_prompt]\n", argv[0]);
      return 1;
  }

  // --- 2. Parse Model Argument and Select API/Key ---
  const char *separator = strchr(model_arg, '/');
  if (separator == NULL) {
      fprintf(stderr, "Error: Invalid model format. Expected 'provider/model_name', got '%s'\n", model_arg);
      return 1;
  }

  size_t provider_len = separator - model_arg;
  model_name_to_send = separator + 1; // Point to the character after '/'

  if (strncmp(model_arg, "openai/", provider_len + 1) == 0) {
      api_url_base = OPENAI_API_URL;
      api_key_env_var = "OPENAI_API_KEY";
  } else if (strncmp(model_arg, "openrouter/", provider_len + 1) == 0) {
      api_url_base = OPENROUTER_API_URL;
      api_key_env_var = "OPENROUTER_API_KEY";
      // OpenRouter specific headers
      headers = curl_slist_append(headers, "HTTP-Referer: https://github.com/michaelskyba/hinata/");
      headers = curl_slist_append(headers, "X-Title: hinata");
  } else if (strncmp(model_arg, "deepseek/", provider_len + 1) == 0) {
      api_url_base = DEEPSEEK_API_URL;
      api_key_env_var = "DEEPSEEK_API_KEY";
  } else if (strncmp(model_arg, "google/", provider_len + 1) == 0) {
      api_url_base = GOOGLE_COMPAT_API_URL; // Use the compatible endpoint URL
      api_key_env_var = "GEMINI_API_KEY";
  } else {
      // Allocate buffer for provider string for error message
      char *provider_str = malloc(provider_len + 1);
      if (!provider_str) {
           fprintf(stderr, "Error: Memory allocation failed for provider string.\n");
           return 1; // Allocation error
      }
      if (!provider_str) {
           fprintf(stderr, "Error: Memory allocation failed for provider string.\n");
           return 1; // Allocation error
      }
      strncpy(provider_str, model_arg, provider_len);
      provider_str[provider_len] = '\0';
      fprintf(stderr, "Error: Unsupported provider '%s' in model '%s'. Use 'openai', 'openrouter', 'deepseek', or 'google'.\n", provider_str, model_arg);
      free(provider_str);
      return 1;
  }

  if (*model_name_to_send == '\0') { // Check if model name part is empty
       fprintf(stderr, "Error: Missing model name after '/' in '%s'.\n", model_arg);
       return 1;
  }


  // --- 3. Initialize stream data buffer ---
  // --- 4. Get API Key from environment variable ---
  api_key = getenv(api_key_env_var); // Use the selected environment variable
  if (api_key == NULL) {
    fprintf(stderr, "Error: %s environment variable not set.\n", api_key_env_var);
    free(stdin_content);
    free(stream_data.buffer);
    return 1; // Keep exit code 1 for consistency
  }

  // Prepare Authorization header (used by all providers now)
  snprintf(auth_header, sizeof(auth_header), "Authorization: Bearer %s", api_key);

  // --- 4a. Read content from stdin ---
  // Inform user only if stdin is a terminal
  if (isatty(STDIN_FILENO)) {
      fprintf(stderr, "Reading prompt from stdin...\n");
  }
  stdin_content = read_stdin_all(&stdin_len);
  if (stdin_content == NULL) {
      fprintf(stderr, "Error reading from stdin.\n");
      free(stream_data.buffer); // Free stream buffer if allocated
      // No need to free api_key, it's from getenv
      return 1;
  }
   // fprintf(stderr, "Read %zu bytes from stdin.\n", stdin_len); // Confirm bytes read

  // --- 5. Construct Final API URL ---
  // URL is now fixed for all providers, API key always goes in header
  strncpy(final_api_url, api_url_base, sizeof(final_api_url) - 1);
  final_api_url[sizeof(final_api_url) - 1] = '\0'; // Ensure null termination

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
      goto cleanup; // Use goto for centralized cleanup
  }

  // --- Standard OpenAI/Compatible Payload Structure (used for all providers now) ---

  // Add model
  if (json_object_set_new(root_payload, "model", json_string(model_name_to_send)) != 0) {
      fprintf(stderr, "Error: Failed to set model '%s' in JSON.\n", model_name_to_send);
      goto cleanup;
  }

  // Create messages array
  json_t *messages_array = json_array();
  if (!messages_array) {
      fprintf(stderr, "Error: Failed to create messages JSON array.\n");
      goto cleanup;
  }
  if (json_object_set_new(root_payload, "messages", messages_array) != 0) {
      fprintf(stderr, "Error: Failed to add messages array to root JSON.\n");
      goto cleanup;
  }

  // Add system message if provided
  if (system_prompt != NULL) {
      json_t *system_message_obj = json_object();
      if (!system_message_obj) {
          fprintf(stderr, "Error: Failed to create system message JSON object.\n");
          goto cleanup;
      }
      if (json_object_set_new(system_message_obj, "role", json_string("system")) != 0 ||
          json_object_set_new(system_message_obj, "content", json_string(system_prompt)) != 0) {
          fprintf(stderr, "Error: Failed to set system message properties in JSON.\n");
          json_decref(system_message_obj);
          goto cleanup;
      }
      if (json_array_append_new(messages_array, system_message_obj) != 0) {
          fprintf(stderr, "Error: Failed to append system message to messages array.\n");
          goto cleanup;
      }
  }

  // Create user message object
  json_t *user_message_obj = json_object();
  if (!user_message_obj) {
      fprintf(stderr, "Error: Failed to create user message JSON object.\n");
      goto cleanup;
  }
  if (json_object_set_new(user_message_obj, "role", json_string("user")) != 0 ||
      json_object_set_new(user_message_obj, "content", json_string(stdin_content)) != 0) {
      fprintf(stderr, "Error: Failed to set user message properties in JSON.\n");
      json_decref(user_message_obj);
      goto cleanup;
  }
  if (json_array_append_new(messages_array, user_message_obj) != 0) {
      fprintf(stderr, "Error: Failed to append user message to messages array.\n");
      goto cleanup;
  }

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
  // fprintf(stderr, "Payload: %s\n", post_data_dynamic); // Debug: Print payload

  // --- 8. Set libcurl options ---
  // Set URL (using the final constructed URL)
  curl_easy_setopt(curl_handle, CURLOPT_URL, final_api_url);

  // Set POST data (using the dynamically generated string)
  curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDS, post_data_dynamic);

  // Set Headers
  headers = curl_slist_append(headers, "Content-Type: application/json");
  headers = curl_slist_append(headers, auth_header); // Add Authorization header (always needed now)
  curl_easy_setopt(curl_handle, CURLOPT_HTTPHEADER, headers);

  if (debug_mode) {
      struct curl_slist *hdr = headers;
      fprintf(stderr, "DEBUG: Request Headers:\n");
      while (hdr) {
          fprintf(stderr, "  %s\n", hdr->data);
          hdr = hdr->next;
      }
  }

  // Set callback function to handle stream response
  curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, WriteStreamCallback);
  curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, (void *)&stream_data);

  // Set user agent (good practice)
  curl_easy_setopt(curl_handle, CURLOPT_USERAGENT, "libcurl-agent/1.0");

  // Enable POST request
  curl_easy_setopt(curl_handle, CURLOPT_POST, 1L);

  // Optional: Enable verbose output for debugging curl issues
  // curl_easy_setopt(curl_handle, CURLOPT_VERBOSE, 1L);

  // --- 9. Perform the request ---
  res = curl_easy_perform(curl_handle);

  // --- 10. Check for errors ---
  if(res != CURLE_OK) {
    // Avoid printing extra newline if stream already printed one before error
    if (stream_data.data_len == 0) printf("\n"); // Add newline only if nothing was printed
    fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
  } else {
    // --- 11. Processing is done in the callback ---
    // Ensure a final newline after streaming is complete
    // Check if the last character printed by the callback was a newline
    // This is tricky as the callback doesn't track this easily.
    // A simple approach is to always print a newline if the curl call succeeded.
    // If the stream ended cleanly, it might result in a double newline,
    // but it guarantees one newline after successful completion.
    printf("\n");
  }

  // --- 12. Cleanup ---
cleanup: // Label for centralized cleanup
  if (post_data_dynamic) free(post_data_dynamic); // Free dynamically generated JSON string
  if (root_payload) json_decref(root_payload);     // Free jansson object structure
  if (stdin_content) free(stdin_content);         // Free stdin buffer
  if (curl_handle) curl_easy_cleanup(curl_handle); // Cleanup curl handle
  free(stream_data.buffer);                       // Free stream buffer
  curl_slist_free_all(headers);                   // Free headers list
  curl_global_cleanup();                          // Global curl cleanup

  // Return 0 on success (request sent without curl error), 1 otherwise.
  // Note: API-level errors might have been printed during the stream or during setup.
  return (res == CURLE_OK && post_data_dynamic != NULL) ? 0 : 1; // Also check if JSON creation succeeded
}
