package main

import (
	"archive/zip"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// Run one target at a time, e.g.
//
//	go test -run '^$' -fuzz '^FuzzParseHeader$' -fuzztime 3m

func FuzzParseHeader(f *testing.F) {
	f.Add(encryptedDLB("pw", 1, 64, []byte("payload"), nil))
	f.Add(dlbHeader(map[string]any{"kind": "dlux-system-backup-increment", "chain": map[string]any{"sequence": 3}}))
	f.Add([]byte("DLB1\x00\x00\x00\x02{}"))
	f.Add([]byte("DLB1\xff\xff\xff\xff"))
	f.Fuzz(func(t *testing.T, data []byte) {
		meta, err := parseHeader(bytes.NewReader(data))
		if err != nil {
			return
		}
		if meta.Kind != "dlux-system-backup" && meta.Kind != "dlux-system-backup-increment" {
			t.Fatalf("accepted kind %q", meta.Kind)
		}
		_ = meta.Unencrypted()
		_ = meta.isIncrement()
		_ = seqOf(meta)
	})
}

func FuzzDecrypt(f *testing.F) {
	payload := []byte(strings.Repeat("inner zip bytes ", 20))
	f.Add(encryptedDLB("pw", 1, 64, payload, nil), "pw")
	f.Add(encryptedDLB("pw", 2, 1000, payload, nil), "wrong")
	f.Add(encryptedDLB(" pw ", 1, 7, payload, nil), "pw")
	legacy := dlbHeader(map[string]any{"kind": "dlux-system-backup", "encryption": map[string]any{"kdf": "sha256-salt-seed", "salt": "00ff"}})
	f.Add(binary.BigEndian.AppendUint64(legacy, 120), "")
	f.Fuzz(func(t *testing.T, data []byte, password string) {
		r := bytes.NewReader(data)
		meta, err := parseHeader(r)
		if err != nil || meta.Unencrypted() {
			return
		}
		// The format default (390,000) is far too slow per fuzz input.
		if meta.Encryption.KDF != "sha256-salt-seed" && (meta.Encryption.Iterations <= 0 || meta.Encryption.Iterations > 64) {
			return
		}
		key, err := deriveKey(meta.Encryption, password)
		if err != nil {
			return
		}
		var out bytes.Buffer
		remaining := r.Len()
		if err := decryptToFile(r, key, &out); err == nil && out.Len() > remaining {
			t.Fatalf("decrypted %d bytes from %d bytes of frames", out.Len(), remaining)
		}
	})
}

func FuzzRecords(f *testing.F) {
	f.Add([]byte(`[{"model":"a.b","pk":1,"fields":{"name":"x","code":"c"}}, {"pk":"k","fields":{"name":null}}]`), uint16(0), uint16(10))
	f.Add([]byte(`[{"pk":9007199254740993,"fields":{"code":["n",1]}},{"pk":[1,2]},null,1,"s"]`), uint16(1), uint16(2))
	f.Add([]byte(`[{"pk":1,"fields":{"name":"a&b<c>","code":" "}}]`), uint16(0), uint16(1))
	f.Add([]byte(`{"not":"an array"}`), uint16(0), uint16(1))
	f.Fuzz(func(t *testing.T, data []byte, offset, limit uint16) {
		lim := 1 + int(limit)%1000
		window, werr := readRecordWindow(bytes.NewReader(data), int(offset), lim)
		if werr == nil && len(window) > lim {
			t.Fatalf("window of %d holds %d records", lim, len(window))
		}
		count := 0
		eerr := eachRecord(bytes.NewReader(data), func(pk string, raw json.RawMessage) {
			if !json.Valid(raw) {
				t.Fatalf("invalid record %q", raw)
			}
			count++
		})
		if eerr == nil && werr == nil && int(offset) < count && len(window) != min(lim, count-int(offset)) {
			t.Fatalf("window %d+%d of %d records holds %d", offset, lim, count, len(window))
		}
		byPK, byNK := map[string]string{}, map[string]string{}
		_ = streamLabels(bytes.NewReader(data), ModelSchema{LabelField: "name", NaturalKeyFields: []string{"code"}}, byPK, byNK)
		for nk := range byNK {
			if !json.Valid([]byte(nk)) {
				t.Fatalf("natural key %q is not JSON", nk)
			}
		}
	})
}

func FuzzModelIndex(f *testing.F) {
	f.Add([]byte(`[ {"pk":1,"fields":{"t":"مرحبا","n":[1,{"x":"[,]"}]}}, {"pk":"id"}, {"pk":null}, 3, "s", [] ]`), uint16(1), uint16(3))
	f.Add([]byte(`[]`), uint16(0), uint16(1))
	f.Add([]byte(`[1] trailing`), uint16(0), uint16(1))
	f.Fuzz(func(t *testing.T, data []byte, offset, limit uint16) {
		index, err := buildModelIndex(bytes.NewReader(data), 1<<20, 10000)
		if err != nil {
			if index != nil {
				t.Fatal("failed build returned an index")
			}
			return
		}
		defer index.close()
		lim := 1 + int(limit)%1000
		got, err := index.window(int(offset), lim)
		if err != nil {
			t.Fatal(err)
		}
		want, err := readRecordWindow(bytes.NewReader(data), int(offset), lim)
		if err != nil {
			t.Fatalf("index accepted what streaming rejects: %v", err)
		}
		if len(got) != len(want) || (len(got) > 0 && !reflect.DeepEqual(got, want)) {
			t.Fatalf("offset=%d limit=%d: index %q, stream %q", offset, lim, got, want)
		}
	})
}

func writeZipFile(t *testing.T, p string, entries map[string]string) {
	t.Helper()
	if err := os.WriteFile(p, zipOf(t, entries), 0o600); err != nil {
		t.Fatal(err)
	}
}

func FuzzChainMerge(f *testing.F) {
	f.Add(`[{"pk":1,"fields":{"u":"alice"}}, {"pk":2,"fields":{"u":"bob"}}]`, `[{"pk":1,"fields":{"u":"alice2"}}, {"pk":3}]`, `["2"]`,
		`{"model":"auth.user","pk":1,"field":"pic","path":"files/a.png","name":"a.png"}`)
	f.Add(`[{"pk":9007199254740993},{"pk":9007199254740992}]`, `[{"pk":"9007199254740993"}]`, `["9007199254740992"]`, ``)
	f.Add(`[]`, `[{"pk":2},{"pk":2}]`, `[1]`, `{"model":"auth.user","pk":2,"field":"pic","path":"files/b.png"}`)
	f.Fuzz(func(t *testing.T, baseData, incData, deleted, fileEntry string) {
		dir := t.TempDir()
		models := `[{"model":"auth.user","count":1},{"model":"nodot","count":0}]`
		files := `[` + fileEntry + `]`
		if !json.Valid([]byte(files)) {
			files = `[]`
		}
		base := filepath.Join(dir, "base.zip")
		inc := filepath.Join(dir, "inc.zip")
		writeZipFile(t, base, map[string]string{
			"manifest.json":       `{"models":` + models + `,"files":` + files + `,"missing_files":` + files + `}`,
			"data/auth/user.json": baseData, "files/a.png": "A", "files/b.png": "B",
		})
		writeZipFile(t, inc, map[string]string{
			"manifest.json":          `{"models":` + models + `,"files":[],"missing_files":[]}`,
			"data/auth/user.json":    incData,
			"deleted/auth/user.json": deleted,
		})
		var out bytes.Buffer
		if err := mergeChain([]string{base, inc}, &out); err != nil {
			return
		}
		zr, err := zip.NewReader(bytes.NewReader(out.Bytes()), int64(out.Len()))
		if err != nil {
			t.Fatalf("merged archive unreadable: %v", err)
		}
		raw, err := readZipMember(zr, "manifest.json")
		if err != nil {
			t.Fatal(err)
		}
		var mani Manifest
		if err := json.Unmarshal(raw, &mani); err != nil {
			t.Fatalf("merged manifest: %v", err)
		}
		for _, m := range mani.Models {
			parts := strings.SplitN(m.Model, ".", 2)
			if len(parts) != 2 {
				continue
			}
			rc, err := zr.Open(fmt.Sprintf("data/%s/%s.json", parts[0], parts[1]))
			if err != nil {
				t.Fatalf("%s listed without data", m.Model)
			}
			seen := map[string]bool{}
			n := 0
			if err := eachRecord(rc, func(pk string, _ json.RawMessage) {
				if seen[pk] {
					t.Fatalf("pk %q merged twice", pk)
				}
				seen[pk] = true
				n++
			}); err != nil {
				t.Fatalf("merged data unreadable: %v", err)
			}
			rc.Close()
			if n != m.Count {
				t.Fatalf("%s: count %d, records %d", m.Model, m.Count, n)
			}
		}
	})
}

// FuzzChainOrder builds candidate members from 4-byte groups
// (sequence, root, parent root, chain id) and orders them behind the first.
func FuzzChainOrder(f *testing.F) {
	f.Add([]byte{2, 2, 1, 0, 0, 0, 9, 0, 1, 1, 0, 0})
	f.Add([]byte{1, 1, 1, 0, 1, 1, 1, 0})
	f.Add([]byte{200, 5, 4, 0, 199, 4, 3, 0})
	f.Fuzz(func(t *testing.T, data []byte) {
		var members []chainMember
		for i := 0; i+4 <= len(data) && len(members) < 64; i += 4 {
			members = append(members, chainMember{
				path: fmt.Sprintf("m%d.dlb", i/4),
				meta: &Metadata{Chain: &ChainInfo{ID: fmt.Sprint(data[i+3] % 2), Sequence: int(data[i]),
					Root: fmt.Sprint(data[i+1]), ParentRoot: fmt.Sprint(data[i+2])}},
			})
		}
		if len(members) == 0 || !members[0].meta.isIncrement() {
			return
		}
		paths, err := orderChain(members[0], members[1:])
		if err != nil {
			return
		}
		byPath := map[string]*Metadata{}
		for _, m := range members {
			byPath[m.path] = m.meta
		}
		if len(paths) != members[0].meta.Chain.Sequence+1 || paths[len(paths)-1] != members[0].path {
			t.Fatalf("chain %v for sequence %d", paths, members[0].meta.Chain.Sequence)
		}
		for i, p := range paths {
			c := byPath[p].Chain
			if c.Sequence != i || c.ID != members[0].meta.Chain.ID {
				t.Fatalf("member %d is %+v", i, c)
			}
			if i > 0 && byPath[paths[i-1]].Chain.Root != c.ParentRoot {
				t.Fatalf("member %d does not continue member %d", i, i-1)
			}
		}
	})
}

// FuzzOpen feeds a whole source file (.dlb or chain ZIP) through open, unlock
// and every read endpoint, then checks no decrypted temp file survives reset.
func FuzzOpen(f *testing.F) {
	plain := map[string]any{"scheme": "none", "key_source": "none"}
	inner := zipOf(f, map[string]string{
		"manifest.json": `{"models":[{"model":"sample.item","count":2},{"model":"x","count":1}],"files":[{"model":"sample.item","pk":1,"field":"f","path":"files/a.txt","name":"a.txt"}],` +
			`"schema":{"sample.item":{"label_field":"name","natural_key_fields":["name"],"relations":{"o":{"kind":"fk","to":"sample.item"}}}}}`,
		"data/sample/item.json":    `[{"pk":1,"fields":{"name":"one","o":2}}, {"pk":2,"fields":{"name":"two"}}]`,
		"files/a.txt":              "hello",
		"deleted/sample/item.json": `["3"]`,
	})
	f.Add(append(dlbHeader(map[string]any{"kind": "dlux-system-backup", "encryption": plain}), inner...))
	f.Add(append(dlbHeader(map[string]any{"kind": "dlux-system-backup-increment", "encryption": plain, "chain": map[string]any{"id": "c", "sequence": 1}}), inner...))
	baseDLB := append(dlbHeader(map[string]any{"kind": "dlux-system-backup", "encryption": plain, "chain": map[string]any{"id": "c", "sequence": 0, "root": "r0"}}), inner...)
	incDLB := append(dlbHeader(map[string]any{"kind": "dlux-system-backup-increment", "encryption": plain, "chain": map[string]any{"id": "c", "sequence": 1, "parent_root": "r0"}}), inner...)
	f.Add(zipOf(f, map[string]string{"base.dlb": string(baseDLB), "inc.dlb": string(incDLB)}))
	tmp := filepath.Join(f.TempDir(), "tmp")
	if err := os.Mkdir(tmp, 0o700); err != nil {
		f.Fatal(err)
	}
	inputs := f.TempDir()
	f.Setenv("TMPDIR", tmp)
	f.Fuzz(func(t *testing.T, data []byte) {
		p := filepath.Join(inputs, "input.dlb")
		if err := os.WriteFile(p, data, 0o600); err != nil {
			t.Fatal(err)
		}
		app := &App{token: "t"}
		if err := app.adoptSource(p, false, p); err == nil {
			get := func(h http.HandlerFunc, target string) *httptest.ResponseRecorder {
				rec := httptest.NewRecorder()
				h(rec, httptest.NewRequest(http.MethodGet, target, nil))
				return rec
			}
			rec := httptest.NewRecorder()
			app.handleUnlock(rec, httptest.NewRequest(http.MethodPost, "/api/unlock", strings.NewReader(`{"password":""}`)))
			get(app.handleState, "/api/state")
			get(app.handleManifest, "/api/manifest")
			if app.manifest != nil {
				for _, m := range app.manifest.Models {
					q := url.QueryEscape(m.Model)
					get(app.handleModel, "/api/model?key="+q)
					get(app.handleModel, "/api/model?offset=1000&key="+q)
					get(app.handleLabels, "/api/labels?key="+q)
					get(app.handleDeleted, "/api/deleted?key="+q)
				}
				for _, file := range app.manifest.Files {
					get(app.handleFile, "/api/file?path="+url.QueryEscape(file.Path))
				}
			}
		}
		app.reset()
		entries, _ := os.ReadDir(tmp)
		for _, e := range entries {
			if strings.HasPrefix(e.Name(), "dlbview-") {
				t.Fatalf("temp file %s survived reset", e.Name())
			}
		}
	})
}
