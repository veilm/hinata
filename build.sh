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
    echo "${BLUE}${BOLD}[BUILD]${NC} ${CYAN}$1${NC}"
}

print_success() {
    echo "${GREEN}${BOLD}[✓]${NC} $1"
}

print_error() {
    echo "${RED}${BOLD}[✗]${NC} ${RED}$1${NC}"
}

print_header() {
    echo "\n${PURPLE}${BOLD}━━━ $1 ━━━${NC}\n"
}

# Check if go is available
# print_header "Checking Prerequisites"
if ! command -v go > /dev/null 2>&1; then
    print_error "Go not found in PATH"
    echo "${RED}Please install Go from ${BOLD}https://go.dev${NC}"
    exit 1
fi

GO_VERSION=$(go version | awk '{print $3}')
print_success "Found ${BOLD}$GO_VERSION${NC}"

# print_header "Building Hinata Binaries"

# List of all Go binaries to build
bins="hnt-llm hnt-chat hnt-apply llm-pack hnt-edit hnt-agent shell-exec tui-select hnt-web"

# Count total binaries
total=$(echo $bins | wc -w)
current=0

# Download dependencies for the main module
# print_info "Downloading dependencies..."
go mod download
print_success "Dependencies downloaded"

# Create bin directory if it doesn't exist
mkdir -p bin

print_header "Compiling Binaries"

# Build each binary with .out extension
for bin in $bins; do
    current=$((current + 1))
    # echo "${WHITE}${BOLD}[$current/$total]${NC} ${YELLOW}⚙${NC} Building ${BOLD}$bin${NC}..."
    echo "${WHITE}${BOLD}[$current/$total]${NC} ${YELLOW}❄️${NC} Building ${BOLD}$bin${NC}..."
    
    if go build -o "bin/$bin.out" "./cmd/$bin/cmd/$bin" 2>/dev/null; then
        # print_success "Built ${BOLD}$bin${NC} successfully"
        true
    else
        print_error "Failed to build $bin"
        exit 1
    fi
done

echo
# echo "\n${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "${GREEN}${BOLD}Build Complete!${NC}"
echo "${GREEN}All binaries built successfully in ${BOLD}./bin/${NC}"
# echo "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
