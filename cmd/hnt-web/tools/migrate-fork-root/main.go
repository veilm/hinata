package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"github.com/veilm/hinata/cmd/hnt-chat/pkg/chat"
)

func main() {
	dryRun := flag.Bool("dry-run", false, "Only report planned changes without writing")
	flag.Parse()

	baseDir, err := chat.GetConversationsDir()
	if err != nil {
		log.Fatalf("failed to get conversations directory: %v", err)
	}

	entries, err := os.ReadDir(baseDir)
	if err != nil {
		log.Fatalf("failed to read conversations directory: %v", err)
	}

	var converted, cleaned, skipped int

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		convID := entry.Name()
		metaDir := filepath.Join(baseDir, convID, "meta")
		forkSourcePath := filepath.Join(metaDir, "fork_source.txt")
		forkRootPath := filepath.Join(metaDir, "fork_root.txt")

		if _, err := os.Stat(forkSourcePath); os.IsNotExist(err) {
			continue
		}

		data, err := os.ReadFile(forkSourcePath)
		if err != nil {
			log.Printf("[%s] warning: cannot read fork_source.txt: %v", convID, err)
			skipped++
			continue
		}

		if *dryRun {
			if _, err := os.Stat(forkRootPath); err == nil {
				log.Printf("[%s] would remove legacy fork_source.txt (fork_root already exists)", convID)
			} else {
				log.Printf("[%s] would create fork_root.txt and remove fork_source.txt", convID)
			}
			converted++
			continue
		}

		if err := os.MkdirAll(metaDir, 0755); err != nil {
			log.Printf("[%s] warning: cannot ensure meta directory: %v", convID, err)
			skipped++
			continue
		}

		if _, err := os.Stat(forkRootPath); err == nil {
			if err := os.Remove(forkSourcePath); err != nil && !os.IsNotExist(err) {
				log.Printf("[%s] warning: failed to remove redundant fork_source.txt: %v", convID, err)
				skipped++
				continue
			}
			cleaned++
			continue
		}

		if err := os.WriteFile(forkRootPath, data, 0644); err != nil {
			log.Printf("[%s] warning: cannot write fork_root.txt: %v", convID, err)
			skipped++
			continue
		}

		if err := os.Remove(forkSourcePath); err != nil {
			log.Printf("[%s] warning: wrote fork_root but failed to remove fork_source: %v", convID, err)
			skipped++
			continue
		}

		converted++
		log.Printf("[%s] converted fork_source.txt -> fork_root.txt", convID)
	}

	fmt.Printf("conversion complete: %d converted, %d cleaned, %d skipped\n", converted, cleaned, skipped)
}
