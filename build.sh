#!/bin/sh -e

cd "$(dirname "$0")"

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    printf "${BLUE}${BOLD}[BUILD]${NC} ${CYAN}%s${NC}\n" "$1"
}

print_success() {
    printf "${GREEN}${BOLD}[✓]${NC} %s\n" "$1"
}

print_error() {
    printf "${RED}${BOLD}[✗]${NC} ${RED}%s${NC}\n" "$1"
}

print_header() {
    printf "\n${PURPLE}${BOLD}━━━ %s ━━━${NC}\n\n" "$1"
}

# Check if go is available
# print_header "Checking Prerequisites"
if ! command -v go > /dev/null 2>&1; then
    print_error "Go not found in PATH"
    printf "${RED}Please install Go from ${BOLD}https://go.dev${NC}\n"
    exit 1
fi

GO_VERSION=$(go version | awk '{print $3}')
printf "${GREEN}${BOLD}[✓]${NC} Found ${BOLD}%s${NC}\n" "$GO_VERSION"

# print_header "Building Hinata Binaries"

# List of all Go binaries to build
bins="hnt-llm hnt-chat hnt-apply llm-pack hnt-edit hnt-agent shell-exec tui-select hnt-web"

# Count total binaries
total=$(echo $bins | wc -w | tr -d ' ')
current=0

# Download dependencies for the main module
# print_info "Downloading dependencies..."
go mod download
printf "${GREEN}${BOLD}[✓]${NC} Dependencies downloaded\n"

# Create bin directory if it doesn't exist
mkdir -p bin

print_header "Compiling Binaries"

# Build each binary with .out extension
for bin in $bins; do
    current=$((current + 1))
    # printf "${WHITE}${BOLD}[$current/$total]${NC} ${YELLOW}⚙${NC} Building ${BOLD}%s${NC}...\n" "$bin"
    printf "${WHITE}${BOLD}[$current/$total]${NC} ${YELLOW}❄️${NC} Building ${BOLD}%s${NC}...\n" "$bin"
    
    if go build -o "bin/$bin.out" "./cmd/$bin/cmd/$bin" 2>/dev/null; then
        # print_success "Built ${BOLD}$bin${NC} successfully"
        true
    else
        printf "${RED}${BOLD}[✗]${NC} ${RED}Failed to build %s${NC}\n" "$bin"
        exit 1
    fi
done

printf "\n"
# printf "\n${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
printf "${GREEN}${BOLD}Build Complete!${NC}\n"
printf "${GREEN}All binaries built successfully in ${BOLD}./bin/${NC}\n"
# printf "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"
