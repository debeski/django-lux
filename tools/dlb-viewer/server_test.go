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

// Decrypted responses must not land in the browser's disk cache, sniffed
// content must not run, and the page must not be framed or leak its token
// through a referrer.
func TestResponsesCarrySecurityHeaders(t *testing.T) {
	paths := writeChain(t, t.TempDir())
	app := openUnlocked(t, paths[0], false)
	app.token = "tok"
	routes := app.routes()
	for _, target := range []string{
		"/?token=tok", "/static/app.js", "/api/state?token=tok", "/api/model?token=tok&key=auth.user",
		"/api/file?token=tok&path=files/auth/user/1/pic/a1.png", "/api/state", "/nope",
	} {
		rec := httptest.NewRecorder()
		routes.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "http://127.0.0.1:9"+target, nil))
		h := rec.Header()
		if h.Get("X-Content-Type-Options") != "nosniff" || h.Get("Cache-Control") != "no-store" ||
			h.Get("Referrer-Policy") != "no-referrer" {
			t.Fatalf("%s (%d): %v", target, rec.Code, h)
		}
	}
	rec := httptest.NewRecorder()
	routes.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "http://127.0.0.1:9/?token=tok", nil))
	if rec.Header().Get("X-Frame-Options") != "DENY" {
		t.Fatal("the page can be framed")
	}
	csp := rec.Header().Get("Content-Security-Policy")
	for _, want := range []string{"default-src 'none'", "script-src 'self'", "frame-ancestors 'none'"} {
		if !strings.Contains(csp, want) {
			t.Fatalf("page CSP %q lacks %q", csp, want)
		}
	}
}
