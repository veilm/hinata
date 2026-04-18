package chat

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/veilm/hinata/cmd/hnt-llm/pkg/llm"
)

type MessageMetadata struct {
	Message      MessageMetadataMessage                `json:"message"`
	Capture      MessageMetadataCapture                `json:"capture"`
	Request      MessageMetadataRequest                `json:"request"`
	Response     MessageMetadataResponse               `json:"response,omitempty"`
	Usage        *llm.UsageMetadata                    `json:"usage,omitempty"`
	ProviderData map[string]MessageMetadataProviderRaw `json:"provider_data,omitempty"`
}

type MessageMetadataMessage struct {
	TimestampNS   int64  `json:"timestamp_ns"`
	File          string `json:"file"`
	ReasoningFile string `json:"reasoning_file,omitempty"`
	ContentSHA256 string `json:"content_sha256,omitempty"`
}

type MessageMetadataCapture struct {
	Status         string   `json:"status"`
	Streamed       bool     `json:"streamed"`
	SavedAtUnix    int64    `json:"saved_at_unix"`
	MetadataSource string   `json:"metadata_source"`
	Errors         []string `json:"errors,omitempty"`
}

type MessageMetadataRequest struct {
	Provider       string `json:"provider,omitempty"`
	APIFamily      string `json:"api_family,omitempty"`
	ModelRequested string `json:"model_requested,omitempty"`
	ModelSent      string `json:"model_sent,omitempty"`
	InputSHA256    string `json:"input_sha256,omitempty"`
}

type MessageMetadataResponse struct {
	ID                 string `json:"id,omitempty"`
	GenerationID       string `json:"generation_id,omitempty"`
	CreatedUnix        int64  `json:"created_unix,omitempty"`
	ModelReturned      string `json:"model_returned,omitempty"`
	FinishReason       string `json:"finish_reason,omitempty"`
	NativeFinishReason string `json:"native_finish_reason,omitempty"`
	SystemFingerprint  string `json:"system_fingerprint,omitempty"`
}

type MessageMetadataProviderRaw struct {
	RawUsage      json.RawMessage `json:"raw_usage,omitempty"`
	ProviderError *llm.APIError   `json:"provider_error,omitempty"`
}

func NewMessageMetadata(timestampNs int64, messageFile, reasoningFile, input, content string, streamMetadata llm.StreamMetadata) MessageMetadata {
	metadata := MessageMetadata{
		Message: MessageMetadataMessage{
			TimestampNS:   timestampNs,
			File:          messageFile,
			ReasoningFile: reasoningFile,
			ContentSHA256: SHA256Hex(content),
		},
		Capture: MessageMetadataCapture{
			Status:         "complete",
			Streamed:       streamMetadata.Streamed,
			SavedAtUnix:    time.Now().Unix(),
			MetadataSource: "stream",
		},
		Request: MessageMetadataRequest{
			Provider:       streamMetadata.Provider,
			APIFamily:      "openai_chat_completions",
			ModelRequested: streamMetadata.ModelRequested,
			ModelSent:      streamMetadata.ModelSent,
			InputSHA256:    SHA256Hex(input),
		},
		Response: MessageMetadataResponse{
			ID:                 streamMetadata.ResponseID,
			GenerationID:       streamMetadata.GenerationID,
			CreatedUnix:        streamMetadata.CreatedUnix,
			ModelReturned:      streamMetadata.ModelReturned,
			FinishReason:       streamMetadata.FinishReason,
			NativeFinishReason: streamMetadata.NativeFinishReason,
			SystemFingerprint:  streamMetadata.SystemFingerprint,
		},
		Usage: streamMetadata.Usage,
	}

	if streamMetadata.ProviderError != nil {
		metadata.Capture.Errors = append(metadata.Capture.Errors, streamMetadata.ProviderError.Message)
	}

	if streamMetadata.Provider != "" && (len(streamMetadata.RawUsage) > 0 || streamMetadata.ProviderError != nil) {
		metadata.ProviderData = map[string]MessageMetadataProviderRaw{
			streamMetadata.Provider: {
				RawUsage:      streamMetadata.RawUsage,
				ProviderError: streamMetadata.ProviderError,
			},
		}
	}

	return metadata
}

func SHA256Hex(content string) string {
	sum := sha256.Sum256([]byte(content))
	return fmt.Sprintf("%x", sum)
}

func WriteMessageMetadataFile(convDir string, metadata MessageMetadata, timestampNs int64) error {
	metaDir := filepath.Join(convDir, "meta", "messages")
	if err := os.MkdirAll(metaDir, 0755); err != nil {
		return fmt.Errorf("failed to create message metadata directory: %w", err)
	}

	filePath := filepath.Join(metaDir, fmt.Sprintf("%d.json", timestampNs))
	data, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal message metadata: %w", err)
	}
	data = append(data, '\n')

	if err := os.WriteFile(filePath, data, 0644); err != nil {
		return fmt.Errorf("failed to write message metadata file: %w", err)
	}

	return nil
}

// CopyMessageMetadataForExistingMessages copies per-message metadata files whose
// timestamps match assistant messages that already exist in dstDir.
func CopyMessageMetadataForExistingMessages(srcDir, dstDir string) error {
	retainedAssistantTimestamps, err := retainedAssistantTimestamps(dstDir)
	if err != nil {
		return err
	}
	if len(retainedAssistantTimestamps) == 0 {
		return nil
	}

	srcMetaDir := filepath.Join(srcDir, "meta", "messages")
	entries, err := os.ReadDir(srcMetaDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("failed to read source message metadata directory: %w", err)
	}

	dstMetaDir := filepath.Join(dstDir, "meta", "messages")
	dstMetaCreated := false
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}

		stem := strings.TrimSuffix(entry.Name(), ".json")
		timestamp, err := strconv.ParseInt(stem, 10, 64)
		if err != nil {
			continue
		}
		if _, ok := retainedAssistantTimestamps[timestamp]; !ok {
			continue
		}

		if !dstMetaCreated {
			if err := os.MkdirAll(dstMetaDir, 0755); err != nil {
				return fmt.Errorf("failed to create destination message metadata directory: %w", err)
			}
			dstMetaCreated = true
		}

		srcPath := filepath.Join(srcMetaDir, entry.Name())
		dstPath := filepath.Join(dstMetaDir, entry.Name())
		data, err := os.ReadFile(srcPath)
		if err != nil {
			return fmt.Errorf("failed to read message metadata file %s: %w", srcPath, err)
		}
		if err := os.WriteFile(dstPath, data, 0644); err != nil {
			return fmt.Errorf("failed to write message metadata file %s: %w", dstPath, err)
		}
	}

	return nil
}

func RemoveMessageMetadataFile(convDir string, timestampNs int64) error {
	path := filepath.Join(convDir, "meta", "messages", fmt.Sprintf("%d.json", timestampNs))
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("failed to remove message metadata file %s: %w", path, err)
	}
	return nil
}

func retainedAssistantTimestamps(convDir string) (map[int64]struct{}, error) {
	messages, err := ListMessages(convDir)
	if err != nil {
		return nil, fmt.Errorf("failed to list destination messages: %w", err)
	}

	timestamps := make(map[int64]struct{})
	for _, msg := range messages {
		if msg.Role == RoleAssistant {
			timestamps[msg.Timestamp] = struct{}{}
		}
	}

	return timestamps, nil
}
