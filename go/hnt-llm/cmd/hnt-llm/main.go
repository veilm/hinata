package main

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"

	"github.com/spf13/cobra"
	"github.com/veilm/hinata/hnt-llm/pkg/keymanagement"
	"github.com/veilm/hinata/hnt-llm/pkg/llm"
)

type OutputPhase int

const (
	PhaseInit OutputPhase = iota
	PhaseThinking
	PhaseResponding
)

var (
	systemPrompt     string
	model            string
	includeReasoning bool
	debugUnsafe      bool
)

func doGenerate(cmd *cobra.Command, args []string) error {
	if model == "" {
		model = os.Getenv("HINATA_LLM_MODEL")
		if model == "" {
			model = os.Getenv("HINATA_MODEL")
			if model == "" {
				model = "openrouter/google/gemini-2.5-flash"
			}
		}
	}

	stdinContent, err := io.ReadAll(os.Stdin)
	if err != nil {
		return err
	}

	config := llm.Config{
		Model:            model,
		SystemPrompt:     systemPrompt,
		IncludeReasoning: includeReasoning,
	}

	ctx := context.Background()
	eventChan, errChan := llm.StreamLLMResponse(ctx, config, string(stdinContent))

	phase := PhaseInit
	thinkTagPrinted := false

	for {
		select {
		case event, ok := <-eventChan:
			if !ok {
				if thinkTagPrinted {
					fmt.Print("</think>\n")
				}
				return nil
			}

			if event.Content != "" {
				if phase == PhaseInit {
					phase = PhaseResponding
				}
				if phase == PhaseThinking {
					phase = PhaseResponding
					if thinkTagPrinted {
						fmt.Print("</think>\n")
						thinkTagPrinted = false
					}
				}
				fmt.Print(event.Content)
			}

			if event.Reasoning != "" && includeReasoning {
				if phase == PhaseInit {
					phase = PhaseThinking
					if !thinkTagPrinted {
						fmt.Print("<think>")
						thinkTagPrinted = true
					}
				}
				if phase == PhaseThinking {
					fmt.Print(event.Reasoning)
				}
			}

		case err := <-errChan:
			if err != nil {
				return err
			}
		}
	}
}

func main() {
	if debugUnsafe {
		log.SetOutput(os.Stderr)
		log.SetFlags(log.LstdFlags | log.Lshortfile)
	} else {
		log.SetOutput(io.Discard)
	}

	var rootCmd = &cobra.Command{
		Use:   "hnt-llm",
		Short: "A streamlined CLI for interacting with multiple LLM providers",
		RunE:  doGenerate,
	}

	rootCmd.PersistentFlags().StringVarP(&model, "model", "m", "", "The model to use for the LLM")
	rootCmd.PersistentFlags().BoolVar(&debugUnsafe, "debug-unsafe", false, "Enable unsafe debugging options")

	rootCmd.Flags().StringVarP(&systemPrompt, "system", "s", "", "The system prompt to use")
	rootCmd.Flags().BoolVar(&includeReasoning, "include-reasoning", false, "Include reasoning in the output")

	var genCmd = &cobra.Command{
		Use:   "gen",
		Short: "Generate text using a language model",
		RunE:  doGenerate,
	}
	genCmd.Flags().StringVarP(&systemPrompt, "system", "s", "", "The system prompt to use")
	genCmd.Flags().BoolVar(&includeReasoning, "include-reasoning", false, "Include reasoning in the output")

	var saveKeyCmd = &cobra.Command{
		Use:   "save-key [provider]",
		Short: "Save an API key for a service",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return keymanagement.HandleSaveKey(args[0])
		},
	}

	var listKeysCmd = &cobra.Command{
		Use:   "list-keys",
		Short: "List saved API keys",
		RunE: func(cmd *cobra.Command, args []string) error {
			return keymanagement.HandleListKeys()
		},
	}

	var deleteKeyCmd = &cobra.Command{
		Use:   "delete-key [provider]",
		Short: "Delete a saved API key",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return keymanagement.HandleDeleteKey(args[0])
		},
	}

	rootCmd.AddCommand(genCmd, saveKeyCmd, listKeysCmd, deleteKeyCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
