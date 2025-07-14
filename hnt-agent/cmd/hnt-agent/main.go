package main

import (
	"fmt"
	"hnt-agent/pkg/agent"
	"os"
	"path/filepath"
	"shared/pkg/prompt"
	"shared/pkg/terminal"

	"github.com/spf13/cobra"
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
	rootCmd.Flags().BoolVar(&noEscape, "no-escape-backticks", false, "Do not escape backticks in shell commands")
	rootCmd.Flags().BoolVar(&shellDisplay, "shell-results-display-xml", false, "Display shell command results")
	rootCmd.Flags().BoolVar(&useJSON, "json", false, "Output shell results as JSON")
	rootCmd.Flags().IntVar(&spinnerIndex, "spinner", -1, "Use specific spinner by index")
	rootCmd.Flags().BoolVar(&useEditor, "use-editor", false, "Use an external editor ($EDITOR) for the user instruction message")

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
	if message != "" {
		userMessage = message
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
		var err error
		configDir, err = os.UserConfigDir()
		if err != nil {
			return "", err
		}
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
