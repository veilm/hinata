package agent

import (
	"log"
	"strings"
)

// TagParser handles detection of <hnt-shell> and </hnt-shell> tags
// across streaming token boundaries
type TagParser struct {
	partialTag   string
	inShellBlock bool
	logger       *log.Logger
}

// ParseResult contains the results of parsing a chunk of text
type ParseResult struct {
	BeforeTag   string // Text before any tag
	TagFound    string // The tag that was found (if any)
	AfterTag    string // Text after the tag
	HasOpenTag  bool   // True if <hnt-shell> was found
	HasCloseTag bool   // True if </hnt-shell> was found
}

// NewTagParser creates a new tag parser
func NewTagParser(logger *log.Logger) *TagParser {
	return &TagParser{logger: logger}
}

// IsInShellBlock returns true if we're currently inside a shell block
func (p *TagParser) IsInShellBlock() bool {
	return p.inShellBlock
}

// Parse processes a chunk of text, detecting tags and returning the content
func (p *TagParser) Parse(chunk string) []ParseResult {
	if p.logger != nil {
		p.logger.Printf("TagParser.Parse called with chunk: %q (len=%d)", chunk, len(chunk))
		p.logger.Printf("  Current state: inShellBlock=%v, partialTag=%q", p.inShellBlock, p.partialTag)
	}

	// Prepend any partial tag from previous chunk
	text := p.partialTag + chunk
	p.partialTag = ""

	var results []ParseResult

	for len(text) > 0 {
		if p.inShellBlock {
			// Look for closing tag
			result := p.findTag(text, "</hnt-shell>")
			if result.TagFound != "" {
				p.inShellBlock = false
				result.HasCloseTag = true
				// Trim trailing newline from BeforeTag if present
				if len(result.BeforeTag) > 0 && result.BeforeTag[len(result.BeforeTag)-1] == '\n' {
					result.BeforeTag = result.BeforeTag[:len(result.BeforeTag)-1]
				}
				if p.logger != nil {
					p.logger.Printf("  Found closing tag: BeforeTag=%q, AfterTag=%q", result.BeforeTag, result.AfterTag)
				}
				results = append(results, result)
				text = result.AfterTag
			} else {
				// No complete tag found
				if result.AfterTag != "" {
					// Save potential partial tag
					p.partialTag = result.AfterTag
					text = ""
				}
				if result.BeforeTag != "" {
					results = append(results, ParseResult{BeforeTag: result.BeforeTag})
					text = ""
				}
			}
		} else {
			// Look for opening tag
			result := p.findTag(text, "<hnt-shell>")
			if result.TagFound != "" {
				p.inShellBlock = true
				result.HasOpenTag = true
				// Trim leading newline from AfterTag if present
				if len(result.AfterTag) > 0 && result.AfterTag[0] == '\n' {
					result.AfterTag = result.AfterTag[1:]
				}
				if p.logger != nil {
					p.logger.Printf("  Found opening tag: BeforeTag=%q, AfterTag=%q", result.BeforeTag, result.AfterTag)
				}
				results = append(results, result)
				text = result.AfterTag
				// Continue processing to handle the content after the opening tag
			} else {
				// No complete tag found
				if result.AfterTag != "" {
					// Save potential partial tag
					p.partialTag = result.AfterTag
					text = ""
				}
				if result.BeforeTag != "" {
					results = append(results, ParseResult{BeforeTag: result.BeforeTag})
					text = ""
				}
			}
		}
	}

	if p.logger != nil {
		p.logger.Printf("  Parse complete. Returned %d results, final state: inShellBlock=%v, partialTag=%q",
			len(results), p.inShellBlock, p.partialTag)
	}

	return results
}

// findTag looks for a specific tag in the text
func (p *TagParser) findTag(text string, tag string) ParseResult {
	idx := strings.Index(text, tag)
	if idx >= 0 {
		// Found complete tag
		return ParseResult{
			BeforeTag: text[:idx],
			TagFound:  tag,
			AfterTag:  text[idx+len(tag):],
		}
	}

	// Check if text might contain a partial tag at the end
	for i := 1; i < len(tag) && i <= len(text); i++ {
		if strings.HasSuffix(text, tag[:i]) {
			// Found partial tag at end
			return ParseResult{
				BeforeTag: text[:len(text)-i],
				AfterTag:  text[len(text)-i:],
			}
		}
	}

	// No tag or partial tag found
	return ParseResult{BeforeTag: text}
}
