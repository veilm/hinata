package shell

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type ExecutionResult struct {
	Stdout   string
	Stderr   string
	ExitCode int
	FinalPwd string
	FinalEnv map[string]string
}

type Executor struct {
	WorkingDir string
	Env        map[string]string
}

func NewExecutor(workingDir string) *Executor {
	return &Executor{
		WorkingDir: workingDir,
		Env:        make(map[string]string),
	}
}

func (e *Executor) Execute(commands string) (*ExecutionResult, error) {
	tmpDir, err := os.MkdirTemp("", "hinata-shell-*")
	if err != nil {
		return nil, fmt.Errorf("failed to create temp dir: %w", err)
	}
	defer os.RemoveAll(tmpDir)

	commandsFile := filepath.Join(tmpDir, "commands.sh")
	if err := os.WriteFile(commandsFile, []byte(commands), 0600); err != nil {
		return nil, fmt.Errorf("failed to write commands file: %w", err)
	}

	envFile := filepath.Join(tmpDir, "env.sh")
	if err := e.writeEnvFile(envFile); err != nil {
		return nil, fmt.Errorf("failed to write env file: %w", err)
	}

	pwdFile := filepath.Join(tmpDir, "pwd.txt")
	if err := os.WriteFile(pwdFile, []byte(e.WorkingDir), 0600); err != nil {
		return nil, fmt.Errorf("failed to write pwd file: %w", err)
	}

	finalPwdFile := filepath.Join(tmpDir, "final_pwd.txt")
	finalEnvFile := filepath.Join(tmpDir, "final_env.txt")

	wrapperScript := fmt.Sprintf(`#!/bin/bash
set -o allexport
cd "%s" 2>/dev/null || true
if [ -f "%s" ]; then
    . "%s" 2>/dev/null || true
fi
set +o allexport

. "%s"
HINATA_EXIT_CODE=$?

pwd > "%s"
set > "%s"

exit $HINATA_EXIT_CODE
`, e.WorkingDir, envFile, envFile, commandsFile, finalPwdFile, finalEnvFile)

	wrapperFile := filepath.Join(tmpDir, "wrapper.sh")
	if err := os.WriteFile(wrapperFile, []byte(wrapperScript), 0700); err != nil {
		return nil, fmt.Errorf("failed to write wrapper script: %w", err)
	}

	cmd := exec.Command("bash", wrapperFile)

	currentEnv := os.Environ()
	for k, v := range e.Env {
		currentEnv = append(currentEnv, fmt.Sprintf("%s=%s", k, v))
	}
	cmd.Env = currentEnv

	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()

	exitCode := 0
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			return nil, fmt.Errorf("failed to execute command: %w", err)
		}
	}

	finalPwd, err := os.ReadFile(finalPwdFile)
	if err != nil {
		return nil, fmt.Errorf("failed to read final pwd: %w", err)
	}

	finalEnv, err := parseEnvFile(finalEnvFile)
	if err != nil {
		return nil, fmt.Errorf("failed to parse final env: %w", err)
	}

	e.WorkingDir = strings.TrimSpace(string(finalPwd))
	e.Env = finalEnv

	return &ExecutionResult{
		Stdout:   stdout.String(),
		Stderr:   stderr.String(),
		ExitCode: exitCode,
		FinalPwd: e.WorkingDir,
		FinalEnv: e.Env,
	}, nil
}

func (e *Executor) writeEnvFile(path string) error {
	var lines []string
	for k, v := range e.Env {
		lines = append(lines, fmt.Sprintf("export %s=%q", k, v))
	}
	content := strings.Join(lines, "\n")
	return os.WriteFile(path, []byte(content), 0600)
}

func parseEnvFile(path string) (map[string]string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	env := make(map[string]string)
	lines := strings.Split(string(content), "\n")

	for _, line := range lines {
		line = strings.TrimSpace(line)

		if strings.HasPrefix(line, "export ") {
			line = strings.TrimPrefix(line, "export ")
		}

		if strings.Contains(line, "=") && !strings.HasPrefix(line, "BASH_FUNC_") {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) == 2 {
				key := parts[0]
				value := parts[1]

				if len(value) >= 2 {
					if strings.HasPrefix(value, "'") && strings.HasSuffix(value, "'") {
						value = value[1 : len(value)-1]
					} else if strings.HasPrefix(value, "\"") && strings.HasSuffix(value, "\"") {
						value = value[1 : len(value)-1]
					}
				}

				if !isSystemVariable(key) {
					env[key] = value
				}
			}
		}
	}

	return env, nil
}

func isSystemVariable(key string) bool {
	systemVars := []string{
		"_", "BASH", "BASHOPTS", "BASHPID", "BASH_ALIASES", "BASH_ARGC",
		"BASH_ARGV", "BASH_CMDS", "BASH_LINENO", "BASH_SOURCE", "BASH_SUBSHELL",
		"BASH_VERSINFO", "BASH_VERSION", "COLUMNS", "COMP_WORDBREAKS", "DIRSTACK",
		"EUID", "GROUPS", "HISTCMD", "HISTFILE", "HISTFILESIZE", "HISTSIZE",
		"HOSTNAME", "HOSTTYPE", "IFS", "LINES", "MACHTYPE", "MAILCHECK",
		"OLDPWD", "OPTERR", "OPTIND", "OSTYPE", "PIPESTATUS", "PPID",
		"PS1", "PS2", "PS4", "PWD", "RANDOM", "SECONDS", "SHELL",
		"SHELLOPTS", "SHLVL", "UID", "USER", "USERNAME",
	}

	for _, v := range systemVars {
		if key == v {
			return true
		}
	}

	return strings.HasPrefix(key, "BASH_") ||
		strings.HasPrefix(key, "COMP_") ||
		strings.HasPrefix(key, "FUNCNAME")
}
