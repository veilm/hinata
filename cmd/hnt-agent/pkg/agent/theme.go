package agent

import "github.com/fatih/color"

// Theme defines the color scheme for the agent UI
type Theme struct {
	Name            string
	Stdout          *color.Color
	Stderr          *color.Color
	ExitCode        *color.Color
	Reasoning       *color.Color
	UserMargin      *color.Color
	HinataLine      *color.Color
	QuerentLine     *color.Color
	TurnNumber      *color.Color
	ShellBlock      *color.Color
	ErrorHighlight  *color.Color
}

// Themes
var (
	// SnowTheme uses cold, winter-inspired true colors
	SnowTheme = Theme{
		Name:            "snow",
		Stdout:          color.RGB(100, 200, 255), // Ice blue
		Stderr:          color.RGB(255, 150, 150), // Soft coral red
		ExitCode:        color.RGB(255, 100, 100), // Warmer red
		Reasoning:       color.RGB(200, 180, 255), // Lavender
		UserMargin:      color.RGB(180, 140, 255), // Purple frost
		HinataLine:      color.RGB(120, 180, 255), // Sky blue
		QuerentLine:     color.RGB(220, 160, 255), // Light purple
		TurnNumber:      color.RGB(160, 255, 200), // Mint green
		ShellBlock:      color.RGB(100, 160, 255), // Deeper ice blue
		ErrorHighlight:  color.RGB(255, 120, 120), // Error red
	}

	// AnsiTheme uses standard ANSI colors (terminal-configurable)
	AnsiTheme = Theme{
		Name:            "ansi",
		Stdout:          color.New(color.FgCyan),
		Stderr:          color.New(color.FgRed),
		ExitCode:        color.New(color.FgRed),
		Reasoning:       color.New(color.FgYellow),
		UserMargin:      color.New(color.FgMagenta),
		HinataLine:      color.New(color.FgBlue),
		QuerentLine:     color.New(color.FgMagenta),
		TurnNumber:      color.New(color.FgGreen),
		ShellBlock:      color.New(color.FgBlue),
		ErrorHighlight:  color.New(color.FgRed),
	}
)

// GetTheme returns the theme based on name
func GetTheme(name string) Theme {
	switch name {
	case "ansi":
		return AnsiTheme
	case "snow":
		return SnowTheme
	default:
		return SnowTheme
	}
}