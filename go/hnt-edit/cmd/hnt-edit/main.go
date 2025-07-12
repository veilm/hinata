package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/hnt-edit/pkg/edit"
)

func main() {
	var opts edit.Options

	var rootCmd = &cobra.Command{
		Use:   "hnt-edit [source files...]",
		Short: "Edit files using hinata LLM agent",
		Long: `Edit files using hinata LLM agent.

Example: hnt-edit -m 'Refactor foo function' src/main.py src/utils.py`,
		RunE: func(cmd *cobra.Command, args []string) error {
			opts.SourceFiles = args
			return edit.Run(opts)
		},
	}

	rootCmd.Flags().StringVarP(&opts.System, "system", "s", "", "System message string or path to system message file")
	rootCmd.Flags().StringVarP(&opts.Message, "message", "m", "", "User instruction message. If not provided, $EDITOR will be opened")
	rootCmd.Flags().StringVar(&opts.Model, "model", "", "Model to use for LLM")
	rootCmd.Flags().StringVar(&opts.ContinueDir, "continue-dir", "", "Path to an existing hnt-chat conversation directory to continue from a failed edit")
	rootCmd.Flags().BoolVar(&opts.UseEditor, "use-editor", false, "Use an external editor ($EDITOR) for the user instruction message")
	rootCmd.Flags().BoolVar(&opts.IgnoreReasoning, "ignore-reasoning", false, "Do not ask the LLM for reasoning")
	rootCmd.Flags().BoolVarP(&opts.Verbose, "verbose", "v", false, "Enable verbose logging")
	rootCmd.Flags().BoolVar(&opts.DebugUnsafe, "debug-unsafe", false, "Enable unsafe debugging options")

	// Note: --use-pane is not implemented as requested

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
