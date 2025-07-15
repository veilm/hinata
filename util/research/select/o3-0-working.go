// cmd/hnt-select-poc/main.go
package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/pflag"
)

type model struct {
	items        []string // menu lines
	cursor       int      // absolute index of highlighted row
	offset       int      // topmost visible row
	windowHeight int      // rows to display
	quitting     bool
	choice       string
}

// ---- init -------------------------------------------------------------------

func newModel(items []string, winH int) model {
	if winH <= 0 || winH > len(items) {
		winH = len(items)
	}
	return model{items: items, windowHeight: winH}
}

func (m model) Init() tea.Cmd { return nil }

// ---- update -----------------------------------------------------------------

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	case tea.KeyMsg:
		switch msg.String() {

		case "ctrl+c", "q", "esc":
			m.quitting = true
			return m, tea.Quit

		case "enter":
			m.choice = m.items[m.cursor]
			m.quitting = true
			return m, tea.Quit

		// move cursor ↓
		case "down", "j", "tab":
			if m.cursor < len(m.items)-1 {
				m.cursor++
				if m.cursor >= m.offset+m.windowHeight {
					m.offset++
				}
			}

		// move cursor ↑
		case "up", "k", "shift+tab":
			if m.cursor > 0 {
				m.cursor--
				if m.cursor < m.offset {
					m.offset--
				}
			}
		}
	}
	return m, nil
}

// ---- view -------------------------------------------------------------------

var (
	hl      = lipgloss.NewStyle().Reverse(true)
	normal  = lipgloss.NewStyle()
	faint   = lipgloss.NewStyle().Faint(true)
	padding = "  "
)

func (m model) View() string {
	if m.quitting {
		if m.choice != "" {
			return "\n" + faint.Render("choice: ") + m.choice + "\n"
		}
		return "\n" + faint.Render("(aborted)") + "\n"
	}

	var s string
	for i := m.offset; i < m.offset+m.windowHeight && i < len(m.items); i++ {
		line := padding + m.items[i]
		if i == m.cursor {
			s += hl.Render(line) + "\n"
		} else {
			s += normal.Render(line) + "\n"
		}
	}
	s += faint.Render("\n↑/k  ↓/j  Enter=select  Esc=quit")
	return "\n" + s
}

// ---- main -------------------------------------------------------------------

func main() {
	var winH int
	pflag.IntVarP(&winH, "height", "H", 10, "window height")
	pflag.Parse()

	options := []string{
		"Retry LLM request.",
		"Skip this execution. Provide new instructions instead.",
		"Exit the Hinata session.",
		"Take a nap.",
		"Order coffee.",
		"Praise the sun.",
		"Write more Go.",
	}

	m := newModel(options, winH)
	if p, err := tea.NewProgram(m).Run(); err == nil {
		final := p.(model)
		if final.choice != "" {
			fmt.Println(final.choice)
			os.Exit(0)
		}
		os.Exit(1) // aborted
	} else {
		fmt.Println("error:", err)
		os.Exit(1)
	}
}
