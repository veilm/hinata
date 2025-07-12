package llm

import (
	"fmt"
	"log"
	"strings"

	"github.com/veilm/hinata/hnt-llm/pkg/escaping"
)

func BuildMessages(content string, systemPrompt string) ([]Message, error) {
	var messages []Message

	if systemPrompt != "" {
		messages = append(messages, Message{
			Role:    "system",
			Content: systemPrompt,
		})
	}

	currentPos := 0
	var nonTagContent strings.Builder

	for {
		tagStartRel := strings.Index(content[currentPos:], "<hnt-")
		if tagStartRel == -1 {
			break
		}

		tagStartAbs := currentPos + tagStartRel
		nonTagContent.WriteString(content[currentPos:tagStartAbs])

		remainingFromTag := content[tagStartAbs:]
		tagEndRel := strings.IndexByte(remainingFromTag, '>')
		if tagEndRel == -1 {
			return nil, fmt.Errorf("malformed hnt chat: unclosed tag starting at position %d", tagStartAbs)
		}

		openTag := remainingFromTag[:tagEndRel+1]
		tagName := openTag[1 : len(openTag)-1]

		contentStartAbs := tagStartAbs + tagEndRel + 1
		closingTag := fmt.Sprintf("</%s>", tagName)

		closingTagStartRel := strings.Index(content[contentStartAbs:], closingTag)
		if closingTagStartRel == -1 {
			return nil, fmt.Errorf("malformed hnt chat: missing closing tag for %s", openTag)
		}

		closingTagStartAbs := contentStartAbs + closingTagStartRel
		tagContent := content[contentStartAbs:closingTagStartAbs]

		var role string
		switch tagName {
		case "hnt-system":
			hasSystem := false
			for _, m := range messages {
				if m.Role == "system" {
					hasSystem = true
					break
				}
			}
			if hasSystem {
				log.Println("WARNING: <hnt-system> tag found in stdin, but a system prompt was already provided via --system argument. The stdin system prompt will be ignored.")
				currentPos = closingTagStartAbs + len(closingTag)
				continue
			}
			role = "system"
		case "hnt-user":
			role = "user"
		case "hnt-assistant":
			role = "assistant"
		default:
			log.Printf("WARNING: Unknown hnt tag '%s' found. It will be ignored.", tagName)
			currentPos = closingTagStartAbs + len(closingTag)
			continue
		}

		messages = append(messages, Message{
			Role:    role,
			Content: escaping.Unescape(tagContent),
		})

		currentPos = closingTagStartAbs + len(closingTag)
	}

	nonTagContent.WriteString(content[currentPos:])

	trimmedUserContent := strings.TrimSpace(nonTagContent.String())
	if trimmedUserContent != "" {
		messages = append(messages, Message{
			Role:    "user",
			Content: escaping.Unescape(trimmedUserContent),
		})
	}

	return messages, nil
}
