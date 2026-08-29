package llm

import "encoding/json"

type Config struct {
	Model            string
	SystemPrompt     string
	IncludeReasoning bool
	RequestOverrides map[string]interface{}
}

type StreamEvent struct {
	Content   string
	Reasoning string
	Metadata  *StreamMetadata
}

type StreamMetadata struct {
	Provider           string          `json:"provider,omitempty"`
	ModelRequested     string          `json:"model_requested,omitempty"`
	ModelSent          string          `json:"model_sent,omitempty"`
	ResponseID         string          `json:"response_id,omitempty"`
	GenerationID       string          `json:"generation_id,omitempty"`
	CreatedUnix        int64           `json:"created_unix,omitempty"`
	ModelReturned      string          `json:"model_returned,omitempty"`
	FinishReason       string          `json:"finish_reason,omitempty"`
	NativeFinishReason string          `json:"native_finish_reason,omitempty"`
	SystemFingerprint  string          `json:"system_fingerprint,omitempty"`
	Streamed           bool            `json:"streamed,omitempty"`
	Usage              *UsageMetadata  `json:"usage,omitempty"`
	RawUsage           json.RawMessage `json:"raw_usage,omitempty"`
	ProviderError      *APIError       `json:"provider_error,omitempty"`
}

type UsageMetadata struct {
	PromptTokens            *int                   `json:"prompt_tokens,omitempty"`
	CompletionTokens        *int                   `json:"completion_tokens,omitempty"`
	TotalTokens             *int                   `json:"total_tokens,omitempty"`
	PromptTokensDetails     map[string]interface{} `json:"prompt_tokens_details,omitempty"`
	CompletionTokensDetails map[string]interface{} `json:"completion_tokens_details,omitempty"`
	CostExact               *CostMetadata          `json:"cost_exact,omitempty"`
	CostDetails             map[string]interface{} `json:"cost_details,omitempty"`
}

type CostMetadata struct {
	Value  float64 `json:"value"`
	Unit   string  `json:"unit"`
	Source string  `json:"source"`
}

type APIError struct {
	Message  string                 `json:"message,omitempty"`
	Code     interface{}            `json:"code,omitempty"`
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

func (m *StreamMetadata) Merge(update *StreamMetadata) {
	if update == nil {
		return
	}
	if update.Provider != "" {
		m.Provider = update.Provider
	}
	if update.ModelRequested != "" {
		m.ModelRequested = update.ModelRequested
	}
	if update.ModelSent != "" {
		m.ModelSent = update.ModelSent
	}
	if update.ResponseID != "" {
		m.ResponseID = update.ResponseID
	}
	if update.GenerationID != "" {
		m.GenerationID = update.GenerationID
	}
	if update.CreatedUnix != 0 {
		m.CreatedUnix = update.CreatedUnix
	}
	if update.ModelReturned != "" {
		m.ModelReturned = update.ModelReturned
	}
	if update.FinishReason != "" {
		m.FinishReason = update.FinishReason
	}
	if update.NativeFinishReason != "" {
		m.NativeFinishReason = update.NativeFinishReason
	}
	if update.SystemFingerprint != "" {
		m.SystemFingerprint = update.SystemFingerprint
	}
	if update.Streamed {
		m.Streamed = true
	}
	if update.Usage != nil {
		m.Usage = update.Usage
	}
	if len(update.RawUsage) > 0 {
		m.RawUsage = append(json.RawMessage(nil), update.RawUsage...)
	}
	if update.ProviderError != nil {
		m.ProviderError = update.ProviderError
	}
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ApiRequest struct {
	Model            string                 `json:"model"`
	Messages         []Message              `json:"messages"`
	Stream           bool                   `json:"stream"`
	StreamOptions    *StreamOptions         `json:"stream_options,omitempty"`
	IncludeReasoning bool                   `json:"include_reasoning"`
	Reasoning        *ReasoningParams       `json:"reasoning,omitempty"`
	ExtraBody        map[string]interface{} `json:"extra_body,omitempty"`
}

type StreamOptions struct {
	IncludeUsage bool `json:"include_usage"`
}

type ReasoningParams struct {
	Enabled bool `json:"enabled"`
}

type ApiResponseChunk struct {
	ID                string          `json:"id,omitempty"`
	Created           int64           `json:"created,omitempty"`
	Model             string          `json:"model,omitempty"`
	SystemFingerprint string          `json:"system_fingerprint,omitempty"`
	Choices           []Choice        `json:"choices"`
	Usage             json.RawMessage `json:"usage,omitempty"`
	Error             *APIError       `json:"error,omitempty"`
}

type Choice struct {
	Delta              Delta   `json:"delta"`
	FinishReason       *string `json:"finish_reason,omitempty"`
	NativeFinishReason *string `json:"native_finish_reason,omitempty"`
}

type Delta struct {
	Content          *string `json:"content,omitempty"`
	Reasoning        *string `json:"reasoning,omitempty"`
	ReasoningContent *string `json:"reasoning_content,omitempty"`
}

type Provider struct {
	Name         string
	ApiURL       string
	EnvVar       string
	ExtraHeaders map[string]string
}

var Providers = []Provider{
	{
		Name:   "openai",
		ApiURL: "https://api.openai.com/v1/chat/completions",
		EnvVar: "OPENAI_API_KEY",
	},
	{
		Name:   "openrouter",
		ApiURL: "https://openrouter.ai/api/v1/chat/completions",
		EnvVar: "OPENROUTER_API_KEY",
		ExtraHeaders: map[string]string{
			"HTTP-Referer":       "https://github.com/veilm/hinata",
			"X-OpenRouter-Title": "hinata",
		},
	},
	{
		Name:   "deepseek",
		ApiURL: "https://api.deepseek.com/chat/completions",
		EnvVar: "DEEPSEEK_API_KEY",
	},
	{
		Name:   "google",
		ApiURL: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
		EnvVar: "GOOGLE_API_KEY",
	},
}

func (d *Delta) UnmarshalJSON(data []byte) error {
	type Alias Delta
	aux := &struct {
		*Alias
	}{
		Alias: (*Alias)(d),
	}
	return json.Unmarshal(data, &aux)
}
