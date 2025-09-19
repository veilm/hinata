#!/bin/bash

echo "=== Testing DUST Theme Colors ==="
echo
echo "This will display different UI elements with the dust theme."
echo "Everything should be in grayscale (shades of gray)."
echo

# Test with a command that shows stdout and stderr
echo "1. Testing stdout/stderr colors:"
cat <<'EOF' | ./hnt-agent --stdin --theme dust
echo "This is stdout"
echo "This is an error" >&2
exit 1
EOF

echo
echo "2. Testing turn headers and reasoning:"
cat <<'EOF' | ./hnt-agent --stdin --theme dust --no-spinner
# Show me the current date
date
EOF

echo
echo "Theme test complete!"