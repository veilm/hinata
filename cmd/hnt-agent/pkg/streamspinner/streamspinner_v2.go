package streamspinner

import (
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/output"
	"github.com/veilm/hinata/cmd/hnt-agent/pkg/spinner"
)

// StreamingSpinnerV2 is a simplified spinner that uses OutputCoordinator
type StreamingSpinnerV2 struct {
	coordinator *output.Coordinator
	spinner     spinner.Spinner
	margin      string
	colorFunc   func(string)
	active      bool
}

// NewV2 creates a new streaming spinner using OutputCoordinator
func NewV2(sp spinner.Spinner, margin string, colorFunc func(string)) *StreamingSpinnerV2 {
	coordinator := output.New(100)
	return &StreamingSpinnerV2{
		coordinator: coordinator,
		spinner:     sp,
		margin:      margin,
		colorFunc:   colorFunc,
	}
}

// Start begins the spinner animation
func (s *StreamingSpinnerV2) Start() {
	if s.active {
		return
	}

	s.active = true
	s.coordinator.Start()

	// Show spinner with random message
	message := spinner.GetRandomLoadingMessage()
	s.coordinator.ShowSpinner(s.spinner, message, s.margin, s.colorFunc)
}

// Stop stops the spinner and cleans up
func (s *StreamingSpinnerV2) Stop() {
	if !s.active {
		return
	}

	s.active = false
	s.coordinator.HideSpinner()
	s.coordinator.Stop()
}

// PrintLine prints a new content line
func (s *StreamingSpinnerV2) PrintLine(line string) {
	if !s.active {
		// If not active, the coordinator isn't running
		// Start it temporarily just for printing
		s.coordinator.Start()
		s.coordinator.PrintLine(s.margin, line, nil)
		s.coordinator.Flush()
		s.coordinator.Stop()
		return
	}

	// Use coordinator to print line
	s.coordinator.PrintLine(s.margin, line, nil)
}