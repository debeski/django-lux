package main

import (
	"archive/zip"
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

var testSalt = []byte("0123456789abcdef")

// fernetToken mirrors cryptography.Fernet.encrypt with a fixed IV and timestamp.
func fernetToken(key, plain []byte) []byte {
	pad := aes.BlockSize - len(plain)%aes.BlockSize
	padded := append(append([]byte{}, plain...), bytes.Repeat([]byte{byte(pad)}, pad)...)
	iv := bytes.Repeat([]byte{7}, aes.BlockSize)
	block, _ := aes.NewCipher(key[16:])
	ct := make([]byte, len(padded))
	cipher.NewCBCEncrypter(block, iv).CryptBlocks(ct, padded)
	body := []byte{fernetVersion}
	body = binary.BigEndian.AppendUint64(body, 0)
	body = append(body, iv...)
	body = append(body, ct...)
	mac := hmac.New(sha256.New, key[:16])
	mac.Write(body)
	body = mac.Sum(body)
	out := make([]byte, base64.URLEncoding.EncodedLen(len(body)))
	base64.URLEncoding.Encode(out, body)
	return out
}

func dlbHeader(meta map[string]any) []byte {
	raw, _ := json.Marshal(meta)
	var b bytes.Buffer
	b.WriteString(dlbMagic)
	binary.Write(&b, binary.BigEndian, uint32(len(raw)))
	b.Write(raw)
	return b.Bytes()
}

func encryptionBlock(keySource string, iterations int) map[string]any {
	return map[string]any{
		"scheme": "fernet-chunked", "kdf": "pbkdf2-sha256", "salt": hex.EncodeToString(testSalt),
		"iterations": iterations, "key_source": keySource, "passphrase_required": keySource == "passphrase",
	}
}

// encryptedDLB frames payload into Fernet tokens of at most chunk plaintext bytes.
func encryptedDLB(password string, iterations, chunk int, payload []byte, meta map[string]any) []byte {
	header := map[string]any{"kind": "dlux-system-backup", "format": 1, "encryption": encryptionBlock("passphrase", iterations)}
	for k, v := range meta {
		header[k] = v
	}
	key := pbkdf2SHA256([]byte(password), testSalt, iterations, 32)
	out := dlbHeader(header)
	for len(payload) > 0 {
		n := min(chunk, len(payload))
		token := fernetToken(key, payload[:n])
		out = binary.BigEndian.AppendUint64(out, uint64(len(token)))
		out = append(out, token...)
		payload = payload[n:]
	}
	return out
}

func zipOf(t testing.TB, entries map[string]string) []byte {
	t.Helper()
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	names := make([]string, 0, len(entries))
	for n := range entries {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		w, err := zw.Create(n)
		if err != nil {
			t.Fatal(err)
		}
		w.Write([]byte(entries[n]))
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

func sampleZip(t testing.TB) []byte {
	return zipOf(t, map[string]string{
		"manifest.json":         `{"kind":"dlux-system-backup","models":[{"model":"sample.item","count":2}],"files":[]}`,
		"data/sample/item.json": `[{"model":"sample.item","pk":1,"fields":{"name":"one"}}, {"model":"sample.item","pk":2,"fields":{"name":"two"}}]`,
	})
}

func writeTemp(t testing.TB, dir, name string, data []byte) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

// tryUnlock opens p and unlocks it with password, returning the status code.
func tryUnlock(t testing.TB, p, password string) (int, string, *App) {
	t.Helper()
	app := &App{token: "t"}
	if err := app.openPath(p); err != nil {
		return -1, err.Error(), app
	}
	body, _ := json.Marshal(map[string]string{"password": password})
	rec := httptest.NewRecorder()
	app.handleUnlock(rec, httptest.NewRequest(http.MethodPost, "/api/unlock", strings.NewReader(string(body))))
	return rec.Code, rec.Body.String(), app
}

// privateTemp points os.CreateTemp at a fresh directory and returns a check
// that fails the test if anything was left behind in it.
func privateTemp(t *testing.T) func() {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("TMPDIR", dir)
	return func() {
		t.Helper()
		if left, _ := os.ReadDir(dir); len(left) != 0 {
			t.Fatalf("temp files left behind: %v", left)
		}
	}
}
