#!/bin/bash

# Test script for V2 streaming refactor

echo "Building hnt-agent..."
go build -o /tmp/hnt-agent-v2 ./cmd/hnt-agent/cmd/hnt-agent || exit 1

echo ""
echo "Testing with V2 streaming (default):"
echo "====================================="
echo "echo 'Hello from V2 streaming'" | /tmp/hnt-agent-v2 -m "Say hello back" --no-confirm --auto-exit

echo ""
echo "Testing with old streaming:"
echo "============================"
echo "echo 'Hello from old streaming'" | /tmp/hnt-agent-v2 -m "Say hello back" --no-confirm --auto-exit --v2-streaming=false

echo ""
echo "Test complete!"