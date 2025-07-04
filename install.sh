#!/bin/sh -e

cd "$(dirname "$0")"

prompts_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts
mkdir -p "$prompts_dir"
cp prompts/* "$prompts_dir"
echo "hinata: created $prompts_dir"
echo "hinata: installed agent system prompts"

./build.sh
cd src

# --- Installation ---
TARGET_DIR="./target/release"
INSTALL_DIR="/usr/local/bin/"
# bins="headlesh hnt-agent hnt-chat hnt-llm hnt-tui"
bins="hnt-apply llm-pack hnt-tui hnt-edit hnt-llm hnt-chat headlesh hnt-agent"

cd "$TARGET_DIR"

for bin in $bins
do
	sudo cp "$bin" "$INSTALL_DIR"
	echo "hinata: installed $bin to $INSTALL_DIR"
done
