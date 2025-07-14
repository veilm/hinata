package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/veilm/hinata/hnt-chat/pkg/chat"
	"github.com/veilm/hinata/hnt-llm/pkg/llm"
)

type ConversationInfo struct {
	ID       string `json:"id"`
	Title    string `json:"title"`
	IsPinned bool   `json:"is_pinned"`
}

type MessageFile struct {
	Filename string `json:"filename"`
	Role     string `json:"role"`
	Content  string `json:"content"`
}

type ConversationDetail struct {
	ID       string        `json:"id"`
	Title    string        `json:"title"`
	Model    string        `json:"model"`
	Messages []MessageFile `json:"messages"`
	Files    []string      `json:"files"`
	IsPinned bool          `json:"is_pinned"`
}

type TitleUpdateRequest struct {
	Title string `json:"title"`
}

type ModelUpdateRequest struct {
	Model string `json:"model"`
}

type MessageAddRequest struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type MessageContentUpdateRequest struct {
	Content string `json:"content"`
}

func getWebDir() string {
	if xdgData := os.Getenv("XDG_DATA_HOME"); xdgData != "" {
		return filepath.Join(xdgData, "hinata", "web")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "share", "hinata", "web")
}

func main() {
	mux := http.NewServeMux()

	// Static file serving
	webDir := getWebDir()
	fs := http.FileServer(http.Dir(webDir))
	mux.Handle("/", fs)

	// API endpoints
	mux.HandleFunc("/api/conversations", handleConversations)
	mux.HandleFunc("/api/conversation/", handleConversation)
	mux.HandleFunc("/api/conversations/create", handleCreateConversation)

	log.Println("Starting server on :2027")
	log.Fatal(http.ListenAndServe(":2027", corsMiddleware(mux)))
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func handleConversations(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	entries, err := os.ReadDir(baseDir)
	if err != nil {
		json.NewEncoder(w).Encode([]ConversationInfo{})
		return
	}

	var conversations []ConversationInfo
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		conv := ConversationInfo{
			ID:    entry.Name(),
			Title: entry.Name(),
		}

		// Check for .title file
		titlePath := filepath.Join(baseDir, entry.Name(), ".title")
		if data, err := os.ReadFile(titlePath); err == nil {
			conv.Title = strings.TrimSpace(string(data))
		}

		// Check for .pin file
		pinPath := filepath.Join(baseDir, entry.Name(), ".pin")
		if _, err := os.Stat(pinPath); err == nil {
			conv.IsPinned = true
		}

		conversations = append(conversations, conv)
	}

	// Sort: pinned first, then by ID
	sort.Slice(conversations, func(i, j int) bool {
		if conversations[i].IsPinned != conversations[j].IsPinned {
			return conversations[i].IsPinned
		}
		return conversations[i].ID > conversations[j].ID
	})

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(conversations)
}

func handleConversation(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/api/conversation/")
	parts := strings.Split(path, "/")

	if len(parts) < 1 {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}

	convID := parts[0]

	if len(parts) == 1 {
		// GET /api/conversation/{id}
		if r.Method != "GET" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		getConversationDetail(w, convID)
		return
	}

	switch parts[1] {
	case "fork":
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		forkConversation(w, convID)

	case "pin-toggle":
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		togglePin(w, convID)

	case "add-message":
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		addMessage(w, r, convID)

	case "gen-assistant":
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		generateAssistant(w, convID)

	case "title":
		if r.Method != "PUT" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		updateTitle(w, r, convID)

	case "model":
		if r.Method != "PUT" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		updateModel(w, r, convID)

	case "message":
		if len(parts) < 4 {
			http.Error(w, "Invalid path", http.StatusBadRequest)
			return
		}
		filename := parts[2]
		action := parts[3]

		switch action {
		case "edit":
			if r.Method != "PUT" {
				http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
				return
			}
			editMessage(w, r, convID, filename)

		case "archive":
			if r.Method != "POST" {
				http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
				return
			}
			archiveMessage(w, convID, filename)

		default:
			http.Error(w, "Unknown action", http.StatusBadRequest)
		}

	default:
		http.Error(w, "Unknown endpoint", http.StatusNotFound)
	}
}

func getConversationDetail(w http.ResponseWriter, convID string) {
	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	convDir := filepath.Join(baseDir, convID)

	if _, err := os.Stat(convDir); os.IsNotExist(err) {
		http.Error(w, "Conversation not found", http.StatusNotFound)
		return
	}

	detail := ConversationDetail{
		ID:       convID,
		Title:    convID,
		Model:    "openrouter/deepseek/deepseek-chat-v3-0324:free",
		Messages: []MessageFile{},
		Files:    []string{},
	}

	// Read title
	if data, err := os.ReadFile(filepath.Join(convDir, ".title")); err == nil {
		detail.Title = strings.TrimSpace(string(data))
	}

	// Read model
	if data, err := os.ReadFile(filepath.Join(convDir, ".model")); err == nil {
		detail.Model = strings.TrimSpace(string(data))
	}

	// Check pin status
	if _, err := os.Stat(filepath.Join(convDir, ".pin")); err == nil {
		detail.IsPinned = true
	}

	// Use chat.ListMessages to get messages
	messages, err := chat.ListMessages(convDir)
	if err != nil {
		http.Error(w, "Failed to list messages", http.StatusInternalServerError)
		return
	}

	// Convert messages and read content
	for _, msg := range messages {
		// Skip assistant-reasoning messages from the web UI
		if msg.Role == chat.RoleAssistantReasoning {
			continue
		}

		content, err := os.ReadFile(msg.Path)
		if err != nil {
			continue
		}

		// Extract filename from path
		filename := filepath.Base(msg.Path)

		// Format content based on role prefix in original Python
		contentStr := string(content)
		role := string(msg.Role)

		// Remove role prefixes if they exist (for backward compatibility)
		if strings.HasPrefix(contentStr, "Human: ") {
			contentStr = strings.TrimPrefix(contentStr, "Human: ")
		} else if strings.HasPrefix(contentStr, "Assistant: ") {
			contentStr = strings.TrimPrefix(contentStr, "Assistant: ")
		} else if strings.HasPrefix(contentStr, "System: ") {
			contentStr = strings.TrimPrefix(contentStr, "System: ")
		}

		detail.Messages = append(detail.Messages, MessageFile{
			Filename: filename,
			Role:     role,
			Content:  strings.TrimSpace(contentStr),
		})
	}

	// Get other files
	entries, _ := os.ReadDir(convDir)
	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasPrefix(name, ".") && !entry.IsDir() && !strings.HasSuffix(name, ".md") {
			detail.Files = append(detail.Files, name)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(detail)
}

func handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	convDir, err := chat.CreateNewConversation(baseDir)
	if err != nil {
		http.Error(w, "Failed to create conversation", http.StatusInternalServerError)
		return
	}

	// Extract just the ID from the full path
	convID := filepath.Base(convDir)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"conversation_id": convID})
}

func forkConversation(w http.ResponseWriter, convID string) {
	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	sourceDir := filepath.Join(baseDir, convID)
	if _, err := os.Stat(sourceDir); os.IsNotExist(err) {
		http.Error(w, "Source conversation not found", http.StatusNotFound)
		return
	}

	// Create new conversation
	newConvDir, err := chat.CreateNewConversation(baseDir)
	if err != nil {
		http.Error(w, "Failed to create new conversation", http.StatusInternalServerError)
		return
	}

	// Copy all files from source to new conversation
	entries, err := os.ReadDir(sourceDir)
	if err != nil {
		http.Error(w, "Failed to read source conversation", http.StatusInternalServerError)
		return
	}

	for _, entry := range entries {
		if entry.IsDir() {
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

	newID := filepath.Base(newConvDir)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"conversation_id": newID})
}

func togglePin(w http.ResponseWriter, convID string) {
	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	pinPath := filepath.Join(baseDir, convID, ".pin")

	if _, err := os.Stat(pinPath); err == nil {
		// Unpin
		os.Remove(pinPath)
		json.NewEncoder(w).Encode(map[string]interface{}{"status": "unpinned", "is_pinned": false})
	} else {
		// Pin
		os.WriteFile(pinPath, []byte(""), 0644)
		json.NewEncoder(w).Encode(map[string]interface{}{"status": "pinned", "is_pinned": true})
	}
}

func addMessage(w http.ResponseWriter, r *http.Request, convID string) {
	var req MessageAddRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	convDir := filepath.Join(baseDir, convID)

	// Parse role
	role, err := chat.ParseRole(req.Role)
	if err != nil {
		http.Error(w, fmt.Sprintf("Invalid role: %s", req.Role), http.StatusBadRequest)
		return
	}

	// Format content based on role (for backward compatibility)
	content := req.Content
	switch role {
	case chat.RoleUser:
		content = "Human: " + content
	case chat.RoleAssistant:
		content = "Assistant: " + content
	case chat.RoleSystem:
		content = "System: " + content
	}

	filename, err := chat.WriteMessageFile(convDir, role, content)
	if err != nil {
		http.Error(w, "Failed to write message", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"filename": filename})
}

func generateAssistant(w http.ResponseWriter, convID string) {
	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	convDir := filepath.Join(baseDir, convID)

	// Read model from .model file
	model := "openrouter/deepseek/deepseek-chat-v3-0324:free"
	if data, err := os.ReadFile(filepath.Join(convDir, ".model")); err == nil {
		model = strings.TrimSpace(string(data))
	}

	// Pack conversation
	var buf bytes.Buffer
	if err := chat.PackConversation(convDir, &buf, true); err != nil {
		http.Error(w, "Failed to pack conversation", http.StatusInternalServerError)
		return
	}

	config := llm.Config{
		Model:            model,
		SystemPrompt:     "",
		IncludeReasoning: false,
	}

	ctx := context.Background()
	eventChan, errChan := llm.StreamLLMResponse(ctx, config, buf.String())

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	var contentBuffer strings.Builder
	var reasoningBuffer strings.Builder

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				goto done
			}

			if event.Content != "" {
				fmt.Fprintf(w, "data: %s\n\n", event.Content)
				flusher.Flush()
				contentBuffer.WriteString(event.Content)
			}

			if event.Reasoning != "" {
				reasoningBuffer.WriteString(event.Reasoning)
			}

		case err := <-errChan:
			if err != nil {
				fmt.Fprintf(w, "data: [ERROR] %s\n\n", err.Error())
				flusher.Flush()
				return
			}
		}
	}

done:
	// Write the assistant message to file
	fullResponse := contentBuffer.String()
	if reasoningBuffer.Len() > 0 {
		fullResponse = fmt.Sprintf("<think>%s</think>\n%s", reasoningBuffer.String(), contentBuffer.String())
	}

	if fullResponse != "" {
		_, err := chat.WriteMessageFile(convDir, chat.RoleAssistant, fullResponse)
		if err != nil {
			fmt.Fprintf(w, "data: [ERROR] Failed to save message\n\n")
			flusher.Flush()
			return
		}
	}

	fmt.Fprintf(w, "data: [DONE]\n\n")
	flusher.Flush()
}

func updateTitle(w http.ResponseWriter, r *http.Request, convID string) {
	var req TitleUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	titlePath := filepath.Join(baseDir, convID, ".title")

	if err := os.WriteFile(titlePath, []byte(req.Title), 0644); err != nil {
		http.Error(w, "Failed to update title", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "success"})
}

func updateModel(w http.ResponseWriter, r *http.Request, convID string) {
	var req ModelUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	modelPath := filepath.Join(baseDir, convID, ".model")

	if err := os.WriteFile(modelPath, []byte(req.Model), 0644); err != nil {
		http.Error(w, "Failed to update model", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "success"})
}

func editMessage(w http.ResponseWriter, r *http.Request, convID string, filename string) {
	var req MessageContentUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	msgPath := filepath.Join(baseDir, convID, filename)

	// Archive current version
	content, err := os.ReadFile(msgPath)
	if err != nil {
		http.Error(w, "Message not found", http.StatusNotFound)
		return
	}

	archiveDir := filepath.Join(baseDir, convID, "archive")
	os.MkdirAll(archiveDir, 0755)

	timestamp := time.Now().Unix()
	archivePath := filepath.Join(archiveDir, fmt.Sprintf("%d-%s", timestamp, filename))
	if err := os.WriteFile(archivePath, content, 0644); err != nil {
		http.Error(w, "Failed to archive message", http.StatusInternalServerError)
		return
	}

	// Write new content
	if err := os.WriteFile(msgPath, []byte(req.Content), 0644); err != nil {
		http.Error(w, "Failed to update message", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "success"})
}

func archiveMessage(w http.ResponseWriter, convID string, filename string) {
	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return
	}

	msgPath := filepath.Join(baseDir, convID, filename)

	content, err := os.ReadFile(msgPath)
	if err != nil {
		http.Error(w, "Message not found", http.StatusNotFound)
		return
	}

	archiveDir := filepath.Join(baseDir, convID, "archive")
	os.MkdirAll(archiveDir, 0755)

	timestamp := time.Now().Unix()
	archivePath := filepath.Join(archiveDir, fmt.Sprintf("%d-%s", timestamp, filename))
	if err := os.WriteFile(archivePath, content, 0644); err != nil {
		http.Error(w, "Failed to archive message", http.StatusInternalServerError)
		return
	}

	if err := os.Remove(msgPath); err != nil {
		http.Error(w, "Failed to remove message", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "archived"})
}
