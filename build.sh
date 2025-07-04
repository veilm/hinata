#!/bin/sh -e

cd "$(dirname "$0")"
. ./util/install_rust

cd src

echo "hinata: building Rust binaries in release mode..."
${CARGO:-cargo} build --release
