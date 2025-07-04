#!/bin/sh -e

cd "$(dirname "$0")"
cd src

echo "hinata: building Rust binaries in release mode..."
cargo build --release
