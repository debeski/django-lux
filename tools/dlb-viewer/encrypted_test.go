package main

import (
	"crypto/sha256"
	"encoding/json"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"testing"
)

// Synthetic multi-frame fixture generated independently with Python hashlib,
// zipfile and cryptography.Fernet; the password is public test data.
func TestPythonEncryptedBackupWrongPasswordRetryAndIndexedBrowsing(t *testing.T) {
	const filename = "testdata/synthetic-encrypted.dlb"
	original, err := os.ReadFile(filename)
	if err != nil {
		t.Fatal(err)
	}
	app := &App{}
	defer app.reset()
	if err := app.openPath(filename); err != nil {
		t.Fatal(err)
	}
	response := httptest.NewRecorder()
	app.handleUnlock(response, httptest.NewRequest("POST", "/api/unlock", strings.NewReader(`{"password":"wrong"}`)))
	if response.Code != 401 || app.zipReader != nil {
		t.Fatal("wrong password exposed backup")
	}
	response = httptest.NewRecorder()
	app.handleUnlock(response, httptest.NewRequest("POST", "/api/unlock", strings.NewReader(`{"password":"synthetic-password"}`)))
	if response.Code != 200 {
		t.Fatal(response.Code, response.Body.String())
	}
	for _, offset := range []int{0, 1050, 1020} {
		response = httptest.NewRecorder()
		request := httptest.NewRequest("GET", "/api/model?key=sample.document&offset="+strconv.Itoa(offset), nil)
		app.handleModel(response, request)
		if response.Code != 200 {
			t.Fatal(response.Body.String())
		}
		var result struct {
			Records []struct {
				PK     int
				Fields struct{ Title string }
			}
		}
		if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		if len(result.Records) != 50 || result.Records[0].PK != offset || !strings.HasPrefix(result.Records[0].Fields.Title, "مستند") {
			t.Fatal("decrypted records changed")
		}
	}
	if len(app.modelIndexes) != 1 {
		t.Fatal("deep-page index not used")
	}
	after, err := os.ReadFile(filename)
	if err != nil {
		t.Fatal(err)
	}
	if sha256.Sum256(original) != sha256.Sum256(after) {
		t.Fatal("source backup was modified")
	}
}
