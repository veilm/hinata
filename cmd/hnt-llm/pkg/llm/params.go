package llm

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// ParseRequestParams accepts either a raw JSON object string or a path prefixed with '@'
// and returns a map suitable for merging into the API request payload.
func ParseRequestParams(value string) (map[string]interface{}, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil, nil
	}

	var raw []byte
	if strings.HasPrefix(value, "@") {
		path := strings.TrimPrefix(value, "@")
		content, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("failed to read request params file: %w", err)
		}
		raw = content
	} else {
		raw = []byte(value)
	}

	var payload map[string]interface{}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, fmt.Errorf("invalid JSON for request params: %w", err)
	}
	return payload, nil
}
