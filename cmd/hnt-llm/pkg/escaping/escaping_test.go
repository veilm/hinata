package escaping

import (
	"bytes"
	"strings"
	"testing"
)

func TestEscape(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "basic hnt tags",
			input:    "<hnt-user>Hello</hnt-user>",
			expected: "<_hnt-user>Hello</_hnt-user>",
		},
		{
			name:     "assistant tag",
			input:    "<hnt-assistant>Hi</hnt-assistant>",
			expected: "<_hnt-assistant>Hi</_hnt-assistant>",
		},
		{
			name:     "system tag",
			input:    "<hnt-system>System</hnt-system>",
			expected: "<_hnt-system>System</_hnt-system>",
		},
		{
			name:     "already escaped",
			input:    "<_hnt-user>Test</_hnt-user>",
			expected: "<__hnt-user>Test</__hnt-user>",
		},
		{
			name:     "multiple underscores",
			input:    "<___hnt-assistant>Multiple</___hnt-assistant>",
			expected: "<____hnt-assistant>Multiple</____hnt-assistant>",
		},
		{
			name:     "regular tags unchanged",
			input:    "<tag>content</tag>",
			expected: "<tag>content</tag>",
		},
		{
			name:     "mixed content",
			input:    "Before <hnt-user>User message with <tag> inside</hnt-user> after",
			expected: "Before <_hnt-user>User message with <tag> inside</_hnt-user> after",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var buf bytes.Buffer
			err := Escape(strings.NewReader(tt.input), &buf)
			if err != nil {
				t.Fatalf("Escape error: %v", err)
			}
			if buf.String() != tt.expected {
				t.Errorf("Expected %q, got %q", tt.expected, buf.String())
			}
		})
	}
}

func TestUnescape(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "basic escaped tags",
			input:    "<_hnt-user>Hello</_hnt-user>",
			expected: "<hnt-user>Hello</hnt-user>",
		},
		{
			name:     "assistant tag",
			input:    "<_hnt-assistant>Hi</_hnt-assistant>",
			expected: "<hnt-assistant>Hi</hnt-assistant>",
		},
		{
			name:     "system tag",
			input:    "<_hnt-system>System</_hnt-system>",
			expected: "<hnt-system>System</hnt-system>",
		},
		{
			name:     "multiple underscores",
			input:    "<__hnt-user>Test</__hnt-user>",
			expected: "<_hnt-user>Test</_hnt-user>",
		},
		{
			name:     "many underscores",
			input:    "<____hnt-assistant>Multiple</____hnt-assistant>",
			expected: "<___hnt-assistant>Multiple</___hnt-assistant>",
		},
		{
			name:     "no underscores",
			input:    "<hnt-user>No underscores</hnt-user>",
			expected: "<hnt-user>No underscores</hnt-user>",
		},
		{
			name:     "regular text unchanged",
			input:    "no escaping here",
			expected: "no escaping here",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := Unescape(tt.input)
			if result != tt.expected {
				t.Errorf("Expected %q, got %q", tt.expected, result)
			}
		})
	}
}
