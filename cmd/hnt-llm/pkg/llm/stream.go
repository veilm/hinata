package llm

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/veilm/hinata/cmd/hnt-llm/pkg/keymanagement"
)

func findSSETerminator(buffer []byte) (int, int) {
	crlfPos := bytes.Index(buffer, []byte("\r\n\r\n"))
	lfPos := bytes.Index(buffer, []byte("\n\n"))

	if crlfPos != -1 && (lfPos == -1 || crlfPos < lfPos) {
		return crlfPos, 4
	}
	if lfPos != -1 {
		return lfPos, 2
	}
	return -1, 0
}

func StreamLLMResponse(ctx context.Context, config Config, promptContent string) (<-chan StreamEvent, <-chan error) {
	eventChan := make(chan StreamEvent, 100)
	errChan := make(chan error, 1)

	go func() {
		defer close(eventChan)
		defer close(errChan)

		// Setup debug logging if enabled
		var debugLogger *log.Logger
		if debugPath := os.Getenv("HINATA_STREAM_DEBUG"); debugPath != "" {
			logDir := filepath.Join(os.TempDir(), "hinata-stream-debug")
			os.MkdirAll(logDir, 0755)

			timestamp := time.Now().Format("20060102-150405")
			logFile := filepath.Join(logDir, fmt.Sprintf("stream-%s.log", timestamp))

			if file, err := os.Create(logFile); err == nil {
				debugLogger = log.New(file, "", log.Ldate|log.Ltime|log.Lmicroseconds)
				debugLogger.Printf("=== Stream Debug Log Started ===")
				debugLogger.Printf("Model: %s", config.Model)
				defer func() {
					debugLogger.Printf("=== Stream Debug Log Ended ===")
					file.Close()
				}()
			}
		}

		providerName, modelName := "openrouter", config.Model
		if idx := strings.Index(config.Model, "/"); idx != -1 {
			providerName = config.Model[:idx]
			modelName = config.Model[idx+1:]
		}

		var provider *Provider
		for i := range Providers {
			if Providers[i].Name == providerName {
				provider = &Providers[i]
				break
			}
		}
		if provider == nil {
			errChan <- fmt.Errorf("provider '%s' not found", providerName)
			return
		}

		apiKey := os.Getenv(provider.EnvVar)
		if apiKey == "" {
			var err error
			apiKey, err = keymanagement.GetAPIKeyFromStore(provider.Name)
			if err != nil || apiKey == "" {
				errChan <- fmt.Errorf("API key for '%s' not found. Please set %s or save the key with `hnt-llm save-key %s`",
					provider.Name, provider.EnvVar, provider.Name)
				return
			}
		}

		messages, err := BuildMessages(promptContent, config.SystemPrompt)
		if err != nil {
			errChan <- err
			return
		}

		actualModel := modelName
		if providerName == "openrouter" {
			actualModel = strings.ReplaceAll(modelName, "/", "/")
		} else if providerName == "google" && !strings.HasPrefix(modelName, "models/") {
			actualModel = "models/" + modelName
		}

		payload := ApiRequest{
			Model:    actualModel,
			Messages: messages,
			Stream:   true,
		}

		jsonPayload, err := json.Marshal(payload)
		if err != nil {
			errChan <- err
			return
		}

		req, err := http.NewRequestWithContext(ctx, "POST", provider.ApiURL, bytes.NewReader(jsonPayload))
		if err != nil {
			errChan <- err
			return
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+apiKey)

		for k, v := range provider.ExtraHeaders {
			req.Header.Set(k, v)
		}

		client := &http.Client{}
		resp, err := client.Do(req)
		if err != nil {
			errChan <- err
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			errChan <- fmt.Errorf("API error: %s - %s", resp.Status, string(body))
			return
		}

		reader := bufio.NewReader(resp.Body)
		var buffer bytes.Buffer
		isDone := false

		for {
			chunk, err := reader.ReadBytes('\n')
			if err != nil && err != io.EOF {
				if debugLogger != nil {
					debugLogger.Printf("Read error: %v", err)
				}
				errChan <- err
				return
			}

			if debugLogger != nil && len(chunk) > 0 {
				debugLogger.Printf("Read %d bytes: %q", len(chunk), string(chunk))
			}

			buffer.Write(chunk)

			for {
				pos, termLen := findSSETerminator(buffer.Bytes())
				if pos == -1 {
					break
				}

				event := buffer.Bytes()[:pos]
				buffer.Next(pos + termLen)

				eventStr := string(event)
				if debugLogger != nil {
					debugLogger.Printf("Extracted event from buffer (len=%d): %q", len(eventStr), eventStr)
				}

				if !strings.HasPrefix(eventStr, "data: ") {
					if debugLogger != nil {
						debugLogger.Printf("DROPPING event (no 'data:' prefix): %q", eventStr)
					}
					continue
				}

				dataStr := strings.TrimPrefix(eventStr, "data: ")
				dataStr = strings.TrimSpace(dataStr)

				if dataStr == "[DONE]" {
					if debugLogger != nil {
						debugLogger.Printf("Received [DONE] signal, will process remaining buffer")
					}
					isDone = true
					continue // Process remaining events in buffer before returning
				}

				var chunk ApiResponseChunk
				if err := json.Unmarshal([]byte(dataStr), &chunk); err != nil {
					if debugLogger != nil {
						debugLogger.Printf("JSON unmarshal error for data: %q, error: %v", dataStr, err)
					}
					continue
				}

				if len(chunk.Choices) > 0 {
					delta := chunk.Choices[0].Delta

					if delta.Content != nil && *delta.Content != "" {
						if debugLogger != nil {
							debugLogger.Printf("Sending content: %q", *delta.Content)
						}
						eventChan <- StreamEvent{Content: *delta.Content}
					}

					if config.IncludeReasoning {
						if delta.Reasoning != nil && *delta.Reasoning != "" {
							eventChan <- StreamEvent{Reasoning: *delta.Reasoning}
						} else if delta.ReasoningContent != nil && *delta.ReasoningContent != "" {
							eventChan <- StreamEvent{Reasoning: *delta.ReasoningContent}
						}
					}
				}
			}

			// Check if we should exit:
			// 1. We've seen [DONE] and processed all events in buffer
			// 2. We've reached EOF
			if isDone || err == io.EOF {
				if debugLogger != nil {
					debugLogger.Printf("Exit condition: isDone=%v, EOF=%v, bufferLen=%d", isDone, err == io.EOF, buffer.Len())
				}
				// Process any remaining data in the buffer before returning
				if buffer.Len() > 0 && !isDone {
					// Check if there's an incomplete SSE event in the buffer
					eventStr := strings.TrimSpace(buffer.String())
					if debugLogger != nil {
						debugLogger.Printf("Processing remaining buffer at EOF (len=%d): %q", len(eventStr), eventStr)
					}
					if strings.HasPrefix(eventStr, "data: ") {
						dataStr := strings.TrimPrefix(eventStr, "data: ")
						dataStr = strings.TrimSpace(dataStr)

						if dataStr != "[DONE]" {
							var chunk ApiResponseChunk
							if err := json.Unmarshal([]byte(dataStr), &chunk); err == nil && len(chunk.Choices) > 0 {
								delta := chunk.Choices[0].Delta

								if delta.Content != nil && *delta.Content != "" {
									if debugLogger != nil {
										debugLogger.Printf("Sending final buffer content: %q", *delta.Content)
									}
									eventChan <- StreamEvent{Content: *delta.Content}
								}

								if config.IncludeReasoning {
									if delta.Reasoning != nil && *delta.Reasoning != "" {
										eventChan <- StreamEvent{Reasoning: *delta.Reasoning}
									} else if delta.ReasoningContent != nil && *delta.ReasoningContent != "" {
										eventChan <- StreamEvent{Reasoning: *delta.ReasoningContent}
									}
								}
							} else if debugLogger != nil && err != nil {
								debugLogger.Printf("JSON unmarshal error for final buffer data: %q, error: %v", dataStr, err)
							}
						}
					} else if debugLogger != nil {
						debugLogger.Printf("DROPPING final buffer (no 'data:' prefix): %q", eventStr)
					}
				}

				// Only return if we've seen [DONE] or reached EOF with no more data
				if isDone || err == io.EOF {
					if debugLogger != nil {
						debugLogger.Printf("Exiting stream loop")
					}
					return
				}
			}
		}
	}()

	return eventChan, errChan
}
