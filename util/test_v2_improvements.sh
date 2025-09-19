#!/bin/bash

# Test script for V2 streaming improvements

echo "Building hnt-agent with all improvements..."
go build -o /tmp/hnt-agent-v2 ./cmd/hnt-agent/cmd/hnt-agent || exit 1

echo ""
echo "Test 1: Basic streaming test"
echo "============================="
/tmp/hnt-agent-v2 -m "Write a haiku about code refactoring" --no-confirm --auto-exit

echo ""
echo "Test 2: Shell command with proper synchronization"
echo "=================================================="
/tmp/hnt-agent-v2 -m "Show me the current date and time using the date command" --no-confirm --auto-exit

echo ""
echo "Test 3: Testing with old streaming for comparison"
echo "=================================================="
/tmp/hnt-agent-v2 -m "Say hello" --no-confirm --auto-exit --v2-streaming=false

echo ""
echo "All tests complete!"