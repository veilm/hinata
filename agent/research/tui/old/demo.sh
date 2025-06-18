#!/bin/bash

echo "=== TUI Demo ==="
echo "This demonstrates how to create a TUI that reserves lines"
echo "without clearing the entire terminal (like fzf does)"
echo ""
echo "We have created two examples:"
echo ""
echo "1. minimal_tui.py - Simple 5-line animation"
echo "2. simple_tui.py - More complex 10-line demo with colors"
echo ""
echo "Press any key to run the minimal example (Ctrl+C to stop)..."
read -n 1

python3 minimal_tui.py

echo ""
echo "Press any key to run the full example (Ctrl+C to stop)..."
read -n 1

python3 simple_tui.py
