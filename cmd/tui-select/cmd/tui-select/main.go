package main

import (
	"bufio"
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/spf13/cobra"
	"github.com/veilm/hinata/cmd/tui-select/pkg/selector"
	"github.com/veilm/hinata/pkg/terminal"
)

var (
	height int
	color  int
	prefix string
)

func main() {
	// Ensure terminal compatibility
	terminal.EnsureCompatibleTerm()

	var rootCmd = &cobra.Command{
		Use:           "tui-select",
		Short:         "Select an item from a list read from stdin",
		RunE:          run,
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	rootCmd.Flags().IntVar(&height, "height", 10, "The height of the selection menu")
	rootCmd.Flags().IntVar(&color, "color", -1, "The color of the selected line (0-7: Black, Red, Green, Yellow, Blue, Magenta, Cyan, White)")
	rootCmd.Flags().StringVar(&prefix, "prefix", "", "The prefix for the selected line")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	// Read lines from stdin
	var lines []string
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("error reading from stdin: %w", err)
	}

	if len(lines) == 0 {
		return nil
	}

	// Check if we can open /dev/tty for interactive mode
	// If not (e.g., in a non-interactive environment), just print the first line
	if tty, err := os.OpenFile("/dev/tty", os.O_RDWR, 0); err != nil {
		if len(lines) > 0 {
			fmt.Println(lines[0])
		}
		return nil
	} else {
		tty.Close()
	}

	// Create and run the select model
	opts := selector.Options{
		Height: height,
		Color:  color,
		Prefix: prefix,
	}

	m := selector.New(lines, opts)
	p := tea.NewProgram(m)

	finalModel, err := p.Run()
	if err != nil {
		return fmt.Errorf("error running program: %w", err)
	}

	final := finalModel.(selector.Model)
	if final.Aborted() {
		os.Exit(1)
	}

	if choice := final.Choice(); choice != "" {
		fmt.Println(choice)
	}

	return nil
}
