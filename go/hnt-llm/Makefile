.PHONY: build test clean install

build:
	go build -o bin/hnt-llm ./cmd/hnt-llm

test:
	go test ./...

clean:
	rm -rf bin/

install: build
	sudo cp bin/hnt-llm /usr/local/bin/

run-example:
	echo "Hello, Claude!" | go run ./cmd/hnt-llm