// cmd/hnt-select-poc/main.go
package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/mattn/go-runewidth"
	"github.com/spf13/pflag"
)

var (
	winH   int
	clrIdx int
	prefix string
)

func init() {
	pflag.IntVarP(&winH, "height", "H", 10, "window height")
	pflag.IntVarP(&clrIdx, "color", "c", -1, "highlight colour (0-7); -1 = reverse video")
	pflag.StringVarP(&prefix, "prefix", "p", "▌ ", "prefix string for selected item")
}

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
	spacePrefix string
	hlStyle     lipgloss.Style
	prefixStyle lipgloss.Style
	normal      = lipgloss.NewStyle()
	faint       = lipgloss.NewStyle().Faint(true)
)

func buildStyles() {
	if clrIdx >= 0 && clrIdx <= 7 { // coloured highlight
		bg := lipgloss.Color(strconv.Itoa(clrIdx))
		hlStyle = lipgloss.NewStyle().Background(bg).Foreground(lipgloss.Color("0"))
		prefixStyle = lipgloss.NewStyle().Foreground(bg)
	} else { // reverse video fallback
		hlStyle = lipgloss.NewStyle().Reverse(true)
		prefixStyle = lipgloss.NewStyle()
	}
}

func (m model) View() string {
	if m.quitting {
		if m.choice != "" {
			return "\n" + faint.Render("choice: ") + m.choice + "\n"
		}
		return "\n" + faint.Render("(aborted)") + "\n"
	}

	var s string
	for i := m.offset; i < m.offset+m.windowHeight && i < len(m.items); i++ {
		line := m.items[i]
		if i == m.cursor {
			s += prefixStyle.Render(prefix) + hlStyle.Render(line) + "\n"
		} else {
			s += spacePrefix + normal.Render(line) + "\n"
		}
	}
	s += faint.Render("\n↑/k  ↓/j  Enter=select  Esc=quit")
	return "\n" + s
}

// ---- main -------------------------------------------------------------------

func main() {
	pflag.Parse()
	spacePrefix = strings.Repeat(" ", runewidth.StringWidth(prefix))
	buildStyles()

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
