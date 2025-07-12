package llm

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/veilm/hinata/hnt-llm/pkg/keymanagement"
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
		authHeader := "Bearer " + apiKey
		if providerName == "google" {
			authHeader = apiKey
			req.Header.Set("x-goog-api-key", authHeader)
		} else {
			req.Header.Set("Authorization", authHeader)
		}

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

		for {
			chunk, err := reader.ReadBytes('\n')
			if err != nil && err != io.EOF {
				errChan <- err
				return
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
				if !strings.HasPrefix(eventStr, "data: ") {
					continue
				}

				dataStr := strings.TrimPrefix(eventStr, "data: ")
				dataStr = strings.TrimSpace(dataStr)

				if dataStr == "[DONE]" {
					return
				}

				var chunk ApiResponseChunk
				if err := json.Unmarshal([]byte(dataStr), &chunk); err != nil {
					continue
				}

				if len(chunk.Choices) > 0 {
					delta := chunk.Choices[0].Delta

					if delta.Content != nil && *delta.Content != "" {
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

			if err == io.EOF {
				return
			}
		}
	}()

	return eventChan, errChan
}
