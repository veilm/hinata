package llm

import "encoding/json"

type Config struct {
	Model            string
	SystemPrompt     string
	IncludeReasoning bool
}

type StreamEvent struct {
	Content   string
	Reasoning string
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ApiRequest struct {
	Model    string    `json:"model"`
	Messages []Message `json:"messages"`
	Stream   bool      `json:"stream"`
}

type ApiResponseChunk struct {
	Choices []Choice `json:"choices"`
}

type Choice struct {
	Delta Delta `json:"delta"`
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
			"HTTP-Referer": "https://hnt-agent.org/",
			"X-Title":      "hinata",
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
