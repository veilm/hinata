package shell

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestNewExecutor(t *testing.T) {
	executor := NewExecutor("/tmp")
	if executor.WorkingDir != "/tmp" {
		t.Errorf("Expected working dir /tmp, got %s", executor.WorkingDir)
	}
	if executor.Env == nil {
		t.Error("Expected env map to be initialized")
	}
}

func TestExecuteSimpleCommand(t *testing.T) {
	executor := NewExecutor("/tmp")
	result, err := executor.Execute("echo hello")

	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if result.ExitCode != 0 {
		t.Errorf("Expected exit code 0, got %d", result.ExitCode)
	}

	if strings.TrimSpace(result.Stdout) != "hello" {
		t.Errorf("Expected stdout 'hello', got '%s'", result.Stdout)
	}

	if result.Stderr != "" {
		t.Errorf("Expected empty stderr, got '%s'", result.Stderr)
	}
}

func TestExecuteWithError(t *testing.T) {
	executor := NewExecutor("/tmp")
	result, err := executor.Execute("bash -c 'exit 42'")

	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if result.ExitCode != 42 {
		t.Errorf("Expected exit code 42, got %d", result.ExitCode)
	}
}

func TestExecuteFailedCommand(t *testing.T) {
	executor := NewExecutor("/tmp")
	result, err := executor.Execute("cat /nonexistent/file.txt")

	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if result.ExitCode == 0 {
		t.Errorf("Expected non-zero exit code, got %d", result.ExitCode)
	}

	if result.Stderr == "" {
		t.Error("Expected stderr output for failed command")
	}
}

func TestExecuteWithStderr(t *testing.T) {
	executor := NewExecutor("/tmp")
	result, err := executor.Execute("echo error >&2")

	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if result.ExitCode != 0 {
		t.Errorf("Expected exit code 0, got %d", result.ExitCode)
	}

	if result.Stdout != "" {
		t.Errorf("Expected empty stdout, got '%s'", result.Stdout)
	}

	if strings.TrimSpace(result.Stderr) != "error" {
		t.Errorf("Expected stderr 'error', got '%s'", result.Stderr)
	}
}

func TestWorkingDirectoryPersistence(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "shell-test-*")
	if err != nil {
		t.Fatalf("Failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	subDir := filepath.Join(tmpDir, "subdir")

	executor := NewExecutor(tmpDir)

	result, err := executor.Execute("mkdir -p subdir && cd subdir && pwd")
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if result.ExitCode != 0 {
		t.Errorf("Expected exit code 0, got %d", result.ExitCode)
	}

	if result.FinalPwd != subDir {
		t.Errorf("Expected final pwd '%s', got '%s'", subDir, result.FinalPwd)
	}

	if executor.WorkingDir != subDir {
		t.Errorf("Expected executor working dir to be updated to '%s', got '%s'", subDir, executor.WorkingDir)
	}

	result2, err := executor.Execute("pwd")
	if err != nil {
		t.Fatalf("Unexpected error on second execution: %v", err)
	}

	if strings.TrimSpace(result2.Stdout) != subDir {
		t.Errorf("Expected second execution to start in '%s', got '%s'", subDir, strings.TrimSpace(result2.Stdout))
	}
}

func TestEnvironmentPersistence(t *testing.T) {
	executor := NewExecutor("/tmp")

	result, err := executor.Execute("export MYVAR=hello && echo $MYVAR")
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if strings.TrimSpace(result.Stdout) != "hello" {
		t.Errorf("Expected stdout 'hello', got '%s'", result.Stdout)
	}

	if val, ok := result.FinalEnv["MYVAR"]; !ok || val != "hello" {
		t.Errorf("Expected MYVAR=hello in final env, got %v", result.FinalEnv["MYVAR"])
	}

	result2, err := executor.Execute("echo $MYVAR")
	if err != nil {
		t.Fatalf("Unexpected error on second execution: %v", err)
	}

	if strings.TrimSpace(result2.Stdout) != "hello" {
		t.Errorf("Expected MYVAR to persist, got '%s'", strings.TrimSpace(result2.Stdout))
	}
}

func TestMultilineCommands(t *testing.T) {
	executor := NewExecutor("/tmp")

	commands := `echo line1
echo line2
echo line3`

	result, err := executor.Execute(commands)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	expectedOutput := "line1\nline2\nline3\n"
	if result.Stdout != expectedOutput {
		t.Errorf("Expected stdout '%s', got '%s'", expectedOutput, result.Stdout)
	}
}

func TestCommandWithFunction(t *testing.T) {
	executor := NewExecutor("/tmp")

	commands := `myfunc() {
    echo "Hello from function"
}
myfunc`

	result, err := executor.Execute(commands)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if strings.TrimSpace(result.Stdout) != "Hello from function" {
		t.Errorf("Expected function output, got '%s'", result.Stdout)
	}
}

func TestInitialEnvironment(t *testing.T) {
	executor := NewExecutor("/tmp")
	executor.Env["INITIAL_VAR"] = "initial_value"

	result, err := executor.Execute("echo $INITIAL_VAR")
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	if strings.TrimSpace(result.Stdout) != "initial_value" {
		t.Errorf("Expected initial env var value, got '%s'", strings.TrimSpace(result.Stdout))
	}
}
