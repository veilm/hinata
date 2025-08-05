package cursor

import (
	"fmt"
	"os"
	"os/signal"
	"sync"
	"syscall"
)

var (
	cursorHidden bool
	cursorMutex  sync.Mutex
	once         sync.Once
)

func init() {
	// Set up signal handling to ensure cursor is shown on exit
	once.Do(func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

		go func() {
			<-sigChan
			// Restore cursor before exiting
			Show()
			os.Exit(1)
		}()
	})
}

// Hide hides the terminal cursor
func Hide() {
	cursorMutex.Lock()
	defer cursorMutex.Unlock()
	if !cursorHidden {
		fmt.Print("\033[?25l")
		cursorHidden = true
	}
}

// Show shows the terminal cursor
func Show() {
	cursorMutex.Lock()
	defer cursorMutex.Unlock()
	if cursorHidden {
		fmt.Print("\033[?25h")
		cursorHidden = false
	}
}
