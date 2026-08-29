#!/bin/sh -e

cd ..

echo "hinata: updating all Go dependencies to latest versions..."

# List of all Go modules (excluding research)
modules="hnt-llm hnt-chat llm-pack shell-exec tui-select shared"

for module in $modules; do
    echo "hinata: updating $module dependencies..."
    (
        cd "$module"
        # Update all dependencies to latest
        go get -u ./...
        # Tidy to remove unused dependencies
        go mod tidy
    )
done

echo "hinata: all dependencies updated!"
echo "hinata: you may want to run ./build.sh to rebuild with new dependencies"
