package tui

import (
	"strings"

	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type textareaModel struct {
	textarea textarea.Model
	aborted  bool
	finished bool
	value    string
}

func (m textareaModel) Init() tea.Cmd {
	return textarea.Blink
}

func (m textareaModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c":
			m.aborted = true
			return m, tea.Quit
		case "ctrl+d", "esc":
			m.value = m.textarea.Value()
			m.finished = true
			return m, tea.Quit
		}
	}

	var cmd tea.Cmd
	m.textarea, cmd = m.textarea.Update(msg)
	return m, cmd
}

func (m textareaModel) View() string {
	if m.finished || m.aborted {
		return ""
	}

	header := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("12")).
		Render("Enter your instructions:")

	helpText := lipgloss.NewStyle().
		Faint(true).
		Render("• Ctrl+D or Esc to submit • Ctrl+C to cancel")

	return strings.Join([]string{
		"",
		header,
		m.textarea.View(),
		"",
		helpText,
		"",
	}, "\n")
}

// PromptForInput shows a textarea interface and returns the user input
func PromptForInput() (string, error) {
	ta := textarea.New()
	ta.Placeholder = "Type your instructions here..."
	ta.Focus()
	ta.CharLimit = 0
	ta.ShowLineNumbers = false
	ta.KeyMap.InsertNewline.SetEnabled(true)

	// Set a reasonable size
	ta.SetWidth(80)
	ta.SetHeight(10)

	m := textareaModel{
		textarea: ta,
	}

	p := tea.NewProgram(m)
	finalModel, err := p.Run()
	if err != nil {
		return "", err
	}

	final := finalModel.(textareaModel)
	if final.aborted {
		return "", nil
	}

	return strings.TrimSpace(final.value), nil
}
