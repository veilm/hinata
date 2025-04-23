#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h> // Requires libcurl development library
#include <jansson.h>   // Requires jansson development library
#include <errno.h>     // For errno

// Define the API endpoint
#define OPENAI_API_URL "https://api.openai.com/v1/chat/completions"
#define READ_CHUNK_SIZE 4096 // Size for reading stdin chunks

// Structure to hold unprocessed stream data
struct StreamData {
    char *buffer;
    size_t buffer_size;
    size_t data_len;
};

// Function to process a single SSE data payload (JSON string)
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

    // Navigate the JSON structure: root -> choices (array) -> 0 (object) -> delta (object) -> content (string)
    json_t *choices_array = json_object_get(root_resp, "choices");
    if (json_is_array(choices_array) && json_array_size(choices_array) > 0) {
        json_t *first_choice = json_array_get(choices_array, 0);
        if (json_is_object(first_choice)) {
            json_t *delta_obj = json_object_get(first_choice, "delta");
            if (json_is_object(delta_obj)) {
                json_t *content_str = json_object_get(delta_obj, "content");
                if (json_is_string(content_str)) {
                    const char *content = json_string_value(content_str);
                    // Print the content chunk immediately
                    printf("%s", content);
                    fflush(stdout); // Ensure it's visible immediately
                }
                // We don't treat absence of 'content' as an error here,
                // as some chunks might only contain role or finish_reason.
                 json_t *finish_reason = json_object_get(first_choice, "finish_reason");
                 if (json_is_string(finish_reason)) {
                     // Optionally handle finish reason if needed
                     // const char *reason = json_string_value(finish_reason);
                     // printf("\n[Finish Reason: %s]\n", reason);
                 }
            }
        }
    } else {
        // It's possible to receive chunks without 'choices', e.g., error messages
        // Check for top-level error object
        json_t *error_obj = json_object_get(root_resp, "error");
        if (json_is_object(error_obj)) {
            json_t *message_str = json_object_get(error_obj, "message");
            if (json_is_string(message_str)) {
                fprintf(stderr, "\nAPI Error: %s\n", json_string_value(message_str));
            } else {
                fprintf(stderr, "\nAPI Error: (Could not parse error message)\n");
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
    while ((message_end = strstr(message_start, "\n\n")) != NULL) {
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


        // Move past the processed message (including the "\n\n")
        message_start = message_end + 2; // Move past "\n\n"
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


int main(void) {
  CURL *curl_handle;
  CURLcode res = CURLE_OK; // Initialize res
  struct StreamData stream_data = {NULL, 0, 0}; // Initialize stream data struct
  struct curl_slist *headers = NULL;
  char *api_key = NULL;
  char auth_header[1024]; // Buffer for the Authorization header
  char *stdin_content = NULL;
  size_t stdin_len = 0;
  json_t *root_payload = NULL;
  char *post_data_dynamic = NULL;

  // --- 1. Initialize stream data buffer ---
  // Initialization moved to struct definition above.

  // --- 2. Read content from stdin ---
  fprintf(stderr, "Reading prompt from stdin...\n"); // Inform user
  stdin_content = read_stdin_all(&stdin_len);
  if (stdin_content == NULL) {
      fprintf(stderr, "Error reading from stdin.\n");
      free(stream_data.buffer); // Free stream buffer if allocated
      return 1;
  }
   fprintf(stderr, "Read %zu bytes from stdin.\n", stdin_len); // Confirm bytes read


  // --- 3. Get API Key from environment variable ---
  api_key = getenv("OPENAI_API_KEY");
  if (api_key == NULL) {
    fprintf(stderr, "Error: OPENAI_API_KEY environment variable not set.\n");
    free(stdin_content);
    free(stream_data.buffer);
    return 1;
  }
  snprintf(auth_header, sizeof(auth_header), "Authorization: Bearer %s", api_key);

  // --- 4. Initialize libcurl ---
  curl_global_init(CURL_GLOBAL_ALL);
  curl_handle = curl_easy_init();
  if (!curl_handle) {
      fprintf(stderr, "Error: Failed to initialize curl handle.\n");
      free(stdin_content);
      free(stream_data.buffer);
      curl_global_cleanup();
      return 1;
  }

  // --- 5. Prepare JSON Payload using Jansson ---
  root_payload = json_object();
  if (!root_payload) {
      fprintf(stderr, "Error: Failed to create root JSON object.\n");
      goto cleanup; // Use goto for centralized cleanup
  }

  // Add model
  if (json_object_set_new(root_payload, "model", json_string("gpt-4.1-nano")) != 0) {
      fprintf(stderr, "Error: Failed to set model in JSON.\n");
      goto cleanup;
  }

  // Create messages array
  json_t *messages_array = json_array();
  if (!messages_array) {
      fprintf(stderr, "Error: Failed to create messages JSON array.\n");
      goto cleanup;
  }
  if (json_object_set_new(root_payload, "messages", messages_array) != 0) { // messages_array ref is stolen
      fprintf(stderr, "Error: Failed to add messages array to root JSON.\n");
      // Note: messages_array is already attached or failed, root_payload cleanup handles it
      goto cleanup;
  }


  // Create the user message object
  json_t *message_obj = json_object();
   if (!message_obj) {
      fprintf(stderr, "Error: Failed to create message JSON object.\n");
      goto cleanup;
  }
  if (json_object_set_new(message_obj, "role", json_string("user")) != 0) {
       fprintf(stderr, "Error: Failed to set role in message JSON.\n");
       json_decref(message_obj); // Clean up the message object itself
       goto cleanup;
  }
  // Add stdin content (jansson handles escaping)
  if (json_object_set_new(message_obj, "content", json_string(stdin_content)) != 0) {
       fprintf(stderr, "Error: Failed to set content in message JSON.\n");
       json_decref(message_obj); // Clean up the message object itself
       goto cleanup;
  }

  // Append message object to messages array
  if (json_array_append_new(messages_array, message_obj) != 0) { // message_obj ref is stolen
      fprintf(stderr, "Error: Failed to append message to messages array.\n");
      // Note: message_obj is already attached or failed, root_payload cleanup handles it
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

  // --- 6. Set libcurl options ---
  // Set URL
  curl_easy_setopt(curl_handle, CURLOPT_URL, OPENAI_API_URL);

  // Set POST data (using the dynamically generated string)
  curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDS, post_data_dynamic);

  // Set Headers
  headers = curl_slist_append(headers, "Content-Type: application/json");
  headers = curl_slist_append(headers, auth_header); // Add Authorization header
  curl_easy_setopt(curl_handle, CURLOPT_HTTPHEADER, headers);

  // Set callback function to handle stream response
  curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, WriteStreamCallback);
  curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, (void *)&stream_data);

  // Set user agent (good practice)
  curl_easy_setopt(curl_handle, CURLOPT_USERAGENT, "libcurl-agent/1.0");

  // Enable POST request
  curl_easy_setopt(curl_handle, CURLOPT_POST, 1L);

  // Optional: Enable verbose output for debugging curl issues
  // curl_easy_setopt(curl_handle, CURLOPT_VERBOSE, 1L);

  // --- 7. Perform the request ---
  res = curl_easy_perform(curl_handle);

  // --- 8. Check for errors ---
  if(res != CURLE_OK) {
    fprintf(stderr, "\ncurl_easy_perform() failed: %s\n", curl_easy_strerror(res));
  } else {
    // --- 9. Processing is done in the callback ---
    // Ensure a final newline after streaming is complete
    printf("\n");
  }

  // --- 10. Cleanup ---
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
