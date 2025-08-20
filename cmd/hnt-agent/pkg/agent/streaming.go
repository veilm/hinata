package agent

import (
	"context"
	"fmt"
	"strings"

	"github.com/fatih/color"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/linebuffer"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/spinner"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/streamspinner"
	"github.com/veilm/hinata/cmd/hnt-llm/pkg/llm"
)

// streamLLMResponseBuffered uses line buffering and a streaming spinner
func (a *Agent) streamLLMResponseBuffered(config llm.Config, packedContent string) (string, string, error) {
	ctx := context.Background()
	eventChan, errChan := llm.StreamLLMResponse(ctx, config, packedContent)

	var response strings.Builder
	var reasoningBuffer strings.Builder

	termWidth := getTerminalWidth()
	wrapAt := termWidth - (MARGIN * 2)
	if wrapAt < 20 {
		wrapAt = 20
	}

	// Create line buffers for content and reasoning
	contentBuffer := linebuffer.New(wrapAt)
	reasoningLineBuffer := linebuffer.New(wrapAt)

	// Tag parser for shell blocks
	tagParser := NewTagParser(a.logger)

	// Setup streaming spinner
	sp := spinner.GetRandomSpinner()
	// Create wrapper function for color
	colorFunc := func(s string) {
		a.theme.Spinner.Print(s)
	}
	streamSpinner := streamspinner.New(sp, marginStr(), colorFunc)

	// Track if we're in different modes
	inReasoning := false
	isFirstContent := true

	// Start spinner
	streamSpinner.Start()
	defer streamSpinner.Stop()

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				// Channel closed - flush any remaining content
				if line := contentBuffer.Flush(); line != nil {
					a.printBufferedLine(*line, streamSpinner, tagParser, a.theme.DefaultText)
				}
				if line := reasoningLineBuffer.Flush(); line != nil && !a.IgnoreReasoning {
					a.printBufferedLine(*line, streamSpinner, nil, a.theme.Reasoning)
				}

				return response.String(), reasoningBuffer.String(), nil
			}

			// Handle content streaming
			if event.Content != "" {
				if a.logger != nil {
					a.logger.Printf("Received content chunk: %q", event.Content)
				}

				// Always accumulate to response
				response.WriteString(event.Content)

				// Add margin for first content
				if isFirstContent {
					isFirstContent = false
				}

				// Process through line buffer
				lines := contentBuffer.AddContent(event.Content)
				for _, line := range lines {
					a.printBufferedLine(line, streamSpinner, tagParser, a.theme.DefaultText)
				}
			}

			// Handle reasoning streaming
			if event.Reasoning != "" && !a.IgnoreReasoning {
				if !inReasoning {
					inReasoning = true
					// Reasoning gets its own visual treatment
				}

				reasoningBuffer.WriteString(event.Reasoning)

				// Process through line buffer
				lines := reasoningLineBuffer.AddContent(event.Reasoning)
				for _, line := range lines {
					a.printBufferedLine(line, streamSpinner, nil, a.theme.Reasoning)
				}
			}

		case err := <-errChan:
			if err != nil {
				return "", "", fmt.Errorf("LLM request failed: %w\nModel: %s", err, a.Model)
			}
		}
	}
}

// printBufferedLine prints a complete line with appropriate coloring
func (a *Agent) printBufferedLine(line string, spinner *streamspinner.StreamingSpinner, tagParser *TagParser, defaultColor *color.Color) {
	if tagParser != nil {
		// Parse for shell blocks and apply appropriate coloring
		results := tagParser.Parse(line)

		var coloredLine strings.Builder
		for _, result := range results {
			// Apply appropriate color based on context
			if result.BeforeTag != "" {
				if result.HasCloseTag || (!result.HasOpenTag && tagParser.IsInShellBlock()) {
					// Shell block content
					coloredLine.WriteString(a.theme.ShellBlockCode.Sprint(result.BeforeTag))
				} else {
					// Regular content
					coloredLine.WriteString(defaultColor.Sprint(result.BeforeTag))
				}
			}

			if result.HasCloseTag && result.AfterTag != "" {
				// Content after closing tag
				coloredLine.WriteString(defaultColor.Sprint(result.AfterTag))
			}
		}

		// If no special parsing needed, just color the whole line
		if len(results) == 0 {
			if tagParser.IsInShellBlock() {
				coloredLine.WriteString(a.theme.ShellBlockCode.Sprint(line))
			} else {
				coloredLine.WriteString(defaultColor.Sprint(line))
			}
		}

		spinner.PrintLine(coloredLine.String())
	} else {
		// No tag parsing needed (e.g., for reasoning)
		coloredLine := defaultColor.Sprint(line)
		spinner.PrintLine(coloredLine)
	}
}

// EnableBufferedStreaming switches the agent to use line-buffered streaming
func (a *Agent) EnableBufferedStreaming() {
	// This would be a flag we could add to the Agent struct
	// For now, we can test by calling streamLLMResponseBuffered directly
}
