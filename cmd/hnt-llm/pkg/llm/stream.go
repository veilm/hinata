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
	"net/http/httputil"
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
			Model:         actualModel,
			Messages:      messages,
			Stream:        true,
			StreamOptions: &StreamOptions{IncludeUsage: true},
			// OpenRouter ignores stream_options.include_usage because usage is
			// automatic there, but OpenAI-compatible providers use it.
			IncludeReasoning: true,
			Reasoning: &ReasoningParams{
				Enabled: true,
			},
		}

		payloadMap, err := structToMap(payload)
		if err != nil {
			errChan <- err
			return
		}

		if len(config.RequestOverrides) > 0 {
			payloadMap = mergePayloadMaps(payloadMap, config.RequestOverrides)
		}

		jsonPayload, err := json.Marshal(payloadMap)
		if err != nil {
			errChan <- err
			return
		}

		req, err := http.NewRequestWithContext(ctx, "POST", provider.ApiURL, bytes.NewReader(jsonPayload))
		if err != nil {
			errChan <- err
			return
		}
		req.GetBody = func() (io.ReadCloser, error) {
			return io.NopCloser(bytes.NewReader(jsonPayload)), nil
		}
		req.ContentLength = int64(len(jsonPayload))

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+apiKey)

		for k, v := range provider.ExtraHeaders {
			req.Header.Set(k, v)
		}

		if debugLogger != nil {
			originalAuth := req.Header.Get("Authorization")
			if originalAuth != "" {
				req.Header.Set("Authorization", "[REDACTED]")
			}

			if dump, err := httputil.DumpRequestOut(req, true); err != nil {
				debugLogger.Printf("Failed to dump request: %v", err)
			} else {
				debugLogger.Printf("=== HTTP Request ===\n%s", dump)
			}

			if originalAuth != "" {
				req.Header.Set("Authorization", originalAuth)
			}

			body, err := req.GetBody()
			if err != nil {
				body = io.NopCloser(bytes.NewReader(jsonPayload))
			}
			req.Body = body
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

		eventChan <- StreamEvent{Metadata: &StreamMetadata{
			Provider:       providerName,
			ModelRequested: config.Model,
			ModelSent:      actualModel,
			GenerationID:   resp.Header.Get("X-Generation-Id"),
			Streamed:       true,
		}}

		reader := bufio.NewReader(resp.Body)
		var buffer bytes.Buffer
		isDone := false

		for {
			chunk, err := reader.ReadBytes('\n')

			// Always process any data we got, even if there was an error
			if len(chunk) > 0 {
				if debugLogger != nil {
					debugLogger.Printf("Read %d bytes: %q", len(chunk), string(chunk))
				}
				buffer.Write(chunk)
			}

			// Now handle the error after processing data
			if err != nil && err != io.EOF {
				if debugLogger != nil {
					debugLogger.Printf("Read error: %v", err)
				}
				errChan <- err
				return
			}

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

				emitChunkEvents(eventChan, chunk, config, debugLogger)
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
							if err := json.Unmarshal([]byte(dataStr), &chunk); err == nil {
								emitChunkEvents(eventChan, chunk, config, debugLogger)
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

func emitChunkEvents(eventChan chan<- StreamEvent, chunk ApiResponseChunk, config Config, debugLogger *log.Logger) {
	if metadata := metadataFromChunk(chunk); metadata != nil {
		eventChan <- StreamEvent{Metadata: metadata}
	}

	if len(chunk.Choices) == 0 {
		return
	}

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

func metadataFromChunk(chunk ApiResponseChunk) *StreamMetadata {
	metadata := &StreamMetadata{
		ResponseID:        chunk.ID,
		CreatedUnix:       chunk.Created,
		ModelReturned:     chunk.Model,
		SystemFingerprint: chunk.SystemFingerprint,
		ProviderError:     chunk.Error,
	}

	if len(chunk.Choices) > 0 {
		choice := chunk.Choices[0]
		if choice.FinishReason != nil {
			metadata.FinishReason = *choice.FinishReason
		}
		if choice.NativeFinishReason != nil {
			metadata.NativeFinishReason = *choice.NativeFinishReason
		}
	}

	if len(chunk.Usage) > 0 && string(chunk.Usage) != "null" {
		metadata.RawUsage = append(json.RawMessage(nil), chunk.Usage...)
		metadata.Usage = parseUsageMetadata(chunk.Usage)
	}

	if metadata.ResponseID == "" &&
		metadata.CreatedUnix == 0 &&
		metadata.ModelReturned == "" &&
		metadata.SystemFingerprint == "" &&
		metadata.FinishReason == "" &&
		metadata.NativeFinishReason == "" &&
		metadata.Usage == nil &&
		metadata.ProviderError == nil {
		return nil
	}

	return metadata
}

func parseUsageMetadata(raw json.RawMessage) *UsageMetadata {
	var usageMap map[string]interface{}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&usageMap); err != nil {
		return nil
	}

	usage := &UsageMetadata{
		PromptTokens:            intField(usageMap, "prompt_tokens"),
		CompletionTokens:        intField(usageMap, "completion_tokens"),
		TotalTokens:             intField(usageMap, "total_tokens"),
		PromptTokensDetails:     mapField(usageMap, "prompt_tokens_details"),
		CompletionTokensDetails: mapField(usageMap, "completion_tokens_details"),
		CostDetails:             mapField(usageMap, "cost_details"),
	}

	if cost, ok := floatField(usageMap, "cost"); ok {
		usage.CostExact = &CostMetadata{
			Value:  cost,
			Unit:   "credits",
			Source: "stream_usage",
		}
	}

	return usage
}

func intField(data map[string]interface{}, key string) *int {
	value, ok := data[key]
	if !ok || value == nil {
		return nil
	}

	switch typed := value.(type) {
	case json.Number:
		if i, err := typed.Int64(); err == nil {
			v := int(i)
			return &v
		}
	case float64:
		v := int(typed)
		return &v
	}

	return nil
}

func floatField(data map[string]interface{}, key string) (float64, bool) {
	value, ok := data[key]
	if !ok || value == nil {
		return 0, false
	}

	switch typed := value.(type) {
	case json.Number:
		if f, err := typed.Float64(); err == nil {
			return f, true
		}
	case float64:
		return typed, true
	case string:
		var number json.Number = json.Number(typed)
		if f, err := number.Float64(); err == nil {
			return f, true
		}
	}

	return 0, false
}

func mapField(data map[string]interface{}, key string) map[string]interface{} {
	value, ok := data[key]
	if !ok || value == nil {
		return nil
	}

	if typed, ok := value.(map[string]interface{}); ok && len(typed) > 0 {
		return typed
	}

	return nil
}

func structToMap(v interface{}) (map[string]interface{}, error) {
	data, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	var result map[string]interface{}
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func mergePayloadMaps(base map[string]interface{}, overrides map[string]interface{}) map[string]interface{} {
	if base == nil {
		base = make(map[string]interface{})
	}
	for key, overrideVal := range overrides {
		overrideMap, overrideIsMap := overrideVal.(map[string]interface{})
		if baseVal, ok := base[key]; ok && overrideIsMap {
			if baseMap, ok := baseVal.(map[string]interface{}); ok {
				base[key] = mergePayloadMaps(baseMap, overrideMap)
				continue
			}
		}
		if overrideIsMap {
			base[key] = mergePayloadMaps(make(map[string]interface{}), overrideMap)
		} else {
			base[key] = overrideVal
		}
	}
	return base
}
