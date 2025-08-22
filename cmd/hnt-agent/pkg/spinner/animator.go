package spinner

import (
	"sync"
	"time"
)

// Animator manages the state and animation logic for a spinner
// It handles frame rotation, time tracking, and status line generation
type Animator struct {
	spinner Spinner
	message string

	mu         sync.Mutex
	startTime  time.Time
	frameIndex int
	started    bool
}

// NewAnimator creates a new animator for the given spinner and message
func NewAnimator(sp Spinner, message string) *Animator {
	return &Animator{
		spinner: sp,
		message: message,
	}
}

// Start initializes the animator's timer
func (a *Animator) Start() {
	a.mu.Lock()
	defer a.mu.Unlock()
	if !a.started {
		a.startTime = time.Now()
		a.frameIndex = 0
		a.started = true
	}
}

// NextFrame advances to the next frame and returns the formatted status line
func (a *Animator) NextFrame() string {
	a.mu.Lock()
	defer a.mu.Unlock()

	if !a.started {
		a.Start()
	}

	// Calculate elapsed time
	elapsedSeconds := int64(time.Since(a.startTime).Seconds())

	// Get current frame
	frame := a.spinner.Frames[a.frameIndex]

	// Advance frame index for next call
	a.frameIndex = (a.frameIndex + 1) % len(a.spinner.Frames)

	// Return formatted status line
	return FormatStatusLine(a.message, elapsedSeconds, frame)
}

// GetCurrentStatus returns the current status line without advancing the frame
func (a *Animator) GetCurrentStatus() string {
	a.mu.Lock()
	defer a.mu.Unlock()

	if !a.started {
		return FormatStatusLine(a.message, 0, a.spinner.Frames[0])
	}

	elapsedSeconds := int64(time.Since(a.startTime).Seconds())
	frame := a.spinner.Frames[a.frameIndex]
	return FormatStatusLine(a.message, elapsedSeconds, frame)
}

// GetSpeed returns the animation speed for this spinner
func (a *Animator) GetSpeed() time.Duration {
	return a.spinner.Speed
}

// Reset resets the animator to its initial state
func (a *Animator) Reset() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.startTime = time.Now()
	a.frameIndex = 0
	a.started = false
}
