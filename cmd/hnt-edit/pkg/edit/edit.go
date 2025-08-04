package edit

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/veilm/hinata/cmd/hnt-apply/pkg/apply"
	"github.com/veilm/hinata/cmd/hnt-chat/pkg/chat"
	"github.com/veilm/hinata/cmd/hnt-llm/pkg/llm"
	"github.com/veilm/hinata/cmd/llm-pack/pkg/pack"
	"github.com/veilm/hinata/pkg/prompt"
)

type Options struct {
	System          string
	Message         string
	SourceFiles     []string
	Model           string
	ContinueDir     string
	UseEditor       bool
	IgnoreReasoning bool
	Verbose         bool
	DebugUnsafe     bool
}

type CreatedFilesGuard struct {
	files []string
}

func NewCreatedFilesGuard() *CreatedFilesGuard {
	return &CreatedFilesGuard{
		files: make([]string, 0),
	}
}

func (g *CreatedFilesGuard) Add(path string) {
	g.files = append(g.files, path)
}

func (g *CreatedFilesGuard) Cleanup() {
	for _, file := range g.files {
		if info, err := os.Stat(file); err == nil && info.Size() == 0 {
			os.Remove(file)
		}
	}
}

func GetUserInstruction(message string, useEditor bool) (string, bool, error) {
	instruction, err := prompt.GetUserInstruction(message, useEditor)
	if err != nil {
		return "", false, err
	}
	return instruction, true, nil
}

func GetSystemMessage(systemArg string) (string, error) {
	if systemArg != "" {
		// Check if it's a file path
		if content, err := os.ReadFile(systemArg); err == nil {
			return string(content), nil
		}
		// Otherwise treat as literal string
		return systemArg, nil
	}

	// Try default locations
	configDir := os.Getenv("XDG_CONFIG_HOME")
	if configDir == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("could not determine home directory: %w", err)
		}
		configDir = filepath.Join(homeDir, ".config")
	}

	defaultPath := filepath.Join(configDir, "hinata/prompts/hnt-edit/main-file_edit.md")
	content, err := os.ReadFile(defaultPath)
	if err != nil {
		// Return error instead of fallback
		return "", fmt.Errorf("no system prompt provided and default not found at %s: %w", defaultPath, err)
	}
	return string(content), nil
}

func PrintUserInstructions(instruction string) error {
	width := 80 // Default width
	if term := os.Getenv("COLUMNS"); term != "" {
		fmt.Sscanf(term, "%d", &width)
	}

	title := "┌─ User Instructions "
	header := title + strings.Repeat("─", width-len(title))
	footer := strings.Repeat("─", width)

	headerStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("14"))
	fmt.Println(headerStyle.Render(header))
	fmt.Println(strings.TrimRight(instruction, "\n"))
	fmt.Println(headerStyle.Render(footer))
	fmt.Println()

	return nil
}

func Run(opts Options) error {
	// Validate inputs
	if opts.ContinueDir == "" && len(opts.SourceFiles) == 0 {
		return fmt.Errorf("source_files are required when not using --continue-dir")
	}

	// Create guard for cleanup
	guard := NewCreatedFilesGuard()
	defer guard.Cleanup()

	// Create missing files
	for _, file := range opts.SourceFiles {
		if _, err := os.Stat(file); os.IsNotExist(err) {
			dir := filepath.Dir(file)
			if dir != "" && dir != "." {
				if _, err := os.Stat(dir); os.IsNotExist(err) {
					pwd, _ := os.Getwd()
					return fmt.Errorf("parent dir '%s' does not exist for file '%s'\nNote: current pwd is '%s'", dir, file, pwd)
				}
			}
			if err := os.WriteFile(file, []byte{}, 0644); err != nil {
				return fmt.Errorf("failed to create file %s: %w", file, err)
			}
			guard.Add(file)
		}
	}

	var conversationDir string
	var sourceFiles []string
	var absolutePaths []string

	if opts.ContinueDir != "" {
		// Continue from existing conversation
		fmt.Fprintf(os.Stderr, "Continuing conversation from: %s\n", opts.ContinueDir)

		if _, err := os.Stat(opts.ContinueDir); os.IsNotExist(err) {
			return fmt.Errorf("continue directory not found: %s", opts.ContinueDir)
		}

		// Read absolute file paths
		absPathsContent, err := os.ReadFile(filepath.Join(opts.ContinueDir, "absolute_file_paths.txt"))
		if err != nil {
			return fmt.Errorf("failed to read absolute_file_paths.txt: %w", err)
		}

		for _, line := range strings.Split(string(absPathsContent), "\n") {
			if line = strings.TrimSpace(line); line != "" {
				absolutePaths = append(absolutePaths, line)
				sourceFiles = append(sourceFiles, line)
			}
		}

		// Repack files
		packed, err := packFiles(sourceFiles)
		if err != nil {
			return fmt.Errorf("failed to pack source files: %w", err)
		}

		// Update source reference
		sourceRefContent, err := os.ReadFile(filepath.Join(opts.ContinueDir, "source_reference.txt"))
		if err != nil {
			return fmt.Errorf("failed to read source_reference.txt: %w", err)
		}

		sourceRefFile := filepath.Join(opts.ContinueDir, strings.TrimSpace(string(sourceRefContent)))
		newContent := fmt.Sprintf("<source_reference>\n%s</source_reference>\n", packed)
		if err := os.WriteFile(sourceRefFile, []byte(newContent), 0644); err != nil {
			return fmt.Errorf("failed to update source reference: %w", err)
		}

		conversationDir = opts.ContinueDir
	} else {
		// New conversation
		systemMessage, err := GetSystemMessage(opts.System)
		if err != nil {
			return fmt.Errorf("failed to get system message: %w", err)
		}

		instruction, fromEditor, err := GetUserInstruction(opts.Message, opts.UseEditor)
		if err != nil {
			return err
		}

		if fromEditor {
			PrintUserInstructions(instruction)
		}

		// Get absolute paths
		for _, file := range opts.SourceFiles {
			absPath, err := filepath.Abs(file)
			if err != nil {
				return fmt.Errorf("failed to get absolute path for %s: %w", file, err)
			}
			absolutePaths = append(absolutePaths, absPath)
			sourceFiles = append(sourceFiles, absPath)
		}

		// Pack files
		packed, err := packFiles(sourceFiles)
		if err != nil {
			return fmt.Errorf("failed to pack source files: %w", err)
		}

		// Create new conversation
		baseDir, err := chat.GetConversationsDir()
		if err != nil {
			return fmt.Errorf("failed to get conversations directory: %w", err)
		}

		conversationDir, err = chat.CreateNewConversation(baseDir)
		if err != nil {
			return fmt.Errorf("failed to create conversation: %w", err)
		}

		// Save absolute paths
		absPathsContent := strings.Join(absolutePaths, "\n")
		if err := os.WriteFile(filepath.Join(conversationDir, "absolute_file_paths.txt"), []byte(absPathsContent), 0644); err != nil {
			return fmt.Errorf("failed to write absolute paths: %w", err)
		}

		// Write messages
		if _, err := chat.WriteMessageFile(conversationDir, chat.RoleSystem, systemMessage); err != nil {
			return fmt.Errorf("failed to write system message: %w", err)
		}

		userRequest := fmt.Sprintf("<user_request>\n%s\n</user_request>", instruction)
		if _, err := chat.WriteMessageFile(conversationDir, chat.RoleUser, userRequest); err != nil {
			return fmt.Errorf("failed to write user request: %w", err)
		}

		sourceReference := fmt.Sprintf("<source_reference>\n%s</source_reference>", packed)
		sourceRefFilename, err := chat.WriteMessageFile(conversationDir, chat.RoleUser, sourceReference)
		if err != nil {
			return fmt.Errorf("failed to write source reference: %w", err)
		}

		if err := os.WriteFile(filepath.Join(conversationDir, "source_reference.txt"), []byte(sourceRefFilename), 0644); err != nil {
			return fmt.Errorf("failed to write source reference filename: %w", err)
		}
	}

	// Determine model
	model := opts.Model
	if model == "" {
		model = os.Getenv("HINATA_EDIT_MODEL")
		if model == "" {
			model = os.Getenv("HINATA_MODEL")
			if model == "" {
				model = "openrouter/google/gemini-2.5-pro"
			}
		}
	}

	// Pack conversation for LLM
	var packedConv strings.Builder
	if err := chat.PackConversation(conversationDir, &packedConv, true); err != nil {
		return fmt.Errorf("failed to pack conversation: %w", err)
	}

	// Stream LLM response
	config := llm.Config{
		Model:            model,
		SystemPrompt:     "",
		IncludeReasoning: !opts.IgnoreReasoning || opts.DebugUnsafe,
	}

	ctx := context.Background()
	eventChan, errChan := llm.StreamLLMResponse(ctx, config, packedConv.String())

	var contentBuffer strings.Builder
	var reasoningBuffer strings.Builder
	inReasoningBlock := false

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				goto done
			}

			if event.Content != "" {
				if inReasoningBlock {
					// End reasoning block with proper spacing
					trailing := 0
					for i := len(reasoningBuffer.String()) - 1; i >= 0 && reasoningBuffer.String()[i] == '\n'; i-- {
						trailing++
					}
					for i := 0; i < 2-trailing; i++ {
						fmt.Println()
					}
					inReasoningBlock = false
				}
				fmt.Print(event.Content)
				contentBuffer.WriteString(event.Content)
			}

			if event.Reasoning != "" && !opts.IgnoreReasoning {
				inReasoningBlock = true
				// Print reasoning with yellow color without lipgloss padding
				fmt.Print("\033[33m" + event.Reasoning + "\033[0m")
				reasoningBuffer.WriteString(event.Reasoning)
			}

		case err := <-errChan:
			if err != nil {
				return fmt.Errorf("LLM stream error: %w", err)
			}
		}
	}

done:
	if inReasoningBlock {
		trailing := 0
		for i := len(reasoningBuffer.String()) - 1; i >= 0 && reasoningBuffer.String()[i] == '\n'; i-- {
			trailing++
		}
		for i := 0; i < 2-trailing; i++ {
			fmt.Println()
		}
	}
	fmt.Println()

	// Save messages
	if !opts.IgnoreReasoning && reasoningBuffer.Len() > 0 {
		reasoningMessage := fmt.Sprintf("<think>%s</think>", reasoningBuffer.String())
		if _, err := chat.WriteMessageFile(conversationDir, chat.RoleAssistantReasoning, reasoningMessage); err != nil {
			return fmt.Errorf("failed to write reasoning message: %w", err)
		}
	}

	if _, err := chat.WriteMessageFile(conversationDir, chat.RoleAssistant, contentBuffer.String()); err != nil {
		return fmt.Errorf("failed to write assistant message: %w", err)
	}

	if strings.TrimSpace(contentBuffer.String()) == "" {
		return fmt.Errorf("LLM produced no output. Aborting before running hnt-apply")
	}

	fmt.Fprintf(os.Stderr, "\nhnt-chat dir: %s\n", conversationDir)

	// Run hnt-apply
	if err := apply.ApplyChanges(sourceFiles, false, opts.IgnoreReasoning, opts.Verbose, contentBuffer.String()); err != nil {
		failureMessage := fmt.Sprintf("<hnt_apply_error>\n%s</hnt_apply_error>", err)
		chat.WriteMessageFile(conversationDir, chat.RoleUser, failureMessage)
		return fmt.Errorf("hnt-apply failed: %w", err)
	}

	return nil
}

func packFiles(paths []string) (string, error) {
	if len(paths) == 0 {
		return "", nil
	}

	// Use the pack library directly
	packed, err := pack.PackFiles(paths)
	if err != nil {
		return "", err
	}

	// Wrap in code fences
	return fmt.Sprintf("```\n%s\n```", packed), nil
}
