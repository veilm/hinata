package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/agent"
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
	useSpinner      bool
	useEditor       bool
	useStdin        bool
	autoExit        bool
	shellBox        bool
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
	rootCmd.Flags().BoolVar(&useEditor, "use-editor", false, "Use an external editor ($EDITOR) for the user instruction message")
	rootCmd.Flags().BoolVar(&useStdin, "stdin", false, "Read message from stdin")
	rootCmd.Flags().BoolVar(&autoExit, "auto-exit", false, "Automatically exit if no shell block is provided")
	rootCmd.Flags().BoolVar(&shellBox, "shell-box", false, "Enable fancy box rendering for shell blocks")

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
		UseEditor:       useEditor,
		AutoExit:        autoExit,
		ShellBox:        shellBox,
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
	return prompt.GetUserInstruction("", useEditor)
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
