#!/bin/bash

# Install unicode-check command to user's local bin

echo "Building unicode-check..."
go build -o unicode-check ./cmd/unicode-check

if [ $? -ne 0 ]; then
    echo "Build failed!"
    exit 1
fi

# Create local bin if it doesn't exist
mkdir -p ~/.local/bin

# Copy the binary
cp unicode-check ~/.local/bin/

echo "unicode-check installed to ~/.local/bin/"
echo

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "NOTE: ~/.local/bin is not in your PATH"
    echo "Add this to your shell config (.bashrc, .zshrc, etc.):"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
else
    echo "You can now run: unicode-check"
fi