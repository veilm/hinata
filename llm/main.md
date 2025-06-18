# main.c – quick developer reference

Command-line utility “hnt-llm” (`VERSION_STRING`) that turns stdin + CLI options
into an OpenAI-compatible streaming chat request and prints the streamed reply.

---

## High-level flow

1. **Parse CLI options**  
   `-m/--model`, `-s/--system`, `--include-reasoning`, `--debug-unsafe`, `-V`.
   Model string is `provider/model_name`; provider picks URL + env-var key.

2. **Read stdin**  
   `read_stdin_all()` loads entire stdin into memory.

3. **Extract XML-wrapped messages**  
   Recognises `<hnt-system>`,`<hnt-user>`,`<hnt-assistant>` blocks.  
   • Builds a linked list of `Message{role,content}` via `add_message_to_list()`.  
   • Removes those ranges from the raw prompt and appends remaining text
     (trimmed) as a final `user` message.

4. **Unescape content**  
   For every message call external helper `hnt-escape -u` through
   `unescape_message_content()`.

5. **Build JSON payload (Jansson)**  
   `{ model, messages[], stream:true }`

6. **Send request (libcurl)**  
   • URL chosen from provider table.  
   • `Authorization: Bearer $ENV_KEY` header.  
   • POST with JSON; streaming callback `WriteStreamCallback()` handles SSE.

7. **Stream processing**  
   `WriteStreamCallback()` buffers SSE chunks, extracts `data: ` lines and
   delegates each JSON payload to `process_sse_data()`.  
   `process_sse_data()` prints tokens, optionally wrapping the model’s
   “reasoning” stream in `<think>...</think>` tags when
   `--include-reasoning` is active.  
   It also detects error payloads and sets `api_error_occurred`.

8. **Cleanup & exit code**  
   Frees all allocations, closes curl, returns 0 on success, 1 otherwise.

---

## Key data structures

| struct | purpose |
|--------|---------|
| `Message`      | singly-linked list node holding `role` + `content`. |
| `XmlRange`     | start/end pointers used to strip XML blocks. |
| `enum OutputPhase` | Init / Thinking / Responding phases for reasoning mode. |
| `StreamData`   | Buffer + state used by curl stream callback. |

---

## Important helpers

• `trim_whitespace()` – in-place trim.  
• `messages_to_json_array()` – convert linked list to Jansson array.  
• `create_message()/free_message_list()` – manage message nodes.

---

## Error / debug aids

* `debug_mode` prints verbose diagnostics and raw data dumps.  
* SSE parser prints hex dumps & separator detection when debug enabled.  
* Global `api_error_occurred` suppresses extra newline on API failure.

---

## Build/runtime deps

`libcurl`, `jansson`, `hnt-escape` binary in `PATH`, POSIX environment,
provider API keys in env variables (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`,
`DEEPSEEK_API_KEY`, `GEMINI_API_KEY`).