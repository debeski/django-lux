package main

import (
	"archive/zip"
	"bytes"
	"encoding/binary"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// An unencrypted .dlb carries the inner ZIP right after the header and must
// unlock without a password.
func TestUnencryptedBackupUnlocksWithoutPassword(t *testing.T) {
	var inner bytes.Buffer
	zw := zip.NewWriter(&inner)
	f, err := zw.Create("manifest.json")
	if err != nil {
		t.Fatal(err)
	}
	f.Write([]byte(`{"kind":"dlux-system-backup","models":[{"model":"auth.user","count":0}],"files":[]}`))
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	header := []byte(`{"kind":"dlux-system-backup","format":1,"system_data_included":false,"encryption":{"scheme":"none","key_source":"none"}}`)
	var dlb bytes.Buffer
	dlb.WriteString(dlbMagic)
	binary.Write(&dlb, binary.BigEndian, uint32(len(header)))
	dlb.Write(header)
	dlb.Write(inner.Bytes())
	path := filepath.Join(t.TempDir(), "plain.dlb")
	if err := os.WriteFile(path, dlb.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}

	app := &App{token: "t"}
	if err := app.openPath(path); err != nil {
		t.Fatal(err)
	}
	if !app.meta.Unencrypted() || app.meta.SystemDataIncluded == nil || *app.meta.SystemDataIncluded {
		t.Fatalf("unexpected metadata: %+v", app.meta)
	}
	rec := httptest.NewRecorder()
	app.handleUnlock(rec, httptest.NewRequest(http.MethodPost, "/api/unlock", strings.NewReader(`{"password":""}`)))
	if rec.Code != http.StatusOK {
		t.Fatalf("unlock returned %d: %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), "auth.user") {
		t.Fatalf("manifest not served: %s", rec.Body.String())
	}
}
