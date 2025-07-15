package terminal

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// EnsureCompatibleTerm checks if the current TERM is recognized and falls back to xterm-256color if not
func EnsureCompatibleTerm() {
	// Check if we're in an SSH session
	if isSSHSession() {
		// Force compatible terminal settings for SSH sessions
		os.Setenv("TERM", "xterm-256color")
		os.Setenv("COLORTERM", "truecolor")
		return
	}

	term := os.Getenv("TERM")
	if term == "" {
		return
	}

	// Check if terminfo exists for this terminal
	if !hasTerminfo(term) {
		fmt.Fprintf(os.Stderr, "hinata: warning: terminal '%s' not recognized, using xterm-256color\n", term)
		os.Setenv("TERM", "xterm-256color")

		// Also set COLORTERM to help with color detection
		if os.Getenv("COLORTERM") == "" {
			os.Setenv("COLORTERM", "truecolor")
		}
	}
}

// isSSHSession checks if we're currently in an SSH session
func isSSHSession() bool {
	// SSH_TTY is set when the session has a TTY allocated
	if os.Getenv("SSH_TTY") != "" {
		return true
	}
	// SSH_CONNECTION contains client and server IP/port info
	if os.Getenv("SSH_CONNECTION") != "" {
		return true
	}
	// SSH_CLIENT contains client IP/port info (older SSH versions)
	if os.Getenv("SSH_CLIENT") != "" {
		return true
	}
	return false
}

func hasTerminfo(term string) bool {
	// First try using infocmp if available
	if _, err := exec.LookPath("infocmp"); err == nil {
		cmd := exec.Command("infocmp", term)
		if err := cmd.Run(); err == nil {
			return true
		}
	}

	// Fallback: check common terminfo directories
	terminfoDirs := []string{
		"/usr/share/terminfo",
		"/etc/terminfo",
		"/lib/terminfo",
		"/usr/lib/terminfo",
		"/usr/local/share/terminfo",
		"/usr/local/lib/terminfo",
	}

	// Also check TERMINFO environment variable
	if customDir := os.Getenv("TERMINFO"); customDir != "" {
		terminfoDirs = append([]string{customDir}, terminfoDirs...)
	}

	// Also check user's terminfo directory
	if home := os.Getenv("HOME"); home != "" {
		terminfoDirs = append(terminfoDirs, home+"/.terminfo")
	}

	// terminfo files are stored in subdirectories by first letter
	firstLetter := strings.ToLower(term[:1])

	for _, dir := range terminfoDirs {
		// Check both first-letter subdirectory and hex subdirectory
		paths := []string{
			fmt.Sprintf("%s/%s/%s", dir, firstLetter, term),
			fmt.Sprintf("%s/%x/%s", dir, firstLetter[0], term),
		}

		for _, path := range paths {
			if _, err := os.Stat(path); err == nil {
				return true
			}
		}
	}

	return false
}
