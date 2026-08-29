#!/bin/sh

set -e

script_dir=$(CDPATH= cd "$(dirname "$0")" 2>/dev/null && pwd || true)
if [ ! -f "$script_dir/go.mod" ] || ! grep -q '^module github.com/veilm/hinata$' "$script_dir/go.mod"
then
    if ! command -v git > /dev/null 2>&1
    then
        printf 'hinata: git is required to install from GitHub\n' >&2
        exit 1
    fi

    hinata_bootstrap_dir=$(mktemp -d "${TMPDIR:-/tmp}/hinata-install.XXXXXX")
    cleanup_bootstrap() {
        if [ -n "$hinata_bootstrap_dir" ] && [ -d "$hinata_bootstrap_dir" ]
        then
            rm -rf -- "$hinata_bootstrap_dir"
        fi
    }
    trap cleanup_bootstrap 0
    trap 'exit 1' HUP INT TERM

    printf 'hinata: cloning veilm/hinata...\n'
    git clone --depth 1 https://github.com/veilm/hinata "$hinata_bootstrap_dir/repo"
    "$hinata_bootstrap_dir/repo/install.sh"
    exit
fi

cd "$script_dir"

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
printf "║${NC}    ❄️ hinata installer ${CYAN}| v1788028365   ║\n"
printf "╚═══════════════════════════════════════╝\n"
printf "${NC}\n\n"

# Install prompts
# print_header "Installing System Prompts"
prompts_dir=${XDG_CONFIG_HOME:-$HOME/.config}/hinata/prompts
mkdir -p "$prompts_dir"
cp -r prompts/* "$prompts_dir"
printf "${GREEN}${BOLD}[✓]${NC} Created directory: ${BOLD}%s${NC}\n" "$prompts_dir"
printf "${GREEN}${BOLD}[✓]${NC} Installed system prompts\n"

# Build binaries
print_header "Building Binaries"
./build.sh

# --- Installation ---
INSTALL_DIR="/usr/local/bin/"

# Create bin directory if it doesn't exist
mkdir -p bin

# List of binaries to install (in order similar to Rust version)
bins="llm-pack hnt-llm hnt-chat hnt-input shell-exec tui-select hnt-web"

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
