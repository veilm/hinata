#!/bin/sh -e

cd "$(dirname "$0")"

# Install prompts
prompts_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts
mkdir -p "$prompts_dir"
cp -r prompts/* "$prompts_dir"
echo "hinata: created $prompts_dir"
echo "hinata: installed agent system prompts"

# Install spinner config
config_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata
mkdir -p "$config_dir"
if [ -d "cmd/hnt-agent/spinners" ]; then
    cp -r cmd/hnt-agent/spinners "$config_dir/"
    echo "hinata: installed spinner config to $config_dir/spinners/"
else
    echo "hinata: warning: spinners directory not found in ./cmd/hnt-agent/"
fi

# Build binaries
./build.sh

# --- Installation ---
INSTALL_DIR="/usr/local/bin/"

# Create bin directory if it doesn't exist
mkdir -p bin

# List of binaries to install (in order similar to Rust version)
bins="hnt-apply llm-pack hnt-edit hnt-llm hnt-chat hnt-agent shell-exec tui-select hnt-web"

echo "hinata: installing binaries to $INSTALL_DIR..."

for bin in $bins; do
    if [ -f "bin/$bin.out" ]; then
        sudo cp "bin/$bin.out" "$INSTALL_DIR/$bin"
        echo "hinata: installed $bin to $INSTALL_DIR"
    else
        echo "hinata: warning: $bin.out not found in ./bin/"
    fi
done

# Install web assets
if [ -d "cmd/hnt-web/static" ]; then
    web="${XDG_DATA_HOME:-$HOME/.local/share}/hinata/web"
    mkdir -p "$web"
    cp -r cmd/hnt-web/static/* "$web/"
    echo "hinata: installed web assets to $web"
fi
