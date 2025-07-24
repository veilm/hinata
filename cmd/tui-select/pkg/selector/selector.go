package selector

import (
	"fmt"
	"strconv"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/mattn/go-runewidth"
)

type Options struct {
	Height int
	Color  int // ANSI color (0-7) for backward compatibility
	Prefix string
	// RGB colors (optional) - if set, these override Color
	BackgroundRGB *[3]int // RGB values for background
	ForegroundRGB *[3]int // RGB values for foreground (text on highlight)
	PrefixRGB     *[3]int // RGB values for prefix
}

type Model struct {
	items        []string
	cursor       int
	offset       int
	windowHeight int
	quitting     bool
	aborted      bool
	choice       string
	prefix       string
	spacePrefix  string
	hlStyle      lipgloss.Style
	prefixStyle  lipgloss.Style
	normalStyle  lipgloss.Style
	faintStyle   lipgloss.Style
}

func New(items []string, opts Options) Model {
	windowHeight := opts.Height
	if windowHeight <= 0 || windowHeight > len(items) {
		windowHeight = len(items)
	}

	// Default prefix
	prefix := opts.Prefix
	if prefix == "" {
		prefix = "▌ "
	}
	spacePrefix := strings.Repeat(" ", runewidth.StringWidth(prefix))

	// Build styles
	var hlStyle, prefixStyle lipgloss.Style

	// Check if RGB colors are provided
	if opts.BackgroundRGB != nil && opts.PrefixRGB != nil {
		// Use RGB colors in hex format
		bgColor := lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
			(*opts.BackgroundRGB)[0],
			(*opts.BackgroundRGB)[1],
			(*opts.BackgroundRGB)[2]))

		var fgColor lipgloss.Color
		if opts.ForegroundRGB != nil {
			fgColor = lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
				(*opts.ForegroundRGB)[0],
				(*opts.ForegroundRGB)[1],
				(*opts.ForegroundRGB)[2]))
		} else {
			fgColor = lipgloss.Color("0") // Default to black
		}

		prefixColor := lipgloss.Color(fmt.Sprintf("#%02X%02X%02X",
			(*opts.PrefixRGB)[0],
			(*opts.PrefixRGB)[1],
			(*opts.PrefixRGB)[2]))

		hlStyle = lipgloss.NewStyle().Background(bgColor).Foreground(fgColor)
		prefixStyle = lipgloss.NewStyle().Foreground(prefixColor)
	} else if opts.Color >= 0 && opts.Color <= 7 {
		// ANSI color codes: 30-37 for foreground, 40-47 for background
		// But lipgloss uses string numbers "0"-"15" for 16 colors
		// 0=black, 1=red, 2=green, 3=yellow, 4=blue, 5=magenta, 6=cyan, 7=white
		bg := lipgloss.Color(strconv.Itoa(opts.Color))
		hlStyle = lipgloss.NewStyle().Background(bg).Foreground(lipgloss.Color("0"))
		prefixStyle = lipgloss.NewStyle().Foreground(bg)
	} else {
		// Reverse video fallback
		hlStyle = lipgloss.NewStyle().Reverse(true)
		prefixStyle = lipgloss.NewStyle()
	}

	return Model{
		items:        items,
		windowHeight: windowHeight,
		prefix:       prefix,
		spacePrefix:  spacePrefix,
		hlStyle:      hlStyle,
		prefixStyle:  prefixStyle,
		normalStyle:  lipgloss.NewStyle(),
		faintStyle:   lipgloss.NewStyle().Faint(true),
	}
}

func (m Model) Init() tea.Cmd {
	return nil
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q", "esc":
			m.quitting = true
			m.aborted = true
			return m, tea.Quit

		case "enter":
			if m.cursor < len(m.items) {
				m.choice = m.items[m.cursor]
				m.quitting = true
				return m, tea.Quit
			}

		// Move cursor down
		case "down", "j", "tab":
			if m.cursor < len(m.items)-1 {
				m.cursor++
				if m.cursor >= m.offset+m.windowHeight {
					m.offset++
				}
			}

		// Move cursor up
		case "up", "k", "shift+tab":
			if m.cursor > 0 {
				m.cursor--
				if m.cursor < m.offset {
					m.offset--
				}
			}

		// Page down
		case "pgdown", "ctrl+f":
			m.cursor += m.windowHeight
			if m.cursor >= len(m.items) {
				m.cursor = len(m.items) - 1
			}
			m.offset = m.cursor - m.windowHeight + 1
			if m.offset < 0 {
				m.offset = 0
			}

		// Page up
		case "pgup", "ctrl+b":
			m.cursor -= m.windowHeight
			if m.cursor < 0 {
				m.cursor = 0
			}
			m.offset = m.cursor

		// Home
		case "home", "g":
			m.cursor = 0
			m.offset = 0

		// End
		case "end", "G":
			m.cursor = len(m.items) - 1
			m.offset = m.cursor - m.windowHeight + 1
			if m.offset < 0 {
				m.offset = 0
			}
		}
	}
	return m, nil
}

func (m Model) View() string {
	if m.quitting {
		return ""
	}

	var s strings.Builder
	s.WriteString("\n")

	// Display items
	for i := m.offset; i < m.offset+m.windowHeight && i < len(m.items); i++ {
		line := m.items[i]
		if i == m.cursor {
			s.WriteString(m.prefixStyle.Render(m.prefix))
			s.WriteString(m.hlStyle.Render(line))
		} else {
			s.WriteString(m.spacePrefix)
			s.WriteString(m.normalStyle.Render(line))
		}
		s.WriteString("\n")
	}

	// Help text
	s.WriteString("\n")
	s.WriteString(m.faintStyle.Render("↑/k  ↓/j  Enter=select  Esc=quit"))

	return s.String()
}

func (m Model) Choice() string {
	return m.choice
}

func (m Model) Aborted() bool {
	return m.aborted
}
