# headlesh

A lightweight daemon for persistent, headless shell sessions. Create named shell sessions that persist in the background and execute commands in them from anywhere.

## Installation

```bash
git clone https://github.com/veilm/hinata
./hinata/install.sh
```

## Quick Start

```bash
# Create a new session
headlesh create my-session

# Execute a command in the session
echo "cd /tmp && pwd" | headlesh exec my-session

# List active sessions
headlesh list

# Terminate a session
headlesh exit my-session
```

## Usage

### Creating Sessions

Start a new background shell session with a unique name:

```bash
headlesh create <session-id>
```

Options:
- `--shell <shell>` - Specify shell to use (default: `bash`)

Example:
```bash
headlesh create dev-env --shell dash
```

### Executing Commands

Run commands in an existing session by piping them through stdin:

```bash
echo "your command here" | headlesh exec <session-id>
```

The command inherits the session's environment and working directory:

```bash
# Set up environment in a session
echo "export API_KEY=secret123" | headlesh exec my-app
echo "cd /opt/myapp" | headlesh exec my-app

# Later commands remember the state
echo "echo \$API_KEY" | headlesh exec my-app  # outputs: secret123
echo "pwd" | headlesh exec my-app             # outputs: /opt/myapp
```

### Managing Sessions

List all active sessions:
```bash
headlesh list
```

Terminate a session:
```bash
headlesh exit <session-id>
```

## How It Works

Each session runs as a background daemon with its own shell process. Commands are passed via named pipes, and the session maintains state (environment variables, working directory) between executions.

Sessions persist until explicitly terminated with `exit` or system restart. Each session is isolated with its own shell instance.

## Notes

- Session IDs must not contain `/` or `..`
- Sessions are stored in `/tmp/headlesh_sessions/`
- Logs are written to `~/.local/share/hinata/headlesh/<session-id>/`
- Exit codes are preserved and returned to the caller
