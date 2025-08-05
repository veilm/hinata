package main

import (
	"fmt"
	"github.com/fatih/color"
	"strings"
)

func main() {
	// Colors
	defaultText := color.RGB(255, 255, 255)    // White
	shellBlockCode := color.RGB(110, 200, 255) // Official snowflake blue
	softerBlue := color.RGB(80, 140, 180)      // Softer blue for stdout
	userMargin := color.RGB(180, 140, 255)     // Purple frost for user

	// Border character options
	borders := []string{
		"│", // Box drawing light vertical
		"┃", // Box drawing heavy vertical
		"┊", // Box drawing light dashed vertical
		"┋", // Box drawing heavy dashed vertical
		"▌", // Left half block
		"▎", // Left one eighth block
		"▏", // Left one eighth block (thin)
		"◆", // Diamond
		"◈", // Diamond with dot
		"❯", // Heavy right-pointing angle
		"▸", // Small right-pointing triangle
		"»", // Right double angle
	}

	fmt.Println("=== Shell Block Left Border Options ===")
	fmt.Println("\nFor comparison - current user message style:")
	userMargin.Print("┆ ")
	defaultText.Println("This is how user messages look")
	fmt.Println()

	for i, border := range borders {
		fmt.Printf("Option %d: Character '%s'\n", i+1, border)

		// Show shell block with border
		lines := []string{
			"echo \"Hello from hinata\"",
			"date",
			"echo \"System check complete ✓\"",
		}

		for _, line := range lines {
			shellBlockCode.Print(border + " ")
			shellBlockCode.Println(line)
		}

		fmt.Println()

		// Show output
		softerBlue.Println("  Hello from hinata")
		softerBlue.Println("  Thu Jan 9 10:45:23 PST 2025")
		softerBlue.Println("  System check complete ✓")

		fmt.Println()
		fmt.Println(strings.Repeat("-", 50))
		fmt.Println()
	}

	// Show recommended options in context
	fmt.Println("\n=== Top Recommendations in Full Context ===")

	recommendations := []struct {
		char string
		desc string
	}{
		{"│", "Clean and minimal"},
		{"▎", "Subtle accent"},
		{"❯", "Directional emphasis"},
	}

	for _, rec := range recommendations {
		fmt.Printf("\n%s - %s:\n\n", rec.char, rec.desc)

		defaultText.Println("  I'll help you check the system status:")
		fmt.Println()

		// Shell block with border
		shellBlockCode.Print(rec.char + " ")
		shellBlockCode.Println("uname -a")
		shellBlockCode.Print(rec.char + " ")
		shellBlockCode.Println("echo \"All systems operational\"")
		fmt.Println()

		// Output
		softerBlue.Println("  Linux winterbox 6.1.0 x86_64 GNU/Linux")
		softerBlue.Println("  All systems operational")
		fmt.Println()
	}
}
