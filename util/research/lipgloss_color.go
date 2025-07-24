package main

import (
	"fmt"
	"os"

	"github.com/charmbracelet/lipgloss"
)

func main() {
	fmt.Println("=== Lipgloss Color Format Test ===")
	fmt.Println("Testing different RGB color formats to see which ones work...\n")

	// Test different color format approaches
	tests := []struct {
		name  string
		color lipgloss.Color
		desc  string
	}{
		// ANSI colors (should work)
		{"ANSI Blue", lipgloss.Color("4"), "ANSI color 4 (blue)"},
		{"ANSI Red", lipgloss.Color("1"), "ANSI color 1 (red)"},
		{"ANSI 12", lipgloss.Color("12"), "ANSI color 12 (bright blue)"},

		// Hex format
		{"Hex #64C8FF", lipgloss.Color("#64C8FF"), "Hex format (ice blue)"},
		{"Hex #FF9696", lipgloss.Color("#FF9696"), "Hex format (soft red)"},

		// RGB with semicolons (what we tried)
		{"RGB 100;200;255", lipgloss.Color("100;200;255"), "RGB with semicolons"},

		// RGB with commas
		{"RGB 100,200,255", lipgloss.Color("100,200,255"), "RGB with commas"},

		// RGB with spaces
		{"RGB 100 200 255", lipgloss.Color("100 200 255"), "RGB with spaces"},

		// RGB function style
		{"rgb(100,200,255)", lipgloss.Color("rgb(100,200,255)"), "RGB function notation"},

		// ANSI escape sequence style
		{"38;2;100;200;255", lipgloss.Color("38;2;100;200;255"), "ANSI RGB escape"},
		{"48;2;100;200;255", lipgloss.Color("48;2;100;200;255"), "ANSI RGB background"},
	}

	// Test foreground colors
	fmt.Println("FOREGROUND COLOR TESTS:")
	fmt.Println("-----------------------")
	for _, test := range tests {
		style := lipgloss.NewStyle().Foreground(test.color)
		fmt.Printf("%-20s: %s (%s)\n", test.name, style.Render("████ Sample Text ████"), test.desc)
	}

	fmt.Println("\nBACKGROUND COLOR TESTS:")
	fmt.Println("-----------------------")
	// Test background colors with more visible examples
	bgTests := []struct {
		name string
		bg   lipgloss.Color
		fg   lipgloss.Color
		desc string
	}{
		{"ANSI Blue BG", lipgloss.Color("4"), lipgloss.Color("15"), "ANSI blue bg, white fg"},
		{"Hex #64C8FF BG", lipgloss.Color("#64C8FF"), lipgloss.Color("#FFFFFF"), "Hex ice blue bg"},
		{"Hex #6464FF BG", lipgloss.Color("#6464FF"), lipgloss.Color("#FFFFFF"), "Hex darker blue bg"},
		{"RGB semicolon BG", lipgloss.Color("100;160;255"), lipgloss.Color("255;255;255"), "RGB with semicolons"},
		{"38;2 format BG", lipgloss.Color("38;2;100;160;255"), lipgloss.Color("38;2;255;255;255"), "ANSI RGB format"},
	}

	for _, test := range bgTests {
		style := lipgloss.NewStyle().Background(test.bg).Foreground(test.fg)
		fmt.Printf("%-20s: %s (%s)\n", test.name, style.Render("  Selected Item  "), test.desc)
	}

	// Test complete selector-like styling
	fmt.Println("\nSELECTOR-STYLE TESTS:")
	fmt.Println("---------------------")

	// Different prefix styles
	prefixTests := []struct {
		name  string
		color lipgloss.Color
	}{
		{"ANSI Blue", lipgloss.Color("4")},
		{"Hex #78B4FF", lipgloss.Color("#78B4FF")},
		{"Hex #64C8FF", lipgloss.Color("#64C8FF")},
	}

	for _, test := range prefixTests {
		prefixStyle := lipgloss.NewStyle().Foreground(test.color)
		fmt.Printf("%-20s: %s Regular Item\n", test.name, prefixStyle.Render("▌"))

		// Also show with highlighted item
		hlStyle := lipgloss.NewStyle().Background(test.color).Foreground(lipgloss.Color("0"))
		fmt.Printf("%-20s: %s %s\n", "", prefixStyle.Render("▌"), hlStyle.Render("Highlighted Item"))
	}

	// Test if we have true color support
	fmt.Println("\nTERMINAL CAPABILITIES:")
	fmt.Println("----------------------")
	fmt.Printf("TERM: %s\n", os.Getenv("TERM"))
	fmt.Printf("COLORTERM: %s\n", os.Getenv("COLORTERM"))

	// Try to detect color support
	if lipgloss.HasDarkBackground() {
		fmt.Println("Terminal detected as: DARK background")
	} else {
		fmt.Println("Terminal detected as: LIGHT background")
	}
}
