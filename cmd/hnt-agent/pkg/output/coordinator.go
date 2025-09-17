package output

import (
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/fatih/color"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/cursor"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/spinner"
)

// CommandType represents the type of output command
type CommandType int

const (
	CmdPrintLine CommandType = iota
	CmdShowSpinner
	CmdUpdateSpinner
	CmdHideSpinner
	CmdClearLine
	CmdFlush
)

// Command represents an output command to be processed
type Command struct {
	Type      CommandType
	Content   string
	Color     *color.Color
	Margin    string
	Callback  chan bool // For synchronous operations
}

// Coordinator manages all terminal output to prevent race conditions
type Coordinator struct {
	commands chan Command
	done     chan bool
	mu       sync.Mutex
	started  bool

	// Spinner state
	spinnerActive  bool
	spinnerShown   bool
	animator       *spinner.Animator
	margin         string
	colorFunc      func(string)
	lastSpinnerUpdate time.Time
}

// New creates a new output coordinator
func New(bufferSize int) *Coordinator {
	if bufferSize <= 0 {
		bufferSize = 100
	}
	return &Coordinator{
		commands: make(chan Command, bufferSize),
		done:     make(chan bool),
	}
}

// Start begins the output coordinator goroutine
func (c *Coordinator) Start() {
	c.mu.Lock()
	if c.started {
		c.mu.Unlock()
		return
	}
	c.started = true
	c.mu.Unlock()

	go c.run()
}

// Stop stops the coordinator and waits for it to finish
func (c *Coordinator) Stop() {
	c.mu.Lock()
	if !c.started {
		c.mu.Unlock()
		return
	}
	c.mu.Unlock()

	// Send stop signal
	close(c.commands)

	// Wait for completion with timeout
	select {
	case <-c.done:
	case <-time.After(500 * time.Millisecond):
		// Timeout - coordinator might be stuck
	}
}

// PrintLine prints a content line, handling spinner state appropriately
func (c *Coordinator) PrintLine(margin string, content string, color *color.Color) {
	cmd := Command{
		Type:    CmdPrintLine,
		Content: content,
		Color:   color,
		Margin:  margin,
	}

	select {
	case c.commands <- cmd:
	case <-time.After(100 * time.Millisecond):
		// Channel full - print directly as fallback
		c.directPrint(margin, content, color)
	}
}

// ShowSpinner starts displaying a spinner
func (c *Coordinator) ShowSpinner(sp spinner.Spinner, message string, margin string, colorFunc func(string)) {
	cmd := Command{
		Type:      CmdShowSpinner,
		Content:   message,
		Margin:    margin,
		Callback:  make(chan bool, 1),
	}

	// Store spinner config
	c.mu.Lock()
	c.animator = spinner.NewAnimator(sp, message)
	c.margin = margin
	c.colorFunc = colorFunc
	c.mu.Unlock()

	select {
	case c.commands <- cmd:
		// Wait for confirmation
		<-cmd.Callback
	case <-time.After(100 * time.Millisecond):
	}
}

// UpdateSpinner updates the spinner animation
func (c *Coordinator) UpdateSpinner() {
	select {
	case c.commands <- Command{Type: CmdUpdateSpinner}:
	default:
		// Skip update if channel is full
	}
}

// HideSpinner stops displaying the spinner
func (c *Coordinator) HideSpinner() {
	cmd := Command{
		Type:     CmdHideSpinner,
		Callback: make(chan bool, 1),
	}

	select {
	case c.commands <- cmd:
		// Wait for confirmation
		<-cmd.Callback
	case <-time.After(100 * time.Millisecond):
	}
}

// Flush ensures all pending output has been written
func (c *Coordinator) Flush() {
	cmd := Command{
		Type:     CmdFlush,
		Callback: make(chan bool, 1),
	}

	select {
	case c.commands <- cmd:
		// Wait for confirmation
		<-cmd.Callback
	case <-time.After(100 * time.Millisecond):
	}
}

// run is the main goroutine that processes all output commands
func (c *Coordinator) run() {
	defer close(c.done)

	// Spinner update ticker
	ticker := time.NewTicker(150 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case cmd, ok := <-c.commands:
			if !ok {
				// Channel closed - clean up and exit
				if c.spinnerShown {
					c.clearSpinner()
				}
				cursor.Show()
				return
			}

			c.processCommand(cmd)

		case <-ticker.C:
			// Auto-update spinner if active
			if c.spinnerActive && c.spinnerShown {
				// Only update if enough time has passed
				if time.Since(c.lastSpinnerUpdate) >= 150*time.Millisecond {
					c.updateSpinnerFrame()
					c.lastSpinnerUpdate = time.Now()
				}
			}
		}
	}
}

// processCommand handles a single output command
func (c *Coordinator) processCommand(cmd Command) {
	switch cmd.Type {
	case CmdPrintLine:
		c.handlePrintLine(cmd)

	case CmdShowSpinner:
		c.handleShowSpinner(cmd)

	case CmdUpdateSpinner:
		c.handleUpdateSpinner()

	case CmdHideSpinner:
		c.handleHideSpinner(cmd)

	case CmdClearLine:
		fmt.Print("\r\033[K")

	case CmdFlush:
		// Just acknowledge
		if cmd.Callback != nil {
			cmd.Callback <- true
		}
	}
}

// handlePrintLine handles printing a content line
func (c *Coordinator) handlePrintLine(cmd Command) {
	// If spinner is shown, clear it first
	if c.spinnerShown {
		c.clearSpinner()
		// Move up to remove the blank line that was above spinner
		if c.spinnerActive {
			fmt.Print("\033[1A\033[K")
		}
	}

	// Print the content line
	fmt.Print(cmd.Margin)
	if cmd.Color != nil {
		cmd.Color.Print(cmd.Content)
	} else {
		fmt.Print(cmd.Content)
	}
	fmt.Println()

	// Redraw spinner on new line if still active
	if c.spinnerActive {
		fmt.Println() // Blank line before spinner
		c.drawSpinner()
		c.spinnerShown = true
	}
}

// handleShowSpinner handles starting the spinner
func (c *Coordinator) handleShowSpinner(cmd Command) {
	c.spinnerActive = true

	if c.animator != nil {
		c.animator.Start()
	}

	cursor.Hide()

	// Initial display with blank line before
	if !c.spinnerShown {
		fmt.Println()
		c.drawSpinner()
		c.spinnerShown = true
	}

	if cmd.Callback != nil {
		cmd.Callback <- true
	}
}

// handleUpdateSpinner handles updating spinner animation
func (c *Coordinator) handleUpdateSpinner() {
	if c.spinnerActive && c.spinnerShown {
		c.updateSpinnerFrame()
	}
}

// handleHideSpinner handles stopping the spinner
func (c *Coordinator) handleHideSpinner(cmd Command) {
	c.spinnerActive = false

	if c.spinnerShown {
		c.clearSpinner()
		// Remove the blank line that was above the spinner
		fmt.Print("\033[1A\033[K")
		c.spinnerShown = false
	}

	cursor.Show()

	if cmd.Callback != nil {
		cmd.Callback <- true
	}
}

// drawSpinner draws the current spinner frame
func (c *Coordinator) drawSpinner() {
	if c.animator == nil {
		return
	}

	statusLine := c.animator.GetCurrentStatus()

	fmt.Print(c.margin)
	if c.colorFunc != nil {
		c.colorFunc(statusLine)
	} else {
		fmt.Print(statusLine)
	}
}

// updateSpinnerFrame advances and redraws the spinner
func (c *Coordinator) updateSpinnerFrame() {
	if c.animator == nil {
		return
	}

	// Clear current line
	fmt.Print("\r\033[K")

	// Get next frame
	statusLine := c.animator.NextFrame()

	// Draw new frame
	fmt.Print(c.margin)
	if c.colorFunc != nil {
		c.colorFunc(statusLine)
	} else {
		fmt.Print(statusLine)
	}
}

// clearSpinner clears the spinner line
func (c *Coordinator) clearSpinner() {
	fmt.Print("\r\033[K")
}

// directPrint is a fallback for when the channel is full
func (c *Coordinator) directPrint(margin string, content string, color *color.Color) {
	var output strings.Builder
	output.WriteString(margin)
	output.WriteString(content)
	output.WriteString("\n")

	// Single atomic write
	fmt.Print(output.String())
}