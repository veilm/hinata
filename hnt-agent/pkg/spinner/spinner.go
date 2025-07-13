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
)

// Fallback spinner - hardcoded as requested
var fallbackSpinner = Spinner{
	Name:   "fallback",
	Frames: []string{"│╱", "╱─", "─╲", "╲│"},
	Speed:  150 * time.Millisecond,
}

func init() {
	// Try to load spinners from config file
	if err := loadSpinnersFromConfig(); err != nil {
		// If loading fails, use fallback spinner
		SPINNERS = []Spinner{fallbackSpinner}
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

	// If no valid spinners in config, use fallback
	if len(SPINNERS) == 0 {
		SPINNERS = []Spinner{fallbackSpinner}
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

func Run(spinner Spinner, message string, margin string, stopCh <-chan bool) {
	fmt.Printf("%s%s", margin, message)

	frameIndex := 0
	ticker := time.NewTicker(spinner.Speed)
	defer ticker.Stop()

	hideCursor()
	defer showCursor()

	for {
		select {
		case <-stopCh:
			clearLine()
			return
		case <-ticker.C:
			frame := spinner.Frames[frameIndex]
			fmt.Printf("\r%s%s %s", margin, frame, message)
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
