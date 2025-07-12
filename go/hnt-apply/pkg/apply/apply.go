package apply

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	pack "github.com/veilm/hinata/llm-pack/pkg/pack"
)

type ChangeBlock struct {
	RelativePath string
	Target       []string
	Replace      []string
}

func ApplyChanges(sourceFiles []string, disallowCreating bool, ignoreReasoning bool, verbose bool, input string) error {
	inputToParse := input

	if ignoreReasoning {
		trimmedInput := strings.TrimSpace(inputToParse)
		if strings.HasPrefix(trimmedInput, "<think>") {
			if endPos := strings.Index(trimmedInput, "</think>"); endPos != -1 {
				inputToParse = trimmedInput[endPos+len("</think>"):]
			}
		}
	}

	pathBufs := make([]string, len(sourceFiles))
	copy(pathBufs, sourceFiles)

	commonRoot, err := pack.GetCommonPrefix(pathBufs)
	if err != nil {
		return fmt.Errorf("failed to find common root for source files: %w", err)
	}

	if verbose {
		fmt.Printf("Common root: %s\n", commonRoot)
	}

	blocks, err := parseBlocks(inputToParse)
	if err != nil {
		return err
	}

	if verbose {
		fmt.Printf("Parsed %d change blocks\n", len(blocks))
	}

	for i, block := range blocks {
		if verbose {
			fmt.Println("---")
		}

		if err := applyChangeBlock(i, &block, commonRoot, sourceFiles, disallowCreating, verbose); err != nil {
			return err
		}
	}

	return nil
}

func parseBlocks(input string) ([]ChangeBlock, error) {
	var blocks []ChangeBlock
	lines := strings.Split(input, "\n")
	i := 0

	for i < len(lines) {
		// 1. Find the start of a block
		startMarkerIdx := -1
		for j := i; j < len(lines); j++ {
			if strings.TrimSpace(lines[j]) == "<<<<<<< TARGET" {
				startMarkerIdx = j
				break
			}
		}
		if startMarkerIdx == -1 {
			break // No more blocks
		}

		// 2. The file path is the last non-empty line before the TARGET marker
		path := ""
		for j := startMarkerIdx - 1; j >= i; j-- {
			if strings.TrimSpace(lines[j]) != "" {
				path = strings.TrimSpace(lines[j])
				break
			}
		}
		if path == "" {
			// Found a TARGET marker but no file path before it
			break
		}

		// 3. Collect the target content
		i = startMarkerIdx + 1
		equalsMarkerIdx := -1
		for j := i; j < len(lines); j++ {
			if strings.TrimSpace(lines[j]) == "=======" {
				equalsMarkerIdx = j
				break
			}
		}
		if equalsMarkerIdx == -1 {
			break // Malformed block
		}
		target := lines[i:equalsMarkerIdx]

		// 4. Collect the replace content
		i = equalsMarkerIdx + 1
		endMarkerIdx := -1
		for j := i; j < len(lines); j++ {
			if strings.TrimSpace(lines[j]) == ">>>>>>> REPLACE" {
				endMarkerIdx = j
				break
			}
		}
		if endMarkerIdx == -1 {
			break // Malformed block
		}
		replace := lines[i:endMarkerIdx]

		// 5. Store the block and prepare for the next one
		blocks = append(blocks, ChangeBlock{
			RelativePath: path,
			Target:       target,
			Replace:      replace,
		})

		i = endMarkerIdx + 1
	}

	return blocks, nil
}

func applyChangeBlock(i int, block *ChangeBlock, commonRoot string, sourceFiles []string, disallowCreating bool, verbose bool) error {
	pathToUse := filepath.Join(commonRoot, block.RelativePath)

	if _, err := os.Stat(pathToUse); os.IsNotExist(err) {
		// Try to find the file in source files
		for _, sourcePath := range sourceFiles {
			if strings.HasSuffix(sourcePath, block.RelativePath) {
				pathToUse = sourcePath
				if verbose {
					fmt.Printf("Verbose: Using fallback path %s for relative path %s\n", pathToUse, block.RelativePath)
				}
				break
			}
		}
	}

	if verbose {
		fmt.Printf("Processing block for %s\n", block.RelativePath)
		fmt.Printf("Absolute path: %s\n", pathToUse)
	}

	if fileInfo, err := os.Stat(pathToUse); err == nil {
		// File exists
		if !fileInfo.Mode().IsRegular() {
			fmt.Printf("[%d] FAILED: %s is not a file\n", i, block.RelativePath)
			return nil
		}

		content, err := os.ReadFile(pathToUse)
		if err != nil {
			return fmt.Errorf("failed to read file %s: %w", pathToUse, err)
		}

		if len(block.Target) == 0 {
			if len(content) == 0 {
				// This is a file creation scenario on an existing empty file
				contentToWrite := strings.Join(block.Replace, "\n")
				if len(block.Replace) > 0 {
					contentToWrite += "\n"
				}
				if err := os.WriteFile(pathToUse, []byte(contentToWrite), 0644); err != nil {
					return fmt.Errorf("failed to create and write to file %s: %w", pathToUse, err)
				}
				fmt.Printf("[%d] CREATED: %s\n", i, block.RelativePath)
				return nil
			} else {
				// The file exists and is not empty, but the target is empty
				return fmt.Errorf("FAILED: empty target for existing, non-empty file: %s", block.RelativePath)
			}
		}

		fileLines := strings.Split(string(content), "\n")
		// Remove the last empty line if the file ends with a newline
		if len(fileLines) > 0 && fileLines[len(fileLines)-1] == "" {
			fileLines = fileLines[:len(fileLines)-1]
		}

		// Find target position
		positions := []int{}
		for j := 0; j <= len(fileLines)-len(block.Target); j++ {
			match := true
			for k := 0; k < len(block.Target); k++ {
				if fileLines[j+k] != block.Target[k] {
					match = false
					break
				}
			}
			if match {
				positions = append(positions, j)
			}
		}

		if len(positions) == 0 {
			return fmt.Errorf("FAILED: target not found in %s", block.RelativePath)
		}
		if len(positions) > 1 {
			return fmt.Errorf("FAILED: target found %d times in %s", len(positions), block.RelativePath)
		}

		pos := positions[0]
		var newLines []string
		newLines = append(newLines, fileLines[:pos]...)
		newLines = append(newLines, block.Replace...)
		newLines = append(newLines, fileLines[pos+len(block.Target):]...)

		newContent := strings.Join(newLines, "\n")
		if len(newLines) > 0 {
			newContent += "\n"
		}
		if err := os.WriteFile(pathToUse, []byte(newContent), 0644); err != nil {
			return fmt.Errorf("failed to write to file %s: %w", pathToUse, err)
		}

		fmt.Printf("[%d] OK: %s\n", i, block.RelativePath)
	} else if os.IsNotExist(err) {
		// File does not exist
		if disallowCreating {
			fmt.Printf("[%d] FAILED: %s - file does not exist and --disallow-creating is set\n", i, block.RelativePath)
			return nil
		}
		if len(block.Target) > 0 {
			fmt.Printf("[%d] FAILED: %s - file does not exist but target is not empty for creation\n", i, block.RelativePath)
			return nil
		}

		if parent := filepath.Dir(pathToUse); parent != "" {
			if err := os.MkdirAll(parent, 0755); err != nil {
				return fmt.Errorf("failed to create parent directories for %s: %w", pathToUse, err)
			}
		}

		contentToWrite := strings.Join(block.Replace, "\n")
		if len(block.Replace) > 0 {
			contentToWrite += "\n"
		}
		if err := os.WriteFile(pathToUse, []byte(contentToWrite), 0644); err != nil {
			return fmt.Errorf("failed to create and write to file %s: %w", pathToUse, err)
		}

		fmt.Printf("[%d] CREATED: %s\n", i, block.RelativePath)
	} else {
		return fmt.Errorf("failed to stat file %s: %w", pathToUse, err)
	}

	return nil
}
