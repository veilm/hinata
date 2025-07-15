package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
	"unicode/utf8"

	"github.com/veilm/hinata/cmd/hnt-chat/pkg/chat"
	"github.com/veilm/hinata/cmd/hnt-llm/pkg/llm"
	"golang.org/x/crypto/bcrypt"
	"golang.org/x/term"
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

type OtherFile struct {
	Filename     string  `json:"filename"`
	IsText       bool    `json:"is_text"`
	Content      *string `json:"content"`
	ErrorMessage *string `json:"error_message"`
}

type ConversationDetail struct {
	ID         string        `json:"conversation_id"`
	Title      string        `json:"title"`
	Model      string        `json:"model"`
	Messages   []MessageFile `json:"messages"`
	OtherFiles []OtherFile   `json:"other_files"`
	IsPinned   bool          `json:"is_pinned"`
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

type RegisterRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type LoginResponse struct {
	Username string `json:"username"`
	Success  bool   `json:"success"`
}

type ShareRequest struct {
	Users []string `json:"users"`
}

func getWebDir() string {
	if xdgData := os.Getenv("XDG_DATA_HOME"); xdgData != "" {
		return filepath.Join(xdgData, "hinata", "web")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "share", "hinata", "web")
}

func getUsersDir() string {
	if xdgData := os.Getenv("XDG_DATA_HOME"); xdgData != "" {
		return filepath.Join(xdgData, "hinata", "users")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "share", "hinata", "users")
}

func getDefaultOwner() string {
	return os.Getenv("USER")
}

func isTerminal() bool {
	return term.IsTerminal(int(os.Stdin.Fd()))
}

func promptPassword(prompt string) (string, error) {
	fmt.Print(prompt)
	password, err := term.ReadPassword(int(syscall.Stdin))
	fmt.Println() // New line after password input
	if err != nil {
		return "", err
	}
	return string(password), nil
}

func main() {
	// Initialize default admin user if needed
	usersDir := getUsersDir()
	if _, err := os.Stat(usersDir); os.IsNotExist(err) {
		defaultUser := getDefaultOwner()
		if defaultUser != "" {
			var password string
			if isTerminal() {
				// Prompt for password if connected to terminal
				fmt.Printf("Creating admin account for user '%s'\n", defaultUser)
				for {
					pwd1, err := promptPassword("Enter password: ")
					if err != nil {
						log.Printf("Error reading password: %v\n", err)
						continue
					}
					if pwd1 == "" {
						fmt.Println("Password cannot be empty")
						continue
					}
					pwd2, err := promptPassword("Confirm password: ")
					if err != nil {
						log.Printf("Error reading password: %v\n", err)
						continue
					}
					if pwd1 != pwd2 {
						fmt.Println("Passwords do not match")
						continue
					}
					password = pwd1
					break
				}
			} else {
				// Use username as password if not connected to terminal
				password = defaultUser
				log.Printf("Not connected to terminal, using username as password for admin user: %s\n", defaultUser)
			}

			if err := createUser(defaultUser, password); err == nil {
				if isTerminal() {
					log.Printf("Created admin user: %s\n", defaultUser)
				} else {
					log.Printf("Created default admin user: %s (password: %s)\n", defaultUser, password)
				}
			} else {
				log.Printf("Failed to create admin user: %v\n", err)
			}
		}
	}

	mux := http.NewServeMux()

	// Auth endpoints (no auth required)
	mux.HandleFunc("/api/auth/register", handleRegister)
	mux.HandleFunc("/api/auth/login", handleLogin)

	// Protected API endpoints
	mux.HandleFunc("/api/conversations", authMiddleware(handleConversations))
	mux.HandleFunc("/api/conversation/", authMiddleware(handleConversation))
	mux.HandleFunc("/api/conversations/create", authMiddleware(handleCreateConversation))

	// Static file serving with custom handler for conversation pages
	webDir := getWebDir()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		// Handle conversation routes
		if strings.HasPrefix(r.URL.Path, "/c/") {
			http.ServeFile(w, r, filepath.Join(webDir, "conversation.html"))
			return
		}

		// Serve static files
		fs := http.FileServer(http.Dir(webDir))
		fs.ServeHTTP(w, r)
	})

	log.Println("Starting server on :2027")
	log.Fatal(http.ListenAndServe(":2027", corsMiddleware(mux)))
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Username, X-Password")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func authMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Skip auth for login/register endpoints
		if strings.HasPrefix(r.URL.Path, "/api/auth/") {
			next.ServeHTTP(w, r)
			return
		}

		username := r.Header.Get("X-Username")
		password := r.Header.Get("X-Password")

		if !validateUser(username, password) {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		ctx := context.WithValue(r.Context(), "username", username)
		next.ServeHTTP(w, r.WithContext(ctx))
	}
}

func handleConversations(w http.ResponseWriter, r *http.Request) {
	if r.Method != "GET" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	username := r.Context().Value("username").(string)

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

		convDir := filepath.Join(baseDir, entry.Name())

		// Check if user has access
		if !hasAccess(convDir, username) {
			continue
		}

		conv := ConversationInfo{
			ID:    entry.Name(),
			Title: entry.Name(),
		}

		// Check for .title file
		titlePath := filepath.Join(convDir, "title.txt")
		if data, err := os.ReadFile(titlePath); err == nil {
			conv.Title = strings.TrimSpace(string(data))
		}

		// Check for .pin file
		pinPath := filepath.Join(convDir, "pinned.txt")
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
	json.NewEncoder(w).Encode(map[string]interface{}{
		"conversations": conversations,
	})
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
		getConversationDetail(w, r, convID)
		return
	}

	switch parts[1] {
	case "fork":
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		forkConversation(w, r, convID)

	case "pin-toggle":
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		togglePin(w, r, convID)

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
		generateAssistant(w, r, convID)

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
			archiveMessage(w, r, convID, filename)

		default:
			http.Error(w, "Unknown action", http.StatusBadRequest)
		}

	case "share":
		handleShare(w, r, convID)

	case "access":
		handleGetAccess(w, r, convID)

	default:
		http.Error(w, "Unknown endpoint", http.StatusNotFound)
	}
}

func getConversationDetail(w http.ResponseWriter, r *http.Request, convID string) {
	username := r.Context().Value("username").(string)

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

	// Check access
	if !hasAccess(convDir, username) {
		http.Error(w, "Access denied", http.StatusForbidden)
		return
	}

	detail := ConversationDetail{
		ID:         convID,
		Title:      convID,
		Model:      "openrouter/deepseek/deepseek-chat-v3-0324:free",
		Messages:   []MessageFile{},
		OtherFiles: []OtherFile{},
	}

	// Read title
	if data, err := os.ReadFile(filepath.Join(convDir, "title.txt")); err == nil {
		detail.Title = strings.TrimSpace(string(data))
	}

	// Read model
	if data, err := os.ReadFile(filepath.Join(convDir, "model.txt")); err == nil {
		detail.Model = strings.TrimSpace(string(data))
	}

	// Check pin status
	if _, err := os.Stat(filepath.Join(convDir, "pinned.txt")); err == nil {
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
			file := OtherFile{
				Filename: name,
				IsText:   false,
			}

			// Try to read file content
			filePath := filepath.Join(convDir, name)
			if data, err := os.ReadFile(filePath); err == nil {
				// Check if it's likely text (no null bytes in first 4096 bytes)
				peekSize := 4096
				if len(data) < peekSize {
					peekSize = len(data)
				}

				if peekSize > 0 && !containsNull(data[:peekSize]) {
					// Try to decode as UTF-8
					content := string(data)
					if isValidUTF8(content) {
						file.IsText = true
						file.Content = &content
					} else {
						errMsg := "[File content not displayed: not valid UTF-8]"
						file.ErrorMessage = &errMsg
					}
				} else {
					errMsg := "[File content not displayed: likely binary]"
					file.ErrorMessage = &errMsg
				}
			} else {
				errMsg := fmt.Sprintf("[Error accessing file: %s]", err.Error())
				file.ErrorMessage = &errMsg
			}

			detail.OtherFiles = append(detail.OtherFiles, file)
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

	username := r.Context().Value("username").(string)

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

	// Set access for the creator
	if err := setAccess(convDir, []string{username}); err != nil {
		log.Printf("Warning: Failed to set access for new conversation: %v", err)
	}

	// Extract just the ID from the full path
	convID := filepath.Base(convDir)

	// Log the conversation creation
	log.Printf("New conversation created by %s (ID: %s)\n", username, convID)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"conversation_id": convID})
}

func forkConversation(w http.ResponseWriter, r *http.Request, convID string) {
	username, sourceDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
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

		// Skip access.txt - we'll set our own
		if entry.Name() == "access.txt" {
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

	// Set access for the user who forked
	if err := setAccess(newConvDir, []string{username}); err != nil {
		log.Printf("Warning: Failed to set access for forked conversation: %v", err)
	}

	newID := filepath.Base(newConvDir)

	// Log the fork operation
	sourceTitle := getConversationTitle(sourceDir)
	if sourceTitle == "" {
		sourceTitle = convID
	}
	log.Printf("Conversation forked (%s) -> new ID: %s\n", sourceTitle, newID)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"conversation_id": newID})
}

func togglePin(w http.ResponseWriter, r *http.Request, convID string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	pinPath := filepath.Join(convDir, "pinned.txt")

	if _, err := os.Stat(pinPath); err == nil {
		// Unpin
		os.Remove(pinPath)

		// Log the unpin operation
		title := getConversationTitle(convDir)
		if title == "" {
			title = convID
		}
		log.Printf("Conversation unpinned (%s)\n", title)

		json.NewEncoder(w).Encode(map[string]interface{}{"status": "unpinned", "is_pinned": false})
	} else {
		// Pin
		os.WriteFile(pinPath, []byte(""), 0644)

		// Log the pin operation
		title := getConversationTitle(convDir)
		if title == "" {
			title = convID
		}
		log.Printf("Conversation pinned (%s)\n", title)

		json.NewEncoder(w).Encode(map[string]interface{}{"status": "pinned", "is_pinned": true})
	}
}

func addMessage(w http.ResponseWriter, r *http.Request, convID string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	var req MessageAddRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

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

	// Log the message addition
	title := getConversationTitle(convDir)
	if title == "" {
		title = convID
	}
	log.Printf("%s message added to conversation (%s)\n", strings.Title(req.Role), title)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"filename": filename})
}

func generateAssistant(w http.ResponseWriter, r *http.Request, convID string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	// Read model from .model file
	model := "openrouter/deepseek/deepseek-chat-v3-0324:free"
	if data, err := os.ReadFile(filepath.Join(convDir, "model.txt")); err == nil {
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
		IncludeReasoning: true,
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
				// Stream reasoning tokens with a special prefix
				fmt.Fprintf(w, "data: [REASONING]%s\n\n", event.Reasoning)
				flusher.Flush()
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
	// Write reasoning and assistant messages to separate files
	if reasoningBuffer.Len() > 0 {
		// Save reasoning to a separate file with RoleAssistantReasoning
		reasoningContent := fmt.Sprintf("<think>%s</think>", reasoningBuffer.String())
		_, err := chat.WriteMessageFile(convDir, chat.RoleAssistantReasoning, reasoningContent)
		if err != nil {
			fmt.Fprintf(w, "data: [ERROR] Failed to save reasoning\n\n")
			flusher.Flush()
			return
		}
	}

	// Write the assistant message content (without reasoning)
	if contentBuffer.Len() > 0 {
		_, err := chat.WriteMessageFile(convDir, chat.RoleAssistant, contentBuffer.String())
		if err != nil {
			fmt.Fprintf(w, "data: [ERROR] Failed to save message\n\n")
			flusher.Flush()
			return
		}

		// Log the assistant message addition
		title := getConversationTitle(convDir)
		if title == "" {
			title = convID
		}
		log.Printf("Assistant message generated for conversation (%s)\n", title)
	}

	fmt.Fprintf(w, "data: [DONE]\n\n")
	flusher.Flush()
}

func updateTitle(w http.ResponseWriter, r *http.Request, convID string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	var req TitleUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	titlePath := filepath.Join(convDir, "title.txt")

	if err := os.WriteFile(titlePath, []byte(req.Title), 0644); err != nil {
		http.Error(w, "Failed to update title", http.StatusInternalServerError)
		return
	}

	// Log the title update
	log.Printf("Conversation title updated (%s) -> (%s)\n", convID, req.Title)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "success"})
}

func updateModel(w http.ResponseWriter, r *http.Request, convID string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	var req ModelUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	modelPath := filepath.Join(convDir, "model.txt")

	if err := os.WriteFile(modelPath, []byte(req.Model), 0644); err != nil {
		http.Error(w, "Failed to update model", http.StatusInternalServerError)
		return
	}

	// Log the model update
	title := getConversationTitle(convDir)
	if title == "" {
		title = convID
	}
	log.Printf("Conversation model updated (%s) -> %s\n", title, req.Model)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "success"})
}

func editMessage(w http.ResponseWriter, r *http.Request, convID string, filename string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	var req MessageContentUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	msgPath := filepath.Join(convDir, filename)

	// Archive current version
	content, err := os.ReadFile(msgPath)
	if err != nil {
		http.Error(w, "Message not found", http.StatusNotFound)
		return
	}

	archiveDir := filepath.Join(convDir, "archive")
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

	// Log the message edit
	title := getConversationTitle(convDir)
	if title == "" {
		title = convID
	}
	log.Printf("Message edited in conversation (%s) - file: %s\n", title, filename)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "success"})
}

func archiveMessage(w http.ResponseWriter, r *http.Request, convID string, filename string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	msgPath := filepath.Join(convDir, filename)

	content, err := os.ReadFile(msgPath)
	if err != nil {
		http.Error(w, "Message not found", http.StatusNotFound)
		return
	}

	archiveDir := filepath.Join(convDir, "archive")
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

	// Log the message archive
	title := getConversationTitle(convDir)
	if title == "" {
		title = convID
	}
	log.Printf("Message archived from conversation (%s) - file: %s\n", title, filename)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "archived"})
}

func containsNull(data []byte) bool {
	for _, b := range data {
		if b == 0 {
			return true
		}
	}
	return false
}

func isValidUTF8(s string) bool {
	return utf8.ValidString(s)
}

func getConversationTitle(convDir string) string {
	titlePath := filepath.Join(convDir, "title.txt")
	if data, err := os.ReadFile(titlePath); err == nil {
		return strings.TrimSpace(string(data))
	}
	return ""
}

func createUser(username, password string) error {
	usersDir := getUsersDir()
	if err := os.MkdirAll(usersDir, 0755); err != nil {
		return fmt.Errorf("failed to create users directory: %w", err)
	}

	userPath := filepath.Join(usersDir, username+".txt")
	if _, err := os.Stat(userPath); err == nil {
		return fmt.Errorf("user already exists")
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return fmt.Errorf("failed to hash password: %w", err)
	}

	return os.WriteFile(userPath, hash, 0600)
}

func validateUser(username, password string) bool {
	if username == "" || password == "" {
		return false
	}

	userPath := filepath.Join(getUsersDir(), username+".txt")
	hash, err := os.ReadFile(userPath)
	if err != nil {
		return false
	}

	err = bcrypt.CompareHashAndPassword(hash, []byte(password))
	return err == nil
}

func hasAccess(convDir, username string) bool {
	accessPath := filepath.Join(convDir, "access.txt")
	data, err := os.ReadFile(accessPath)
	if err != nil {
		// No access.txt means only default owner has access
		return username == getDefaultOwner()
	}

	users := strings.Split(strings.TrimSpace(string(data)), "\n")
	for _, u := range users {
		if strings.TrimSpace(u) == username {
			return true
		}
	}
	return false
}

func setAccess(convDir string, users []string) error {
	accessPath := filepath.Join(convDir, "access.txt")
	content := strings.Join(users, "\n")
	return os.WriteFile(accessPath, []byte(content), 0644)
}

func getAccess(convDir string) []string {
	accessPath := filepath.Join(convDir, "access.txt")
	data, err := os.ReadFile(accessPath)
	if err != nil {
		// Default to owner only
		return []string{getDefaultOwner()}
	}

	var users []string
	for _, u := range strings.Split(string(data), "\n") {
		if u = strings.TrimSpace(u); u != "" {
			users = append(users, u)
		}
	}
	return users
}

func checkConversationAccess(w http.ResponseWriter, r *http.Request, convID string) (string, string, bool) {
	username := r.Context().Value("username").(string)

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		http.Error(w, "Failed to get conversations directory", http.StatusInternalServerError)
		return "", "", false
	}

	convDir := filepath.Join(baseDir, convID)

	if _, err := os.Stat(convDir); os.IsNotExist(err) {
		http.Error(w, "Conversation not found", http.StatusNotFound)
		return "", "", false
	}

	if !hasAccess(convDir, username) {
		http.Error(w, "Access denied", http.StatusForbidden)
		return "", "", false
	}

	return username, convDir, true
}

func handleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.Username == "" || req.Password == "" {
		http.Error(w, "Username and password are required", http.StatusBadRequest)
		return
	}

	if err := createUser(req.Username, req.Password); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	log.Printf("New user registered: %s\n", req.Username)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(LoginResponse{
		Username: req.Username,
		Success:  true,
	})
}

func handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req RegisterRequest // Same structure as register
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if !validateUser(req.Username, req.Password) {
		http.Error(w, "Invalid credentials", http.StatusUnauthorized)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(LoginResponse{
		Username: req.Username,
		Success:  true,
	})
}

func handleShare(w http.ResponseWriter, r *http.Request, convID string) {
	username, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	if r.Method != "POST" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req ShareRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Always include the owner in the access list
	users := append([]string{username}, req.Users...)

	// Remove duplicates
	seen := make(map[string]bool)
	unique := []string{}
	for _, u := range users {
		if !seen[u] {
			seen[u] = true
			unique = append(unique, u)
		}
	}

	if err := setAccess(convDir, unique); err != nil {
		http.Error(w, "Failed to update access", http.StatusInternalServerError)
		return
	}

	title := getConversationTitle(convDir)
	if title == "" {
		title = convID
	}
	log.Printf("Conversation shared (%s) with users: %v\n", title, unique)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "success",
		"users":  unique,
	})
}

func handleGetAccess(w http.ResponseWriter, r *http.Request, convID string) {
	_, convDir, ok := checkConversationAccess(w, r, convID)
	if !ok {
		return
	}

	if r.Method != "GET" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	users := getAccess(convDir)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"users": users,
	})
}
