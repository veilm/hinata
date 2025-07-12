package pack

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// GetCommonPrefix calculates the longest common path prefix for a slice of absolute file paths
func GetCommonPrefix(paths []string) (string, error) {
	if len(paths) == 0 {
		return "", fmt.Errorf("cannot find common path of an empty list of paths")
	}

	// Convert to absolute paths
	absPaths := make([]string, len(paths))
	for i, path := range paths {
		absPath, err := filepath.Abs(path)
		if err != nil {
			return "", fmt.Errorf("failed to get absolute path for %s: %w", path, err)
		}
		absPaths[i] = absPath
	}

	if len(absPaths) == 1 {
		// For a single file, the common prefix is its parent directory
		return filepath.Dir(absPaths[0]), nil
	}

	// Find common prefix by comparing paths component by component
	// First, split all paths into components
	var pathComponents [][]string
	for _, path := range absPaths {
		components := strings.Split(path, string(filepath.Separator))
		pathComponents = append(pathComponents, components)
	}

	// Find the minimum length
	minLen := len(pathComponents[0])
	for _, components := range pathComponents[1:] {
		if len(components) < minLen {
			minLen = len(components)
		}
	}

	// Find common prefix
	var commonComponents []string
	for i := 0; i < minLen; i++ {
		component := pathComponents[0][i]
		allMatch := true
		for _, components := range pathComponents[1:] {
			if components[i] != component {
				allMatch = false
				break
			}
		}
		if allMatch {
			commonComponents = append(commonComponents, component)
		} else {
			break
		}
	}

	if len(commonComponents) == 0 {
		return "", fmt.Errorf("could not find a common path for the source files")
	}

	// Reconstruct the common path
	commonPath := strings.Join(commonComponents, string(filepath.Separator))

	// On Unix-like systems, ensure we have the leading separator
	if len(absPaths) > 0 && strings.HasPrefix(absPaths[0], string(filepath.Separator)) && !strings.HasPrefix(commonPath, string(filepath.Separator)) {
		commonPath = string(filepath.Separator) + commonPath
	}

	// Check if the common path is a file
	if info, err := os.Stat(commonPath); err == nil && !info.IsDir() {
		return filepath.Dir(commonPath), nil
	}

	return commonPath, nil
}

// PackFiles packs a list of files into a single string with metadata
func PackFiles(paths []string) (string, error) {
	if len(paths) == 0 {
		return "", nil
	}

	commonPrefix, err := GetCommonPrefix(paths)
	if err != nil {
		return "", err
	}

	var relativePaths []string
	var fileContentBlocks []string

	for _, path := range paths {
		absPath, err := filepath.Abs(path)
		if err != nil {
			return "", fmt.Errorf("failed to get absolute path for %s: %w", path, err)
		}

		relPath, err := filepath.Rel(commonPrefix, absPath)
		if err != nil {
			return "", fmt.Errorf("path %s does not have prefix %s: %w", absPath, commonPrefix, err)
		}

		// Convert to forward slashes for cross-platform compatibility
		relPathStr := strings.ReplaceAll(relPath, string(filepath.Separator), "/")
		relativePaths = append(relativePaths, relPathStr)

		content, err := os.ReadFile(absPath)
		if err != nil {
			return "", fmt.Errorf("failed to read file %s: %w", absPath, err)
		}

		fileBlock := fmt.Sprintf("<%s>\n%s</%s>", relPathStr, string(content), relPathStr)
		fileContentBlocks = append(fileContentBlocks, fileBlock)
	}

	var result strings.Builder
	result.WriteString("<file_paths>\n")
	result.WriteString(strings.Join(relativePaths, "\n"))
	result.WriteString("\n</file_paths>\n\n")
	result.WriteString(strings.Join(fileContentBlocks, "\n\n"))

	return result.String(), nil
}

type FileInfo struct {
	AbsolutePath string
	RelativePath string
}

// GetFileInfos returns FileInfo for each path, sorted if requested
func GetFileInfos(paths []string, sortPaths bool) ([]FileInfo, string, error) {
	// Resolve all input file paths to their canonical, absolute paths
	absolutePaths := make([]string, 0, len(paths))
	for _, path := range paths {
		absPath, err := filepath.Abs(path)
		if err != nil {
			return nil, "", fmt.Errorf("failed to find or access path: %s: %w", path, err)
		}

		info, err := os.Stat(absPath)
		if err != nil {
			return nil, "", fmt.Errorf("failed to stat path: %s: %w", path, err)
		}

		if !info.Mode().IsRegular() {
			return nil, "", fmt.Errorf("input path is not a file: %s", path)
		}

		absolutePaths = append(absolutePaths, absPath)
	}

	// Sort if requested
	if sortPaths {
		sort.Strings(absolutePaths)
	}

	// Calculate common path prefix
	commonPrefix, err := GetCommonPrefix(absolutePaths)
	if err != nil {
		return nil, "", err
	}

	// Create FileInfo for each path
	fileInfos := make([]FileInfo, 0, len(absolutePaths))
	for _, absPath := range absolutePaths {
		relPath, err := filepath.Rel(commonPrefix, absPath)
		if err != nil {
			return nil, "", fmt.Errorf("failed to create relative path for %s from base %s: %w", absPath, commonPrefix, err)
		}

		fileInfos = append(fileInfos, FileInfo{
			AbsolutePath: absPath,
			RelativePath: relPath,
		})
	}

	return fileInfos, commonPrefix, nil
}
