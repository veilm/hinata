package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
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

func getDataDir() string {
	if xdgData := os.Getenv("XDG_DATA_HOME"); xdgData != "" {
		return filepath.Join(xdgData, "hinata", "conversations")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "share", "hinata", "conversations")
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

	dataDir := getDataDir()
	entries, err := os.ReadDir(dataDir)
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
		titlePath := filepath.Join(dataDir, entry.Name(), ".title")
		if data, err := os.ReadFile(titlePath); err == nil {
			conv.Title = strings.TrimSpace(string(data))
		}

		// Check for .pin file
		pinPath := filepath.Join(dataDir, entry.Name(), ".pin")
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
	dataDir := getDataDir()
	convDir := filepath.Join(dataDir, convID)

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

	// Read message files
	entries, _ := os.ReadDir(convDir)
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasSuffix(name, ".md") && !strings.HasPrefix(name, ".") {
			msgPath := filepath.Join(convDir, name)
			content, err := os.ReadFile(msgPath)
			if err != nil {
				continue
			}

			// Determine role from content
			role := "user"
			contentStr := string(content)
			if strings.HasPrefix(contentStr, "Human: ") {
				role = "user"
				contentStr = strings.TrimPrefix(contentStr, "Human: ")
			} else if strings.HasPrefix(contentStr, "Assistant: ") {
				role = "assistant"
				contentStr = strings.TrimPrefix(contentStr, "Assistant: ")
			} else if strings.HasPrefix(contentStr, "System: ") {
				role = "system"
				contentStr = strings.TrimPrefix(contentStr, "System: ")
			}

			detail.Messages = append(detail.Messages, MessageFile{
				Filename: name,
				Role:     role,
				Content:  strings.TrimSpace(contentStr),
			})
		} else if !strings.HasPrefix(name, ".") && !entry.IsDir() {
			detail.Files = append(detail.Files, name)
		}
	}

	// Sort messages by filename
	sort.Slice(detail.Messages, func(i, j int) bool {
		return detail.Messages[i].Filename < detail.Messages[j].Filename
	})

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(detail)
}

func handleCreateConversation(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	cmd := exec.Command("hnt-chat", "new")
	output, err := cmd.CombinedOutput()
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to create conversation: %s", output), http.StatusInternalServerError)
		return
	}

	convID := strings.TrimSpace(string(output))
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"conversation_id": convID})
}

func forkConversation(w http.ResponseWriter, convID string) {
	cmd := exec.Command("hnt-chat", "fork", convID)
	output, err := cmd.CombinedOutput()
	if err != nil {
		http.Error(w, fmt.Sprintf("Failed to fork conversation: %s", output), http.StatusInternalServerError)
		return
	}

	newID := strings.TrimSpace(string(output))
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"conversation_id": newID})
}

func togglePin(w http.ResponseWriter, convID string) {
	dataDir := getDataDir()
	pinPath := filepath.Join(dataDir, convID, ".pin")

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

	dataDir := getDataDir()
	convDir := filepath.Join(dataDir, convID)

	// Find next message number
	entries, _ := os.ReadDir(convDir)
	maxNum := 0
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasSuffix(name, ".md") && len(name) > 3 {
			if num := 0; fmt.Sscanf(name[:3], "%03d", &num) == 1 {
				if num > maxNum {
					maxNum = num
				}
			}
		}
	}

	filename := fmt.Sprintf("%03d.md", maxNum+1)
	msgPath := filepath.Join(convDir, filename)

	// Format content based on role
	content := req.Content
	switch req.Role {
	case "user":
		content = "Human: " + content
	case "assistant":
		content = "Assistant: " + content
	case "system":
		content = "System: " + content
	}

	if err := os.WriteFile(msgPath, []byte(content), 0644); err != nil {
		http.Error(w, "Failed to write message", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"filename": filename})
}

func generateAssistant(w http.ResponseWriter, convID string) {
	cmd := exec.Command("hnt-chat", "gen", convID)
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		http.Error(w, "Failed to create pipe", http.StatusInternalServerError)
		return
	}

	if err := cmd.Start(); err != nil {
		http.Error(w, "Failed to start command", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
		return
	}

	buf := make([]byte, 1024)
	for {
		n, err := stdout.Read(buf)
		if n > 0 {
			fmt.Fprintf(w, "data: %s\n\n", string(buf[:n]))
			flusher.Flush()
		}
		if err != nil {
			break
		}
	}

	cmd.Wait()
	fmt.Fprintf(w, "data: [DONE]\n\n")
	flusher.Flush()
}

func updateTitle(w http.ResponseWriter, r *http.Request, convID string) {
	var req TitleUpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	dataDir := getDataDir()
	titlePath := filepath.Join(dataDir, convID, ".title")

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

	dataDir := getDataDir()
	modelPath := filepath.Join(dataDir, convID, ".model")

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

	dataDir := getDataDir()
	msgPath := filepath.Join(dataDir, convID, filename)

	// Archive current version
	content, err := os.ReadFile(msgPath)
	if err != nil {
		http.Error(w, "Message not found", http.StatusNotFound)
		return
	}

	archiveDir := filepath.Join(dataDir, convID, "archive")
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
	dataDir := getDataDir()
	msgPath := filepath.Join(dataDir, convID, filename)

	content, err := os.ReadFile(msgPath)
	if err != nil {
		http.Error(w, "Message not found", http.StatusNotFound)
		return
	}

	archiveDir := filepath.Join(dataDir, convID, "archive")
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