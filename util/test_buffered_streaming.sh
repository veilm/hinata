#!/bin/bash

# Test script for the new buffered streaming feature

echo "Testing hnt-agent with buffered streaming enabled..."
echo ""

# Test with buffered streaming ON
echo "=== WITH BUFFERED STREAMING ==="
./cmd/hnt-agent/hnt-agent --buffered-streaming -m "Tell me a short joke" --auto-exit

echo ""
echo "=== WITHOUT BUFFERED STREAMING (default) ==="
./cmd/hnt-agent/hnt-agent -m "Tell me a short joke" --auto-exit

echo ""
echo "Test complete!"