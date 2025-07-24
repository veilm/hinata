package prompt

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type ColorConfig struct {
	HeaderRGB *[3]int // RGB values for header text
	HelpRGB   *[3]int // RGB values for help text
	PromptRGB *[3]int // RGB values for textarea prompt (left border)
	TextRGB   *[3]int // RGB values for input text
}

type textareaModel struct {
	textarea textarea.Model
	aborted  bool
	finished bool
	value    string
	colors   ColorConfig
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
		case "ctrl+d": // , "esc":
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

	headerStyle := lipgloss.NewStyle().Bold(true)
	if m.colors.HeaderRGB != nil {
		headerStyle = headerStyle.Foreground(lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
			(*m.colors.HeaderRGB)[0],
			(*m.colors.HeaderRGB)[1],
			(*m.colors.HeaderRGB)[2])))
	} else {
		headerStyle = headerStyle.Foreground(lipgloss.Color("12"))
	}
	header := headerStyle.Render("Enter your instructions:")

	helpStyle := lipgloss.NewStyle().Faint(true)
	if m.colors.HelpRGB != nil {
		helpStyle = helpStyle.Foreground(lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
			(*m.colors.HelpRGB)[0],
			(*m.colors.HelpRGB)[1],
			(*m.colors.HelpRGB)[2])))
	}
	helpText := helpStyle.Render("• Ctrl+D to submit • Ctrl+C to cancel")

	return strings.Join([]string{
		header,
		m.textarea.View(),
		"",
		helpText,
		"",
	}, "\n")
}

func PromptForInput() (string, error) {
	return PromptForInputWithColors(ColorConfig{})
}

func PromptForInputWithColors(colors ColorConfig) (string, error) {
	ta := textarea.New()
	ta.Placeholder = "Type your instructions here..."
	ta.Focus()
	ta.CharLimit = 0
	ta.ShowLineNumbers = false
	ta.KeyMap.InsertNewline.SetEnabled(true)

	ta.SetWidth(80)
	ta.SetHeight(7)

	// Style the prompt (left border) if color is provided
	if colors.PromptRGB != nil {
		promptColor := lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
			(*colors.PromptRGB)[0],
			(*colors.PromptRGB)[1],
			(*colors.PromptRGB)[2]))
		ta.FocusedStyle.Prompt = lipgloss.NewStyle().Foreground(promptColor)
		ta.BlurredStyle.Prompt = lipgloss.NewStyle().Foreground(promptColor)
	}

	// Style the input text if color is provided
	if colors.TextRGB != nil {
		textColor := lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
			(*colors.TextRGB)[0],
			(*colors.TextRGB)[1],
			(*colors.TextRGB)[2]))
		// Apply text color to the base style which affects the input text
		ta.FocusedStyle.Base = ta.FocusedStyle.Base.Foreground(textColor)
		ta.BlurredStyle.Base = ta.BlurredStyle.Base.Foreground(textColor)
	}

	m := textareaModel{
		textarea: ta,
		colors:   colors,
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
