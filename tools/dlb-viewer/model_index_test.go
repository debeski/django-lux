package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"sync"
	"testing"
)

func TestModelIndexMatchesStreamingWindows(t *testing.T) {
	const data = `[ {"pk":1,"fields":{"title":"مرحبا","nested":[1,{"x":"[,]"}]}}, {"pk":"id","fields":{}}, {"pk":null}, {"fields":{"empty":null}} ]`
	index, err := buildModelIndex(strings.NewReader(data), 1024, 10)
	if err != nil {
		t.Fatal(err)
	}
	defer index.close()
	info, err := index.file.Stat()
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm()&0077 != 0 {
		t.Fatal("private model records exposed")
	}
	for _, offset := range []int{0, 1, 3, 4, 100} {
		for _, limit := range []int{1, 2, 50} {
			got, err := index.window(offset, limit)
			if err != nil {
				t.Fatal(err)
			}
			want, err := readRecordWindow(strings.NewReader(data), offset, limit)
			if err != nil {
				t.Fatal(err)
			}
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("offset=%d limit=%d: got %s want %s", offset, limit, got, want)
			}
		}
	}
}

func TestModelHandlerIndexedPagesAndErrorResponses(t *testing.T) {
	app := indexedTestApp(t)
	app.manifest = &Manifest{Models: []ManifestModel{{Model: "sample.one", Count: 1100}}}
	defer app.reset()
	for _, tc := range []struct {
		query                 string
		status, offset, count int
	}{
		{"key=sample.one&offset=1050&limit=50", 200, 1050, 50},
		{"key=sample.one&offset=1000&limit=3", 200, 1000, 3},
		{"key=sample.one&offset=-10&limit=5000", 200, 0, 50},
		{"key=sample.one&offset=2000", 200, 2000, 0},
		{"key=sample.missing", 404, 0, 0},
		{"key=invalid", 400, 0, 0},
	} {
		response := httptest.NewRecorder()
		app.handleModel(response, httptest.NewRequest("GET", "/api/model?"+tc.query, nil))
		if response.Code != tc.status {
			t.Fatalf("%s: status=%d body=%s", tc.query, response.Code, response.Body.String())
		}
		if tc.status != 200 {
			continue
		}
		var result struct {
			Offset, Total int
			Records       []json.RawMessage
		}
		if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		if result.Offset != tc.offset || result.Total != 1100 || len(result.Records) != tc.count {
			t.Fatalf("%s: %+v", tc.query, result)
		}
	}
	app.reset()
	response := httptest.NewRecorder()
	app.handleModel(response, httptest.NewRequest("GET", "/api/model?key=sample.one", nil))
	if response.Code != 400 {
		t.Fatal("locked archive was browsable")
	}
}

func TestModelIndexLimitsCorruptionAndCleanup(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("TMPDIR", dir)
	for _, tc := range []struct {
		data  string
		bytes int64
		rows  int
	}{
		{`[1,2,3]`, 2, 10}, {`[1,2,3]`, 100, 2}, {`[1,`, 100, 10}, {`{}`, 100, 10}, {`[1] garbage`, 100, 10}, {`[1] {}`, 100, 10},
	} {
		index, err := buildModelIndex(strings.NewReader(tc.data), tc.bytes, tc.rows)
		if err == nil || index != nil {
			t.Fatalf("expected rejection for %+v", tc)
		}
		files, err := os.ReadDir(dir)
		if err != nil || len(files) != 0 {
			t.Fatalf("leaked temp files: %v %v", files, err)
		}
	}
	index, err := buildModelIndex(strings.NewReader(`[]`), 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	filename := index.file.Name()
	index.close()
	if _, err = os.Stat(filename); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("index file not cleaned")
	}
}

func indexedTestApp(t *testing.T) *App {
	t.Helper()
	var buffer bytes.Buffer
	zw := zip.NewWriter(&buffer)
	for _, name := range []string{"one", "two", "three"} {
		w, err := zw.Create("data/sample/" + name + ".json")
		if err != nil {
			t.Fatal(err)
		}
		io.WriteString(w, "[")
		for i := 0; i < 1100; i++ {
			if i > 0 {
				io.WriteString(w, ",")
			}
			fmt.Fprintf(w, `{"pk":%d,"fields":{"title":"%s"}}`, i, name)
		}
		io.WriteString(w, "]")
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	zr, err := zip.NewReader(bytes.NewReader(buffer.Bytes()), int64(buffer.Len()))
	if err != nil {
		t.Fatal(err)
	}
	return &App{zipReader: zr}
}

func TestModelCacheEvictionResetAndConcurrentReads(t *testing.T) {
	app := indexedTestApp(t)
	defer app.reset()
	read := func(key string) {
		app.mu.Lock()
		defer app.mu.Unlock()
		rows, err := app.modelWindow("data/sample/"+key+".json", 1050, 50)
		if err != nil || len(rows) != 50 {
			t.Errorf("rows=%d err=%v", len(rows), err)
			return
		}
		var first struct {
			PK int `json:"pk"`
		}
		json.Unmarshal(rows[0], &first)
		if first.PK != 1050 {
			t.Error("wrong page")
		}
	}
	read("one")
	read("two")
	first := app.modelIndexes[0].file.Name()
	read("one") // one is now most recent; two must be evicted.
	evicted := app.modelIndexes[0].file.Name()
	read("three")
	if _, err := os.Stat(evicted); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("LRU index not evicted")
	}
	if _, err := os.Stat(first); err != nil {
		t.Fatal("recent index was evicted")
	}
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); read("one") }()
	}
	wg.Wait()
	paths := []string{app.modelIndexes[0].file.Name(), app.modelIndexes[1].file.Name()}
	app.reset()
	for _, p := range paths {
		if _, err := os.Stat(p); !errors.Is(err, os.ErrNotExist) {
			t.Fatal("reset retained index")
		}
	}
	if len(app.modelIndexes) != 0 || app.modelIndexSkipped != nil {
		t.Fatal("cache survived reset")
	}
}

func TestLabelsDoNotReuseMissingFields(t *testing.T) {
	byPK, byNK := map[string]string{}, map[string]string{}
	data := `[{"pk":1,"fields":{"name":"Alice","code":"a"}},{"pk":2,"fields":{}},{"pk":3,"fields":null},{"fields":{"name":"No PK"}}]`
	err := streamLabels(strings.NewReader(data), ModelSchema{LabelField: "name", NaturalKeyFields: []string{"code"}}, byPK, byNK)
	if err != nil {
		t.Fatal(err)
	}
	if byPK["1"] != "Alice" || byPK["2"] != "2" || byPK["3"] != "3" || len(byPK) != 3 || len(byNK) != 1 {
		t.Fatalf("stale labels: %v %v", byPK, byNK)
	}
}

func TestModelIndexStorageFailureFallsBackToStreaming(t *testing.T) {
	t.Setenv("TMPDIR", t.TempDir()+"/missing")
	app := indexedTestApp(t)
	defer app.reset()
	for i := 0; i < 2; i++ {
		rows, err := app.modelWindow("data/sample/one.json", 1050, 50)
		if err != nil || len(rows) != 50 {
			t.Fatalf("fallback rows=%d err=%v", len(rows), err)
		}
	}
	if len(app.modelIndexes) != 0 || !app.modelIndexSkipped["data/sample/one.json"] {
		t.Fatal("failed index was not bypassed")
	}
}
