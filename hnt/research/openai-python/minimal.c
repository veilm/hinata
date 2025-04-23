#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h> // Requires libcurl development library
#include <jansson.h>   // Requires jansson development library

// Define the API endpoint
#define OPENAI_API_URL "https://api.openai.com/v1/chat/completions"

// Structure to hold the response data from libcurl
struct MemoryStruct {
  char *memory;
  size_t size;
};

// Callback function for libcurl to write received data into memory
static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, void *userp) {
  size_t realsize = size * nmemb;
  struct MemoryStruct *mem = (struct MemoryStruct *)userp;

  // Reallocate memory buffer to fit the new data chunk
  char *ptr = realloc(mem->memory, mem->size + realsize + 1);
  if(ptr == NULL) {
    /* out of memory! */
    fprintf(stderr, "Error: not enough memory (realloc returned NULL)\n");
    return 0; // Returning 0 signals an error to libcurl
  }

  mem->memory = ptr;
  memcpy(&(mem->memory[mem->size]), contents, realsize);
  mem->size += realsize;
  mem->memory[mem->size] = 0; // Null-terminate the string

  return realsize;
}

int main(void) {
  CURL *curl_handle;
  CURLcode res;
  struct MemoryStruct chunk;
  struct curl_slist *headers = NULL;
  char *api_key = NULL;
  char auth_header[1024]; // Buffer for the Authorization header
  json_t *root_resp = NULL; // Jansson root object for response
  json_error_t error;      // Jansson error structure

  // --- 1. Initialize response memory ---
  chunk.memory = malloc(1);  // Start with 1 byte, will be grown by realloc
  if (chunk.memory == NULL) {
      fprintf(stderr, "Error: Failed to allocate initial memory.\n");
      return 1;
  }
  chunk.size = 0;            // No data received yet

  // --- 2. Get API Key from environment variable ---
  api_key = getenv("OPENAI_API_KEY");
  if (api_key == NULL) {
    fprintf(stderr, "Error: OPENAI_API_KEY environment variable not set.\n");
    free(chunk.memory);
    return 1;
  }
  snprintf(auth_header, sizeof(auth_header), "Authorization: Bearer %s", api_key);

  // --- 3. Initialize libcurl ---
  curl_global_init(CURL_GLOBAL_ALL);
  curl_handle = curl_easy_init();
  if (!curl_handle) {
      fprintf(stderr, "Error: Failed to initialize curl handle.\n");
      free(chunk.memory);
      curl_global_cleanup();
      return 1;
  }

  // --- 4. Prepare JSON Payload ---
  // For simplicity, using a fixed string. For dynamic content, use a JSON library
  // like jansson to build the string or construct it carefully.
  const char *post_data = "{"
                          "  \"model\": \"gpt-4.1-nano\","
                          "  \"messages\": ["
                          "    {"
                          "      \"role\": \"user\","
                          "      \"content\": \"Please output the word `apple` with no other surrounding text or formatting\""
                          "    }"
                          "  ]"
                          "}";

  // --- 5. Set libcurl options ---
  // Set URL
  curl_easy_setopt(curl_handle, CURLOPT_URL, OPENAI_API_URL);

  // Set POST data
  curl_easy_setopt(curl_handle, CURLOPT_POSTFIELDS, post_data);

  // Set Headers
  headers = curl_slist_append(headers, "Content-Type: application/json");
  headers = curl_slist_append(headers, auth_header); // Add Authorization header
  curl_easy_setopt(curl_handle, CURLOPT_HTTPHEADER, headers);

  // Set callback function to handle response
  curl_easy_setopt(curl_handle, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
  curl_easy_setopt(curl_handle, CURLOPT_WRITEDATA, (void *)&chunk);

  // Set user agent (good practice)
  curl_easy_setopt(curl_handle, CURLOPT_USERAGENT, "libcurl-agent/1.0");

  // Enable POST request
  curl_easy_setopt(curl_handle, CURLOPT_POST, 1L);

  // Optional: Enable verbose output for debugging curl issues
  // curl_easy_setopt(curl_handle, CURLOPT_VERBOSE, 1L);

  // --- 6. Perform the request ---
  res = curl_easy_perform(curl_handle);

  // --- 7. Check for errors ---
  if(res != CURLE_OK) {
    fprintf(stderr, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
  } else {
    // --- 8. Parse the JSON response ---
    // Ensure response is null-terminated (done in callback)
    // printf("Received response:\n%s\n", chunk.memory); // Optional: print raw response

    root_resp = json_loads(chunk.memory, 0, &error);
    if (!root_resp) {
        fprintf(stderr, "Error parsing JSON response: on line %d: %s\n", error.line, error.text);
    } else {
        // Navigate the JSON structure: root -> choices (array) -> 0 (object) -> message (object) -> content (string)
        json_t *choices_array = json_object_get(root_resp, "choices");
        if (json_is_array(choices_array) && json_array_size(choices_array) > 0) {
            json_t *first_choice = json_array_get(choices_array, 0);
            if (json_is_object(first_choice)) {
                json_t *message_obj = json_object_get(first_choice, "message");
                if (json_is_object(message_obj)) {
                    json_t *content_str = json_object_get(message_obj, "content");
                    if (json_is_string(content_str)) {
                        // --- 9. Print the extracted content ---
                        printf("%s\n", json_string_value(content_str));
                    } else {
                        fprintf(stderr, "Error: 'content' field is not a string.\n");
                    }
                } else {
                     fprintf(stderr, "Error: 'message' field is not an object.\n");
                }
            } else {
                 fprintf(stderr, "Error: First element in 'choices' is not an object.\n");
            }
        } else {
             fprintf(stderr, "Error: 'choices' field is not a valid array or is empty.\n");
        }
        // Decrement reference count for the root JSON object (frees memory)
        json_decref(root_resp);
    }
  }

  // --- 10. Cleanup ---
  curl_easy_cleanup(curl_handle); // Cleanup curl handle
  free(chunk.memory);             // Free response buffer
  curl_slist_free_all(headers);   // Free headers list
  curl_global_cleanup();          // Global curl cleanup

  return (res == CURLE_OK) ? 0 : 1; // Return 0 on success, 1 on curl error
}
