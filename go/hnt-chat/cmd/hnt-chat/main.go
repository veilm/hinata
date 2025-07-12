package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/hnt-chat/pkg/chat"
	"github.com/veilm/hinata/hnt-llm/pkg/llm"
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
		Use:   "hnt-chat",
		Short: "Hinata Chat CLI tool",
	}

	var newCmd = &cobra.Command{
		Use:     "new",
		Aliases: []string{"new-conversation"},
		Short:   "Create a new conversation directory",
		RunE:    handleNewCommand,
	}

	var addCmd = &cobra.Command{
		Use:     "add [role]",
		Aliases: []string{"add-message"},
		Short:   "Add a message to a conversation",
		Args:    cobra.ExactArgs(1),
		RunE:    handleAddCommand,
	}
	addCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")
	addCmd.Flags().BoolVar(&separateReasoning, "separate-reasoning", false, "For assistant role, save <think> content separately")

	var packCmd = &cobra.Command{
		Use:     "pack",
		Aliases: []string{"package"},
		Short:   "Pack conversation messages for processing",
		RunE:    handlePackCommand,
	}
	packCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")
	packCmd.Flags().BoolVar(&merge, "merge", false, "Merge consecutive messages from same author")

	var genCmd = &cobra.Command{
		Use:   "gen",
		Short: "Generate the next message in a conversation",
		RunE:  handleGenCommand,
	}
	genCmd.Flags().StringVarP(&conversationPath, "conversation", "c", "", "Path to conversation directory")
	genCmd.Flags().BoolVarP(&write, "write", "w", false, "Write generated output as new assistant message")
	genCmd.Flags().BoolVar(&outputFilename, "output-filename", false, "Print filename of created message")
	genCmd.Flags().BoolVar(&includeReasoning, "include-reasoning", false, "Include reasoning in output")
	genCmd.Flags().BoolVar(&merge, "merge", false, "Merge consecutive messages from same author")
	genCmd.Flags().StringVar(&model, "model", "", "Model to use for LLM")
	genCmd.Flags().BoolVar(&debugUnsafe, "debug-unsafe", false, "Enable unsafe debugging options")

	rootCmd.AddCommand(newCmd, addCmd, packCmd, genCmd)

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
				if hasThinkTag {
					fmt.Print("</think>\n")
					hasThinkTag = false
				}
				fmt.Print(event.Content)
				contentBuffer.WriteString(event.Content)
			}

			if event.Reasoning != "" && (includeReasoning || debugUnsafe) {
				if !hasThinkTag {
					fmt.Print("<think>")
					hasThinkTag = true
				}
				fmt.Print(event.Reasoning)
				reasoningBuffer.WriteString(event.Reasoning)
			}

		case err := <-errChan:
			if err != nil {
				return fmt.Errorf("error from LLM stream: %w", err)
			}
		}
	}

done:
	if hasThinkTag {
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
		fmt.Println()
		fmt.Println(assistantFilePath)
	}

	return nil
}

func determineConversationDir(cliPath string) (string, error) {
	var convPath string

	if cliPath != "" {
		convPath = cliPath
	} else if envPath := os.Getenv("HINATA_CHAT_CONVERSATION"); envPath != "" {
		convPath = envPath
	} else {
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
