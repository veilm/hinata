package streamspinner

import (
	"fmt"
	"sync"
	"time"

	"github.com/veilm/hinata/cmd/hnt-agent/pkg/cursor"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/spinner"
)

// StreamingSpinner manages a spinner that appears during LLM streaming
type StreamingSpinner struct {
	spinner   spinner.Spinner
	margin    string
	colorFunc func(string)
	message   string // Loading message to display

	// State management
	mu         sync.Mutex
	active     bool
	stopCh     chan bool
	contentCh  chan string // Channel to receive new content lines
	startTime  time.Time
	frameIndex int
	hasContent bool // Track if any content has been printed yet
}

// New creates a new streaming spinner
func New(sp spinner.Spinner, margin string, colorFunc func(string)) *StreamingSpinner {
	return &StreamingSpinner{
		spinner:   sp,
		margin:    margin,
		colorFunc: colorFunc,
		message:   spinner.GetRandomLoadingMessage(),
		contentCh: make(chan string, 10),
		stopCh:    make(chan bool, 1),
	}
}

// Start begins the spinner animation
func (s *StreamingSpinner) Start() {
	s.mu.Lock()
	if s.active {
		s.mu.Unlock()
		return
	}
	s.active = true
	s.startTime = time.Now()
	s.frameIndex = 0
	s.mu.Unlock()

	cursor.Hide()

	// Initial spinner display with blank line before
	fmt.Println()
	s.drawSpinner()

	go s.run()
}

// Stop stops the spinner and clears its line
func (s *StreamingSpinner) Stop() {
	s.mu.Lock()
	if !s.active {
		s.mu.Unlock()
		return
	}
	s.active = false
	hasContent := s.hasContent
	s.mu.Unlock()

	// Signal stop
	select {
	case s.stopCh <- true:
	default:
	}

	// Clear spinner line and the blank line above it
	s.clearLine()
	if hasContent {
		fmt.Print("\033[1A\033[K") // Move up one line and clear the blank line
	}
	cursor.Show()
}

// PrintLine prints a new content line, temporarily clearing the spinner
func (s *StreamingSpinner) PrintLine(line string) {
	s.mu.Lock()
	if !s.active {
		s.mu.Unlock()
		// If spinner not active, just print the line
		fmt.Printf("%s%s\n", s.margin, line)
		return
	}
	s.mu.Unlock()

	// Send line to content channel
	select {
	case s.contentCh <- line:
	default:
		// If channel is full, print directly (shouldn't happen with buffer of 10)
		s.clearLine()
		fmt.Printf("%s%s\n", s.margin, line)
		s.drawSpinner()
	}
}

func (s *StreamingSpinner) run() {
	ticker := time.NewTicker(s.spinner.Speed)
	defer ticker.Stop()

	for {
		select {
		case <-s.stopCh:
			return

		case line := <-s.contentCh:
			// Clear spinner line and the blank line above it
			s.clearLine()
			fmt.Print("\033[1A\033[K") // Move up one line and clear it

			// Print content line
			fmt.Printf("%s%s\n", s.margin, line)

			// Mark that we have content
			s.mu.Lock()
			s.hasContent = true

			// Redraw spinner on new line with blank line before (if still active)
			if s.active {
				fmt.Println() // Blank line before spinner
				s.drawSpinner()
			}
			s.mu.Unlock()

		case <-ticker.C:
			// Update spinner animation
			s.mu.Lock()
			if s.active {
				s.frameIndex = (s.frameIndex + 1) % len(s.spinner.Frames)
				s.clearLine()
				s.drawSpinner()
			}
			s.mu.Unlock()
		}
	}
}

func (s *StreamingSpinner) drawSpinner() {
	elapsedSeconds := int64(time.Since(s.startTime).Seconds())

	// Get current frame
	frame := s.spinner.Frames[s.frameIndex]

	// Generate status line using shared function
	statusLine := spinner.FormatStatusLine(s.message, elapsedSeconds, frame)

	// Display with margin
	fmt.Printf("%s", s.margin)
	if s.colorFunc != nil {
		s.colorFunc(statusLine)
	} else {
		fmt.Print(statusLine)
	}
}

func (s *StreamingSpinner) clearLine() {
	fmt.Print("\r\033[K")
}
