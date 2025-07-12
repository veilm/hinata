package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/llm-pack/pkg/pack"
)

var (
	noFences        bool
	printCommonPath bool
	sortPaths       bool
)

func main() {
	var rootCmd = &cobra.Command{
		Use:   "llm-pack [source files...]",
		Short: "A utility to pack source files for language models",
		Args:  cobra.MinimumNArgs(1),
		RunE:  run,
	}

	rootCmd.Flags().BoolVarP(&noFences, "no-fences", "n", false, "Disable printing the markdown code fences (```)")
	rootCmd.Flags().BoolVarP(&printCommonPath, "print-common-path", "p", false, "Print only the common ancestor directory of the source files and then exit")
	rootCmd.Flags().BoolVarP(&sortPaths, "sort", "s", false, "Sort the files alphabetically by their absolute paths before processing")

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(cmd *cobra.Command, args []string) error {
	// Get file infos
	fileInfos, commonPrefix, err := pack.GetFileInfos(args, sortPaths)
	if err != nil {
		return err
	}

	// If -p flag is present, print common path and exit
	if printCommonPath {
		fmt.Println(commonPrefix)
		return nil
	}

	// Print the packed output
	if !noFences {
		fmt.Println("```")
	}

	fmt.Println("<file_paths>")
	for _, info := range fileInfos {
		// Use forward slashes for cross-platform compatibility
		relPathStr := strings.ReplaceAll(info.RelativePath, "\\", "/")
		fmt.Println(relPathStr)
	}
	fmt.Println("</file_paths>")

	for _, info := range fileInfos {
		fmt.Println() // Blank line between file blocks

		// Use forward slashes for cross-platform compatibility
		relPathStr := strings.ReplaceAll(info.RelativePath, "\\", "/")
		fmt.Printf("<%s>\n", relPathStr)

		content, err := os.ReadFile(info.AbsolutePath)
		if err != nil {
			return fmt.Errorf("failed to read file content: %s: %w", info.AbsolutePath, err)
		}

		fmt.Print(string(content))
		if len(content) > 0 && content[len(content)-1] != '\n' {
			fmt.Println()
		}

		fmt.Printf("</%s>\n", relPathStr)
	}

	if !noFences {
		fmt.Println("```")
	}

	return nil
}
