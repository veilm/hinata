package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/cmd/hnt-chat/pkg/chat"
	"github.com/veilm/hinata/cmd/hnt-llm/pkg/llm"
	"golang.org/x/term"
)

var (
	conversationPath  string
	merge             bool
	write             bool
	outputFilename    bool
	includeReasoning  bool
	separateReasoning bool
	model             string
	debugUnsafe       bool
)

func main() {
	var rootCmd = &cobra.Command{
		Use:           "hnt-chat",
		Short:         "Hinata Chat CLI tool",
		SilenceUsage:  true,
		SilenceErrors: true,
	}

	var newCmd = &cobra.Command{
		Use:          "new",
		Aliases:      []string{"new-conversation"},
		Short:        "Create a new conversation directory",
		RunE:         handleNewCommand,
		SilenceUsage: true,
	}

	var addCmd = &cobra.Command{
		Use:          "add [role]",
		Aliases:      []string{"add-message"},
		Short:        "Add a message to a conversation",
		Args:         cobra.ExactArgs(1),
		RunE:         handleAddCommand,
		SilenceUsage: true,
	}
	addCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")
	addCmd.Flags().BoolVar(&separateReasoning, "separate-reasoning", false, "For assistant role, save <think> content separately")

	var packCmd = &cobra.Command{
		Use:          "pack",
		Aliases:      []string{"package"},
		Short:        "Pack conversation messages for processing",
		RunE:         handlePackCommand,
		SilenceUsage: true,
	}
	packCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")
	packCmd.Flags().BoolVar(&merge, "merge", false, "Merge consecutive messages from same author")

	var genCmd = &cobra.Command{
		Use:          "gen",
		Short:        "Generate the next message in a conversation",
		RunE:         handleGenCommand,
		SilenceUsage: true,
	}
	genCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")
	genCmd.Flags().BoolVarP(&write, "write", "w", false, "Write generated output as new assistant message")
	genCmd.Flags().BoolVar(&outputFilename, "output-filename", false, "Print filename of created message")
	genCmd.Flags().BoolVar(&includeReasoning, "include-reasoning", false, "Include reasoning in output")
	genCmd.Flags().BoolVar(&merge, "merge", false, "Merge consecutive messages from same author")
	genCmd.Flags().StringVar(&model, "model", "", "Model to use for LLM")
	genCmd.Flags().BoolVar(&debugUnsafe, "debug-unsafe", false, "Enable unsafe debugging options")

	var listCmd = &cobra.Command{
		Use:          "list",
		Aliases:      []string{"ls"},
		Short:        "List all conversations",
		RunE:         handleListCommand,
		SilenceUsage: true,
	}

	var pinCmd = &cobra.Command{
		Use:          "pin",
		Short:        "Pin a conversation",
		RunE:         handlePinCommand,
		SilenceUsage: true,
	}
	pinCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")

	var unpinCmd = &cobra.Command{
		Use:          "unpin",
		Short:        "Unpin a conversation",
		RunE:         handleUnpinCommand,
		SilenceUsage: true,
	}
	unpinCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")

	var forkCmd = &cobra.Command{
		Use:          "fork",
		Short:        "Fork a conversation",
		RunE:         handleForkCommand,
		SilenceUsage: true,
	}
	forkCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")

	var titleCmd = &cobra.Command{
		Use:          "title [title]",
		Short:        "Set conversation title",
		Args:         cobra.ExactArgs(1),
		RunE:         handleTitleCommand,
		SilenceUsage: true,
	}
	titleCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")

	rootCmd.AddCommand(newCmd, addCmd, packCmd, genCmd, listCmd, pinCmd, unpinCmd, forkCmd, titleCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func handleNewCommand(cmd *cobra.Command, args []string) error {
	baseConvDir, err := chat.GetConversationsDir()
	if err != nil {
		return fmt.Errorf("failed to determine conversations directory: %w", err)
	}

	newConvPath, err := chat.CreateNewConversation(baseConvDir)
	if err != nil {
		return fmt.Errorf("failed to create new conversation: %w", err)
	}

	absolutePath, err := filepath.Abs(newConvPath)
	if err != nil {
		return fmt.Errorf("failed to get absolute path: %w", err)
	}

	fmt.Println(absolutePath)
	return nil
}

func handleAddCommand(cmd *cobra.Command, args []string) error {
	role, err := chat.ParseRole(args[0])
	if err != nil {
		return err
	}

	convDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	content, err := io.ReadAll(os.Stdin)
	if err != nil {
		return fmt.Errorf("failed to read from stdin: %w", err)
	}

	contentStr := string(content)

	if role == chat.RoleAssistant && separateReasoning && strings.HasPrefix(contentStr, "<think>") {
		if endPos := strings.Index(contentStr, "</think>"); endPos != -1 {
			splitPos := endPos + len("</think>")
			reasoningContent := contentStr[:splitPos]
			mainContent := strings.TrimLeft(contentStr[splitPos:], " \t\n")

			if _, err := chat.WriteMessageFile(convDir, chat.RoleAssistantReasoning, reasoningContent); err != nil {
				return fmt.Errorf("failed to write reasoning file: %w", err)
			}

			relativePath, err := chat.WriteMessageFile(convDir, chat.RoleAssistant, mainContent)
			if err != nil {
				return fmt.Errorf("failed to write assistant message: %w", err)
			}

			fmt.Println(relativePath)
			return nil
		}
	}

	relativePath, err := chat.WriteMessageFile(convDir, role, contentStr)
	if err != nil {
		return fmt.Errorf("failed to write message file: %w", err)
	}

	fmt.Println(relativePath)
	return nil
}

func handlePackCommand(cmd *cobra.Command, args []string) error {
	convDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	if err := chat.PackConversation(convDir, os.Stdout, merge); err != nil {
		return fmt.Errorf("failed to pack conversation: %w", err)
	}

	return nil
}

func handleGenCommand(cmd *cobra.Command, args []string) error {
	convDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	// Model precedence: --model flag > HINATA_CHAT_MODEL > HINATA_MODEL > default
	if model == "" {
		model = os.Getenv("HINATA_CHAT_MODEL")
		if model == "" {
			model = os.Getenv("HINATA_MODEL")
			if model == "" {
				model = "openrouter/google/gemini-2.5-pro"
			}
		}
	}

	shouldWrite := write || outputFilename

	if model != "" && cmd.Flags().Changed("model") {
		modelPath := filepath.Join(convDir, "model.txt")
		if err := os.WriteFile(modelPath, []byte(model), 0644); err != nil {
			return fmt.Errorf("failed to write model file: %w", err)
		}
	}

	var buf bytes.Buffer
	if err := chat.PackConversation(convDir, &buf, merge); err != nil {
		return fmt.Errorf("failed to pack conversation: %w", err)
	}

	config := llm.Config{
		Model:            model,
		SystemPrompt:     "",
		IncludeReasoning: debugUnsafe || includeReasoning,
	}

	ctx := context.Background()
	eventChan, errChan := llm.StreamLLMResponse(ctx, config, buf.String())

	var contentBuffer strings.Builder
	var reasoningBuffer strings.Builder
	hasThinkTag := false

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				goto done
			}

			if event.Content != "" {
				if !outputFilename {
					if hasThinkTag {
						fmt.Print("</think>\n")
						hasThinkTag = false
					}
					fmt.Print(event.Content)
				}
				contentBuffer.WriteString(event.Content)
			}

			if event.Reasoning != "" && (includeReasoning || debugUnsafe) {
				if !outputFilename {
					if !hasThinkTag {
						fmt.Print("<think>")
						hasThinkTag = true
					}
					fmt.Print(event.Reasoning)
				}
				reasoningBuffer.WriteString(event.Reasoning)
			}

		case err := <-errChan:
			if err != nil {
				return fmt.Errorf("error from LLM stream: %w", err)
			}
		}
	}

done:
	if !outputFilename && hasThinkTag {
		fmt.Print("</think>\n")
	}

	var assistantFilePath string

	if shouldWrite {
		if includeReasoning {
			if reasoningBuffer.Len() > 0 {
				reasoningContent := fmt.Sprintf("<think>%s</think>", reasoningBuffer.String())
				if _, err := chat.WriteMessageFile(convDir, chat.RoleAssistantReasoning, reasoningContent); err != nil {
					return fmt.Errorf("failed to write reasoning file: %w", err)
				}
			}
			path, err := chat.WriteMessageFile(convDir, chat.RoleAssistant, contentBuffer.String())
			if err != nil {
				return fmt.Errorf("failed to write assistant message: %w", err)
			}
			assistantFilePath = path
		} else {
			fullResponse := contentBuffer.String()
			if reasoningBuffer.Len() > 0 {
				fullResponse = fmt.Sprintf("<think>%s</think>\n%s", reasoningBuffer.String(), contentBuffer.String())
			}

			if fullResponse != "" {
				path, err := chat.WriteMessageFile(convDir, chat.RoleAssistant, fullResponse)
				if err != nil {
					return fmt.Errorf("failed to write assistant message: %w", err)
				}
				assistantFilePath = path
			}
		}
	}

	if outputFilename && assistantFilePath != "" {
		fmt.Println(assistantFilePath)
	}

	return nil
}

func isatty() bool {
	return term.IsTerminal(int(os.Stdout.Fd()))
}

func handleListCommand(cmd *cobra.Command, args []string) error {
	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		return fmt.Errorf("failed to get conversations directory: %w", err)
	}

	entries, err := os.ReadDir(baseDir)
	if err != nil {
		// No conversations yet
		fmt.Println("No conversations found.")
		return nil
	}

	type ConversationInfo struct {
		ID         string
		Title      string
		IsPinned   bool
		ForkSource string
		HasForks   bool
	}

	var conversations []ConversationInfo
	forkMap := make(map[string][]string) // Maps root conversation to its forks

	// First pass: collect all conversations and build fork relationships
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		convDir := filepath.Join(baseDir, entry.Name())
		conv := ConversationInfo{
			ID:    entry.Name(),
			Title: entry.Name(),
		}

		// Check for title file
		titlePath := filepath.Join(convDir, "title.txt")
		if data, err := os.ReadFile(titlePath); err == nil {
			conv.Title = strings.TrimSpace(string(data))
		}

		// Check for pin file
		pinPath := filepath.Join(convDir, "pinned.txt")
		if _, err := os.Stat(pinPath); err == nil {
			conv.IsPinned = true
		}

		// Check for fork_source.txt
		forkSourcePath := filepath.Join(convDir, "fork_source.txt")
		if data, err := os.ReadFile(forkSourcePath); err == nil {
			conv.ForkSource = strings.TrimSpace(string(data))
			// Add to fork map
			if conv.ForkSource != "" {
				forkMap[conv.ForkSource] = append(forkMap[conv.ForkSource], conv.ID)
			}
		}

		conversations = append(conversations, conv)
	}

	// Second pass: mark conversations that have forks
	for i := range conversations {
		if forks, exists := forkMap[conversations[i].ID]; exists && len(forks) > 0 {
			conversations[i].HasForks = true
		}
	}

	// Sort: pinned first, then by ID (newest first)
	sort.Slice(conversations, func(i, j int) bool {
		if conversations[i].IsPinned != conversations[j].IsPinned {
			return conversations[i].IsPinned
		}
		return conversations[i].ID > conversations[j].ID
	})

	// Print conversations
	if len(conversations) == 0 {
		fmt.Println("No conversations found.")
		return nil
	}

	// Find max width for ID column for alignment
	maxIDLen := 0
	for _, conv := range conversations {
		if len(conv.ID) > maxIDLen {
			maxIDLen = len(conv.ID)
		}
	}

	// Print header
	fmt.Printf("%-*s  %-10s  %s\n", maxIDLen, "ID", "Status", "Title")
	fmt.Printf("%s  %s  %s\n", strings.Repeat("-", maxIDLen), strings.Repeat("-", 10), strings.Repeat("-", 40))

	// Print conversations
	for _, conv := range conversations {
		var statusParts []string

		if conv.IsPinned {
			// Print [P] in cyan if terminal supports color
			if isatty() {
				statusParts = append(statusParts, "\033[36m[P]\033[0m")
			} else {
				statusParts = append(statusParts, "[P]")
			}
		}
		if conv.ForkSource != "" {
			statusParts = append(statusParts, "→")
		}
		if conv.HasForks {
			statusParts = append(statusParts, "❖")
		}

		status := strings.Join(statusParts, " ")
		if status == "" {
			status = "-"
		}

		fmt.Printf("%-*s  %-10s  %s\n", maxIDLen, conv.ID, status, conv.Title)
	}

	// Print legend
	legendParts := []string{}
	if isatty() {
		legendParts = append(legendParts, "\033[36m[P]\033[0m = Pinned")
	} else {
		legendParts = append(legendParts, "[P] = Pinned")
	}
	legendParts = append(legendParts, "→ = Fork", "❖ = Has forks")
	fmt.Printf("\nLegend: %s\n", strings.Join(legendParts, ", "))

	return nil
}

func handlePinCommand(cmd *cobra.Command, args []string) error {
	convDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	pinPath := filepath.Join(convDir, "pinned.txt")
	if err := os.WriteFile(pinPath, []byte(""), 0644); err != nil {
		return fmt.Errorf("failed to pin conversation: %w", err)
	}

	fmt.Printf("Conversation pinned: %s\n", filepath.Base(convDir))
	return nil
}

func handleUnpinCommand(cmd *cobra.Command, args []string) error {
	convDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	pinPath := filepath.Join(convDir, "pinned.txt")
	if err := os.Remove(pinPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("failed to unpin conversation: %w", err)
	}

	fmt.Printf("Conversation unpinned: %s\n", filepath.Base(convDir))
	return nil
}

func handleForkCommand(cmd *cobra.Command, args []string) error {
	sourceDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		return fmt.Errorf("failed to get conversations directory: %w", err)
	}

	// Create new conversation
	newConvDir, err := chat.CreateNewConversation(baseDir)
	if err != nil {
		return fmt.Errorf("failed to create new conversation: %w", err)
	}

	// Copy all files from source to new conversation
	entries, err := os.ReadDir(sourceDir)
	if err != nil {
		return fmt.Errorf("failed to read source conversation: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		// Skip fork tracking files - we'll set our own
		if entry.Name() == "fork_source.txt" || entry.Name() == "forks.txt" {
			continue
		}

		srcPath := filepath.Join(sourceDir, entry.Name())
		dstPath := filepath.Join(newConvDir, entry.Name())

		srcData, err := os.ReadFile(srcPath)
		if err != nil {
			continue
		}

		os.WriteFile(dstPath, srcData, 0644)
	}

	sourceID := filepath.Base(sourceDir)
	newID := filepath.Base(newConvDir)

	// Handle fork tracking
	// 1. Check if source has a fork_source.txt (meaning it's already a fork)
	var rootID string
	forkSourcePath := filepath.Join(sourceDir, "fork_source.txt")
	if data, err := os.ReadFile(forkSourcePath); err == nil {
		// Source is a fork, use its root
		rootID = strings.TrimSpace(string(data))
	} else {
		// Source is a root, use it as the root
		rootID = sourceID
	}

	// 2. Write fork_source.txt to the new conversation
	newForkSourcePath := filepath.Join(newConvDir, "fork_source.txt")
	if err := os.WriteFile(newForkSourcePath, []byte(rootID), 0644); err != nil {
		return fmt.Errorf("failed to write fork_source.txt: %w", err)
	}

	// 3. Append new conversation ID to root's forks.txt
	rootDir := filepath.Join(baseDir, rootID)
	forksPath := filepath.Join(rootDir, "forks.txt")

	// Read existing forks
	var forks []string
	if data, err := os.ReadFile(forksPath); err == nil {
		existing := strings.TrimSpace(string(data))
		if existing != "" {
			forks = strings.Split(existing, "\n")
		}
	}

	// Append new fork ID
	forks = append(forks, newID)
	forksData := strings.Join(forks, "\n")

	if err := os.WriteFile(forksPath, []byte(forksData), 0644); err != nil {
		// Non-fatal error
		fmt.Fprintf(os.Stderr, "Warning: Failed to update root's forks.txt: %v\n", err)
	}

	fmt.Printf("Forked conversation %s -> %s\n", sourceID, newID)
	fmt.Println(newConvDir)
	return nil
}

func handleTitleCommand(cmd *cobra.Command, args []string) error {
	convDir, err := determineConversationDir(conversationPath)
	if err != nil {
		return fmt.Errorf("failed to determine conversation directory: %w", err)
	}

	title := args[0]
	titlePath := filepath.Join(convDir, "title.txt")

	if err := os.WriteFile(titlePath, []byte(title), 0644); err != nil {
		return fmt.Errorf("failed to set title: %w", err)
	}

	fmt.Printf("Title set for conversation %s: %s\n", filepath.Base(convDir), title)
	return nil
}

func determineConversationDir(cliPath string) (string, error) {
	var convPath string

	// 1. If -c flag is given, use it
	if cliPath != "" {
		convPath = cliPath
	} else if envPath := os.Getenv("HINATA_CHAT_CONVERSATION"); envPath != "" {
		// 2. If HINATA_CHAT_CONVERSATION is set
		if filepath.IsAbs(envPath) {
			// 2a. If it's an absolute path, use it
			convPath = envPath
		} else if strings.HasPrefix(envPath, "./") {
			// 2d. If it explicitly starts with "./" then only look at current dir
			convPath = envPath
		} else {
			// 2b. Check if it exists relative to conversations home dir
			baseDir, err := chat.GetConversationsDir()
			if err != nil {
				return "", err
			}
			relativeToConvDir := filepath.Join(baseDir, envPath)
			if info, err := os.Stat(relativeToConvDir); err == nil && info.IsDir() {
				convPath = relativeToConvDir
			} else {
				// 2c. Look for it relative to current dir
				convPath = envPath
			}
		}
	} else {
		// 3. Otherwise fallback to using the most recent conversation
		baseDir, err := chat.GetConversationsDir()
		if err != nil {
			return "", err
		}
		latest, err := chat.FindLatestConversation(baseDir)
		if err != nil {
			return "", err
		}
		if latest == "" {
			return "", fmt.Errorf("no conversation specified and no existing conversations found")
		}
		convPath = latest
	}

	info, err := os.Stat(convPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", fmt.Errorf("conversation directory not found: %s", convPath)
		}
		return "", err
	}

	if !info.IsDir() {
		return "", fmt.Errorf("specified conversation path is not a directory: %s", convPath)
	}

	return convPath, nil
}
