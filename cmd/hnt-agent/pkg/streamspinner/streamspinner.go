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

	// State management
	mu         sync.Mutex
	active     bool
	stopCh     chan bool
	contentCh  chan string // Channel to receive new content lines
	startTime  time.Time
	frameIndex int
}

// New creates a new streaming spinner
func New(sp spinner.Spinner, margin string, colorFunc func(string)) *StreamingSpinner {
	return &StreamingSpinner{
		spinner:   sp,
		margin:    margin,
		colorFunc: colorFunc,
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

	// Initial spinner display
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
	s.mu.Unlock()

	// Signal stop
	select {
	case s.stopCh <- true:
	default:
	}

	// Clear spinner line
	s.clearLine()
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
			// Clear spinner line
			s.clearLine()

			// Print content line
			fmt.Printf("%s%s\n", s.margin, line)

			// Redraw spinner on new line (if still active)
			s.mu.Lock()
			if s.active {
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
	timeStr := fmt.Sprintf("(%ds)", elapsedSeconds)
	frame := s.spinner.Frames[s.frameIndex]

	// Format: [margin]Thinking... (Xs) [frame]
	message := fmt.Sprintf("Thinking... %s %s", timeStr, frame)

	fmt.Printf("%s", s.margin)
	if s.colorFunc != nil {
		s.colorFunc(message)
	} else {
		fmt.Print(message)
	}
}

func (s *StreamingSpinner) clearLine() {
	fmt.Print("\r\033[K")
}
