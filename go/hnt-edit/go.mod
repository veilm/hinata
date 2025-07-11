module github.com/veilm/hinata/hnt-edit

go 1.21

require (
	github.com/charmbracelet/bubbles v0.18.0
	github.com/charmbracelet/bubbletea v0.26.1
	github.com/charmbracelet/lipgloss v0.10.0
	github.com/spf13/cobra v1.8.0
	github.com/veilm/hinata/hnt-apply v0.0.0-00010101000000-000000000000
	github.com/veilm/hinata/hnt-chat v0.0.0-00010101000000-000000000000
	github.com/veilm/hinata/hnt-llm v0.0.0
	github.com/veilm/hinata/llm-pack v0.0.0-00010101000000-000000000000
)

require (
	github.com/atotto/clipboard v0.1.4 // indirect
	github.com/aymanbagabas/go-osc52/v2 v2.0.1 // indirect
	github.com/erikgeiser/coninput v0.0.0-20211004153227-1c3628e74d0f // indirect
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/lucasb-eyer/go-colorful v1.2.0 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/mattn/go-localereader v0.0.1 // indirect
	github.com/mattn/go-runewidth v0.0.15 // indirect
	github.com/muesli/ansi v0.0.0-20230316100256-276c6243b2f6 // indirect
	github.com/muesli/cancelreader v0.2.2 // indirect
	github.com/muesli/reflow v0.3.0 // indirect
	github.com/muesli/termenv v0.15.2 // indirect
	github.com/rivo/uniseg v0.4.7 // indirect
	github.com/spf13/pflag v1.0.5 // indirect
	golang.org/x/sync v0.7.0 // indirect
	golang.org/x/sys v0.21.0 // indirect
	golang.org/x/term v0.21.0 // indirect
	golang.org/x/text v0.16.0 // indirect
)

replace github.com/veilm/hinata/hnt-apply => ../hnt-apply

replace github.com/veilm/hinata/hnt-chat => ../hnt-chat

replace github.com/veilm/hinata/hnt-llm => ../hnt-llm

replace github.com/veilm/hinata/llm-pack => ../llm-pack
