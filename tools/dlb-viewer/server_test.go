package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The page embeds the API token, so serving it without the token would hand the
// token (and the decrypted backup behind it) to any local process, and its Host
// check keeps a DNS-rebound page from reading it.
func TestIndexDoesNotHandOutTheToken(t *testing.T) {
	app := &App{token: "secret-token"}
	for _, target := range []string{
		"http://127.0.0.1/", "http://localhost:1234/", "http://127.0.0.1:1234/?token=wrong",
		"http://evil.example:1234/?token=secret-token",
	} {
		rec := httptest.NewRecorder()
		app.handleIndex(rec, httptest.NewRequest(http.MethodGet, target, nil))
		if rec.Code != http.StatusForbidden || strings.Contains(rec.Body.String(), "secret-token") {
			t.Fatalf("%s: %d served the API token", target, rec.Code)
		}
	}
	rec := httptest.NewRecorder()
	app.handleIndex(rec, httptest.NewRequest(http.MethodGet, "http://127.0.0.1:1234/?token=secret-token", nil))
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), `content="secret-token"`) {
		t.Fatalf("token URL refused: %d", rec.Code)
	}
}
