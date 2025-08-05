package spinner

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Spinner struct {
	Name   string
	Frames []string
	Speed  time.Duration
}

type SpinnerConfig struct {
	Filename string `json:"filename"`
	Interval int    `json:"interval"` // milliseconds
}

type Config struct {
	Spinners        []SpinnerConfig `json:"spinners"`
	LoadingMessages []string        `json:"loadingMessages"`
}

var (
	SPINNERS        []Spinner
	loadingMessages []string
	unicodeSupport  UnicodeSupport
)

// Fallback spinners for different Unicode support levels
var asciiSpinner = Spinner{
	Name:   "ascii",
	Frames: []string{"|", "/", "-", "\\"},
	Speed:  150 * time.Millisecond,
}

var basicUnicodeSpinner = Spinner{
	Name:   "basic-unicode",
	Frames: []string{"│╱", "╱─", "─╲", "╲│"},
	Speed:  150 * time.Millisecond,
}

func init() {
	// Always check NO_UNICODE first (highest priority)
	if os.Getenv("NO_UNICODE") != "" {
		unicodeSupport = UnicodeNone
	} else if os.Getenv("HINATA_ENABLE_UNICODE_DETECTION") != "" {
		// If detection is enabled, run full detection
		unicodeSupport = DetectUnicodeSupport()
	} else {
		// Default behavior - assume full Unicode support
		unicodeSupport = UnicodeFull
	}

	// Try to load spinners from config file
	if err := loadSpinnersFromConfig(); err != nil {
		// If loading fails, use appropriate fallback spinner
		switch unicodeSupport {
		case UnicodeNone:
			SPINNERS = []Spinner{asciiSpinner}
		default:
			SPINNERS = []Spinner{basicUnicodeSpinner}
		}
		loadingMessages = []string{"Working..."}
	}
}

func loadSpinnersFromConfig() error {
	// Try multiple locations for the config file
	configDirs := []string{
		"/etc/hinata/spinners",
	}

	// Check XDG_CONFIG_HOME first, then fall back to ~/.config
	if xdgConfig := os.Getenv("XDG_CONFIG_HOME"); xdgConfig != "" {
		configDirs = append(configDirs, filepath.Join(xdgConfig, "hinata", "spinners"))
	}
	configDirs = append(configDirs, filepath.Join(os.Getenv("HOME"), ".config", "hinata", "spinners"))
	configDirs = append(configDirs, "./spinners")

	var configDir string
	var configData []byte
	var err error

	// Find the spinners directory
	for _, dir := range configDirs {
		configPath := filepath.Join(dir, "spinners.json")
		configData, err = os.ReadFile(configPath)
		if err == nil {
			configDir = dir
			break
		}
	}

	if err != nil {
		return fmt.Errorf("failed to read config file from any location: %w", err)
	}

	var config Config
	if err := json.Unmarshal(configData, &config); err != nil {
		return fmt.Errorf("failed to parse config file: %w", err)
	}

	// Convert config spinners to internal format
	SPINNERS = make([]Spinner, 0, len(config.Spinners))
	for _, sc := range config.Spinners {
		// Skip invalid spinners
		if sc.Interval <= 0 || sc.Filename == "" {
			continue
		}

		// Read frames from text file
		framesPath := filepath.Join(configDir, sc.Filename)
		framesData, err := os.ReadFile(framesPath)
		if err != nil {
			continue
		}

		// Split into lines
		lines := strings.Split(strings.TrimSpace(string(framesData)), "\n")
		if len(lines) == 0 {
			continue
		}

		SPINNERS = append(SPINNERS, Spinner{
			Name:   sc.Filename,
			Frames: lines,
			Speed:  time.Duration(sc.Interval) * time.Millisecond,
		})
	}

	// Filter spinners based on Unicode support
	if unicodeSupport < UnicodeFull {
		filteredSpinners := []Spinner{}
		for _, spinner := range SPINNERS {
			// Check if spinner contains complex Unicode
			hasComplexChars := false
			for _, frame := range spinner.Frames {
				for _, r := range frame {
					if IsComplexUnicodeChar(r) {
						hasComplexChars = true
						break
					}
				}
				if hasComplexChars {
					break
				}
			}

			// Only include spinners without complex chars for limited Unicode support
			if !hasComplexChars {
				filteredSpinners = append(filteredSpinners, spinner)
			}
		}

		if len(filteredSpinners) > 0 {
			SPINNERS = filteredSpinners
		}
	}

	// If no valid spinners in config, use fallback
	if len(SPINNERS) == 0 {
		switch unicodeSupport {
		case UnicodeNone:
			SPINNERS = []Spinner{asciiSpinner}
		default:
			SPINNERS = []Spinner{basicUnicodeSpinner}
		}
	}

	// Load messages
	loadingMessages = config.LoadingMessages
	if len(loadingMessages) == 0 {
		loadingMessages = []string{"Working..."}
	}

	return nil
}

func GetRandomSpinner() Spinner {
	return SPINNERS[rand.Intn(len(SPINNERS))]
}

func GetRandomLoadingMessage() string {
	return loadingMessages[rand.Intn(len(loadingMessages))]
}

func Run(spinner Spinner, message string, margin string, stopCh <-chan bool, colorFunc func(string)) {
	startTime := time.Now()
	frameIndex := 0
	ticker := time.NewTicker(spinner.Speed)
	defer ticker.Stop()

	hideCursor()
	defer showCursor()

	// Initial display
	fmt.Print(margin)
	if colorFunc != nil {
		colorFunc(message)
	} else {
		fmt.Print(message)
	}

	for {
		select {
		case <-stopCh:
			clearLine()
			return
		case <-ticker.C:
			// Calculate elapsed time
			elapsedSeconds := int64(time.Since(startTime).Seconds())

			// Format timer with spacing rules matching Rust implementation
			timeStr := fmt.Sprintf("(%ds)", elapsedSeconds)
			var prefix string
			if elapsedSeconds < 10 {
				prefix = "  " // 2 spaces for single digit
			} else {
				prefix = " " // 1 space for double digit
			}

			// Total width for time display block is 10 characters
			totalWidth := 10
			currentWidth := len(prefix) + len(timeStr)

			var timeDisplayBlock string
			if currentWidth < totalWidth {
				suffix := strings.Repeat(" ", totalWidth-currentWidth)
				timeDisplayBlock = fmt.Sprintf("%s%s%s", prefix, timeStr, suffix)
			} else {
				timeDisplayBlock = fmt.Sprintf("%s%s ", prefix, timeStr)
			}

			// Get current frame
			frame := spinner.Frames[frameIndex]

			// Clear the line first, then display
			// Display format: [margin][message][time][frame]
			fmt.Printf("\r\033[K%s", margin)
			if colorFunc != nil {
				colorFunc(fmt.Sprintf("%s%s%s", message, timeDisplayBlock, frame))
			} else {
				fmt.Printf("%s%s%s", message, timeDisplayBlock, frame)
			}

			frameIndex = (frameIndex + 1) % len(spinner.Frames)
		}
	}
}

func hideCursor() {
	fmt.Print("\033[?25l")
}

func showCursor() {
	fmt.Print("\033[?25h")
}

func clearLine() {
	fmt.Print("\r\033[K")
}

// GetUnicodeSupport returns the detected Unicode support level
func GetUnicodeSupport() UnicodeSupport {
	return unicodeSupport
}

// GetUnicodeSupportString returns a human-readable description of the Unicode support level
func GetUnicodeSupportString() string {
	switch unicodeSupport {
	case UnicodeNone:
		return "ASCII only"
	case UnicodeBasic:
		return "Basic Unicode (box drawing)"
	case UnicodeFull:
		return "Full Unicode (including complex symbols)"
	default:
		return "Unknown"
	}
}
