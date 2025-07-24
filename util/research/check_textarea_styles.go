package main

import (
	"fmt"
	"github.com/charmbracelet/bubbles/textarea"
)

func main() {
	ta := textarea.New()

	// Check what style fields are available
	fmt.Printf("FocusedStyle fields:\n")
	fmt.Printf("  Base: %+v\n", ta.FocusedStyle.Base)
	fmt.Printf("  CursorLine: %+v\n", ta.FocusedStyle.CursorLine)
	fmt.Printf("  Prompt: %+v\n", ta.FocusedStyle.Prompt)
	fmt.Printf("  Placeholder: %+v\n", ta.FocusedStyle.Placeholder)
	fmt.Printf("  EndOfBuffer: %+v\n", ta.FocusedStyle.EndOfBuffer)
	fmt.Printf("  Text: %+v\n", ta.FocusedStyle.Text)

	// Check if CharLimit affects anything
	fmt.Printf("\nCharLimit: %d\n", ta.CharLimit)
}
