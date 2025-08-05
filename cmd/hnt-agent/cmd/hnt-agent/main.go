package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/agent"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/spinner"
	"github.com/veilm/hinata/pkg/prompt"
	"github.com/veilm/hinata/pkg/terminal"
)

var (
	systemPrompt    string
	message         string
	session         string
	pwd             string
	model           string
	ignoreReasoning bool
	noConfirm       bool
	noEscape        bool
	shellDisplay    bool
	useJSON         bool
	spinnerIndex    int
	spinnerFile     string
	useSpinner      bool
	useEditor       bool
	useStdin        bool
	autoExit        bool
	theme           string
)

func main() {
	// Ensure terminal compatibility
	terminal.EnsureCompatibleTerm()

	rootCmd := &cobra.Command{
		Use:           "hnt-agent",
		Short:         "Interact with hinata LLM agent to execute shell commands",
		RunE:          run,
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	// Add subcommands
	rootCmd.AddCommand(newUnicodeCheckCmd())
	rootCmd.AddCommand(newSpinnerDemoCmd())

	rootCmd.Flags().StringVar(&systemPrompt, "system", "", "System message string or path to system message file")
	rootCmd.Flags().StringVarP(&message, "message", "m", "", "User instruction message")
	rootCmd.Flags().StringVarP(&session, "session", "s", "", "Path to conversation directory to resume a session")
	rootCmd.Flags().StringVar(&pwd, "pwd", "", "Set the initial working directory")
	rootCmd.Flags().StringVar(&model, "model", "", "LLM model to use")
	rootCmd.Flags().BoolVar(&ignoreReasoning, "ignore-reasoning", false, "Do not display or save LLM reasoning")
	rootCmd.Flags().BoolVar(&noConfirm, "no-confirm", false, "Skip confirmation steps")
	rootCmd.Flags().BoolVarP(&noConfirm, "yes", "y", false, "Skip confirmation steps (alias for --no-confirm)")
	rootCmd.Flags().BoolVar(&noEscape, "no-escape-backticks", false, "Do not escape backticks in shell commands")
	rootCmd.Flags().BoolVar(&shellDisplay, "shell-results-display-xml", false, "Display shell command results")
	rootCmd.Flags().BoolVar(&useJSON, "json", false, "Output shell results as JSON")
	rootCmd.Flags().IntVar(&spinnerIndex, "spinner", -1, "Use specific spinner by index")
	rootCmd.Flags().StringVar(&spinnerFile, "spinner-file", "", "Path to a text file containing spinner frames (overrides --spinner)")
	rootCmd.Flags().BoolVar(&useEditor, "use-editor", false, "Use an external editor ($EDITOR) for the user instruction message")
	rootCmd.Flags().BoolVar(&useStdin, "stdin", false, "Read message from stdin")
	rootCmd.Flags().BoolVar(&autoExit, "auto-exit", false, "Automatically exit if no shell block is provided")
	rootCmd.Flags().StringVar(&theme, "theme", "snow", "Color theme: snow (default, true color) or ansi (terminal colors)")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	var sysPrompt string

	if systemPrompt != "" {
		content, err := readSystemPrompt(systemPrompt)
		if err != nil {
			return fmt.Errorf("failed to read system prompt: %w", err)
		}
		sysPrompt = content
	} else {
		defaultPrompt, err := loadDefaultPrompt()
		if err != nil {
			return fmt.Errorf("failed to load default prompt: %w", err)
		}
		if defaultPrompt == "" {
			return fmt.Errorf("no prompt files found. Please ensure prompts are installed in $XDG_CONFIG_HOME/hinata/prompts/hnt-agent/ or ~/.config/hinata/prompts/hnt-agent/")
		}
		sysPrompt = defaultPrompt
	}

	var userMessage string
	var stdinContent string

	// Read from stdin if requested
	if useStdin {
		bytes, err := io.ReadAll(os.Stdin)
		if err != nil {
			return fmt.Errorf("failed to read from stdin: %w", err)
		}
		stdinContent = strings.TrimSpace(string(bytes))
	}

	// Handle message input based on flags
	if message != "" && useStdin {
		// Combine -m flag and stdin content
		userMessage = message + "\n\n" + stdinContent
	} else if message != "" {
		userMessage = message
	} else if useStdin {
		userMessage = stdinContent
	} else {
		msg, err := promptForMessage(useEditor)
		if err != nil {
			return err
		}
		userMessage = msg
	}

	var spinnerPtr *int
	if spinnerIndex >= 0 {
		spinnerPtr = &spinnerIndex
	}

	cfg := agent.Config{
		ConversationDir: session,
		SystemPrompt:    sysPrompt,
		Model:           model,
		PWD:             pwd,
		IgnoreReasoning: ignoreReasoning,
		NoConfirm:       noConfirm,
		NoEscape:        noEscape,
		ShellDisplay:    shellDisplay,
		UseJSON:         useJSON,
		SpinnerIndex:    spinnerPtr,
		SpinnerFile:     spinnerFile,
		UseEditor:       useEditor,
		AutoExit:        autoExit,
		Theme:           theme,
	}

	ag, err := agent.New(cfg)
	if err != nil {
		return fmt.Errorf("failed to create agent: %w", err)
	}

	// if session == "" {
	// 	fmt.Fprintf(os.Stderr, "Created conversation: %s\n", ag.ConversationDir)
	// }

	return ag.Run(userMessage)
}

func readSystemPrompt(path string) (string, error) {
	if _, err := os.Stat(path); err == nil {
		content, err := os.ReadFile(path)
		if err != nil {
			return "", err
		}
		return string(content), nil
	}

	return path, nil
}

func loadDefaultPrompt() (string, error) {
	// First try HINATA_PROMPTS_DIR environment variable
	promptsDir := os.Getenv("HINATA_PROMPTS_DIR")
	if promptsDir != "" {
		promptPath := filepath.Join(promptsDir, "hnt-agent/main-shell_agent.md")
		if content, err := os.ReadFile(promptPath); err == nil {
			return string(content), nil
		}
	}

	// Fall back to XDG_CONFIG_HOME/hinata/prompts
	configDir := os.Getenv("XDG_CONFIG_HOME")
	if configDir == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		configDir = filepath.Join(homeDir, ".config")
	}

	promptPath := filepath.Join(configDir, "hinata/prompts/hnt-agent/main-shell_agent.md")
	content, err := os.ReadFile(promptPath)
	if err != nil {
		return "", fmt.Errorf("failed to read prompt file %s: %w", promptPath, err)
	}

	return string(content), nil
}

func promptForMessage(useEditor bool) (string, error) {
	// Check theme to determine colors
	if theme == "snow" {
		// Use RGB colors for snow theme
		colors := prompt.ColorConfig{
			HeaderRGB: &[3]int{255, 255, 255}, // White header
			HelpRGB:   &[3]int{160, 200, 255}, // Lighter blue for help text
			PromptRGB: &[3]int{110, 200, 255}, // Official snowflake blue for prompt
			TextRGB:   &[3]int{255, 255, 255}, // Explicit white for input text
		}
		return prompt.GetUserInstructionWithColors("", useEditor, colors)
	} else {
		// Use default colors for ansi theme
		return prompt.GetUserInstruction("", useEditor)
	}
}

func newUnicodeCheckCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "unicode-check",
		Short: "Check Unicode detection and font support for spinners",
		Long: `Diagnostic tool for the hnt-agent spinner Unicode detection system.
Shows environment variables, locale detection, terminal detection,
font support, and the final Unicode support level determination.`,
		Run: runUnicodeCheck,
	}
}

func newSpinnerDemoCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "spinner-demo [seconds]",
		Short: "Display a spinner for N seconds",
		Long:  "Demonstrates the spinner animation for the specified number of seconds. Useful for testing spinner appearance and theme colors.",
		Args:  cobra.ExactArgs(1),
		RunE:  runSpinnerDemo,
	}

	// Add local flags for spinner demo
	cmd.Flags().IntVar(&spinnerIndex, "spinner", -1, "Use specific spinner by index")
	cmd.Flags().StringVar(&spinnerFile, "spinner-file", "", "Path to a text file containing spinner frames")
	cmd.Flags().StringVar(&theme, "theme", "snow", "Color theme: snow (default, true color) or ansi (terminal colors)")

	return cmd
}

func runSpinnerDemo(cmd *cobra.Command, args []string) error {
	// Parse duration
	seconds, err := strconv.Atoi(args[0])
	if err != nil || seconds <= 0 {
		return fmt.Errorf("invalid duration: %s (must be a positive integer)", args[0])
	}

	// Get spinner
	var sp spinner.Spinner
	if spinnerFile != "" {
		// Load spinner from file
		sp, err = loadSpinnerFromFile(spinnerFile)
		if err != nil {
			return fmt.Errorf("failed to load spinner from file: %w", err)
		}
	} else if spinnerIndex >= 0 && spinnerIndex < len(spinner.SPINNERS) {
		sp = spinner.SPINNERS[spinnerIndex]
	} else {
		sp = spinner.GetRandomSpinner()
	}

	// Get theme
	t := agent.GetTheme(theme)

	// Get random loading message - same logic as regular hnt-agent
	msg := spinner.GetRandomLoadingMessage()

	// Set up stop channel
	stopCh := make(chan bool)

	// Start spinner
	go spinner.Run(sp, msg, "  ", stopCh, func(s string) {
		t.Spinner.Print(s)
	})

	// Wait for specified duration
	time.Sleep(time.Duration(seconds) * time.Second)

	// Stop spinner
	close(stopCh)
	time.Sleep(50 * time.Millisecond) // Give spinner time to clean up

	fmt.Println()
	return nil
}

func loadSpinnerFromFile(path string) (spinner.Spinner, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return spinner.Spinner{}, err
	}

	lines := strings.Split(strings.TrimSpace(string(content)), "\n")
	if len(lines) == 0 {
		return spinner.Spinner{}, fmt.Errorf("spinner file is empty")
	}

	return spinner.Spinner{
		Name:   filepath.Base(path),
		Frames: lines,
		Speed:  150 * time.Millisecond, // Default speed
	}, nil
}
