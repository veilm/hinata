package spinner

import (
	"bytes"
	"os"
	"os/exec"
	"strings"
)

type UnicodeSupport int

const (
	UnicodeNone  UnicodeSupport = iota // ASCII only
	UnicodeBasic                       // Box drawing characters
	UnicodeFull                        // Complex symbols, emoji
)

// DetectUnicodeSupport determines the level of Unicode support in the current terminal
func DetectUnicodeSupport() UnicodeSupport {
	// Check if NO_UNICODE environment variable is set (user override)
	if os.Getenv("NO_UNICODE") != "" {
		return UnicodeNone
	}

	// Check locale settings first
	if !isUTF8Locale() {
		return UnicodeNone
	}

	// Check if we're in an SSH session - cap at Basic Unicode
	if isSSHSession() {
		// SSH sessions often have font rendering issues with complex Unicode
		// 1752554096 well it's more because it feels possible that you'd ssh
		// into a host that has fonts, without having fonts yourself. having fonts
		// yourself but not on the remote host would already fail regardless of
		// this check. and then having fonts on both seems less likely than only
		// having on the machine, I think
		return UnicodeBasic
	}

	// Check terminal type
	term := strings.ToLower(os.Getenv("TERM"))

	// Linux console has limited font
	if strings.Contains(term, "linux") && !strings.Contains(term, "xterm") {
		return UnicodeBasic
	}

	// Check for fonts that support Legacy Computing symbols
	if hasLegacyComputingFont() {
		return UnicodeFull
	}

	// Check for modern terminal
	if isModernTerminal() {
		// Even modern terminals need proper fonts
		return UnicodeBasic
	}

	// Conservative default for unknown terminals
	return UnicodeBasic
}

func isSSHSession() bool {
	// Check common SSH environment variables
	return os.Getenv("SSH_CLIENT") != "" ||
		os.Getenv("SSH_TTY") != "" ||
		os.Getenv("SSH_CONNECTION") != ""
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

// hasLegacyComputingFont checks if any installed font supports Legacy Computing symbols
func hasLegacyComputingFont() bool {
	// Check if fc-list is available
	if _, err := exec.LookPath("fc-list"); err != nil {
		// fc-list not available, can't check fonts
		return false
	}

	// Test for a character in the Legacy Computing block (U+1FB90)
	cmd := exec.Command("fc-list", ":charset=1fb90")
	output, err := cmd.Output()
	if err != nil {
		return false
	}

	// Parse the output to find monospace fonts
	fonts := strings.Split(string(output), "\n")
	for _, font := range fonts {
		if font == "" {
			continue
		}

		// Look for known good fonts that support Legacy Computing
		fontLower := strings.ToLower(font)

		// Known fonts with Legacy Computing support
		goodFonts := []string{
			"cascadia code",    // Microsoft's terminal font (v2404.03+)
			"cascadia mono",    // Monospace variant
			"gnu unifont",      // Comprehensive Unicode coverage
			"unifont",          // Alternative name
			"fairfax hd",       // Designed for terminals
			"fairfax",          // Alternative name
			"legacy_computing", // Dedicated font for this block
			"unscii",           // Retro computing font
			"adwaita mono",     // GNOME's new mono font
		}

		for _, gf := range goodFonts {
			if strings.Contains(fontLower, gf) {
				// Check if it's a monospace variant (for terminal use)
				if strings.Contains(fontLower, "mono") ||
					strings.Contains(fontLower, "code") ||
					strings.Contains(fontLower, "unifont") ||
					strings.Contains(fontLower, "unscii") ||
					strings.Contains(fontLower, "fairfax") ||
					strings.Contains(fontLower, "legacy") {
					return true
				}
			}
		}
	}

	// Also check by testing multiple Legacy Computing characters
	// This catches fonts we might not know about
	testChars := []string{"1fb90", "1fb95", "1fba0", "1fbb0"}
	supportCount := 0

	for _, char := range testChars {
		cmd := exec.Command("fc-list", ":charset="+char, "family", "style")
		output, err := cmd.Output()
		if err == nil && len(bytes.TrimSpace(output)) > 0 {
			supportCount++
		}
	}

	// If multiple test characters are supported, we likely have good font coverage
	return supportCount >= 3
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
		(r >= 0x1F680 && r <= 0x1F6FF) { // Transport and Map Symbols
		return true
	}

	return false
}
