module github.com/veilm/hinata/hnt-web

go 1.23.0

toolchain go1.24.4

require (
	github.com/veilm/hinata/hnt-chat v0.0.0
	github.com/veilm/hinata/hnt-llm v0.0.0
)

require (
	golang.org/x/sys v0.34.0 // indirect
	golang.org/x/term v0.33.0 // indirect
)

replace github.com/veilm/hinata/hnt-chat => ../hnt-chat

replace github.com/veilm/hinata/hnt-llm => ../hnt-llm
