// cmd/hnt-agent-poc/main.go
package main

import (
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/textarea"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/spf13/pflag"
)

/* ---------- tiny helper types ---------- */

type phase int

const (
	editing phase = iota
	thinking
	done
)

type llmReplyMsg string // delivered after the fake “LLM” finishes

/* ---------- Bubble Tea model ---------- */

type model struct {
	ta      textarea.Model
	sp      spinner.Model
	phase   phase
	reply   string
	timeout time.Duration
}

func newModel(sp spinner.Spinner, timeout time.Duration) model {
	ta := textarea.New()
	ta.Placeholder = "Write your instruction here…"
	ta.Focus()
	ta.CharLimit = 0
	ta.ShowLineNumbers = false
	ta.KeyMap.InsertNewline.SetEnabled(true) // allow ⏎ inside textarea

	spn := spinner.New(spinner.WithSpinner(sp), spinner.WithStyle(lipgloss.NewStyle().Foreground(lipgloss.Color("5"))))

	return model{ta: ta, sp: spn, phase: editing, timeout: timeout}
}

/* ---------- Init ---------- */

func (m model) Init() tea.Cmd {
	return textarea.Blink
}

/* ---------- Update ---------- */

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch m.phase {

	case editing:
		switch msg := msg.(type) {
		case tea.KeyMsg:
			switch msg.String() {
			case "ctrl+s", "esc": // “Send”
				if text := m.ta.Value(); text != "" {
					m.phase = thinking
					return m, tea.Batch(
						m.sp.Tick,
						waitCmd(text, m.timeout),
					)
				}
			case "ctrl+c":
				return m, tea.Quit
			}
		}
		ta, cmd := m.ta.Update(msg)
		m.ta = ta
		return m, cmd

	case thinking:
		// Feed everything to the spinner until we get a reply
		switch msg := msg.(type) {
		case llmReplyMsg:
			m.reply = string(msg)
			m.phase = done
			return m, nil
		}
		sp, cmd := m.sp.Update(msg)
		m.sp = sp
		return m, cmd

	case done:
		if k, ok := msg.(tea.KeyMsg); ok && k.String() == "ctrl+c" {
			return m, tea.Quit
		}
	}
	return m, nil
}

/* ---------- View ---------- */

func (m model) View() string {
	switch m.phase {
	case editing:
		return "\n" + m.ta.View() + "\n\n" + lipgloss.NewStyle().Faint(true).Render("• Press Ctrl+S or Esc to send • Ctrl+C to quit")
	case thinking:
		return "\n" + m.sp.View() + "  thinking…"
	case done:
		return lipgloss.NewStyle().Bold(true).Render("\nAssistant:") + "\n\n" + indent(m.reply, 2) + "\n\n" +
			lipgloss.NewStyle().Faint(true).Render("Ctrl+C to quit")
	default:
		return ""
	}
}

/* ---------- Cmd helpers ---------- */

// waitCmd sleeps for `timeout` then returns an llmReplyMsg.
func waitCmd(prompt string, timeout time.Duration) tea.Cmd {
	return func() tea.Msg {
		time.Sleep(timeout)
		// Here you’d call your real LLM and return its answer.
		fake := fmt.Sprintf("You wrote: %q\n(pretend this came from the LLM)", prompt)
		return llmReplyMsg(fake)
	}
}

/* ---------- util ---------- */

func indent(s string, n int) string {
	pad := strings.Repeat(" ", n)
	return pad + strings.ReplaceAll(s, "\n", "\n"+pad)
}

/* ---------- main ---------- */

func main() {
	var useSpinner int
	var thinkMs int
	pflag.IntVarP(&useSpinner, "spinner", "s", 0, "0=line, 1=dot")
	pflag.IntVar(&thinkMs, "latency", 2000, "fake LLM latency in ms")
	pflag.Parse()

	// pick one of two simple spinners
	spinners := []spinner.Spinner{spinner.Line, spinner.Dot}
	if useSpinner < 0 || useSpinner >= len(spinners) {
		fmt.Fprintf(os.Stderr, "spinner index out of range\n")
		os.Exit(1)
	}

	m := newModel(spinners[useSpinner], time.Duration(thinkMs)*time.Millisecond)
	if _, err := tea.NewProgram(m).Run(); err != nil {
		fmt.Println("error running program:", err)
		os.Exit(1)
	}
}
