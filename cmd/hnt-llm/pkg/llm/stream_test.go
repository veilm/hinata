package llm

import (
	"encoding/json"
	"testing"
)

func TestRequestOverridesCanDisableStreamUsage(t *testing.T) {
	payload := ApiRequest{
		Model:         "test-model",
		Messages:      []Message{{Role: "user", Content: "hello"}},
		Stream:        true,
		StreamOptions: &StreamOptions{IncludeUsage: true},
	}

	base, err := structToMap(payload)
	if err != nil {
		t.Fatalf("structToMap() error = %v", err)
	}

	merged := mergePayloadMaps(base, map[string]interface{}{
		"stream_options": map[string]interface{}{
			"include_usage": false,
		},
	})

	streamOptions, ok := merged["stream_options"].(map[string]interface{})
	if !ok {
		t.Fatalf("stream_options missing or wrong type: %#v", merged["stream_options"])
	}
	if got := streamOptions["include_usage"]; got != false {
		t.Fatalf("include_usage = %#v, want false", got)
	}
}

func TestParseUsageMetadataCapturesOpenRouterCost(t *testing.T) {
	usage := parseUsageMetadata(json.RawMessage(`{
		"prompt_tokens": 13,
		"completion_tokens": 1,
		"total_tokens": 14,
		"cost": 0.0000025245,
		"prompt_tokens_details": {"cached_tokens": 0},
		"completion_tokens_details": {"reasoning_tokens": 0},
		"cost_details": {"upstream_inference_cost": 0.00000255}
	}`))

	if usage == nil {
		t.Fatal("parseUsageMetadata() returned nil")
	}
	if usage.TotalTokens == nil || *usage.TotalTokens != 14 {
		t.Fatalf("total_tokens = %#v, want 14", usage.TotalTokens)
	}
	if usage.CostExact == nil {
		t.Fatal("CostExact is nil")
	}
	if usage.CostExact.Value != 0.0000025245 {
		t.Fatalf("cost = %v, want 0.0000025245", usage.CostExact.Value)
	}
	if usage.CostExact.Source != "stream_usage" {
		t.Fatalf("cost source = %q, want stream_usage", usage.CostExact.Source)
	}
}
