package chat

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/veilm/hinata/hnt-llm/pkg/escaping"
)

func GetConversationsDir() (string, error) {
	dataDir := os.Getenv("XDG_DATA_HOME")
	if dataDir == "" {
		homeDir, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("could not determine home directory: %w", err)
		}
		dataDir = filepath.Join(homeDir, ".local", "share")
	}

	conversationsDir := filepath.Join(dataDir, "hinata", "chat", "conversations")
	if err := os.MkdirAll(conversationsDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create conversations directory: %w", err)
	}

	return conversationsDir, nil
}

func CreateNewConversation(baseDir string) (string, error) {
	for {
		timestampNs := time.Now().UnixNano()
		newConvPath := filepath.Join(baseDir, strconv.FormatInt(timestampNs, 10))

		err := os.Mkdir(newConvPath, 0755)
		if err == nil {
			return newConvPath, nil
		}
		if os.IsExist(err) {
			time.Sleep(time.Millisecond)
			continue
		}
		return "", fmt.Errorf("failed to create conversation directory: %w", err)
	}
}

func FindLatestConversation(baseDir string) (string, error) {
	if _, err := os.Stat(baseDir); os.IsNotExist(err) {
		return "", nil
	}

	entries, err := os.ReadDir(baseDir)
	if err != nil {
		return "", err
	}

	var dirs []string
	for _, entry := range entries {
		if entry.IsDir() {
			dirs = append(dirs, entry.Name())
		}
	}

	if len(dirs) == 0 {
		return "", nil
	}

	sort.Strings(dirs)
	return filepath.Join(baseDir, dirs[len(dirs)-1]), nil
}

func WriteMessageFile(convDir string, role Role, content string) (string, error) {
	timestampNs := time.Now().UnixNano()
	filename := fmt.Sprintf("%d-%s.md", timestampNs, role)
	filePath := filepath.Join(convDir, filename)

	if _, err := os.Stat(filePath); err == nil {
		return "", fmt.Errorf("file collision detected for path: %s", filePath)
	}

	if err := os.WriteFile(filePath, []byte(content), 0644); err != nil {
		return "", fmt.Errorf("failed to write message file: %w", err)
	}

	return filename, nil
}

func ListMessages(convDir string) ([]ChatMessage, error) {
	entries, err := os.ReadDir(convDir)
	if err != nil {
		return nil, err
	}

	var messages []ChatMessage
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
			continue
		}

		name := entry.Name()
		stem := strings.TrimSuffix(name, ".md")
		parts := strings.SplitN(stem, "-", 2)
		if len(parts) != 2 {
			continue
		}

		timestamp, err := strconv.ParseInt(parts[0], 10, 64)
		if err != nil {
			continue
		}

		role, err := ParseRole(parts[1])
		if err != nil {
			continue
		}

		messages = append(messages, ChatMessage{
			Path:      filepath.Join(convDir, name),
			Timestamp: timestamp,
			Role:      role,
		})
	}

	sort.Slice(messages, func(i, j int) bool {
		return messages[i].Less(messages[j])
	})

	return messages, nil
}

func PackConversation(convDir string, writer io.Writer, merge bool) error {
	messages, err := ListMessages(convDir)
	if err != nil {
		return err
	}

	// Filter out assistant-reasoning messages - they're internal only
	var filteredMessages []ChatMessage
	for _, msg := range messages {
		if msg.Role != RoleAssistantReasoning {
			filteredMessages = append(filteredMessages, msg)
		}
	}
	messages = filteredMessages

	if merge {
		i := 0
		for i < len(messages) {
			msg := messages[i]
			role := msg.Role

			if _, err := fmt.Fprintf(writer, "<hnt-%s>", role); err != nil {
				return err
			}

			file, err := os.Open(msg.Path)
			if err != nil {
				return fmt.Errorf("failed to open message file %s: %w", msg.Path, err)
			}
			if err := escaping.Escape(file, writer); err != nil {
				file.Close()
				return err
			}
			file.Close()

			for i+1 < len(messages) && messages[i+1].Role == role {
				i++
				if _, err := writer.Write([]byte("\n")); err != nil {
					return err
				}
				file, err := os.Open(messages[i].Path)
				if err != nil {
					return fmt.Errorf("failed to open message file %s: %w", messages[i].Path, err)
				}
				if err := escaping.Escape(file, writer); err != nil {
					file.Close()
					return err
				}
				file.Close()
			}

			if _, err := fmt.Fprintf(writer, "</hnt-%s>\n", role); err != nil {
				return err
			}
			i++
		}
	} else {
		for _, msg := range messages {
			if _, err := fmt.Fprintf(writer, "<hnt-%s>", msg.Role); err != nil {
				return err
			}

			file, err := os.Open(msg.Path)
			if err != nil {
				return fmt.Errorf("failed to open message file %s: %w", msg.Path, err)
			}
			if err := escaping.Escape(file, writer); err != nil {
				file.Close()
				return err
			}
			file.Close()

			if _, err := fmt.Fprintf(writer, "</hnt-%s>\n", msg.Role); err != nil {
				return err
			}
		}
	}

	return nil
}
