#!/bin/bash
# Test script for tui-select

echo "Testing tui-select with various options..."
echo

# Test 1: Basic usage
echo "Test 1: Basic selection"
echo -e "Apple\nBanana\nCherry\nDate\nElderberry" | ./tui-select
echo

# Test 2: With custom height
echo "Test 2: Limited height (3 items visible)"
echo -e "Item 1\nItem 2\nItem 3\nItem 4\nItem 5\nItem 6\nItem 7" | ./tui-select --height 3
echo

# Test 3: With color
echo "Test 3: With green highlight"
echo -e "Red text\nGreen highlight\nBlue text" | ./tui-select --color 2
echo

# Test 4: With custom prefix
echo "Test 4: Custom prefix"
echo -e "First\nSecond\nThird" | ./tui-select --prefix "→ "
echo

# Test 5: Long list
echo "Test 5: Long list with scrolling"
seq 1 20 | ./tui-select --height 5