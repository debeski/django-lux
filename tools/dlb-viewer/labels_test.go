package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRawScalarString(t *testing.T) {
	cases := map[string]string{
		`"alice"`: "alice",
		`5`:       "5",
		`true`:    "true",
		`null`:    "",
		`{"a":1}`: `{"a":1}`,
	}
	for in, want := range cases {
		if got := rawScalarString(json.RawMessage(in)); got != want {
			t.Errorf("rawScalarString(%s) = %q, want %q", in, got, want)
		}
	}
}

func TestNaturalKeyOf(t *testing.T) {
	fields := map[string]json.RawMessage{
		"username": json.RawMessage(`"alice"`),
		"name":     json.RawMessage(`"Alice"`),
	}
	// Matches how an FK to a model with natural_key()==(username,) serializes.
	if got := naturalKeyOf(fields, []string{"username"}); got != `["alice"]` {
		t.Errorf("naturalKeyOf single = %q, want %q", got, `["alice"]`)
	}
	if got := naturalKeyOf(fields, []string{"missing"}); got != "" {
		t.Errorf("naturalKeyOf missing field = %q, want empty", got)
	}
}

func TestStreamLabels(t *testing.T) {
	data := `[
		{"model":"auth.user","pk":1,"fields":{"username":"alice","first_name":"Alice"}},
		{"model":"auth.user","pk":2,"fields":{"username":"bob","first_name":"Bob"}}
	]`
	ms := ModelSchema{LabelField: "first_name", NaturalKeyFields: []string{"username"}}
	byPK, byNK := map[string]string{}, map[string]string{}
	if err := streamLabels(strings.NewReader(data), ms, byPK, byNK); err != nil {
		t.Fatalf("streamLabels: %v", err)
	}
	if byPK["1"] != "Alice" || byPK["2"] != "Bob" {
		t.Errorf("by_pk = %v, want Alice/Bob", byPK)
	}
	// A natural-key FK reference ["alice"] must resolve to the same label.
	if byNK[`["alice"]`] != "Alice" {
		t.Errorf("by_nk[\"alice\"] = %q, want Alice", byNK[`["alice"]`])
	}
}

// With no label field, resolving must fall back to the natural key (readable),
// never the PK — otherwise resolving a column makes it less readable.
func TestStreamLabelsFallsBackToNaturalKeyNotPK(t *testing.T) {
	data := `[{"model":"auth.user","pk":1,"fields":{"username":"alice"}}]`
	ms := ModelSchema{LabelField: "", NaturalKeyFields: []string{"username"}}
	byPK, byNK := map[string]string{}, map[string]string{}
	if err := streamLabels(strings.NewReader(data), ms, byPK, byNK); err != nil {
		t.Fatal(err)
	}
	if byPK["1"] != "alice" {
		t.Errorf("by_pk[1] = %q, want alice (natural key), not the PK", byPK["1"])
	}
}

// appWithBackup builds an App backed by an in-memory backup zip carrying a
// relation schema, exercising the real manifest-parse + handler path.
func appWithBackup(t *testing.T) *App {
	t.Helper()
	const manifest = `{
		"models":[{"model":"auth.user","count":2}],
		"schema":{
			"auth.user":{"label_field":"first_name","natural_key_fields":["username"],"relations":{}},
			"shop.order":{"label_field":"","relations":{"owner":{"kind":"fk","to":"auth.user"}}}
		}
	}`
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for name, body := range map[string]string{
		"manifest.json": manifest,
		"data/auth/user.json": `[
			{"model":"auth.user","pk":1,"fields":{"username":"alice","first_name":"Alice"}},
			{"model":"auth.user","pk":2,"fields":{"username":"bob","first_name":"Bob"}}
		]`,
	} {
		w, err := zw.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := w.Write([]byte(body)); err != nil {
			t.Fatal(err)
		}
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	zr, err := zip.NewReader(bytes.NewReader(buf.Bytes()), int64(buf.Len()))
	if err != nil {
		t.Fatal(err)
	}
	var mani Manifest
	if err := json.Unmarshal([]byte(manifest), &mani); err != nil {
		t.Fatal(err)
	}
	return &App{token: "t", zipReader: zr, manifest: &mani}
}

func TestHandleLabelsResolvesPKAndNaturalKey(t *testing.T) {
	a := appWithBackup(t)
	req := httptest.NewRequest(http.MethodGet, "/api/labels?key=auth.user", nil)
	rec := httptest.NewRecorder()
	a.handleLabels(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var out struct {
		LabelField string            `json:"label_field"`
		ByPK       map[string]string `json:"by_pk"`
		ByNK       map[string]string `json:"by_nk"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	if out.LabelField != "first_name" {
		t.Errorf("label_field = %q, want first_name", out.LabelField)
	}
	if out.ByPK["1"] != "Alice" || out.ByPK["2"] != "Bob" {
		t.Errorf("by_pk = %v", out.ByPK)
	}
	if out.ByNK[`["alice"]`] != "Alice" {
		t.Errorf("by_nk = %v", out.ByNK)
	}
}

// A backup with no schema (older .dlb) must not error — the endpoint returns
// empty maps and the UI falls back to raw references.
func TestHandleLabelsNoSchemaFallsBack(t *testing.T) {
	a := appWithBackup(t)
	a.manifest.Schema = nil
	req := httptest.NewRequest(http.MethodGet, "/api/labels?key=auth.user", nil)
	rec := httptest.NewRecorder()
	a.handleLabels(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	var out struct {
		ByPK map[string]string `json:"by_pk"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	if len(out.ByPK) != 0 {
		t.Errorf("expected empty by_pk without schema, got %v", out.ByPK)
	}
}
