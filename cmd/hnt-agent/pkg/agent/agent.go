package agent

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/fatih/color"
	"github.com/mattn/go-runewidth"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/output"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/spinner"
	"github.com/veilm/hinata/cmd/hnt-chat/pkg/chat"
	"github.com/veilm/hinata/cmd/hnt-llm/pkg/llm"
	"github.com/veilm/hinata/cmd/shell-exec/pkg/shell"
	"github.com/veilm/hinata/cmd/tui-select/pkg/selector"
	"github.com/veilm/hinata/pkg/prompt"
	"golang.org/x/term"
)

const MARGIN = 2

type Agent struct {
	ConversationDir string
	SystemPrompt    string
	Model           string
	IgnoreReasoning bool
	NoConfirm       bool
	NoEscape        bool
	ShellDisplay    bool
	UseJSON         bool
	SpinnerIndex    *int
	SpinnerFile     string
	UseEditor       bool
	AutoExit        bool
	PromptHeight    int
	UseV2Streaming  bool  // Use the new OutputCoordinator-based streaming

	shellExecutor    *shell.Executor
	turnCounter      int
	humanTurnCounter int
	logger           *log.Logger
	theme            Theme
	customSpinner    *spinner.Spinner
}

type Config struct {
	ConversationDir string
	SystemPrompt    string
	Model           string
	PWD             string
	IgnoreReasoning bool
	NoConfirm       bool
	NoEscape        bool
	ShellDisplay    bool
	UseJSON         bool
	SpinnerIndex    *int
	SpinnerFile     string
	UseEditor       bool
	AutoExit        bool
	Theme           string
	PromptHeight    int
	ShellStartup    string
	UseV2Streaming  bool  // Use the new OutputCoordinator-based streaming
}

func New(cfg Config) (*Agent, error) {
	if cfg.ConversationDir == "" {
		// Use standard hnt-chat conversation directory
		baseDir, err := chat.GetConversationsDir()
		if err != nil {
			return nil, fmt.Errorf("failed to get conversations dir: %w", err)
		}

		convDir, err := chat.CreateNewConversation(baseDir)
		if err != nil {
			return nil, fmt.Errorf("failed to create conversation: %w", err)
		}
		cfg.ConversationDir = convDir
	}

	pwd := cfg.PWD
	if pwd == "" {
		var err error
		pwd, err = os.Getwd()
		if err != nil {
			return nil, fmt.Errorf("failed to get current directory: %w", err)
		}
	}

	if cfg.Model == "" {
		cfg.Model = os.Getenv("HINATA_AGENT_MODEL")
		if cfg.Model == "" {
			cfg.Model = os.Getenv("HINATA_MODEL")
			if cfg.Model == "" {
				cfg.Model = "openrouter/google/gemini-2.5-pro"
			}
		}
	}

	// Load or create shell state
	stateFile := filepath.Join(cfg.ConversationDir, "hnt-agent-state.json")
	var executor *shell.Executor

	if state, err := shell.LoadState(stateFile); err == nil {
		// Loaded existing state
		executor = shell.NewExecutorFromState(state)
	} else {
		// Create new state
		executor = shell.NewExecutor(pwd)

		// Check for legacy state files and migrate if they exist
		if existingPwd, err := os.ReadFile(filepath.Join(cfg.ConversationDir, "hnt-agent-pwd.txt")); err == nil {
			executor.WorkingDir = strings.TrimSpace(string(existingPwd))
		}

		if existingEnv, err := os.ReadFile(filepath.Join(cfg.ConversationDir, "hnt-agent-env.json")); err == nil {
			var env map[string]string
			if err := json.Unmarshal(existingEnv, &env); err == nil {
				executor.Env = env
			}
		}

		if existingAliases, err := os.ReadFile(filepath.Join(cfg.ConversationDir, "hnt-agent-aliases.txt")); err == nil {
			executor.Aliases = string(existingAliases)
		}
	}

	// Run shell startup script if provided
	if cfg.ShellStartup != "" {
		// Check if file exists
		if _, err := os.Stat(cfg.ShellStartup); err != nil {
			return nil, fmt.Errorf("shell startup script not found: %w", err)
		}

		// Source the startup script
		sourceCmd := fmt.Sprintf(". %s", cfg.ShellStartup)
		result, err := executor.Execute(sourceCmd)
		if err != nil {
			return nil, fmt.Errorf("failed to execute shell startup script: %w", err)
		}

		// Check for errors in the startup script
		if result.ExitCode != 0 {
			return nil, fmt.Errorf("shell startup script failed with exit code %d: %s", result.ExitCode, result.Stderr)
		}

		// Save the state immediately after startup
		state := executor.GetState()
		if err := shell.SaveState(state, stateFile); err != nil {
			// Log but don't fail if we can't save initial state
			if debugEnv := os.Getenv("HNT_AGENT_DEBUG"); debugEnv != "" {
				fmt.Fprintf(os.Stderr, "Warning: failed to save initial state after startup: %v\n", err)
			}
		}
	}

	// Create debug log file
	var logger *log.Logger
	if debugEnv := os.Getenv("HNT_AGENT_DEBUG"); debugEnv != "" {
		logFile, err := os.Create(filepath.Join(cfg.ConversationDir, "hnt-agent-debug.log"))
		if err == nil {
			logger = log.New(logFile, "[HNT-AGENT] ", log.Ltime|log.Lmicroseconds)
			logger.Printf("Debug logging enabled for conversation: %s", cfg.ConversationDir)
		}
	}

	// Load custom spinner if specified
	var customSpinner *spinner.Spinner
	if cfg.SpinnerFile != "" {
		sp, err := spinner.LoadSpinnerFromFile(cfg.SpinnerFile)
		if err != nil {
			return nil, fmt.Errorf("failed to load spinner from file: %w", err)
		}
		customSpinner = &sp
	}

	// Default prompt height if not specified
	promptHeight := cfg.PromptHeight
	if promptHeight <= 0 {
		promptHeight = 3
	}

	return &Agent{
		ConversationDir:  cfg.ConversationDir,
		SystemPrompt:     cfg.SystemPrompt,
		Model:            cfg.Model,
		IgnoreReasoning:  cfg.IgnoreReasoning,
		NoConfirm:        cfg.NoConfirm,
		NoEscape:         cfg.NoEscape,
		ShellDisplay:     cfg.ShellDisplay,
		UseJSON:          cfg.UseJSON,
		SpinnerIndex:     cfg.SpinnerIndex,
		SpinnerFile:      cfg.SpinnerFile,
		UseEditor:        cfg.UseEditor,
		AutoExit:         cfg.AutoExit,
		PromptHeight:     promptHeight,
		UseV2Streaming:   cfg.UseV2Streaming,
		shellExecutor:    executor,
		turnCounter:      1,
		humanTurnCounter: 1,
		logger:           logger,
		theme:            GetTheme(cfg.Theme),
		customSpinner:    customSpinner,
	}, nil
}

func (a *Agent) Run(userMessage string) error {
	isNewSession := !a.isExistingSession()

	if isNewSession {
		// Welcome message is now shown at program start in main.go
		if a.SystemPrompt != "" {
			if err := a.writeMessage("system", a.SystemPrompt); err != nil {
				return err
			}
		}

		configDir := os.Getenv("XDG_CONFIG_HOME")
		if configDir == "" {
			homeDir, _ := os.UserHomeDir()
			configDir = filepath.Join(homeDir, ".config")
		}
		hinataMdPath := filepath.Join(configDir, "hinata/agent/HINATA.md")
		if content, err := os.ReadFile(hinataMdPath); err == nil && len(content) > 0 {
			message := fmt.Sprintf("<info>\n%s\n</info>", string(content))
			if err := a.writeMessage("user", message); err != nil {
				return err
			}
		}
	} else {
		a.resumeSession()
	}

	a.humanTurnCounter++
	a.printUserMessage(userMessage)
	fmt.Println()
	fmt.Println()

	taggedMessage := fmt.Sprintf("<user_request>\n%s\n</user_request>", userMessage)
	if err := a.writeMessage("user", taggedMessage); err != nil {
		return err
	}

	for {
		a.turnCounter++

		llmContent, llmReasoning, err := a.streamLLMResponse()
		if err != nil {
			return fmt.Errorf("failed to generate LLM response: %w", err)
		}

		fmt.Println()

		// Save reasoning to separate file if present
		if llmReasoning != "" && !a.IgnoreReasoning {
			thinkContent := fmt.Sprintf("<think>%s</think>", llmReasoning)
			if err := a.writeMessage("assistant-reasoning", thinkContent); err != nil {
				return err
			}
		}

		// Save only content to assistant file
		if err := a.writeMessage("assistant", llmContent); err != nil {
			return err
		}

		// Combine for shell command extraction
		llmResponse := llmContent
		if llmReasoning != "" && !a.IgnoreReasoning {
			llmResponse = fmt.Sprintf("<think>%s</think>\n%s", llmReasoning, llmContent)
		}

		shellCommands := extractShellCommands(llmResponse)
		if len(shellCommands) == 0 {
			fmt.Fprint(os.Stderr, "\n")
			fmt.Fprint(os.Stderr, marginStr())
			a.theme.StatusMessage.Fprint(os.Stderr, "◦ Hinata did not suggest a shell block.\n")

			if a.AutoExit {
				return nil
			}

			newMessage := a.promptForMessage()
			if newMessage == "" {
				return fmt.Errorf("Aborted: User did not provide new instructions.")
			}

			a.humanTurnCounter++
			a.printUserMessage(newMessage)
			fmt.Println()
			fmt.Println()

			taggedMessage := fmt.Sprintf("<user_request>\n%s\n</user_request>", newMessage)
			if err := a.writeMessage("user", taggedMessage); err != nil {
				return err
			}
		} else {
			commands := shellCommands[len(shellCommands)-1]

			if !a.NoEscape {
				re := regexp.MustCompile(`(^|[^\\])` + "`")
				commands = re.ReplaceAllString(commands, "$1\\`")
			}

			if !a.NoConfirm {
				fmt.Fprint(os.Stderr, "\n")
				fmt.Fprint(os.Stderr, marginStr())
				a.theme.DefaultText.Fprint(os.Stderr, "Hinata wants to execute a shell block. Proceed?\n")
				choice := a.promptExecute()

				// Clear the prompt message and selection menu
				// Move up 1 line and clear from cursor to end
				fmt.Fprint(os.Stderr, "\033[1A\033[J")

				switch choice {
				case executeExit:
					return nil
				case executeSkip:
					fmt.Fprint(os.Stderr, marginStr())
					a.theme.StatusMessage.Fprint(os.Stderr, "◦ Chose to provide new instructions.\n")
					newMessage := a.promptForMessage()
					if newMessage == "" {
						return fmt.Errorf("no message provided")
					}

					a.humanTurnCounter++
					a.printUserMessage(newMessage)
					fmt.Println()
					fmt.Println()

					taggedMessage := fmt.Sprintf("<user_request>\n%s\n</user_request>", newMessage)
					if err := a.writeMessage("user", taggedMessage); err != nil {
						return err
					}
					continue
				case executeYes:
					fmt.Fprint(os.Stderr, marginStr())
					a.theme.StatusMessage.Fprint(os.Stderr, "◦ Executing command.\n")
					fmt.Fprintln(os.Stderr) // Add blank line before spinner
					// Continue with execution
				}
			}

			result, err := a.executeShellCommands(commands)
			if err != nil {
				return fmt.Errorf("shell execution error: %w", err)
			}

			if err := a.saveState(); err != nil {
				return fmt.Errorf("failed to save state: %w", err)
			}

			var resultMessage string
			if a.UseJSON {
				jsonResult := map[string]interface{}{
					"stdout":    result.Stdout,
					"stderr":    result.Stderr,
					"exit_code": result.ExitCode,
				}
				jsonBytes, _ := json.MarshalIndent(jsonResult, "", "  ")
				resultMessage = fmt.Sprintf("<shell-results>\n%s\n</shell-results>", string(jsonBytes))
			} else {
				resultMessage = formatShellResults(result)
			}

			if err := a.writeMessage("user", resultMessage); err != nil {
				return err
			}

			// Display shell output to the user
			if a.ShellDisplay {
				fmt.Println()
				a.printWithIndent(resultMessage)
				fmt.Println()
			} else {
				// Display colored output like Rust version
				stdoutContent := strings.TrimSpace(result.Stdout)
				stderrContent := strings.TrimSpace(result.Stderr)
				exitCode := result.ExitCode

				// Shell block already has proper spacing, no need for extra newline

				if stdoutContent != "" {
					a.theme.Stdout.Print(indentMultiline(stdoutContent))
					fmt.Println()
				}

				if stdoutContent != "" && stderrContent != "" {
					fmt.Println()
				}

				if stderrContent != "" {
					a.theme.Stderr.Print(indentMultiline(stderrContent))
					fmt.Println()
				}

				if stdoutContent != "" && stderrContent == "" && exitCode != 0 {
					fmt.Println()
				}

				if exitCode != 0 {
					exitMessage := fmt.Sprintf("🫀 exit code: %d", exitCode)
					a.theme.ExitCode.Print(indentMultiline(exitMessage))
					fmt.Println()
				}

				fmt.Println()
			}
		}
	}
}

func (a *Agent) streamLLMResponse() (string, string, error) {
	var packedBuf bytes.Buffer
	err := chat.PackConversation(a.ConversationDir, &packedBuf, false)
	if err != nil {
		return "", "", fmt.Errorf("failed to pack conversation: %w", err)
	}

	config := llm.Config{
		Model:            a.Model,
		IncludeReasoning: !a.IgnoreReasoning,
	}

	// Use V2 streaming if enabled, otherwise use buffered streaming
	if a.UseV2Streaming {
		return a.streamLLMResponseV2(config, packedBuf.String())
	}
	return a.streamLLMResponseBuffered(config, packedBuf.String())
}

// getSelectedSpinner returns the spinner based on agent configuration
func (a *Agent) getSelectedSpinner() spinner.Spinner {
	if a.customSpinner != nil {
		// Use custom spinner from file
		return *a.customSpinner
	} else if a.SpinnerIndex != nil && *a.SpinnerIndex < len(spinner.SPINNERS) {
		// Use spinner by index
		return spinner.SPINNERS[*a.SpinnerIndex]
	} else {
		// Use random spinner
		return spinner.GetRandomSpinner()
	}
}

func (a *Agent) executeShellCommands(commands string) (*shell.ExecutionResult, error) {
	// Use V2 spinner if enabled for better synchronization
	if a.UseV2Streaming {
		return a.executeShellCommandsV2(commands)
	}

	// Legacy implementation with sleep
	stopCh := make(chan bool)

	sp := a.getSelectedSpinner()

	msg := spinner.GetRandomLoadingMessage()

	go spinner.Run(sp, msg, marginStr(), stopCh, func(s string) {
		a.theme.Spinner.Print(s)
	})

	result, err := a.shellExecutor.Execute(commands)

	close(stopCh)
	time.Sleep(50 * time.Millisecond)

	return result, err
}

func (a *Agent) executeShellCommandsV2(commands string) (*shell.ExecutionResult, error) {
	sp := a.getSelectedSpinner()
	msg := spinner.GetRandomLoadingMessage()

	// Create output coordinator for shell execution
	coordinator := output.New(10)
	coordinator.Start()
	defer coordinator.Stop()

	// Show spinner
	coordinator.ShowSpinner(sp, msg, marginStr(), func(s string) {
		a.theme.Spinner.Print(s)
	})

	// Execute command
	result, err := a.shellExecutor.Execute(commands)

	// Hide spinner with proper synchronization
	coordinator.HideSpinner()
	coordinator.Flush() // Ensure all output is written

	return result, err
}

func (a *Agent) writeMessage(role, content string) error {
	chatRole, err := chat.ParseRole(role)
	if err != nil {
		return fmt.Errorf("invalid role %s: %w", role, err)
	}

	_, err = chat.WriteMessageFile(a.ConversationDir, chatRole, content)
	if err != nil {
		return fmt.Errorf("failed to write message: %w", err)
	}
	return nil
}

func (a *Agent) saveState() error {
	stateFile := filepath.Join(a.ConversationDir, "hnt-agent-state.json")
	state := a.shellExecutor.GetState()
	return shell.SaveState(state, stateFile)
}

func (a *Agent) printTurnHeader(role string, turn int) {
	width := getTerminalWidth()

	if a.logger != nil {
		a.logger.Printf("getTerminalWidth returned: %d", width)
	}

	var icon string
	var lineColor *color.Color

	switch role {
	case "hinata":
		icon = "❄️"
		lineColor = a.theme.HinataLine
	case "querent":
		icon = "🗝️"
		lineColor = a.theme.QuerentLine
	default:
		icon = "?"
		lineColor = a.theme.FallbackLine
	}

	roleText := fmt.Sprintf("%s %s", icon, role)
	turnText := fmt.Sprintf("turn %d", turn)
	prefix := "─────── "

	// Calculate visual width using runewidth
	marginPart := marginStr()
	prefixPart := prefix     // "─────── "
	roleTextPart := roleText // e.g. "🗝️ querent"
	bulletPart := " • "
	turnTextPart := turnText // e.g. "turn 1"
	spacePart := " "

	marginWidth := runewidth.StringWidth(marginPart)
	prefixWidth := runewidth.StringWidth(prefixPart)
	roleWidth := runewidth.StringWidth(roleTextPart)
	bulletWidth := runewidth.StringWidth(bulletPart)
	turnWidth := runewidth.StringWidth(turnTextPart)
	spaceWidth := runewidth.StringWidth(spacePart)

	// Emoji width correction: these emojis display as double-width but runewidth
	// may report them as single-width
	if icon == "❄️" || icon == "🗝️" {
		// Add 1 to compensate for emoji being double-width
		roleWidth += 1
	}

	totalFixedContent := prefixWidth + roleWidth + bulletWidth + turnWidth + spaceWidth

	if a.logger != nil {
		a.logger.Printf("=== printTurnHeader for '%s' turn %d ===", role, turn)
		a.logger.Printf("Terminal width: %d", width)
		a.logger.Printf("Parts to print:")
		a.logger.Printf("  1. margin: '%s' (width=%d)", marginPart, marginWidth)
		a.logger.Printf("  2. prefix: '%s' (width=%d)", prefixPart, prefixWidth)
		if icon == "❄️" || icon == "🗝️" {
			a.logger.Printf("  3. roleText: '%s' (width=%d, corrected for emoji)", roleTextPart, roleWidth)
		} else {
			a.logger.Printf("  3. roleText: '%s' (width=%d)", roleTextPart, roleWidth)
		}
		a.logger.Printf("  4. bullet: '%s' (width=%d)", bulletPart, bulletWidth)
		a.logger.Printf("  5. turnText: '%s' (width=%d)", turnTextPart, turnWidth)
		a.logger.Printf("  6. space: '%s' (width=%d)", spacePart, spaceWidth)
		a.logger.Printf("  7. line: will be repeated '─' characters")
		a.logger.Printf("Total fixed content width (2-6): %d", totalFixedContent)
	}

	// Calculate line length to ensure proper right margin
	// Terminal width: 88
	// We want the line to end at column 86 (leaving 2 spaces)
	// The content starts at column 3 (after 2-space margin)
	// So we have 84 columns for actual content (86 - 2)
	// Subtract the fixed content length to get the line length
	lineLen := (width - (MARGIN * 2)) - totalFixedContent
	if lineLen < 0 {
		lineLen = 0
	}

	line := strings.Repeat("─", lineLen)

	if a.logger != nil {
		a.logger.Printf("Line calculation:")
		a.logger.Printf("  Available width for content: %d - %d (both margins) = %d", width, MARGIN*2, width-(MARGIN*2))
		a.logger.Printf("  Fixed content uses: %d", totalFixedContent)
		a.logger.Printf("  Space left for line: %d - %d = %d", width-(MARGIN*2), totalFixedContent, lineLen)
		a.logger.Printf("  Line will be: '%s' (length=%d)", line, len(line))
		a.logger.Printf("Final total: %d (margin) + %d (fixed) + %d (line) = %d",
			marginWidth, totalFixedContent, lineLen, marginWidth+totalFixedContent+lineLen)
		a.logger.Printf("Expected to end at column: %d", marginWidth+totalFixedContent+lineLen)
		a.logger.Printf("Leaves %d columns at the end", width-(marginWidth+totalFixedContent+lineLen))
		a.logger.Printf("===")
	}

	fmt.Print(marginStr())
	lineColor.Print(prefix)
	a.theme.DefaultText.Print(roleText)
	lineColor.Print(" • ")
	a.theme.TurnNumber.Print(turnText)
	a.theme.DefaultText.Print(" ")
	lineColor.Print(line)
	fmt.Println()
}

func (a *Agent) promptContinue() bool {
	items := []string{"Retry LLM request.", "Quit."}

	var opts selector.Options
	opts.Height = 2

	if a.theme.Name == "snow" {
		// Use RGB colors for snow theme
		opts.BackgroundRGB = a.theme.BackgroundRGB
		opts.ForegroundRGB = a.theme.HinataLineRGB
		opts.PrefixRGB = a.theme.HinataLineRGB
		opts.NormalRGB = a.theme.DefaultTextRGB
		opts.HelpRGB = a.theme.HelpTextRGB
	} else {
		// Use ANSI color for ansi theme
		opts.Color = 4 // Blue
	}

	model := selector.New(items, opts)
	p := tea.NewProgram(model)

	finalModel, err := p.Run()
	if err != nil {
		return false
	}

	final := finalModel.(selector.Model)
	if final.Aborted() {
		return false
	}

	return final.Choice() == "Retry LLM request."
}

type executeChoice int

const (
	executeYes executeChoice = iota
	executeSkip
	executeExit
)

func (a *Agent) promptExecute() executeChoice {
	items := []string{
		"Confirm. Proceed to execute Hinata's shell block.",
		"Skip this execution. Provide new instructions instead.",
		"Exit the Hinata session.",
	}

	var opts selector.Options
	opts.Height = 3

	if a.theme.Name == "snow" {
		// Use RGB colors for snow theme
		opts.BackgroundRGB = a.theme.BackgroundRGB
		opts.ForegroundRGB = a.theme.HinataLineRGB
		opts.PrefixRGB = a.theme.HinataLineRGB
		opts.NormalRGB = a.theme.DefaultTextRGB
		opts.HelpRGB = a.theme.HelpTextRGB
	} else {
		// Use ANSI color for ansi theme
		opts.Color = 4 // Blue
	}

	model := selector.New(items, opts)
	p := tea.NewProgram(model)

	finalModel, err := p.Run()
	if err != nil {
		return executeExit
	}

	final := finalModel.(selector.Model)
	if final.Aborted() {
		return executeExit
	}

	switch final.Choice() {
	case "Confirm. Proceed to execute Hinata's shell block.":
		return executeYes
	case "Skip this execution. Provide new instructions instead.":
		return executeSkip
	default:
		return executeExit
	}
}

func (a *Agent) promptForMessage() string {
	// Print a blank line before showing the textarea during conversation
	fmt.Println()

	var instruction string
	var err error

	if a.theme.Name == "snow" {
		// Use RGB colors for snow theme
		colors := prompt.ColorConfig{
			HeaderRGB: a.theme.DefaultTextRGB,
			HelpRGB:   a.theme.HelpTextRGB,
			PromptRGB: a.theme.HinataLineRGB,
			TextRGB:   a.theme.DefaultTextRGB,
		}
		instruction, err = prompt.GetUserInstructionWithColorsAndHeight("", a.UseEditor, colors, a.PromptHeight)
	} else {
		// Use default colors for ansi theme
		instruction, err = prompt.GetUserInstructionWithHeight("", a.UseEditor, a.PromptHeight)
	}

	if err != nil {
		if a.UseEditor {
			fmt.Fprint(os.Stderr, marginStr())
			a.theme.DefaultText.Fprintf(os.Stderr, "Error: %v\n", err)
		}
		return ""
	}

	return instruction
}

func extractShellCommands(text string) []string {
	re := regexp.MustCompile(`(?s)<shell>(.*?)</shell>`)
	matches := re.FindAllStringSubmatch(text, -1)

	var commands []string
	for _, match := range matches {
		if len(match) > 1 {
			commands = append(commands, strings.TrimSpace(match[1]))
		}
	}

	return commands
}

func formatShellResults(result *shell.ExecutionResult) string {
	var parts []string
	parts = append(parts, "<shell-results>")

	if result.Stdout != "" {
		parts = append(parts, "<stdout>")
		parts = append(parts, result.Stdout)
		parts = append(parts, "</stdout>")
	}

	if result.Stderr != "" {
		parts = append(parts, "<stderr>")
		parts = append(parts, result.Stderr)
		parts = append(parts, "</stderr>")
	}

	parts = append(parts, fmt.Sprintf("<exit-code>%d</exit-code>", result.ExitCode))
	parts = append(parts, "</shell-results>")

	return strings.Join(parts, "\n")
}

func marginStr() string {
	return strings.Repeat(" ", MARGIN)
}

func (a *Agent) userMarginStr() string {
	return a.theme.UserMargin.Sprint("┆ ")
}

func (a *Agent) printUserMessage(text string) {
	if text == "" {
		return
	}

	lines := strings.Split(text, "\n")
	for i, line := range lines {
		// Print the margin (purple ┆)
		fmt.Print(a.userMarginStr())
		// Print the text in explicit white for snow theme
		a.theme.DefaultText.Print(line)
		if i < len(lines)-1 {
			fmt.Println()
		}
	}
}

func (a *Agent) printAssistantMessage(text string) {
	if text == "" {
		return
	}

	lines := strings.Split(text, "\n")
	for i, line := range lines {
		// Print the margin
		fmt.Print(marginStr())
		// Print the text in explicit white for snow theme
		a.theme.DefaultText.Print(line)
		if i < len(lines)-1 {
			fmt.Println()
		}
	}
}

func (a *Agent) printWithIndent(text string) {
	if text == "" {
		return
	}

	lines := strings.Split(text, "\n")
	for i, line := range lines {
		// Print the margin
		fmt.Print(marginStr())
		// Print the text in explicit white for snow theme
		a.theme.DefaultText.Print(line)
		if i < len(lines)-1 {
			fmt.Println()
		}
	}
}

func indentMultiline(text string) string {
	return indentMultilineWithMargin(text, marginStr())
}

func (a *Agent) indentMultilineUser(text string) string {
	return indentMultilineWithMargin(text, a.userMarginStr())
}

func indentMultilineWithMargin(text string, margin string) string {
	if text == "" {
		return ""
	}

	lines := strings.Split(text, "\n")
	for i := range lines {
		// Always add margin, even for empty lines
		lines[i] = margin + lines[i]
	}

	return strings.Join(lines, "\n")
}

func (a *Agent) isExistingSession() bool {
	entries, err := os.ReadDir(a.ConversationDir)
	if err != nil {
		return false
	}

	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), "-system.md") ||
			strings.HasSuffix(entry.Name(), "-user.md") ||
			strings.HasSuffix(entry.Name(), "-assistant.md") {
			return true
		}
	}

	return false
}

func (a *Agent) resumeSession() {
	entries, _ := os.ReadDir(a.ConversationDir)

	var assistantCount, userCount int
	var lastAssistantMessage string

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		name := entry.Name()
		if strings.HasSuffix(name, "-assistant.md") {
			assistantCount++
			content, _ := os.ReadFile(filepath.Join(a.ConversationDir, name))
			lastAssistantMessage = string(content)
		} else if strings.HasSuffix(name, "-user.md") {
			content, _ := os.ReadFile(filepath.Join(a.ConversationDir, name))
			if strings.Contains(string(content), "<user_request>") {
				userCount++
			}
		}
	}

	if lastAssistantMessage != "" {
		a.humanTurnCounter = userCount + 1
		a.turnCounter = assistantCount + 1

		a.printAssistantMessage(lastAssistantMessage)
		fmt.Println()
	}
}

func getTerminalWidth() int {
	width, _, err := term.GetSize(int(os.Stdout.Fd()))
	if err != nil {
		return 80
	}
	return width
}
