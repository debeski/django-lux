package main

import (
	"encoding/binary"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const testPassword = "hostile-test"

func validEncrypted(t *testing.T) ([]byte, int) {
	t.Helper()
	data := encryptedDLB(testPassword, 1, 64, sampleZip(t), nil)
	headerEnd := 8 + int(binary.BigEndian.Uint32(data[4:8]))
	return data, headerEnd
}

func TestTruncatedContainersNeverUnlock(t *testing.T) {
	check := privateTemp(t)
	data, headerEnd := validEncrypted(t)
	dir := t.TempDir()
	for n := 0; n < len(data); n++ {
		// Every header byte, then every frame boundary and a point inside each frame.
		if n > headerEnd && (n-headerEnd)%37 != 0 {
			continue
		}
		p := writeTemp(t, dir, "cut.dlb", data[:n])
		code, body, app := tryUnlock(t, p, testPassword)
		if code == http.StatusOK {
			t.Fatalf("truncated to %d of %d bytes unlocked: %s", n, len(data), body)
		}
		app.reset()
	}
	check()
}

func TestEncryptedGarbagePayloadFailsCleanly(t *testing.T) {
	check := privateTemp(t)
	data := encryptedDLB(testPassword, 1, 1000, []byte(strings.Repeat("not a zip ", 300)), nil)
	code, body, app := tryUnlock(t, writeTemp(t, t.TempDir(), "x.dlb", data), testPassword)
	app.reset()
	if code != http.StatusBadRequest || !strings.Contains(body, "not a valid archive") {
		t.Fatalf("garbage payload: %d %s", code, body)
	}
	check()
}

func TestWrongPassphraseOnRealFrames(t *testing.T) {
	data, _ := validEncrypted(t)
	code, _, app := tryUnlock(t, writeTemp(t, t.TempDir(), "x.dlb", data), "nope")
	defer app.reset()
	if code != http.StatusUnauthorized {
		t.Fatalf("wrong passphrase status %d", code)
	}
}

func TestZeroLengthAndTinyFiles(t *testing.T) {
	dir := t.TempDir()
	for _, data := range [][]byte{nil, []byte("D"), []byte("DLB1"), []byte("DLB1\x00\x00\x00\x00"), []byte("DLB1\xff\xff\xff\xff{}")} {
		app := &App{}
		if err := app.openPath(writeTemp(t, dir, "z.dlb", data)); err == nil {
			t.Fatalf("%q opened", data)
		}
	}
}

func adopt(t *testing.T, p string) *App {
	t.Helper()
	app := &App{token: "t"}
	if err := app.adoptSource(p, false, p); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(app.reset)
	return app
}

func TestChainWithMissingParentShowsChangesOnly(t *testing.T) {
	dir := t.TempDir()
	paths := writeChain(t, dir)
	if err := os.Rename(paths[1], filepath.Join(t.TempDir(), "inc1.dlb")); err != nil {
		t.Fatal(err)
	}
	app := adopt(t, paths[2])
	if app.chainMode != chainModeDelta || !strings.Contains(app.chainNote, "member 1 of the chain is missing") {
		t.Fatalf("mode %q note %q", app.chainMode, app.chainNote)
	}
}

func TestChainOrderIgnoresFileNamesAndForeignChains(t *testing.T) {
	dir := t.TempDir()
	paths := writeChain(t, dir)
	// Names that sort against the chain order, plus a full backup and an
	// increment of another chain that reuse its sequence numbers and roots.
	for i, name := range []string{"z.dlb", "m.dlb", "a.dlb"} {
		if err := os.Rename(paths[i], filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	}
	member(t, dir, "other-base.dlb", ChainInfo{ID: "d", Sequence: 0, Root: "r0"}, map[string]string{"manifest.json": manifestJSON(``, ``)})
	member(t, dir, "other-inc.dlb", ChainInfo{ID: "d", Sequence: 1, Root: "r1", ParentRoot: "r0"}, map[string]string{"manifest.json": manifestJSON(``, ``)})
	app := adopt(t, filepath.Join(dir, "a.dlb"))
	want := []string{"z.dlb", "m.dlb", "a.dlb"}
	if app.chainMode != chainModeChain || len(app.members) != 3 {
		t.Fatalf("mode %q members %v", app.chainMode, app.members)
	}
	for i, p := range app.members {
		if filepath.Base(p) != want[i] {
			t.Fatalf("members %v", app.members)
		}
	}
}

func TestSelfReferencingIncrementCannotLoop(t *testing.T) {
	dir := t.TempDir()
	// Claims to continue itself, and a second member claims the same root.
	p := member(t, dir, "loop.dlb", ChainInfo{ID: "c", Sequence: 1, Root: "r", ParentRoot: "r"}, map[string]string{"manifest.json": manifestJSON(``, ``)})
	member(t, dir, "twin.dlb", ChainInfo{ID: "c", Sequence: 1, Root: "r", ParentRoot: "r"}, map[string]string{"manifest.json": manifestJSON(``, ``)})
	member(t, dir, "deep.dlb", ChainInfo{ID: "c", Sequence: 1 << 40, Root: "x", ParentRoot: "r"}, map[string]string{"manifest.json": manifestJSON(``, ``)})
	for _, target := range []string{p, filepath.Join(dir, "deep.dlb")} {
		app := adopt(t, target)
		if app.chainMode != chainModeDelta || !strings.Contains(app.chainNote, "missing") {
			t.Fatalf("%s: mode %q note %q", target, app.chainMode, app.chainNote)
		}
	}
}

func TestDuplicateRecordsAcrossAChainMergeOnce(t *testing.T) {
	dir := t.TempDir()
	member(t, dir, "base.dlb", ChainInfo{ID: "c", Sequence: 0, Root: "r0"}, map[string]string{
		"manifest.json":       manifestJSON(`{"model":"auth.user","count":2}`, ``),
		"data/auth/user.json": `[{"pk":1,"fields":{"username":"a"}}, {"pk":1,"fields":{"username":"a-dup"}}]`,
	})
	inc := member(t, dir, "inc.dlb", ChainInfo{ID: "c", Sequence: 1, Root: "r1", ParentRoot: "r0"}, map[string]string{
		"manifest.json":          manifestJSON(`{"model":"auth.user","count":2}`, ``),
		"data/auth/user.json":    `[{"pk":2,"fields":{"username":"b"}}, {"pk":2,"fields":{"username":"b-dup"}}]`,
		"deleted/auth/user.json": `["2", "2", "404"]`,
	})
	app := openUnlocked(t, inc, false)
	if got := strings.Join(usernames(t, app), ","); got != "a-dup" {
		t.Fatalf("merged users = %s", got)
	}
}
