package main

import (
	"fmt"
	"io"
	"os"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/hnt-apply/pkg/apply"
)

var (
	disallowCreating bool
	ignoreReasoning  bool
	verbose          bool
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "hnt-apply [source files...]",
		Short: "A utility to apply file modifications based on structured blocks from stdin",
		Args:  cobra.MinimumNArgs(1),
		RunE:  run,
	}

	rootCmd.Flags().BoolVar(&disallowCreating, "disallow-creating", false, "Disallow creating new files")
	rootCmd.Flags().BoolVar(&ignoreReasoning, "ignore-reasoning", false, "Skip a leading <think>...</think> block in the input stream")
	rootCmd.Flags().BoolVar(&verbose, "verbose", false, "Verbose logging output")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	input, err := io.ReadAll(os.Stdin)
	if err != nil {
		return fmt.Errorf("failed to read from stdin: %w", err)
	}

	return apply.ApplyChanges(args, disallowCreating, ignoreReasoning, verbose, string(input))
}
