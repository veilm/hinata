package prompt

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

func GetUserInstruction(message string, useEditor bool) (string, error) {
	return GetUserInstructionWithHeight(message, useEditor, 3)
}

func GetUserInstructionWithHeight(message string, useEditor bool, height int) (string, error) {
	return GetUserInstructionWithColorsAndHeight(message, useEditor, ColorConfig{}, height)
}

func GetUserInstructionWithColors(message string, useEditor bool, colors ColorConfig) (string, error) {
	return GetUserInstructionWithColorsAndHeight(message, useEditor, colors, 3)
}

func GetUserInstructionWithColorsAndHeight(message string, useEditor bool, colors ColorConfig, height int) (string, error) {
	if message != "" {
		return message, nil
	}

	if useEditor {
		return PromptWithEditor()
	}

	return PromptWithTUIColorsAndHeight(colors, height)
}

func PromptWithEditor() (string, error) {
	editor := os.Getenv("EDITOR")
	if editor == "" {
		return "", fmt.Errorf("EDITOR environment variable not set")
	}

	tmpfile, err := os.CreateTemp("", "hinata-*.md")
	if err != nil {
		return "", fmt.Errorf("failed to create temporary file: %w", err)
	}
	defer os.Remove(tmpfile.Name())

	initialText := "Replace this text with your instructions. Then write to this file and exit your\ntext editor. Leave the file unchanged or empty to abort."
	if _, err := tmpfile.Write([]byte(initialText)); err != nil {
		return "", fmt.Errorf("failed to write to temporary file: %w", err)
	}
	tmpfile.Close()

	editorParts := strings.Fields(editor)
	cmd := exec.Command(editorParts[0], append(editorParts[1:], tmpfile.Name())...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("editor exited with error: %w", err)
	}

	content, err := os.ReadFile(tmpfile.Name())
	if err != nil {
		return "", fmt.Errorf("failed to read temporary file: %w", err)
	}

	instruction := string(content)
	if strings.TrimSpace(instruction) == strings.TrimSpace(initialText) || strings.TrimSpace(instruction) == "" {
		return "", fmt.Errorf("no message provided")
	}

	return instruction, nil
}

func PromptWithTUI() (string, error) {
	return PromptWithTUIHeight(3)
}

func PromptWithTUIHeight(height int) (string, error) {
	instruction, err := PromptForInputWithColors(ColorConfig{}, height)
	if err != nil {
		return "", err
	}
	if instruction == "" {
		return "", fmt.Errorf("no message provided")
	}
	return instruction, nil
}

func PromptWithTUIColors(colors ColorConfig) (string, error) {
	return PromptWithTUIColorsAndHeight(colors, 3)
}

func PromptWithTUIColorsAndHeight(colors ColorConfig, height int) (string, error) {
	instruction, err := PromptForInputWithColors(colors, height)
	if err != nil {
		return "", err
	}
	if instruction == "" {
		return "", fmt.Errorf("no message provided")
	}
	return instruction, nil
}
