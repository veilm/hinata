import os
import httpx  # Requires installation: pip install httpx
import json
import sys  # To control exit code

# Define the API endpoint
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def main():
    """
    Makes a request to the OpenAI Chat Completions API using httpx
    and prints the assistant's message content.
    """
    # --- 1. Get API Key from environment variable ---
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        return 1  # Indicate error

    # --- 2. Prepare Headers ---
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # --- 3. Prepare JSON Payload ---
    payload = {
        "model": "gpt-4.1-nano",  # Same model as the previous examples
        "messages": [
            {
                "role": "user",
                "content": "Please output the word `apple` with no other surrounding text or formatting",
            }
        ],
        # Optional parameters can be added here, e.g.:
        # "temperature": 0.7,
        # "max_tokens": 50,
    }

    # --- 4. Send the POST request using httpx ---
    try:
        # print("Sending request to OpenAI API using httpx...")
        # httpx uses a client model, which is good practice for managing connections
        # For a single request, httpx.post() is convenient
        response = httpx.post(
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=30.0,  # httpx recommends float for timeout
        )

        # --- 5. Check for HTTP errors ---
        response.raise_for_status()  # Raises an httpx.HTTPStatusError for bad responses (4xx or 5xx)

        # --- 6. Parse the JSON response ---
        response_json = response.json()
        # print(f"Raw JSON response:\n{json.dumps(response_json, indent=2)}") # Optional: print raw response

        # --- 7. Extract the message content ---
        # Add checks for existence of keys to prevent KeyErrors
        if (
            "choices" in response_json
            and isinstance(response_json.get("choices"), list)
            and len(response_json["choices"]) > 0
        ):
            first_choice = response_json["choices"][0]
            if "message" in first_choice and isinstance(
                first_choice.get("message"), dict
            ):
                message = first_choice["message"]
                if "content" in message:
                    content = message["content"]
                    # --- 8. Print the extracted content ---
                    # print(f"Assistant's response: {content}")
                    print(content)
                    return 0  # Indicate success
                else:
                    print(
                        "Error: 'content' key not found in message object.",
                        file=sys.stderr,
                    )
            else:
                print(
                    "Error: 'message' key not found or not an object in the first choice.",
                    file=sys.stderr,
                )
        else:
            print(
                "Error: 'choices' key not found, not a list, or empty in the response.",
                file=sys.stderr,
            )

    # Catch httpx specific request errors
    except httpx.RequestError as e:
        print(f"Error during API request: {e}", file=sys.stderr)
    # Catch errors during status code checking (4xx, 5xx)
    except httpx.HTTPStatusError as e:
        print(
            f"HTTP error occurred: {e.response.status_code} - {e.response.text}",
            file=sys.stderr,
        )
    # Catch JSON decoding errors
    except json.JSONDecodeError:
        print(
            f"Error: Failed to decode JSON response: {response.text}", file=sys.stderr
        )
    # Catch potential KeyErrors during dictionary access
    except KeyError as e:
        print(f"Error: Missing expected key {e} in the JSON response.", file=sys.stderr)
    # Catch any other unexpected exceptions
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

    return 1  # Indicate error if any exception occurred or keys were missing


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)  # Use sys.exit to properly return the exit code
