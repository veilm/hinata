(written by Gemini 2.5 for now. will do docs overhaul later)

# `hnt-agent`

A command-line agent that uses an LLM to interact with a persistent shell to accomplish tasks.

## What it is

`hnt-agent` orchestrates a conversation between a user, a large language model (LLM), and a persistent shell session. It allows you to provide a high-level task, and the agent will have the LLM generate and execute shell commands to achieve it. It's an interactive process where you can guide the agent, approve its actions, and see the results in real-time.

## How it works

The agent follows an interactive loop:

1.  **Instruction**: You start `hnt-agent` with a task, e.g., "analyze disk usage in my home directory and summarize the top 5 largest folders".
2.  **Setup**: The agent starts a persistent shell session (`headlesh`) and a new chat conversation (`hnt-chat`). It populates the conversation with initial context (OS info, current directory) and your task.
3.  **Generation**: It asks the LLM for the next step. The LLM responds with reasoning and shell commands inside a `<hnt-shell>` block.
4.  **Confirmation**: The agent presents the LLM's plan to you for approval.
5.  **Execution**: If you approve, it extracts and runs the shell commands using `hnt-shell-apply`.
6.  **Observation**: The command output is captured and added back to the chat history for the LLM to see.
7.  **Repeat**: The agent asks the LLM for the next step, now with the new information.

This loop continues until the task is complete, or you decide to quit or provide new instructions.

## Usage

To start the agent, run `hnt-agent` and provide your instructions.

#### Via command-line argument:

```bash
hnt-agent -m "Your task description here"
```

#### Via your text editor:

If you run `hnt-agent` without the `-m` flag, it will open your default text editor (`$EDITOR`) to let you write a more detailed instruction.

```bash
hnt-agent
```

### Example Session

```bash
$ hnt-agent -m "What's the current working directory and what's in it?"
```

The agent will start and show the LLM's first response, which includes a plan and the commands to execute.

```
hnt-chat dir: /tmp/hnt-chat-1628793312

──────────────────── LLM Navigator <0> ─────────────────────
I will run `pwd` to find the current directory and `ls -F` to list its contents.

<hnt-shell>
pwd
ls -F
</hnt-shell>
──────────────────────────────────────────────────────────

Proceed to hnt-shell-apply?
 > Yes. Proceed to execute Hinata's shell commands.
   No, and provide new instructions instead.
   No. Abort execution.
```

If you select "Yes", the commands are executed and their output is displayed.

```
────────────────── hnt-shell-apply <0> ───────────────────
/home/user/project

HINATA.md
README.md
hnt-agent.py
──────────────────────────────────────────────────────────

Add hnt-shell-apply output to chat and continue?
 > Yes, and continue to next LLM generation.
   Yes, but provide further instructions.
   No, halt (will not add output to chat).
```

The loop then continues with this new information fed back to the LLM.

### Command-Line Options

| Flag                   | Description                                                                                       |
|------------------------|---------------------------------------------------------------------------------------------------|
| `-m, --message <inst>` | Provide your task instruction directly. If omitted, `$EDITOR` is used.                            |
| `-s, --system <path>`  | Specify a custom system prompt (string or path to a file). Defaults to the standard agent prompt. |
| `--model <name>`       | Specify which LLM to use (passed through to `hnt-chat`).                                          |
| `--no-confirm`         | **Use with caution.** Automatically approves and executes all shell commands from the LLM.          |
| `--debug-unsafe`       | Enable verbose debug logging to `stderr`.                                                         |

## Interactivity

The agent is designed to be interactive:

*   **Confirmation**: Before executing commands, it will ask for your confirmation using `tui-select`. You can approve, provide new instructions, or abort.
*   **Continuation**: After commands are run, you can decide whether to continue to the next LLM step, provide more instructions first, or stop.
*   **Correction**: If the LLM doesn't suggest a command, you will be prompted to either provide new instructions or quit.

## Dependencies

`hnt-agent` is part of the Hinata tool suite and relies on several other components to function:

*   `headlesh`: For managing the persistent shell session.
*   `hnt-chat`: For managing the conversation log and calling the LLM.
*   `hnt-shell-apply`: For safely extracting and running shell commands from the LLM's output.
*   `tui-select`: For interactive prompts in the terminal.
*   An optional syntax highlighter (like `hlmd-st`) for nicer output formatting.

Ensure these tools are in your `PATH`.
