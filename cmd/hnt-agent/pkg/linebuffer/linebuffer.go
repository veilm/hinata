package linebuffer

import (
	"strings"
	"unicode"
)

// Line represents a complete line ready for output
type Line struct {
	Content string
	Color   func(string) // Optional color function to apply
}

// LineBuffer accumulates streaming content and emits complete lines
type LineBuffer struct {
	buffer      strings.Builder
	wrapAt      int
	currentCol  int
	pendingWord strings.Builder
}

// New creates a new LineBuffer with the specified wrap width
func New(wrapAt int) *LineBuffer {
	if wrapAt < 20 {
		wrapAt = 20 // Minimum sane width
	}
	return &LineBuffer{
		wrapAt: wrapAt,
	}
}

// AddContent adds streaming content and returns any complete lines
func (lb *LineBuffer) AddContent(content string) []string {
	var lines []string

	for _, ch := range content {
		if ch == '\n' {
			// Explicit newline - flush everything
			if lb.pendingWord.Len() > 0 {
				lb.buffer.WriteString(lb.pendingWord.String())
				lb.pendingWord.Reset()
			}

			lines = append(lines, lb.buffer.String())
			lb.buffer.Reset()
			lb.currentCol = 0
		} else if unicode.IsSpace(ch) {
			// Space character - flush pending word and check wrap
			if lb.pendingWord.Len() > 0 {
				wordLen := lb.pendingWord.Len()

				// Check if word would exceed wrap limit
				if lb.currentCol > 0 && lb.currentCol+wordLen > lb.wrapAt {
					// Emit current line and start new one
					lines = append(lines, lb.buffer.String())
					lb.buffer.Reset()
					lb.currentCol = 0
				}

				// Add word to buffer
				lb.buffer.WriteString(lb.pendingWord.String())
				lb.currentCol += wordLen
				lb.pendingWord.Reset()
			}

			// Handle the space itself
			if ch == ' ' && lb.currentCol < lb.wrapAt {
				lb.buffer.WriteRune(ch)
				lb.currentCol++
			}

			// Check if we've reached wrap point after adding space
			if lb.currentCol >= lb.wrapAt {
				lines = append(lines, lb.buffer.String())
				lb.buffer.Reset()
				lb.currentCol = 0
			}
		} else {
			// Regular character - accumulate in pending word
			lb.pendingWord.WriteRune(ch)
		}
	}

	// Check if pending word + buffer exceeds wrap limit
	if lb.pendingWord.Len() > 0 {
		wordLen := lb.pendingWord.Len()
		if lb.currentCol > 0 && lb.currentCol+wordLen > lb.wrapAt {
			// Emit current buffer as a line
			if lb.buffer.Len() > 0 {
				lines = append(lines, lb.buffer.String())
				lb.buffer.Reset()
				lb.currentCol = 0
			}
		}
	}

	return lines
}

// Flush returns any remaining buffered content as a line
func (lb *LineBuffer) Flush() *string {
	// Flush pending word to buffer
	if lb.pendingWord.Len() > 0 {
		lb.buffer.WriteString(lb.pendingWord.String())
		lb.pendingWord.Reset()
	}

	// Return buffer contents if any
	if lb.buffer.Len() > 0 {
		line := lb.buffer.String()
		lb.buffer.Reset()
		lb.currentCol = 0
		return &line
	}

	return nil
}

// Reset clears all buffers
func (lb *LineBuffer) Reset() {
	lb.buffer.Reset()
	lb.pendingWord.Reset()
	lb.currentCol = 0
}

// HasPending returns true if there's any buffered content
func (lb *LineBuffer) HasPending() bool {
	return lb.buffer.Len() > 0 || lb.pendingWord.Len() > 0
}
