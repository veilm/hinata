package main

import (
	"fmt"
	"github.com/fatih/color"
)

func main() {
	// Base colors
	defaultText := color.RGB(255, 255, 255)          // White
	currentSnowflakeBlue := color.RGB(110, 200, 255) // Current stdout color
	icyCyan := color.RGB(100, 220, 220)              // Icy Cyan option

	// Dimmed stdout options
	dimOptions := []struct {
		name  string
		color *color.Color
	}{
		{"Softer Blue", color.RGB(80, 140, 180)},
		{"Muted Sky", color.RGB(100, 150, 190)},
		{"Gentle Blue", color.RGB(90, 160, 200)},
		{"Faded Snowflake", color.RGB(80, 150, 200)},
		{"Subtle Cyan", color.RGB(70, 130, 160)},
	}

	fmt.Println("=== OPTION A: Shell blocks use current snowflake blue ===")
	fmt.Println()

	for i, dim := range dimOptions {
		fmt.Printf("--- A.%d: With %s stdout ---\n\n", i+1, dim.name)

		fmt.Print("  ")
		defaultText.Println("I'll help you check the system status:")
		fmt.Println()

		// Shell block (using current snowflake blue)
		fmt.Print("  ")
		currentSnowflakeBlue.Println("uname -a")
		fmt.Print("  ")
		currentSnowflakeBlue.Println("date")
		fmt.Print("  ")
		currentSnowflakeBlue.Println("echo \"System check complete ✓\"")
		fmt.Println()

		// Shell results (dimmed)
		fmt.Print("  ")
		dim.color.Println("Linux winterbox 6.1.0 x86_64 GNU/Linux")
		fmt.Print("  ")
		dim.color.Println("Thu Jan 9 10:45:23 PST 2025")
		fmt.Print("  ")
		dim.color.Println("System check complete ✓")
		fmt.Println()
		fmt.Println()
	}

	fmt.Println("\n=== OPTION B: Shell blocks use Icy Cyan ===")
	fmt.Println()

	for i, dim := range dimOptions {
		fmt.Printf("--- B.%d: With %s stdout ---\n\n", i+1, dim.name)

		fmt.Print("  ")
		defaultText.Println("I'll help you check the system status:")
		fmt.Println()

		// Shell block (using icy cyan)
		fmt.Print("  ")
		icyCyan.Println("uname -a")
		fmt.Print("  ")
		icyCyan.Println("date")
		fmt.Print("  ")
		icyCyan.Println("echo \"System check complete ✓\"")
		fmt.Println()

		// Shell results (dimmed)
		fmt.Print("  ")
		dim.color.Println("Linux winterbox 6.1.0 x86_64 GNU/Linux")
		fmt.Print("  ")
		dim.color.Println("Thu Jan 9 10:45:23 PST 2025")
		fmt.Print("  ")
		dim.color.Println("System check complete ✓")
		fmt.Println()
		fmt.Println()
	}

	// Bonus: Show them side by side for direct comparison
	fmt.Println("\n=== Direct Comparison (using Gentle Blue for stdout) ===")
	fmt.Println()

	gentleBlue := color.RGB(90, 160, 200)

	fmt.Println("Option A - Snowflake Blue for shell blocks:")
	fmt.Print("  ")
	currentSnowflakeBlue.Println("echo \"Hello from hinata\"")
	fmt.Print("  ")
	gentleBlue.Println("Hello from hinata")

	fmt.Println("\nOption B - Icy Cyan for shell blocks:")
	fmt.Print("  ")
	icyCyan.Println("echo \"Hello from hinata\"")
	fmt.Print("  ")
	gentleBlue.Println("Hello from hinata")
}
