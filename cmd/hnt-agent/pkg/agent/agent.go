package agent

import (
	"bytes"
	"context"
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
	UseEditor       bool
	AutoExit        bool

	shellExecutor    *shell.Executor
	turnCounter      int
	humanTurnCounter int
	logger           *log.Logger
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
	UseEditor       bool
	AutoExit        bool
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

	executor := shell.NewExecutor(pwd)

	if existingPwd, err := os.ReadFile(filepath.Join(cfg.ConversationDir, "hnt-agent-pwd.txt")); err == nil {
		executor.WorkingDir = strings.TrimSpace(string(existingPwd))
	}

	if existingEnv, err := os.ReadFile(filepath.Join(cfg.ConversationDir, "hnt-agent-env.json")); err == nil {
		var env map[string]string
		if err := json.Unmarshal(existingEnv, &env); err == nil {
			executor.Env = env
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
		UseEditor:        cfg.UseEditor,
		AutoExit:         cfg.AutoExit,
		shellExecutor:    executor,
		turnCounter:      1,
		humanTurnCounter: 1,
		logger:           logger,
	}, nil
}

func (a *Agent) Run(userMessage string) error {
	isNewSession := !a.isExistingSession()

	if isNewSession {
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

	a.printTurnHeader("querent", a.humanTurnCounter)
	a.humanTurnCounter++
	fmt.Print(indentMultiline(userMessage))
	fmt.Println()
	fmt.Println()

	taggedMessage := fmt.Sprintf("<user_request>\n%s\n</user_request>", userMessage)
	if err := a.writeMessage("user", taggedMessage); err != nil {
		return err
	}

	for {
		a.printTurnHeader("hinata", a.turnCounter)
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
			fmt.Fprintf(os.Stderr, "\n%s-> Hinata did not suggest a shell block.\n", marginStr())

			if a.AutoExit {
				return nil
			}

			newMessage := a.promptForMessage()
			if newMessage == "" {
				return fmt.Errorf("Aborted: User did not provide new instructions.")
			}

			a.printTurnHeader("querent", a.humanTurnCounter)
			a.humanTurnCounter++
			fmt.Print(indentMultiline(newMessage))
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
				fmt.Fprintf(os.Stderr, "\n%sHinata wants to execute a shell block. Proceed?\n", marginStr())
				choice := a.promptExecute()

				// Clear the prompt message and selection menu
				// Move up 1 line and clear from cursor to end
				fmt.Fprint(os.Stderr, "\033[1A\033[J")

				switch choice {
				case executeExit:
					return nil
				case executeSkip:
					fmt.Fprintf(os.Stderr, "%s-> Chose to provide new instructions.\n", marginStr())
					newMessage := a.promptForMessage()
					if newMessage == "" {
						return fmt.Errorf("no message provided")
					}

					a.printTurnHeader("querent", a.humanTurnCounter)
					a.humanTurnCounter++
					fmt.Print(indentMultiline(newMessage))
					fmt.Println()
					fmt.Println()

					taggedMessage := fmt.Sprintf("<user_request>\n%s\n</user_request>", newMessage)
					if err := a.writeMessage("user", taggedMessage); err != nil {
						return err
					}
					continue
				case executeYes:
					fmt.Fprintf(os.Stderr, "%s-> Executing command.\n", marginStr())
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
				resultMessage = fmt.Sprintf("<hnt-shell-results>\n%s\n</hnt-shell-results>", string(jsonBytes))
			} else {
				resultMessage = formatShellResults(result)
			}

			if err := a.writeMessage("user", resultMessage); err != nil {
				return err
			}

			// Display shell output to the user
			if a.ShellDisplay {
				fmt.Println()
				fmt.Print(indentMultiline(resultMessage))
				fmt.Println()
			} else {
				// Display colored output like Rust version
				stdoutContent := strings.TrimSpace(result.Stdout)
				stderrContent := strings.TrimSpace(result.Stderr)
				exitCode := result.ExitCode

				// Only print blank line before output if there's any output to display
				hasOutput := stdoutContent != "" || stderrContent != "" || exitCode != 0
				if hasOutput {
					fmt.Println()
				}

				if stdoutContent != "" {
					cyan := color.New(color.FgCyan)
					cyan.Print(indentMultiline(stdoutContent))
					fmt.Println()
				}

				if stdoutContent != "" && stderrContent != "" {
					fmt.Println()
				}

				if stderrContent != "" {
					red := color.New(color.FgRed)
					red.Print(indentMultiline(stderrContent))
					fmt.Println()
				}

				if stdoutContent != "" && stderrContent == "" && exitCode != 0 {
					fmt.Println()
				}

				if exitCode != 0 {
					exitMessage := fmt.Sprintf("🫀 exit code: %d", exitCode)
					red := color.New(color.FgRed)
					red.Print(indentMultiline(exitMessage))
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

	ctx := context.Background()
	eventChan, errChan := llm.StreamLLMResponse(ctx, config, packedBuf.String())

	var response strings.Builder
	var reasoningBuffer strings.Builder
	termWidth := getTerminalWidth()
	wrapAt := termWidth - (MARGIN * 2)
	if wrapAt < 20 {
		wrapAt = 20 // Minimum wrap width
	}

	currentColumn := 0
	isFirstToken := true
	inReasoning := false
	yellow := color.New(color.FgYellow)

	// Buffer to accumulate partial content between chunks
	var contentBuffer strings.Builder
	var reasoningChunkBuffer strings.Builder

	// Hide cursor before streaming starts
	hideCursor()
	defer showCursor()

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				// Flush any remaining buffered content
				if contentBuffer.Len() > 0 {
					a.printWrappedText(contentBuffer.String(), &currentColumn, wrapAt, nil)
					contentBuffer.Reset()
				}
				if reasoningChunkBuffer.Len() > 0 {
					a.printWrappedText(reasoningChunkBuffer.String(), &currentColumn, wrapAt, yellow)
					reasoningChunkBuffer.Reset()
				}
				return response.String(), reasoningBuffer.String(), nil
			}

			if event.Content != "" {
				if a.logger != nil {
					a.logger.Printf("Received content chunk: %q (len=%d)", event.Content, len(event.Content))
				}

				if isFirstToken {
					fmt.Print(marginStr())
					currentColumn = 0
					isFirstToken = false
				}

				// Print content directly without buffering
				a.printWrappedText(event.Content, &currentColumn, wrapAt, nil)
				response.WriteString(event.Content)

				if a.logger != nil {
					a.logger.Printf("Current response so far: %q", response.String())
				}
			}

			if event.Reasoning != "" && !a.IgnoreReasoning {
				if isFirstToken {
					fmt.Print(marginStr())
					currentColumn = 0
					isFirstToken = false
				}

				if !inReasoning {
					inReasoning = true
				}

				// Print reasoning directly without buffering
				a.printWrappedText(event.Reasoning, &currentColumn, wrapAt, yellow)
				reasoningBuffer.WriteString(event.Reasoning)
			}
		case err := <-errChan:
			if err != nil {
				return "", "", fmt.Errorf("LLM request failed: %w\nModel: %s", err, a.Model)
			}
		}
	}
}

func (a *Agent) executeShellCommands(commands string) (*shell.ExecutionResult, error) {
	stopCh := make(chan bool)

	sp := spinner.GetRandomSpinner()
	if a.SpinnerIndex != nil && *a.SpinnerIndex < len(spinner.SPINNERS) {
		sp = spinner.SPINNERS[*a.SpinnerIndex]
	}

	msg := spinner.GetRandomLoadingMessage()

	go spinner.Run(sp, msg, marginStr(), stopCh)

	result, err := a.shellExecutor.Execute(commands)

	close(stopCh)
	time.Sleep(50 * time.Millisecond)

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
	pwdFile := filepath.Join(a.ConversationDir, "hnt-agent-pwd.txt")
	if err := os.WriteFile(pwdFile, []byte(a.shellExecutor.WorkingDir), 0644); err != nil {
		return err
	}

	envFile := filepath.Join(a.ConversationDir, "hnt-agent-env.json")
	envData, err := json.MarshalIndent(a.shellExecutor.Env, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(envFile, envData, 0644)
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
		lineColor = color.New(color.FgBlue)
	case "querent":
		icon = "🗝️"
		lineColor = color.New(color.FgMagenta)
	default:
		icon = "?"
		lineColor = color.New(color.FgWhite)
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
	fmt.Print(roleText)
	lineColor.Print(" • ")
	green := color.New(color.FgGreen)
	green.Print(turnText)
	fmt.Print(" ")
	lineColor.Print(line)
	fmt.Println()
}

func (a *Agent) promptContinue() bool {
	items := []string{"Retry LLM request.", "Quit."}
	opts := selector.Options{
		Height: 2,
		Color:  4, // Blue
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
	opts := selector.Options{
		Height: 3,
		Color:  4, // Blue
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

	instruction, err := prompt.GetUserInstruction("", a.UseEditor)
	if err != nil {
		if a.UseEditor {
			fmt.Fprintf(os.Stderr, "%sError: %v\n", marginStr(), err)
		}
		return ""
	}

	return instruction
}

func extractShellCommands(text string) []string {
	re := regexp.MustCompile(`(?s)<hnt-shell>(.*?)</hnt-shell>`)
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
	parts = append(parts, "<hnt-shell-results>")

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
	parts = append(parts, "</hnt-shell-results>")

	return strings.Join(parts, "\n")
}

func marginStr() string {
	return strings.Repeat(" ", MARGIN)
}

func indentMultiline(text string) string {
	if text == "" {
		return ""
	}

	lines := strings.Split(text, "\n")
	for i := range lines {
		if lines[i] != "" {
			lines[i] = marginStr() + lines[i]
		}
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

		a.printTurnHeader("hinata", assistantCount)
		fmt.Print(indentMultiline(lastAssistantMessage))
		fmt.Println()
	}
}

func (a *Agent) printWrappedText(text string, currentColumn *int, wrapAt int, colorFunc *color.Color) {
	if a.logger != nil {
		a.logger.Printf("printWrappedText called with: %q (currentColumn=%d, wrapAt=%d)", text, *currentColumn, wrapAt)
	}

	// Process character by character to preserve exact spacing
	for i := 0; i < len(text); i++ {
		ch := text[i]

		if ch == '\n' {
			// Handle newline
			fmt.Println()
			fmt.Print(marginStr())
			*currentColumn = 0
		} else if ch == ' ' {
			// Handle space - check if we need to wrap
			if *currentColumn >= wrapAt {
				fmt.Println()
				fmt.Print(marginStr())
				*currentColumn = 0
			} else {
				// Print the space
				if colorFunc != nil {
					colorFunc.Print(" ")
				} else {
					fmt.Print(" ")
				}
				*currentColumn++
			}
		} else {
			// For non-space characters, find the whole word
			wordStart := i
			for i < len(text) && text[i] != ' ' && text[i] != '\n' {
				i++
			}
			word := text[wordStart:i]
			i-- // Back up one since the loop will increment

			// Check if word fits on current line
			if *currentColumn > 0 && *currentColumn+len(word) > wrapAt {
				fmt.Println()
				fmt.Print(marginStr())
				*currentColumn = 0
			}

			// Print the word
			if colorFunc != nil {
				colorFunc.Print(word)
			} else {
				fmt.Print(word)
			}
			*currentColumn += len(word)
		}
	}
}

func (a *Agent) printWord(word string, currentColumn *int, wrapAt int, colorFunc *color.Color) {
	wordLen := len(word)

	// If word is longer than wrap width, print it anyway
	if *currentColumn > 0 && *currentColumn+wordLen > wrapAt && wordLen < wrapAt {
		fmt.Println()
		fmt.Print(marginStr())
		*currentColumn = 0
	}

	if colorFunc != nil {
		colorFunc.Print(word)
	} else {
		fmt.Print(word)
	}
	*currentColumn += wordLen
}

func getTerminalWidth() int {
	width, _, err := term.GetSize(int(os.Stdout.Fd()))
	if err != nil {
		return 80
	}
	return width
}

func hideCursor() {
	fmt.Print("\033[?25l")
}

func showCursor() {
	fmt.Print("\033[?25h")
}
