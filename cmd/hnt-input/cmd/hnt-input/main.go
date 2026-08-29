package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/pkg/prompt"
	"github.com/veilm/hinata/pkg/terminal"
)

var (
	saveTo       string
	promptHeight int
	theme        string
	useEditor    bool
	appendMode   bool
)

func main() {
	// Ensure terminal compatibility
	terminal.EnsureCompatibleTerm()

	rootCmd := &cobra.Command{
		Use:           "hnt-input",
		Short:         "Simple textarea that saves input to a file",
		Long:          "A minimal CLI tool providing an interactive textarea. When the user submits text (Ctrl+D), it saves to the specified file.",
		RunE:          run,
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	rootCmd.Flags().StringVarP(&saveTo, "save-to", "o", "", "File path to save submitted text (required)")
	rootCmd.Flags().IntVar(&promptHeight, "prompt-height", 3, "Height of the textarea (default 3)")
	rootCmd.Flags().StringVar(&theme, "theme", "dust", "Color theme: snow (true color), dust (default, grayscale), or ansi (terminal colors)")
	rootCmd.Flags().BoolVar(&useEditor, "use-editor", false, "Use an external editor ($EDITOR) instead of TUI")
	rootCmd.Flags().BoolVar(&appendMode, "append", false, "Append to file instead of overwriting")

	rootCmd.MarkFlagRequired("save-to")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	// Get user input using the textarea
	var userInput string
	var err error

	if useEditor {
		userInput, err = prompt.PromptWithEditor()
	} else {
		userInput, err = prompt.PromptForInputWithColors(inputColors(theme), promptHeight)
	}

	if err != nil {
		return fmt.Errorf("failed to get input: %w", err)
	}

	// Check if user aborted (empty input)
	if userInput == "" {
		return fmt.Errorf("aborted: no input provided")
	}

	// Add newline to the end if not present
	if userInput[len(userInput)-1] != '\n' {
		userInput += "\n"
	}

	// Save to file
	var writeErr error
	if appendMode {
		file, openErr := os.OpenFile(saveTo, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if openErr != nil {
			return fmt.Errorf("failed to open file for appending: %w", openErr)
		}
		defer file.Close()

		_, writeErr = file.WriteString(userInput)
	} else {
		writeErr = os.WriteFile(saveTo, []byte(userInput), 0644)
	}

	if writeErr != nil {
		return fmt.Errorf("failed to write to file: %w", writeErr)
	}

	return nil
}

func inputColors(name string) prompt.ColorConfig {
	if name == "ansi" {
		return prompt.ColorConfig{}
	}

	text := [3]int{255, 255, 255}
	help := [3]int{160, 200, 255}
	border := [3]int{110, 200, 255}
	if name == "dust" {
		text = [3]int{220, 220, 220}
		help = [3]int{170, 170, 170}
		border = [3]int{190, 190, 190}
	}

	return prompt.ColorConfig{
		HeaderRGB: &text,
		HelpRGB:   &help,
		PromptRGB: &border,
		TextRGB:   &text,
	}
}
