#!/bin/bash
set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Ensure hnt-web.py exists in the script's directory
HNT_WEB_PY="$SCRIPT_DIR/hnt-web.py"
if [ ! -f "$HNT_WEB_PY" ]; then
    echo "Error: hnt-web.py not found in $SCRIPT_DIR"
    exit 1
fi

# Destination for the executable
DEST_BIN="/usr/local/bin/hnt-web"

echo "Copying hnt-web.py to $DEST_BIN..."
# Use sudo if not running as root, but check if we can write first to avoid unnecessary sudo prompt if already root
if [ "$(id -u)" -ne 0 ] && [ ! -w "$(dirname "$DEST_BIN")" ]; then
    SUDO_CMD="sudo"
else
    SUDO_CMD=""
fi

$SUDO_CMD cp "$HNT_WEB_PY" "$DEST_BIN"
$SUDO_CMD chmod +x "$DEST_BIN"
echo "hnt-web copied and made executable."

# Determine web assets directory
# Use XDG_DATA_HOME if set, otherwise default to $HOME/.local/share
WEB_ASSET_PARENT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
WEB_ASSET_DIR="$WEB_ASSET_PARENT_DIR/hinata/web"

echo "Ensuring web asset directory exists: $WEB_ASSET_DIR..."
mkdir -p "$WEB_ASSET_DIR"
mkdir -p "$WEB_ASSET_DIR/css"
mkdir -p "$WEB_ASSET_DIR/js"

# Source static files directory
STATIC_SRC_DIR="$SCRIPT_DIR/static"
if [ ! -d "$STATIC_SRC_DIR" ]; then
    echo "Error: Source static directory $STATIC_SRC_DIR not found."
    exit 1
fi

echo "Copying static assets to $WEB_ASSET_DIR..."

# Copy HTML files
if [ -f "$STATIC_SRC_DIR/index.html" ]; then
    cp "$STATIC_SRC_DIR/index.html" "$WEB_ASSET_DIR/index.html"
else
    echo "Warning: index.html not found in $STATIC_SRC_DIR"
fi

if [ -f "$STATIC_SRC_DIR/conversation.html" ]; then
    cp "$STATIC_SRC_DIR/conversation.html" "$WEB_ASSET_DIR/conversation.html"
else
    echo "Warning: conversation.html not found in $STATIC_SRC_DIR"
fi

# Copy CSS
if [ -f "$STATIC_SRC_DIR/css/style.css" ]; then
    cp "$STATIC_SRC_DIR/css/style.css" "$WEB_ASSET_DIR/css/style.css"
else
    echo "Warning: css/style.css not found in $STATIC_SRC_DIR"
fi

# Copy JS
if [ -f "$STATIC_SRC_DIR/js/script.js" ]; then
    cp "$STATIC_SRC_DIR/js/script.js" "$WEB_ASSET_DIR/js/script.js"
else
    echo "Warning: js/script.js not found in $STATIC_SRC_DIR"
fi

echo "Build process completed."
echo "hnt-web server should now be run, e.g., by executing: $DEST_BIN"
echo "It will serve static files from: $WEB_ASSET_DIR"
echo "If you are not running as root, you might have needed to enter your password for copying to $DEST_BIN."