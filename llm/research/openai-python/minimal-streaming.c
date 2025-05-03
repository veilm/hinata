#include <curl/curl.h>  // Requires libcurl development library
#include <jansson.h>    // Requires jansson development library
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Define the API endpoint
#define OPENAI_API_URL "https://api.openai.com/v1/chat/completions"

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
		fprintf(stderr,
		        "\nError parsing JSON chunk: on line %d: %s\nData: %s\n",
		        error.line, error.text, json_data);
		return;  // Skip this chunk
	}

	// Navigate the JSON structure: root -> choices (array) -> 0 (object) ->
	// delta (object) -> content (string)
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
					fflush(stdout);  // Ensure it's visible immediately
				}
				// We don't treat absence of 'content' as an error here,
				// as some chunks might only contain role or finish_reason.
				json_t *finish_reason =
				    json_object_get(first_choice, "finish_reason");
				if (json_is_string(finish_reason)) {
					// Optionally handle finish reason if needed
					// const char *reason = json_string_value(finish_reason);
					// printf("\n[Finish Reason: %s]\n", reason);
				}
			}
		}
	} else {
		// It's possible to receive chunks without 'choices', e.g., error
		// messages Check for top-level error object
		json_t *error_obj = json_object_get(root_resp, "error");
		if (json_is_object(error_obj)) {
			json_t *message_str = json_object_get(error_obj, "message");
			if (json_is_string(message_str)) {
				fprintf(stderr, "\nAPI Error: %s\n",
				        json_string_value(message_str));
			} else {
				fprintf(stderr,
				        "\nAPI Error: (Could not parse error message)\n");
			}
		}
	}

	json_decref(root_resp);  // Free the parsed JSON object
}

// Callback function for libcurl to handle incoming stream data
static size_t WriteStreamCallback(void *contents, size_t size, size_t nmemb,
                                  void *userp) {
	size_t realsize = size * nmemb;
	struct StreamData *stream_data = (struct StreamData *)userp;
	const char *data_prefix = "data: ";
	size_t prefix_len = strlen(data_prefix);

	// --- 1. Append new data to buffer ---
	size_t needed_size =
	    stream_data->data_len + realsize + 1;  // +1 for null terminator
	if (stream_data->buffer == NULL || needed_size > stream_data->buffer_size) {
		size_t new_size = (stream_data->buffer_size == 0)
		                      ? 1024
		                      : stream_data->buffer_size * 2;
		if (new_size < needed_size)
			new_size = needed_size;  // Ensure enough space

		char *new_buffer = realloc(stream_data->buffer, new_size);
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
	char *message_start = stream_data->buffer;
	char *message_end;
	while ((message_end = strstr(message_start, "\n\n")) != NULL) {
		// Found a potential message boundary
		size_t message_len = message_end - message_start;

		// Process lines within this message block
		char *line_start = message_start;
		char *line_end;
		while (line_start < message_end &&
		       (line_end = memchr(line_start, '\n',
		                          message_end - line_start)) != NULL) {
			// Check if the line starts with "data: "
			if ((line_end - line_start > prefix_len) &&
			    memcmp(line_start, data_prefix, prefix_len) == 0) {
				// Extract the JSON payload part
				char *json_start = line_start + prefix_len;
				size_t json_len = line_end - json_start;

				// Temporarily null-terminate the JSON string for processing
				char original_char = *line_end;
				*line_end = '\0';
				process_sse_data(json_start);
				*line_end = original_char;  // Restore original character
			}
			// Move to the next line
			line_start = line_end + 1;
		}
		// Check the last part of the message block if it didn't end with \n
		if (line_start < message_end) {
			if ((message_end - line_start > prefix_len) &&
			    memcmp(line_start, data_prefix, prefix_len) == 0) {
				char *json_start = line_start + prefix_len;
				size_t json_len = message_end - json_start;
				char original_char = *message_end;
				*message_end = '\0';
				process_sse_data(json_start);
				*message_end = original_char;
			}
		}

		// Move past the processed message (including the "\n\n")
		message_start = message_end + 2;  // Move past "\n\n"
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

int main(void) {
	CURL *curl_handle;
	CURLcode res;
	struct StreamData stream_data = {NULL, 0,
	                                 0};  // Initialize stream data struct
	struct curl_slist *headers = NULL;
	char *api_key = NULL;
	char auth_header[1024];  // Buffer for the Authorization header
	// Removed unused jansson variables from main scope
	// json_t *root_resp = NULL;
	// json_error_t error;

	// --- 1. Initialize stream data buffer ---
	// Initialization moved to struct definition above.

	// --- 2. Get API Key from environment variable ---
	api_key = getenv("OPENAI_API_KEY");
	if (api_key == NULL) {
		fprintf(stderr,
		        "Error: OPENAI_API_KEY environment variable not set.\n");
		// No chunk.memory to free here yet
		return 1;
	}
	snprintf(auth_header, sizeof(auth_header), "Authorization: Bearer %s",
	         api_key);

	// --- 3. Initialize libcurl ---
	curl_global_init(CURL_GLOBAL_ALL);
	curl_handle = curl_easy_init();
	if (!curl_handle) {
		fprintf(stderr, "Error: Failed to initialize curl handle.\n");
		// No chunk.memory to free here yet
		curl_global_cleanup();
		return 1;
	}

	// --- 4. Prepare JSON Payload ---
	// For simplicity, using a fixed string. For dynamic content, use a JSON
	// library like jansson to build the string or construct it carefully.
	const char *post_data =
	    "{"
	    "  \"model\": \"gpt-4o-mini\","
	    "  \"messages\": ["
	    "    {"
	    "      \"role\": \"user\","
	    "      \"content\": \"output the number 1. no other surrounding "
	    "formatting\""
	    "    }"
	    "  ],"
	    "  \"stream\": true"  // Add stream parameter
	    "}";

	// --- 5. Set libcurl options ---
	// Set URL
	curl_easy_setopt(curl_handle, CURLOPT_URL, OPENAI_API_URL);

	// Set POST data
	curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDS, post_data);

	// Set Headers
	headers = curl_slist_append(headers, "Content-Type: application/json");
	headers =
	    curl_slist_append(headers, auth_header);  // Add Authorization header
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

	// --- 6. Perform the request ---
	res = curl_easy_perform(curl_handle);

	// --- 7. Check for errors ---
	if (res != CURLE_OK) {
		fprintf(stderr, "\ncurl_easy_perform() failed: %s\n",
		        curl_easy_strerror(res));
	} else {
		// --- 8. Processing is done in the callback ---
		// Ensure a final newline after streaming is complete
		printf("\n");
	}

	// --- 10. Cleanup ---
	curl_easy_cleanup(curl_handle);  // Cleanup curl handle
	free(stream_data.buffer);        // Free stream buffer
	curl_slist_free_all(headers);    // Free headers list
	curl_global_cleanup();           // Global curl cleanup

	// Return 0 on success (request sent without curl error), 1 otherwise.
	// Note: API-level errors might have been printed during the stream.
	return (res == CURLE_OK) ? 0 : 1;
}
