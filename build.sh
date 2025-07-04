#!/bin/sh -e

cd "$(dirname "$0")"

# offer rustup install if cargo not found
./util/check_cargo_path > /dev/null 2>&1 || ./util/install_rust

# exit if still not found despite attempted install
if ! ./util/check_cargo_path > /dev/null 2>&1
then
	echo "hinata: cargo not found in PATH or CARGO_BIN or HOME/.cargo. exiting"
	exit 1
fi

# should be available now. redundant but easy to follow
cargo=$(./util/check_cargo_path)

echo "hinata: building Rust binaries in release mode..."

cd src
$cargo build --release
