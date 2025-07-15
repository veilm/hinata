#!/usr/bin/env bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Installing hnt-web...${NC}"

# Build the binary
echo -e "${YELLOW}Building hnt-web...${NC}"
go build -o hnt-web ./cmd/hnt-web

# Install the binary
echo -e "${YELLOW}Installing binary to /usr/local/bin...${NC}"
sudo cp hnt-web /usr/local/bin/

# Clean up build artifact
rm hnt-web

# Install web assets
if [ -d "static" ]; then
    web="${XDG_DATA_HOME:-$HOME/.local/share}/hinata/web"
    echo -e "${YELLOW}Installing web assets to ${web}...${NC}"
    mkdir -p "$web"
    cp -r static/* "$web/"
    echo -e "${GREEN}Installed web assets to $web${NC}"
fi

echo -e "${GREEN}hnt-web installed successfully!${NC}"
echo -e "${GREEN}You can now run: hnt-web${NC}"