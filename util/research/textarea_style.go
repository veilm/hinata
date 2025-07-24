package main

import (
	"fmt"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/lipgloss"
)

func main() {
	ta := textarea.New()

	// Check available style options
	fmt.Println("Testing textarea styling options...")

	// Try different prompt styles
	ta.Prompt = "┃ "
	ta.FocusedStyle.Prompt = lipgloss.NewStyle().Foreground(lipgloss.Color("#6EC8FF"))
	ta.FocusedStyle.CursorLine = lipgloss.NewStyle().Background(lipgloss.Color("#1a1a1a"))
	ta.FocusedStyle.Base = lipgloss.NewStyle().BorderForeground(lipgloss.Color("#6EC8FF"))

	// Print the focused style to see structure
	fmt.Printf("FocusedStyle fields:\n")
	fmt.Printf("  Base: %+v\n", ta.FocusedStyle.Base)
	fmt.Printf("  CursorLine: %+v\n", ta.FocusedStyle.CursorLine)
	fmt.Printf("  Prompt: %+v\n", ta.FocusedStyle.Prompt)
	fmt.Printf("  Placeholder: %+v\n", ta.FocusedStyle.Placeholder)
	fmt.Printf("  EndOfBuffer: %+v\n", ta.FocusedStyle.EndOfBuffer)

	// Check what the default prompt is
	fmt.Printf("\nDefault prompt: %q\n", ta.Prompt)
}
