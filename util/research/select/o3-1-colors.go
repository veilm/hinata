// cmd/hnt-select-poc/main.go
package main

import (
	"fmt"
	"os"
	"strconv"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/pflag"
)

/* ---------------- flag parsing ---------------- */

var (
	winH   int
	clrIdx int
	prefix string
)

func init() {
	pflag.IntVarP(&winH, "height", "H", 10, "window height")
	pflag.IntVarP(&clrIdx, "color", "c", -1, "highlight colour (0-7); -1 = reverse video")
	pflag.StringVarP(&prefix, "prefix", "p", "▌ ", "prefix before selected line")
	pflag.Parse()
}

/* ---------------- model ---------------- */

type model struct {
	items        []string
	cursor       int
	offset       int
	windowHeight int
	choice       string
	quitting     bool
}

/* ---------- styles built from CLI ---------- */

var (
	prefixWidth  = lipgloss.Width(prefix)
	spacePrefix  = lipgloss.NewStyle().Width(prefixWidth).Render("") // spaces fill
	hlStyle      lipgloss.Style
	unSelStyle   = lipgloss.NewStyle()
	helpStyle    = lipgloss.NewStyle().Faint(true)
	paddingSpace = " "
)

func buildStyles() {
	if clrIdx >= 0 && clrIdx <= 7 { // coloured highlight
		bg := lipgloss.Color(strconv.Itoa(clrIdx))
		hlStyle = lipgloss.NewStyle().Background(bg).Foreground(lipgloss.Color("0"))
	} else { // reverse video fallback
		hlStyle = lipgloss.NewStyle().Reverse(true)
	}
}

/* ---------- Bubble Tea plumbing ---------- */

func newModel(items []string, h int) model {
	if h <= 0 || h > len(items) {
		h = len(items)
	}
	return model{items: items, windowHeight: h}
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q", "esc":
			m.quitting = true
			return m, tea.Quit
		case "enter":
			m.choice, m.quitting = m.items[m.cursor], true
			return m, tea.Quit
		case "down", "j", "tab":
			if m.cursor < len(m.items)-1 {
				m.cursor++
				if m.cursor >= m.offset+m.windowHeight {
					m.offset++
				}
			}
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

func (m model) View() string {
	if m.quitting {
		if m.choice == "" {
			return helpStyle.Render("\n(aborted)\n")
		}
		return helpStyle.Render("\nchoice: ") + m.choice + "\n"
	}

	var out string
	for i := m.offset; i < m.offset+m.windowHeight && i < len(m.items); i++ {
		line := paddingSpace + m.items[i] // small left pad after prefix

		if i == m.cursor { // selected line
			out += hlStyle.Render(prefix+line) + "\n"
		} else {
			out += spacePrefix + unSelStyle.Render(line) + "\n"
		}
	}

	out += helpStyle.Render("\n↑/k  ↓/j  Enter=select  Esc=quit")
	return "\n" + out
}

/* ---------------- main ---------------- */

func main() {
	buildStyles()

	menu := []string{
		"Retry LLM request.",
		"Skip this execution. Provide new instructions instead.",
		"Exit the Hinata session.",
		"Praise the sun.",
		"Order coffee.",
		"Write more Go.",
	}

	m := newModel(menu, winH)
	if p, err := tea.NewProgram(m).Run(); err == nil {
		if res := p.(model).choice; res != "" {
			fmt.Println(res)
			os.Exit(0)
		}
		os.Exit(1)
	} else {
		fmt.Println("error:", err)
		os.Exit(1)
	}
}
