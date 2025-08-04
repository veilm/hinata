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
    echo "${BLUE}${BOLD}[hinata]${NC} ${CYAN}$1${NC}"
}

print_success() {
    echo "${GREEN}${BOLD}[✓]${NC} $1"
}

print_warning() {
    echo "${YELLOW}${BOLD}[!]${NC} ${YELLOW}$1${NC}"
}

print_error() {
    echo "${RED}${BOLD}[✗]${NC} ${RED}$1${NC}"
}

print_header() {
    echo "\n${PURPLE}${BOLD}━━━ $1 ━━━${NC}\n"
}

# Main installation starts
echo "${BOLD}${CYAN}"
echo "╔═══════════════════════════════════════╗"
echo "║${NC}    ❄️ hinata installer ${CYAN}| v20250804    ║"
echo "╚═══════════════════════════════════════╝"
echo "${NC}\n"

# Install prompts
# print_header "Installing System Prompts"
prompts_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts
mkdir -p "$prompts_dir"
cp -r prompts/* "$prompts_dir"
print_success "Created directory: ${BOLD}$prompts_dir${NC}"
print_success "Installed agent system prompts"

# Install spinner config
# print_header "Installing Spinner Config"
config_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata
mkdir -p "$config_dir"
if [ -d "cmd/hnt-agent/spinners" ]; then
    cp -r cmd/hnt-agent/spinners "$config_dir/"
    print_success "Installed spinner config to ${BOLD}$config_dir/spinners/${NC}"
else
    print_warning "Spinners directory not found in ./cmd/hnt-agent/"
fi

# Build binaries
print_header "Building Binaries"
./build.sh

# --- Installation ---
INSTALL_DIR="/usr/local/bin/"

# Create bin directory if it doesn't exist
mkdir -p bin

# List of binaries to install (in order similar to Rust version)
bins="hnt-apply llm-pack hnt-edit hnt-llm hnt-chat hnt-agent shell-exec tui-select hnt-web"

print_header "Installing Binaries"
print_info "Target directory: ${BOLD}$INSTALL_DIR${NC}"
echo ""

for bin in $bins; do
    if [ -f "bin/$bin.out" ]; then
        sudo cp "bin/$bin.out" "$INSTALL_DIR/$bin"
        print_success "Installed ${BOLD}$bin${NC} → $INSTALL_DIR"
    else
        print_warning "$bin.out not found in ./bin/"
    fi
done

# Install web assets
print_header "Installing Web Assets"
if [ -d "cmd/hnt-web/static" ]; then
    web="${XDG_DATA_HOME:-$HOME/.local/share}/hinata/web"
    mkdir -p "$web"
    cp -r cmd/hnt-web/static/* "$web/"
    print_success "Installed web assets to ${BOLD}$web${NC}"
else
    print_info "No web assets found to install"
fi

echo "\n${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "${GREEN}${BOLD}Installation Complete!${NC}"
echo "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
