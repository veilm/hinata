#!/bin/sh -e

cd "$(dirname "$0")"

echo "hinata: building Rust binaries in release mode..."
cargo build --release
