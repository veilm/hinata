package spinner

import (
	"os"
	"runtime"
	"strings"
)

type UnicodeSupport int

const (
	UnicodeNone UnicodeSupport = iota  // ASCII only
	UnicodeBasic                        // Box drawing characters
	UnicodeFull                         // Complex symbols, emoji
)

// DetectUnicodeSupport determines the level of Unicode support in the current terminal
func DetectUnicodeSupport() UnicodeSupport {
	// Check if NO_UNICODE environment variable is set (user override)
	if os.Getenv("NO_UNICODE") != "" {
		return UnicodeNone
	}

	// Platform-specific checks
	switch runtime.GOOS {
	case "windows":
		// Windows Terminal supports full Unicode
		if os.Getenv("WT_SESSION") != "" {
			return UnicodeFull
		}
		// ConEmu also has good support
		if os.Getenv("ConEmuPID") != "" {
			return UnicodeFull
		}
		// Legacy console has limited support
		return UnicodeNone

	case "darwin":
		// macOS Terminal.app and iTerm2 have excellent support
		return UnicodeFull

	default: // Linux and others
		// Check locale settings
		if !isUTF8Locale() {
			return UnicodeNone
		}

		// Check terminal type
		term := strings.ToLower(os.Getenv("TERM"))
		
		// Linux console has limited font
		if strings.Contains(term, "linux") && !strings.Contains(term, "xterm") {
			return UnicodeBasic
		}

		// Check for known good terminals
		if isModernTerminal() {
			return UnicodeFull
		}

		// Conservative default for unknown terminals
		return UnicodeBasic
	}
}

func isUTF8Locale() bool {
	localeVars := []string{"LC_ALL", "LC_CTYPE", "LANG"}
	for _, v := range localeVars {
		if locale := os.Getenv(v); locale != "" {
			locale = strings.ToLower(locale)
			if strings.Contains(locale, "utf-8") || strings.Contains(locale, "utf8") {
				return true
			}
		}
	}
	return false
}

func isModernTerminal() bool {
	term := strings.ToLower(os.Getenv("TERM"))
	
	// List of terminals known to have good Unicode support
	modernTerms := []string{
		"xterm-256color",
		"screen-256color",
		"tmux-256color",
		"rxvt-unicode",
		"alacritty",
		"kitty",
		"wezterm",
		"foot",
		"gnome-256color",
		"konsole",
	}
	
	for _, mt := range modernTerms {
		if strings.Contains(term, mt) {
			return true
		}
	}
	
	// Check for color support as a proxy for modern terminal
	if os.Getenv("COLORTERM") == "truecolor" || os.Getenv("COLORTERM") == "24bit" {
		return true
	}
	
	return false
}

// IsComplexUnicodeChar checks if a character is likely to have font support issues
func IsComplexUnicodeChar(r rune) bool {
	// Legacy Computing symbols (U+1FB00-U+1FBFF) - very poor support
	if r >= 0x1FB00 && r <= 0x1FBFF {
		return true
	}
	
	// Symbols for Legacy Computing (U+1FB00-U+1FBCF) - poor support
	if r >= 0x1FB90 && r <= 0x1FBCF {
		return true
	}
	
	// Braille patterns - medium support
	if r >= 0x2800 && r <= 0x28FF {
		return true
	}
	
	// Mathematical Alphanumeric Symbols - medium support
	if r >= 0x1D400 && r <= 0x1D7FF {
		return true
	}
	
	// Emoji - variable support
	if (r >= 0x1F300 && r <= 0x1F5FF) || // Misc Symbols and Pictographs
	   (r >= 0x1F600 && r <= 0x1F64F) || // Emoticons
	   (r >= 0x1F680 && r <= 0x1F6FF) {  // Transport and Map Symbols
		return true
	}
	
	return false
}