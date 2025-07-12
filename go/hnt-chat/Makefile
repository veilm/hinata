.PHONY: build test clean install

build:
	go build -o bin/hnt-chat ./cmd/hnt-chat

test:
	go test ./...

clean:
	rm -rf bin/

install: build
	sudo cp bin/hnt-chat /usr/local/bin/

run-example:
	./bin/hnt-chat new