module github.com/veilm/hinata/hnt-apply

go 1.21

require (
	github.com/spf13/cobra v1.8.0
	github.com/veilm/hinata/llm-pack v0.0.0-00010101000000-000000000000
)

require (
	github.com/inconshreveable/mousetrap v1.1.0 // indirect
	github.com/spf13/pflag v1.0.5 // indirect
)

replace github.com/veilm/hinata/llm-pack => ../llm-pack
