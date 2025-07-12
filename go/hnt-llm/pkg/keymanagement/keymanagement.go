package keymanagement

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"golang.org/x/term"
)

type KeyStore struct {
	Keys map[string]string `json:"keys"`
}

func getKeyStorePath() (string, error) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	dataDir := filepath.Join(homeDir, ".local", "share", "hinata")
	return filepath.Join(dataDir, "api_keys.json"), nil
}

func deriveKey(passphrase string) []byte {
	hash := sha256.Sum256([]byte(passphrase))
	return hash[:]
}

func encrypt(plaintext, passphrase string) (string, error) {
	key := deriveKey(passphrase)
	
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}

	ciphertext := gcm.Seal(nonce, nonce, []byte(plaintext), nil)
	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

func decrypt(ciphertext, passphrase string) (string, error) {
	key := deriveKey(passphrase)
	
	data, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}

	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonceSize := gcm.NonceSize()
	if len(data) < nonceSize {
		return "", fmt.Errorf("ciphertext too short")
	}

	nonce, ciphertextBytes := data[:nonceSize], data[nonceSize:]
	plaintext, err := gcm.Open(nil, nonce, ciphertextBytes, nil)
	if err != nil {
		return "", err
	}

	return string(plaintext), nil
}

func loadKeyStore() (*KeyStore, error) {
	storePath, err := getKeyStorePath()
	if err != nil {
		return nil, err
	}

	data, err := os.ReadFile(storePath)
	if err != nil {
		if os.IsNotExist(err) {
			return &KeyStore{Keys: make(map[string]string)}, nil
		}
		return nil, err
	}

	var store KeyStore
	if err := json.Unmarshal(data, &store); err != nil {
		return nil, err
	}

	if store.Keys == nil {
		store.Keys = make(map[string]string)
	}

	return &store, nil
}

func saveKeyStore(store *KeyStore) error {
	storePath, err := getKeyStorePath()
	if err != nil {
		return err
	}

	dir := filepath.Dir(storePath)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}

	data, err := json.MarshalIndent(store, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(storePath, data, 0600)
}

func SaveAPIKey(provider, apiKey string) error {
	fmt.Print("Enter encryption passphrase: ")
	passphrase, err := term.ReadPassword(int(syscall.Stdin))
	fmt.Println()
	if err != nil {
		return err
	}

	encryptedKey, err := encrypt(apiKey, string(passphrase))
	if err != nil {
		return err
	}

	store, err := loadKeyStore()
	if err != nil {
		return err
	}

	store.Keys[provider] = encryptedKey
	return saveKeyStore(store)
}

func GetAPIKeyFromStore(provider string) (string, error) {
	store, err := loadKeyStore()
	if err != nil {
		return "", err
	}

	encryptedKey, exists := store.Keys[provider]
	if !exists {
		return "", nil
	}

	fmt.Fprintf(os.Stderr, "Enter passphrase to decrypt %s API key: ", provider)
	passphrase, err := term.ReadPassword(int(syscall.Stdin))
	fmt.Fprintln(os.Stderr)
	if err != nil {
		return "", err
	}

	return decrypt(encryptedKey, string(passphrase))
}

func ListKeys() ([]string, error) {
	store, err := loadKeyStore()
	if err != nil {
		return nil, err
	}

	var providers []string
	for provider := range store.Keys {
		providers = append(providers, provider)
	}
	return providers, nil
}

func DeleteKey(provider string) error {
	store, err := loadKeyStore()
	if err != nil {
		return err
	}

	if _, exists := store.Keys[provider]; !exists {
		return fmt.Errorf("no key found for provider: %s", provider)
	}

	delete(store.Keys, provider)
	return saveKeyStore(store)
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

	fmt.Printf("API key for '%s' saved successfully.\n", provider)
	return nil
}

func HandleListKeys() error {
	providers, err := ListKeys()
	if err != nil {
		return err
	}

	if len(providers) == 0 {
		fmt.Println("No saved API keys found.")
		return nil
	}

	fmt.Println("Saved API keys for:")
	for _, provider := range providers {
		fmt.Printf("  - %s\n", provider)
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

	fmt.Printf("API key for '%s' deleted successfully.\n", provider)
	return nil
}