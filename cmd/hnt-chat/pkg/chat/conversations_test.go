package chat

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCopyReasoningForExistingMessagesCopiesOnlyRetainedAssistantReasoning(t *testing.T) {
	tmpDir := t.TempDir()
	srcDir := filepath.Join(tmpDir, "src")
	dstDir := filepath.Join(tmpDir, "dst")

	mustMkdir(t, filepath.Join(srcDir, "reasoning"))
	mustMkdir(t, dstDir)
	mustWrite(t, filepath.Join(srcDir, "reasoning", "2000.md"), "<think>keep</think>")
	mustWrite(t, filepath.Join(srcDir, "reasoning", "3000.md"), "<think>drop missing assistant</think>")
	mustWrite(t, filepath.Join(srcDir, "reasoning", "not-a-timestamp.md"), "<think>drop invalid</think>")
	mustWrite(t, filepath.Join(dstDir, "1000-user.md"), "hello")
	mustWrite(t, filepath.Join(dstDir, "2000-assistant.md"), "answer")

	if err := CopyReasoningForExistingMessages(srcDir, dstDir); err != nil {
		t.Fatalf("CopyReasoningForExistingMessages() error = %v", err)
	}

	assertFileExists(t, filepath.Join(dstDir, "reasoning", "2000.md"))
	assertFileDoesNotExist(t, filepath.Join(dstDir, "reasoning", "3000.md"))
	assertFileDoesNotExist(t, filepath.Join(dstDir, "reasoning", "not-a-timestamp.md"))
}

func TestCopyReasoningForExistingMessagesDoesNotCreateDirWithoutMatchingReasoning(t *testing.T) {
	tmpDir := t.TempDir()
	srcDir := filepath.Join(tmpDir, "src")
	dstDir := filepath.Join(tmpDir, "dst")

	mustMkdir(t, filepath.Join(srcDir, "reasoning"))
	mustMkdir(t, dstDir)
	mustWrite(t, filepath.Join(srcDir, "reasoning", "3000.md"), "<think>drop</think>")
	mustWrite(t, filepath.Join(dstDir, "2000-assistant.md"), "answer")

	if err := CopyReasoningForExistingMessages(srcDir, dstDir); err != nil {
		t.Fatalf("CopyReasoningForExistingMessages() error = %v", err)
	}

	assertFileDoesNotExist(t, filepath.Join(dstDir, "reasoning"))
}

func TestCopyMessageMetadataForExistingMessagesCopiesOnlyRetainedAssistantMetadata(t *testing.T) {
	tmpDir := t.TempDir()
	srcDir := filepath.Join(tmpDir, "src")
	dstDir := filepath.Join(tmpDir, "dst")

	mustMkdir(t, filepath.Join(srcDir, "meta", "messages"))
	mustMkdir(t, dstDir)
	mustWrite(t, filepath.Join(srcDir, "meta", "messages", "2000.json"), `{"usage":{"total_tokens":5}}`)
	mustWrite(t, filepath.Join(srcDir, "meta", "messages", "3000.json"), `{"usage":{"total_tokens":9}}`)
	mustWrite(t, filepath.Join(srcDir, "meta", "messages", "not-a-timestamp.json"), `{}`)
	mustWrite(t, filepath.Join(dstDir, "1000-user.md"), "hello")
	mustWrite(t, filepath.Join(dstDir, "2000-assistant.md"), "answer")

	if err := CopyMessageMetadataForExistingMessages(srcDir, dstDir); err != nil {
		t.Fatalf("CopyMessageMetadataForExistingMessages() error = %v", err)
	}

	assertFileExists(t, filepath.Join(dstDir, "meta", "messages", "2000.json"))
	assertFileDoesNotExist(t, filepath.Join(dstDir, "meta", "messages", "3000.json"))
	assertFileDoesNotExist(t, filepath.Join(dstDir, "meta", "messages", "not-a-timestamp.json"))
}

func TestCopyMessageMetadataForExistingMessagesDoesNotCreateDirWithoutMatchingMetadata(t *testing.T) {
	tmpDir := t.TempDir()
	srcDir := filepath.Join(tmpDir, "src")
	dstDir := filepath.Join(tmpDir, "dst")

	mustMkdir(t, filepath.Join(srcDir, "meta", "messages"))
	mustMkdir(t, dstDir)
	mustWrite(t, filepath.Join(srcDir, "meta", "messages", "3000.json"), `{}`)
	mustWrite(t, filepath.Join(dstDir, "2000-assistant.md"), "answer")

	if err := CopyMessageMetadataForExistingMessages(srcDir, dstDir); err != nil {
		t.Fatalf("CopyMessageMetadataForExistingMessages() error = %v", err)
	}

	assertFileDoesNotExist(t, filepath.Join(dstDir, "meta", "messages"))
}

func mustMkdir(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(path, 0755); err != nil {
		t.Fatalf("failed to create %s: %v", path, err)
	}
}

func mustWrite(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("failed to write %s: %v", path, err)
	}
}

func assertFileExists(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("expected %s to exist: %v", path, err)
	}
}

func assertFileDoesNotExist(t *testing.T, path string) {
	t.Helper()
	if _, err := os.Stat(path); err == nil {
		t.Fatalf("expected %s not to exist", path)
	} else if !os.IsNotExist(err) {
		t.Fatalf("unexpected stat error for %s: %v", path, err)
	}
}
