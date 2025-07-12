package chat

import (
	"fmt"
	"strings"
)

type Role string

const (
	RoleUser               Role = "user"
	RoleAssistant          Role = "assistant"
	RoleSystem             Role = "system"
	RoleAssistantReasoning Role = "assistant-reasoning"
)

func (r Role) String() string {
	return string(r)
}

func ParseRole(s string) (Role, error) {
	switch strings.ToLower(s) {
	case "user":
		return RoleUser, nil
	case "assistant":
		return RoleAssistant, nil
	case "system":
		return RoleSystem, nil
	case "assistant-reasoning":
		return RoleAssistantReasoning, nil
	default:
		return "", fmt.Errorf("unknown role: %s", s)
	}
}

type ChatMessage struct {
	Path      string
	Timestamp int64
	Role      Role
}

func (m ChatMessage) Less(other ChatMessage) bool {
	return m.Timestamp < other.Timestamp
}
