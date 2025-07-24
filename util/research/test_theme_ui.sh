#!/bin/bash

echo "=== Testing hnt-agent Theme UI Components ==="
echo
echo "This script will test the TUI components with both themes."
echo "Please observe the colors and report what you see."
echo
echo "Press Enter to continue..."
read

echo "1. Testing SNOW theme (default - should use RGB colors)"
echo "   Expected:"
echo "   - Select menu: Ice blue background with white text"
echo "   - Prefix ▌ should be sky blue"
echo "   - Textarea header 'Enter your instructions:' should be sky blue"
echo "   - Help text should be lighter blue"
echo
echo "Running: echo 'test' | ../hnt-agent --stdin --theme snow"
echo "Press Ctrl+C after observing the colors..."
echo 'test' | ../hnt-agent --stdin --theme snow

echo
echo "2. Testing ANSI theme"
echo "   Expected:"
echo "   - Select menu: Terminal's blue background (ANSI 4)"
echo "   - Prefix ▌ should be terminal's blue"
echo "   - Textarea header should be terminal's bright blue (ANSI 12)"
echo "   - Help text should be faint/gray"
echo
echo "Running: echo 'test' | ../hnt-agent --stdin --theme ansi"
echo "Press Ctrl+C after observing the colors..."
echo 'test' | ../hnt-agent --stdin --theme ansi

echo
echo "Test complete! Please report what you observed."