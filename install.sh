#!/bin/sh -e

cd "$(dirname "$0")"

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    printf "${BLUE}${BOLD}[hinata]${NC} ${CYAN}%s${NC}\n" "$1"
}

print_success() {
    printf "${GREEN}${BOLD}[✓]${NC} %s\n" "$1"
}

print_warning() {
    printf "${YELLOW}${BOLD}[!]${NC} ${YELLOW}%s${NC}\n" "$1"
}

print_error() {
    printf "${RED}${BOLD}[✗]${NC} ${RED}%s${NC}\n" "$1"
}

print_header() {
    printf "\n${PURPLE}${BOLD}━━━ %s ━━━${NC}\n\n" "$1"
}

# Main installation starts
printf "${BOLD}${CYAN}"
printf "╔═══════════════════════════════════════╗\n"
printf "║${NC}    ❄️ hinata installer ${CYAN}| v20250804    ║\n"
printf "╚═══════════════════════════════════════╝\n"
printf "${NC}\n\n"

# Install prompts
# print_header "Installing System Prompts"
prompts_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts
mkdir -p "$prompts_dir"
cp -r prompts/* "$prompts_dir"
printf "${GREEN}${BOLD}[✓]${NC} Created directory: ${BOLD}%s${NC}\n" "$prompts_dir"
printf "${GREEN}${BOLD}[✓]${NC} Installed agent system prompts\n"

# Install spinner config
# print_header "Installing Spinner Config"
config_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata
mkdir -p "$config_dir"
if [ -d "cmd/hnt-agent/spinners" ]; then
    cp -r cmd/hnt-agent/spinners "$config_dir/"
    printf "${GREEN}${BOLD}[✓]${NC} Installed spinner config to ${BOLD}%s/spinners/${NC}\n" "$config_dir"
else
    printf "${YELLOW}${BOLD}[!]${NC} ${YELLOW}Spinners directory not found in ./cmd/hnt-agent/${NC}\n"
fi

# Build binaries
print_header "Building Binaries"
./build.sh

# --- Installation ---
INSTALL_DIR="/usr/local/bin/"

# Create bin directory if it doesn't exist
mkdir -p bin

# List of binaries to install (in order similar to Rust version)
bins="hnt-apply llm-pack hnt-edit hnt-llm hnt-chat hnt-agent hnt-input shell-exec tui-select hnt-web"

print_header "Installing Binaries"
printf "${BLUE}${BOLD}[hinata]${NC} ${CYAN}Target directory: ${BOLD}%s${NC}${CYAN}${NC}\n" "$INSTALL_DIR"
printf "\n"

for bin in $bins; do
    if [ -f "bin/$bin.out" ]; then
        sudo cp "bin/$bin.out" "$INSTALL_DIR/$bin"
        printf "${GREEN}${BOLD}[✓]${NC} Installed ${BOLD}%s${NC} → %s\n" "$bin" "$INSTALL_DIR"
    else
        printf "${YELLOW}${BOLD}[!]${NC} ${YELLOW}%s.out not found in ./bin/${NC}\n" "$bin"
    fi
done

# Install web assets
print_header "Installing Web Assets"
if [ -d "cmd/hnt-web/static" ]; then
    web="${XDG_DATA_HOME:-$HOME/.local/share}/hinata/web"
    mkdir -p "$web"
    cp -r cmd/hnt-web/static/* "$web/"
    printf "${GREEN}${BOLD}[✓]${NC} Installed web assets to ${BOLD}%s${NC}\n" "$web"
else
    printf "${BLUE}${BOLD}[hinata]${NC} ${CYAN}No web assets found to install${NC}\n"
fi

printf "\n${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${GREEN}${BOLD}Installation Complete!${NC}\n"
printf "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"
