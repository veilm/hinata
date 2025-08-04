# hnt-edit

`hnt-edit` is a command-line tool that empowers you to edit source code files using a Large Language Model (LLM). You provide the files and a set of instructions in natural language, and `hnt-edit` intelligently generates and applies the necessary changes.

## How It Works

The tool follows a straightforward process to integrate LLM capabilities into your file editing workflow:

1.  **File Packing**: `hnt-edit` takes the source files you specify and "packs" them into a single context block for the LLM. It can even create new files on the fly if you point it to a path that doesn't exist.
2.  **Prompt Construction**: It combines the packed source code with your instructions (from the `-m` flag) and a configurable system prompt.
3.  **LLM Interaction**: The entire package is sent to the configured LLM. `hnt-edit` then streams the response back to your terminal, showing you the model's reasoning process in real-time, followed by the proposed code modifications.
4.  **Applying Changes**: The LLM's output, containing the code edits, is passed to an internal companion tool (`hnt-apply`) that intelligently parses and applies the changes to your local files.
5.  **Conversation History**: Every edit session is saved in a `hnt-chat` directory. This allows you to resume a failed or incomplete edit, providing further clarification to the agent without starting over.

## Usage

### Basic Example

To refactor a function across multiple files, you can run:

```bash
hnt-edit -m "Refactor the getUser function to handle database errors more gracefully" src/api.go src/database.go
```

### Creating a New File

If you specify a file that does not exist, `hnt-edit` will create it for you.

```bash
hnt-edit -m "Create a simple Python Flask server in a file named app.py" app.py
```

## Key Features & Flags

- **Natural Language Instructions**: Edit code by describing the changes you want.
- **Multi-File Context**: The LLM can reason about and edit multiple files in a single session.
- **On-the-Fly File Creation**: Automatically creates files that are part of the prompt but don't exist yet.
- **Real-time Streaming**: Watch the LLM's reasoning and code generation as it happens.
- **Session Resumption**: Use the `--continue-dir` flag with a `hnt-chat` conversation path to resume a previous session and provide new instructions.
- **Customizable Prompts**: Use the `-s, --system` flag to provide a custom system prompt, either as a string or a file path.
- **Model Selection**: Specify an LLM with the `--model` flag. This can also be configured via `HINATA_EDIT_MODEL` or `HINATA_MODEL` environment variables.

### Important Flags

- `hnt-edit [source files...]`: The file(s) to be edited.
- `-m, --message "..."`: The user instructions for the edit.
- `--continue-dir <path>`: Path to an existing `hnt-chat` conversation directory to continue from a previous edit.
- `--model <model_name>`: Specify the LLM to use (e.g., `openrouter/google/gemini-2.5-pro`).
