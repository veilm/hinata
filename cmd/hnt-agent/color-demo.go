package main

import (
	"fmt"
	"github.com/fatih/color"
)

func main() {
	// Existing colors
	defaultText := color.RGB(255, 255, 255)   // White
	snowflakeBlue := color.RGB(110, 200, 255) // Official snowflake blue (current stdout)

	// Color options for shell blocks
	options := []struct {
		name  string
		color *color.Color
	}{
		{"Current - Mint Green", color.RGB(160, 255, 200)},
		{"Icy Cyan/Turquoise", color.RGB(100, 220, 220)},
		{"Aurora Purple", color.RGB(180, 120, 255)},
		{"Frost White (Blue Tint)", color.RGB(240, 248, 255)},
		{"Winter Sky Blue", color.RGB(135, 206, 235)},
		{"Glacier Blue", color.RGB(120, 180, 200)},
		{"Soft Gold/Amber", color.RGB(255, 220, 140)},
	}

	// Demo each option
	for i, opt := range options {
		fmt.Println()
		fmt.Printf("=== Option %d: %s ===\n", i+1, opt.name)
		fmt.Println()

		// Simulate conversation
		fmt.Print("  ")
		defaultText.Println("I'll create a simple greeting script for you.")
		fmt.Println()

		// Shell block
		fmt.Print("  ")
		opt.color.Println("echo \"Hello, Winter!\"")
		fmt.Print("  ")
		opt.color.Println("echo \"Welcome to the magical world of hinata ❄️\"")
		fmt.Println()

		// Shell results
		fmt.Print("  ")
		snowflakeBlue.Println("Hello, Winter!")
		fmt.Print("  ")
		snowflakeBlue.Println("Welcome to the magical world of hinata ❄️")
		fmt.Println()

		fmt.Print("  ")
		defaultText.Println("The greeting has been displayed successfully.")
	}

	// Show alternative with dimmed stdout
	fmt.Println("\n\n=== Alternative: Make stdout less prominent ===")
	fmt.Println()

	dimmerBlue := color.RGB(80, 140, 180) // Muted blue for stdout
	icyCyan := color.RGB(100, 220, 220)

	fmt.Print("  ")
	defaultText.Println("Here's the same example with shell blocks standing out more:")
	fmt.Println()

	// Shell block (prominent)
	fmt.Print("  ")
	icyCyan.Println("echo \"Hello, Winter!\"")
	fmt.Print("  ")
	icyCyan.Println("echo \"Welcome to the magical world of hinata ❄️\"")
	fmt.Println()

	// Shell results (dimmed)
	fmt.Print("  ")
	dimmerBlue.Println("Hello, Winter!")
	fmt.Print("  ")
	dimmerBlue.Println("Welcome to the magical world of hinata ❄️")
	fmt.Println()
}
