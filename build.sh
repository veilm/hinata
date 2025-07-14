#!/bin/sh -e

cd "$(dirname "$0")"

# Check if go is available
if ! command -v go > /dev/null 2>&1; then
    echo "hinata: go not found in PATH. Please install Go from https://go.dev"
    exit 1
fi

echo "hinata: building binaries..."

# List of all Go binaries to build
bins="hnt-llm hnt-chat hnt-apply llm-pack hnt-edit hnt-agent shell-exec tui-select hnt-web"

# Download dependencies for each module
echo "hinata: downloading dependencies..."
for bin in $bins; do
    echo "hinata: downloading dependencies for $bin..."
    (cd "$bin" && go mod download)
done

# Build each binary with .out extension
for bin in $bins; do
    echo "hinata: building $bin..."
    (cd "$bin" && go build -o "../bin/$bin.out" "./cmd/$bin")
done

echo "hinata: all binaries built successfully in ./bin/"
