package keymanagement

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"golang.org/x/term"
)

func getHinataDir(dirType string) (string, error) {
	var baseDir string

	switch dirType {
	case "config":
		baseDir = os.Getenv("XDG_CONFIG_HOME")
		if baseDir == "" {
			homeDir, err := os.UserHomeDir()
			if err != nil {
				return "", err
			}
			baseDir = filepath.Join(homeDir, ".config")
		}
	case "data":
		baseDir = os.Getenv("XDG_DATA_HOME")
		if baseDir == "" {
			homeDir, err := os.UserHomeDir()
			if err != nil {
				return "", err
			}
			baseDir = filepath.Join(homeDir, ".local", "share")
		}
	default:
		return "", fmt.Errorf("invalid directory type: %s", dirType)
	}

	hinataDir := filepath.Join(baseDir, "hinata")
	if err := os.MkdirAll(hinataDir, 0700); err != nil {
		return "", err
	}

	return hinataDir, nil
}

func ensureLocalKey(dataDir string) error {
	keyPath := filepath.Join(dataDir, ".local_key")
	if _, err := os.Stat(keyPath); os.IsNotExist(err) {
		key := make([]byte, 32)
		if _, err := rand.Read(key); err != nil {
			return err
		}
		if err := os.WriteFile(keyPath, key, 0600); err != nil {
			return err
		}
		setPermissions(keyPath)
	}
	return nil
}

func readLocalKey(dataDir string) ([]byte, error) {
	keyPath := filepath.Join(dataDir, ".local_key")
	return os.ReadFile(keyPath)
}

func xorCrypt(key []byte, data []byte) {
	for i := range data {
		data[i] ^= key[i%len(key)]
	}
}

func setPermissions(path string) error {
	return os.Chmod(path, 0600)
}

func SaveAPIKey(provider, apiKey string) error {
	configDir, err := getHinataDir("config")
	if err != nil {
		return err
	}

	dataDir, err := getHinataDir("data")
	if err != nil {
		return err
	}

	if err := ensureLocalKey(dataDir); err != nil {
		return err
	}

	keysPath := filepath.Join(configDir, "keys")

	var lines []string
	if content, err := os.ReadFile(keysPath); err == nil {
		lines = strings.Split(string(content), "\n")
	}

	keyPrefix := provider + "="
	var newLines []string
	for _, line := range lines {
		if line != "" && !strings.HasPrefix(line, keyPrefix) {
			newLines = append(newLines, line)
		}
	}

	localKey, err := readLocalKey(dataDir)
	if err != nil {
		return err
	}

	dataToEncrypt := []byte(apiKey)
	xorCrypt(localKey, dataToEncrypt)

	encodedKey := base64.StdEncoding.EncodeToString(dataToEncrypt)
	newLines = append(newLines, fmt.Sprintf("%s=%s", provider, encodedKey))

	content := strings.Join(newLines, "\n") + "\n"
	if err := os.WriteFile(keysPath, []byte(content), 0600); err != nil {
		return err
	}

	return setPermissions(keysPath)
}

func GetAPIKeyFromStore(provider string) (string, error) {
	configDir, err := getHinataDir("config")
	if err != nil {
		return "", err
	}

	keysPath := filepath.Join(configDir, "keys")
	content, err := os.ReadFile(keysPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}

	keyPrefix := provider + "="
	lines := strings.Split(string(content), "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, keyPrefix) {
			encodedKey := strings.TrimPrefix(line, keyPrefix)

			dataDir, err := getHinataDir("data")
			if err != nil {
				return "", err
			}

			localKey, err := readLocalKey(dataDir)
			if err != nil {
				return "", err
			}

			encryptedData, err := base64.StdEncoding.DecodeString(encodedKey)
			if err != nil {
				return "", err
			}

			xorCrypt(localKey, encryptedData)
			return string(encryptedData), nil
		}
	}

	return "", nil
}

func ListKeys() ([]string, error) {
	configDir, err := getHinataDir("config")
	if err != nil {
		return nil, err
	}

	keysPath := filepath.Join(configDir, "keys")
	content, err := os.ReadFile(keysPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var providers []string
	lines := strings.Split(string(content), "\n")
	for _, line := range lines {
		if line != "" && strings.Contains(line, "=") {
			provider := strings.Split(line, "=")[0]
			providers = append(providers, provider)
		}
	}

	return providers, nil
}

func DeleteKey(provider string) error {
	configDir, err := getHinataDir("config")
	if err != nil {
		return err
	}

	keysPath := filepath.Join(configDir, "keys")
	content, err := os.ReadFile(keysPath)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("key '%s' not found", provider)
		}
		return err
	}

	keyPrefix := provider + "="
	lines := strings.Split(string(content), "\n")
	var newLines []string
	found := false

	for _, line := range lines {
		if line != "" && !strings.HasPrefix(line, keyPrefix) {
			newLines = append(newLines, line)
		} else if strings.HasPrefix(line, keyPrefix) {
			found = true
		}
	}

	if !found {
		return fmt.Errorf("key '%s' not found", provider)
	}

	newContent := strings.Join(newLines, "\n") + "\n"
	if err := os.WriteFile(keysPath, []byte(newContent), 0600); err != nil {
		return err
	}

	return setPermissions(keysPath)
}

func HandleSaveKey(provider string) error {
	if provider == "" {
		return fmt.Errorf("provider is required")
	}

	fmt.Printf("Enter API key for '%s': ", provider)
	apiKey, err := term.ReadPassword(int(syscall.Stdin))
	fmt.Println()
	if err != nil {
		return err
	}

	if err := SaveAPIKey(provider, strings.TrimSpace(string(apiKey))); err != nil {
		return err
	}

	fmt.Printf("Saved key '%s'.\n", provider)
	return nil
}

func HandleListKeys() error {
	providers, err := ListKeys()
	if err != nil {
		return err
	}

	if len(providers) == 0 {
		fmt.Println("No keys saved.")
		return nil
	}

	fmt.Println("Saved API keys:")
	for _, provider := range providers {
		fmt.Printf("- %s\n", provider)
	}
	return nil
}

func HandleDeleteKey(provider string) error {
	if provider == "" {
		return fmt.Errorf("provider is required")
	}

	if err := DeleteKey(provider); err != nil {
		return err
	}

	fmt.Printf("Deleted key '%s'.\n", provider)
	return nil
}
