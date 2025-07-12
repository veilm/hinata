module github.com/veilm/hinata/hnt-chat

go 1.21

require (
	github.com/spf13/cobra v1.8.0
	github.com/veilm/hinata/hnt-llm v0.0.0
)

require (
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/spf13/pflag v1.0.5 // indirect
	golang.org/x/sys v0.15.0 // indirect
	golang.org/x/term v0.15.0 // indirect
)

replace github.com/veilm/hinata/hnt-llm => ../hnt-llm
