#!/usr/bin/env python3
"""
PSH - Prompt Shell Helper
A utility to get user input, compose it into a prompt, send to Claude, and execute the result.
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

def main():
    # Set up directories
    input_dir = Path("/tmp/psh/input")
    scripts_dir = Path("/tmp/psh/scripts")
    input_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Create temp file for user input
    with tempfile.NamedTemporaryFile(mode='w', dir=input_dir, delete=False, suffix='.txt') as tmp:
        tmp_path = tmp.name

    try:
        # Get user input
        print("Getting user input...")
        result = subprocess.run(['hnt-input', '-o', tmp_path])
        if result.returncode != 0:
            print("Input cancelled or failed")
            sys.exit(1)

        # Read user input
        with open(tmp_path, 'r') as f:
            user_input = f.read()

        # Read prompt template
        prompt_md_path = Path(__file__).parent / "prompt.md"
        with open(prompt_md_path, 'r') as f:
            prompt_template = f.read()

        # Replace placeholder with user input
        prompt = prompt_template.replace("__INPUT_REQUEST__", user_input)

        # Create new chat
        print("Creating new chat...")
        result = subprocess.run(['hnt-chat', 'new'], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Failed to create chat: {result.stderr}")
            sys.exit(1)
        chat_id = result.stdout.strip()

        # Add system prompt
        print("Adding system prompt...")
        result = subprocess.run(
            ['hnt-chat', 'add', 'system', '-c', chat_id],
            input=prompt,
            text=True
        )
        if result.returncode != 0:
            print("Failed to add system prompt")
            sys.exit(1)

        # Generate response
        print("Generating response from Claude...")
        result = subprocess.run([
            'hnt-chat', 'gen',
            '--model', 'openrouter/anthropic/claude-sonnet-4.5',
            '--include-reasoning',
            '--write',
            '--output-filename',
            '-c', chat_id
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Failed to generate response: {result.stderr}")
            sys.exit(1)

        output_filename = result.stdout.strip()
        output_path = Path(chat_id) / output_filename

        # Read and parse output
        print(f"Parsing output from {output_path}...")
        with open(output_path, 'r') as f:
            content = f.read()

        # Extract solution block
        solution_start = content.find("<solution>")
        solution_end = content.find("</solution>")

        if solution_start == -1 or solution_end == -1:
            print("Error: Could not find <solution> tags in output")
            sys.exit(1)

        solution = content[solution_start + len("<solution>"):solution_end].strip()

        # Save script
        timestamp = int(datetime.now().timestamp())
        script_path = scripts_dir / f"{timestamp}.py"
        with open(script_path, 'w') as f:
            f.write(solution)

        print(f"Saved script to {script_path}")
        print("Executing...")
        print("-" * 60)

        # Execute script
        result = subprocess.run(['uv', 'run', 'python3', str(script_path)])
        sys.exit(result.returncode)

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

if __name__ == '__main__':
    main()
