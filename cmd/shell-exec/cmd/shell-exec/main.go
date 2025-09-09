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
		aliasFile  = flag.String("aliases", "", "File containing initial aliases (output of 'alias' command)")
		stateFile  = flag.String("state", "", "JSON state file to read from and write back to")
		loadState  = flag.String("load-state", "", "JSON state file to read from (no write back)")
		outputJSON = flag.Bool("output-json", false, "Output final state as JSON to stdout")
	)
	flag.Parse()

	var executor *shell.Executor
	var usingStateFile bool
	var stateFilePath string

	// Determine which state source to use
	if *stateFile != "" && *loadState != "" {
		fmt.Fprintf(os.Stderr, "Error: cannot use both --state and --load-state\n")
		os.Exit(1)
	}

	if *stateFile != "" || *loadState != "" {
		// Use state file (either read-write or read-only)
		sourceFile := *stateFile
		if sourceFile == "" {
			sourceFile = *loadState
		}

		state, err := shell.LoadState(sourceFile)
		if err != nil {
			// If file doesn't exist and using --state (not --load-state), create new state
			if os.IsNotExist(err) && *stateFile != "" {
				pwd, err := os.Getwd()
				if err != nil {
					fmt.Fprintf(os.Stderr, "Error getting current directory: %v\n", err)
					os.Exit(1)
				}
				state = &shell.State{
					Pwd:     pwd,
					Env:     make(map[string]string),
					Aliases: "",
				}
			} else {
				fmt.Fprintf(os.Stderr, "Error reading state file: %v\n", err)
				os.Exit(1)
			}
		}
		executor = shell.NewExecutorFromState(state)

		// Mark if we should write back to state file
		if *stateFile != "" {
			usingStateFile = true
			stateFilePath = *stateFile
		}
	} else {
		// Use individual flags (backward compatibility)
		if *workingDir == "" {
			pwd, err := os.Getwd()
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error getting current directory: %v\n", err)
				os.Exit(1)
			}
			*workingDir = pwd
		}

		executor = shell.NewExecutor(*workingDir)

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

		if *aliasFile != "" {
			data, err := os.ReadFile(*aliasFile)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error reading alias file: %v\n", err)
				os.Exit(1)
			}
			executor.Aliases = string(data)
		}
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

	// Save state back to file if using --state
	if usingStateFile {
		finalState := executor.GetState()
		if err := shell.SaveState(finalState, stateFilePath); err != nil {
			fmt.Fprintf(os.Stderr, "Error saving state: %v\n", err)
			// Don't exit here, still output results
		}
	}

	// Handle output based on flags
	if *outputJSON {
		// Output state as JSON to stdout
		finalState := executor.GetState()
		encoder := json.NewEncoder(os.Stdout)
		encoder.SetIndent("", "  ")
		if err := encoder.Encode(finalState); err != nil {
			fmt.Fprintf(os.Stderr, "Error encoding JSON: %v\n", err)
			os.Exit(1)
		}
		// Still output command stderr for visibility
		if result.Stderr != "" {
			fmt.Fprint(os.Stderr, result.Stderr)
		}
	} else {
		// Standard output mode - output command results normally
		if result.Stdout != "" {
			fmt.Fprint(os.Stdout, result.Stdout)
		}
		if result.Stderr != "" {
			fmt.Fprint(os.Stderr, result.Stderr)
		}
	}

	os.Exit(result.ExitCode)
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
