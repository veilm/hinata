package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/veilm/hinata/cmd/shell-exec/pkg/shell"
	"io"
	"os"
	"strings"
)

func main() {
	var (
		workingDir = flag.String("pwd", "", "Initial working directory (default: current directory)")
		envFile    = flag.String("env", "", "JSON file containing initial environment variables")
		jsonOutput = flag.Bool("json", false, "Output result as JSON")
	)
	flag.Parse()

	if *workingDir == "" {
		pwd, err := os.Getwd()
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error getting current directory: %v\n", err)
			os.Exit(1)
		}
		*workingDir = pwd
	}

	executor := shell.NewExecutor(*workingDir)

	if *envFile != "" {
		data, err := os.ReadFile(*envFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error reading env file: %v\n", err)
			os.Exit(1)
		}

		var env map[string]string
		if err := json.Unmarshal(data, &env); err != nil {
			fmt.Fprintf(os.Stderr, "Error parsing env file: %v\n", err)
			os.Exit(1)
		}

		executor.Env = env
	}

	commands, err := readAllInput()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading input: %v\n", err)
		os.Exit(1)
	}

	result, err := executor.Execute(commands)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error executing commands: %v\n", err)
		os.Exit(1)
	}

	if *jsonOutput {
		output := map[string]interface{}{
			"stdout":    result.Stdout,
			"stderr":    result.Stderr,
			"exit_code": result.ExitCode,
			"final_pwd": result.FinalPwd,
			"final_env": result.FinalEnv,
		}

		encoder := json.NewEncoder(os.Stdout)
		encoder.SetIndent("", "  ")
		if err := encoder.Encode(output); err != nil {
			fmt.Fprintf(os.Stderr, "Error encoding JSON: %v\n", err)
			os.Exit(1)
		}
	} else {
		if result.Stdout != "" {
			fmt.Fprint(os.Stdout, result.Stdout)
		}
		if result.Stderr != "" {
			fmt.Fprint(os.Stderr, result.Stderr)
		}
		os.Exit(result.ExitCode)
	}
}

func readAllInput() (string, error) {
	reader := bufio.NewReader(os.Stdin)
	var lines []string

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				if line != "" {
					lines = append(lines, line)
				}
				break
			}
			return "", err
		}
		lines = append(lines, line)
	}

	return strings.Join(lines, ""), nil
}
