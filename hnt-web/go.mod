module github.com/veilm/hinata/hnt-web

go 1.21

require (
	github.com/veilm/hinata/hnt-chat v0.0.0
	github.com/veilm/hinata/hnt-llm v0.0.0
)

replace github.com/veilm/hinata/hnt-chat => ../hnt-chat
replace github.com/veilm/hinata/hnt-llm => ../hnt-llm