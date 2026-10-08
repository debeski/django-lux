package main

import (
	"archive/zip"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

// member writes an unencrypted .dlb whose inner ZIP holds the given entries.
func member(t *testing.T, dir, name string, chain ChainInfo, entries map[string]string) string {
	t.Helper()
	var inner bytes.Buffer
	zw := zip.NewWriter(&inner)
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
	zw.Close()
	header, _ := json.Marshal(map[string]any{
		"kind":       "dlux-system-backup",
		"format":     1,
		"chain":      chain,
		"encryption": map[string]string{"scheme": "none", "key_source": "none"},
	})
	var dlb bytes.Buffer
	dlb.WriteString(dlbMagic)
	binary.Write(&dlb, binary.BigEndian, uint32(len(header)))
	dlb.Write(header)
	dlb.Write(inner.Bytes())
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, dlb.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func manifestJSON(models string, files string) string {
	return `{"kind":"dlux-system-backup","models":[` + models + `],"files":[` + files + `],"missing_files":[]}`
}

// writeChain builds base -> inc1 -> inc2 in dir and returns the three paths.
//
//	base: users 1 alice, 2 bob; alice has a1.png
//	inc1: alice renamed, 3 carol added, alice's picture now a2.png
//	inc2: bob (2) deleted, 4 dave added
func writeChain(t *testing.T, dir string) []string {
	base := member(t, dir, "base.dlb", ChainInfo{ID: "c", Sequence: 0, Root: "r0", Kind: "full"}, map[string]string{
		"manifest.json": manifestJSON(`{"model":"auth.user","count":2}`,
			`{"model":"auth.user","pk":1,"field":"pic","path":"files/auth/user/1/pic/a1.png","name":"a1.png"}`),
		"data/auth/user.json":          `[{"model":"auth.user","pk":1,"fields":{"username":"alice"}}, {"model":"auth.user","pk":2,"fields":{"username":"bob"}}]`,
		"files/auth/user/1/pic/a1.png": "one",
	})
	inc1 := member(t, dir, "inc1.dlb", ChainInfo{ID: "c", Sequence: 1, Root: "r1", ParentRoot: "r0", Kind: "incremental"}, map[string]string{
		"manifest.json": manifestJSON(`{"model":"auth.user","count":2}`,
			`{"model":"auth.user","pk":1,"field":"pic","path":"files/auth/user/1/pic/a2.png","name":"a2.png"}`),
		"data/auth/user.json":          `[{"model":"auth.user","pk":1,"fields":{"username":"alice-renamed"}}, {"model":"auth.user","pk":3,"fields":{"username":"carol"}}]`,
		"files/auth/user/1/pic/a2.png": "two",
	})
	inc2 := member(t, dir, "inc2.dlb", ChainInfo{ID: "c", Sequence: 2, Root: "r2", ParentRoot: "r1", Kind: "incremental"}, map[string]string{
		"manifest.json":          manifestJSON(`{"model":"auth.user","count":1}`, ``),
		"data/auth/user.json":    `[{"model":"auth.user","pk":4,"fields":{"username":"dave"}}]`,
		"deleted/auth/user.json": `["2"]`,
	})
	return []string{base, inc1, inc2}
}

func openUnlocked(t *testing.T, p string, isTemp bool) *App {
	t.Helper()
	app := &App{token: "t"}
	if err := app.adoptSource(p, isTemp, p); err != nil {
		t.Fatal(err)
	}
	rec := httptest.NewRecorder()
	app.handleUnlock(rec, httptest.NewRequest(http.MethodPost, "/api/unlock", strings.NewReader(`{}`)))
	if rec.Code != http.StatusOK {
		t.Fatalf("unlock %s: %d %s", p, rec.Code, rec.Body.String())
	}
	t.Cleanup(app.reset)
	return app
}

func usernames(t *testing.T, app *App) []string {
	t.Helper()
	rec := httptest.NewRecorder()
	app.handleModel(rec, httptest.NewRequest(http.MethodGet, "/api/model?key=auth.user&limit=100", nil))
	var out struct {
		Records []struct {
			Fields map[string]string `json:"fields"`
		} `json:"records"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatal(err)
	}
	names := []string{}
	for _, r := range out.Records {
		names = append(names, r.Fields["username"])
	}
	return names
}

func TestIncrementMergesWithSiblingMembers(t *testing.T) {
	paths := writeChain(t, t.TempDir())
	app := openUnlocked(t, paths[2], false)
	if app.chainMode != chainModeChain || len(app.members) != 3 {
		t.Fatalf("mode %q with %d members", app.chainMode, len(app.members))
	}
	if got := strings.Join(usernames(t, app), ","); got != "alice-renamed,carol,dave" {
		t.Fatalf("merged users = %s", got)
	}
	if len(app.manifest.Files) != 1 || app.manifest.Files[0].Name != "a2.png" {
		t.Fatalf("merged files = %+v", app.manifest.Files)
	}
	f, err := app.zipReader.Open("files/auth/user/1/pic/a2.png")
	if err != nil {
		t.Fatal("newest picture not copied into the merged archive")
	}
	f.Close()
	if app.modelCountLocked("auth.user") != 3 {
		t.Fatalf("merged count = %d", app.modelCountLocked("auth.user"))
	}
}

func TestMiddleMemberShowsItsOwnPointInTime(t *testing.T) {
	paths := writeChain(t, t.TempDir())
	app := openUnlocked(t, paths[1], false)
	if got := strings.Join(usernames(t, app), ","); got != "alice-renamed,bob,carol" {
		t.Fatalf("users at increment 1 = %s", got)
	}
}

func TestChainZipOpensTheNewestMember(t *testing.T) {
	dir := t.TempDir()
	paths := writeChain(t, dir)
	bundle := filepath.Join(t.TempDir(), "chain.zip")
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for _, p := range paths {
		w, _ := zw.Create(filepath.Base(p))
		data, _ := os.ReadFile(p)
		w.Write(data)
	}
	zw.Close()
	os.WriteFile(bundle, buf.Bytes(), 0o600)
	app := openUnlocked(t, bundle, true)
	if got := strings.Join(usernames(t, app), ","); got != "alice-renamed,carol,dave" {
		t.Fatalf("chain zip users = %s", got)
	}
}

func TestLoneIncrementShowsChangesAndDeletions(t *testing.T) {
	paths := writeChain(t, t.TempDir())
	lone := filepath.Join(t.TempDir(), "inc2.dlb")
	data, _ := os.ReadFile(paths[2])
	os.WriteFile(lone, data, 0o600)
	app := openUnlocked(t, lone, false)
	if app.chainMode != chainModeDelta || app.chainNote == "" {
		t.Fatalf("mode %q note %q", app.chainMode, app.chainNote)
	}
	if got := strings.Join(usernames(t, app), ","); got != "dave" {
		t.Fatalf("delta users = %s", got)
	}
	rec := httptest.NewRecorder()
	app.handleDeleted(rec, httptest.NewRequest(http.MethodGet, "/api/deleted?key=auth.user", nil))
	if !strings.Contains(rec.Body.String(), `"deleted":["2"]`) {
		t.Fatalf("deleted = %s", rec.Body.String())
	}
}

func TestForeignMemberIsNotMerged(t *testing.T) {
	dir := t.TempDir()
	paths := writeChain(t, dir)
	// Replace inc1 with a member of the right sequence but the wrong root.
	member(t, dir, "inc1.dlb", ChainInfo{ID: "c", Sequence: 1, Root: "other", ParentRoot: "r0"}, map[string]string{
		"manifest.json": manifestJSON(``, ``),
	})
	app := &App{token: "t"}
	if err := app.adoptSource(paths[2], false, paths[2]); err != nil {
		t.Fatal(err)
	}
	if app.chainMode != chainModeDelta || !strings.Contains(app.chainNote, "does not belong") {
		t.Fatalf("mode %q note %q", app.chainMode, app.chainNote)
	}
}
