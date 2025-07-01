#!/bin/sh -e

cd "$(dirname "$0")"

echo "hinata: building Rust binaries in release mode..."
cargo build --release

# --- Installation ---
TARGET_DIR="./target/release"
INSTALL_DIR="/usr/local/bin/"
bins="headlesh hnt-agent hnt-chat hnt-llm hnt-tui"

cd "$TARGET_DIR"

for bin in $bins
do
	sudo cp "$bin" "$INSTALL_DIR"
	echo "hinata: installed $bin to $INSTALL_DIR"
done
