// Command msb-viewer is a standalone, dependency-free viewer for Microsys
// encrypted system backups (.msb). It runs a tiny local web server on
// 127.0.0.1, opens your browser, prompts for the backup password, decrypts the
// container in a temp file, and lets you browse models, rows, and stored files.
//
// Build:   go build -o msb-viewer .
// Run:     ./msb-viewer [path/to/backup.msb]
//
// No third-party modules: AES/HMAC/SHA-256/ZIP come from the Go standard
// library; Fernet and PBKDF2 are implemented in msb.go.
package main

import (
	"archive/zip"
	"crypto/rand"
	"crypto/subtle"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
)

//go:embed web
var webFS embed.FS

// ManifestModel / ManifestFile / Manifest mirror the manifest.json the backup
// writes (see microsys/reports.py stream_model_into_zip + backup.py).
type ManifestModel struct {
	Model string `json:"model"`
	Count int    `json:"count"`
}

type ManifestFile struct {
	Model string          `json:"model"`
	PK    json.RawMessage `json:"pk"`
	Field string          `json:"field"`
	Path  string          `json:"path"`
	Name  string          `json:"name"`
}

type Manifest struct {
	GeneratedAt     string          `json:"generated_at"`
	MicrosysVersion string          `json:"microsys_version"`
	MigrationState  []string        `json:"migration_state"`
	Models          []ManifestModel `json:"models"`
	Files           []ManifestFile  `json:"files"`
	MissingFiles    []ManifestFile  `json:"missing_files"`
	SuperuserPolicy json.RawMessage `json:"superuser_policy"`
}

// App holds the (single, local) viewer session state.
type App struct {
	token string

	mu        sync.Mutex
	srcPath   string // path to the .msb on disk
	srcIsTemp bool   // true when the source was uploaded into a temp file
	meta      *Metadata

	zipPath   string // decrypted inner zip (temp file)
	zipFile   *os.File
	zipReader *zip.Reader
	manifest  *Manifest
	rawMani   []byte
}

func main() {
	log.SetFlags(0)
	app := &App{token: randomToken()}

	if len(os.Args) > 1 && os.Args[1] != "" {
		// Pre-load a file passed on the command line.
		if err := app.openPath(os.Args[1]); err != nil {
			log.Printf("warning: could not open %q: %v", os.Args[1], err)
		}
	}

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		log.Fatalf("cannot start local server: %v", err)
	}
	addr := ln.Addr().(*net.TCPAddr)
	url := fmt.Sprintf("http://127.0.0.1:%d/?token=%s", addr.Port, app.token)

	mux := http.NewServeMux()
	mux.HandleFunc("/", app.handleIndex)
	staticSub, _ := fs.Sub(webFS, "web")
	mux.Handle("/static/", http.StripPrefix("/static/", http.FileServer(http.FS(staticSub))))
	mux.HandleFunc("/api/state", app.guard(app.handleState))
	mux.HandleFunc("/api/open-path", app.guard(app.handleOpenPath))
	mux.HandleFunc("/api/open-upload", app.guard(app.handleOpenUpload))
	mux.HandleFunc("/api/unlock", app.guard(app.handleUnlock))
	mux.HandleFunc("/api/manifest", app.guard(app.handleManifest))
	mux.HandleFunc("/api/model", app.guard(app.handleModel))
	mux.HandleFunc("/api/file", app.guard(app.handleFile))

	srv := &http.Server{Handler: mux}

	// Clean up temp files on Ctrl-C.
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sig
		app.reset()
		_ = srv.Close()
		os.Exit(0)
	}()

	fmt.Println("Microsys .msb viewer")
	fmt.Printf("  Open in your browser:  %s\n", url)
	fmt.Println("  Press Ctrl-C to quit (temp files are removed on exit).")
	openBrowser(url)

	if err := srv.Serve(ln); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

// ── HTTP plumbing ────────────────────────────────────────────────────────────

// guard restricts API calls to local requests carrying the session token,
// mitigating DNS-rebinding / drive-by access from other local processes.
func (a *App) guard(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !isLocalHost(r.Host) {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		tok := r.Header.Get("X-MSB-Token")
		if tok == "" {
			tok = r.URL.Query().Get("token")
		}
		if subtle.ConstantTimeCompare([]byte(tok), []byte(a.token)) != 1 {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		h(w, r)
	}
}

func (a *App) handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	raw, err := webFS.ReadFile("web/index.html")
	if err != nil {
		http.Error(w, "missing UI", http.StatusInternalServerError)
		return
	}
	out := strings.ReplaceAll(string(raw), "__MSB_TOKEN__", a.token)
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = io.WriteString(w, out)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"error": msg})
}

// ── API handlers ─────────────────────────────────────────────────────────────

// handleState reports whether a file is loaded and whether it's been unlocked.
func (a *App) handleState(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	defer a.mu.Unlock()
	resp := map[string]any{
		"loaded":   a.meta != nil,
		"unlocked": a.zipReader != nil,
	}
	if a.meta != nil {
		resp["meta"] = a.meta
		resp["source"] = path.Base(a.srcPath)
	}
	if a.manifest != nil {
		resp["manifest"] = a.manifestSummary()
	}
	writeJSON(w, http.StatusOK, resp)
}

func (a *App) handleOpenPath(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Path string `json:"path"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Path) == "" {
		writeErr(w, http.StatusBadRequest, "a file path is required")
		return
	}
	if err := a.openPath(strings.TrimSpace(body.Path)); err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	a.handleState(w, r)
}

func (a *App) handleOpenUpload(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeErr(w, http.StatusBadRequest, "could not read upload")
		return
	}
	file, hdr, err := r.FormFile("file")
	if err != nil {
		writeErr(w, http.StatusBadRequest, "no file in upload")
		return
	}
	defer file.Close()

	tmp, err := os.CreateTemp("", "msbview-src-*.msb")
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "cannot buffer upload")
		return
	}
	if _, err := io.Copy(tmp, file); err != nil {
		tmp.Close()
		os.Remove(tmp.Name())
		writeErr(w, http.StatusInternalServerError, "cannot buffer upload")
		return
	}
	tmp.Close()

	if err := a.adoptSource(tmp.Name(), true, hdr.Filename); err != nil {
		os.Remove(tmp.Name())
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	a.handleState(w, r)
}

func (a *App) handleUnlock(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Password string `json:"password"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)

	a.mu.Lock()
	meta := a.meta
	srcPath := a.srcPath
	a.mu.Unlock()
	if meta == nil {
		writeErr(w, http.StatusBadRequest, "no backup loaded")
		return
	}

	key, err := deriveKey(meta.Encryption, body.Password)
	if err != nil {
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}

	src, err := os.Open(srcPath)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "backup file went away")
		return
	}
	defer src.Close()
	if _, err := parseHeader(src); err != nil { // re-advance past the header
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}

	zf, err := os.CreateTemp("", "msbview-zip-*.zip")
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "cannot create temp file")
		return
	}
	if err := decryptToFile(src, key, zf); err != nil {
		zf.Close()
		os.Remove(zf.Name())
		if errors.Is(err, ErrBadPassword) {
			writeErr(w, http.StatusUnauthorized, ErrBadPassword.Error())
			return
		}
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}

	fi, err := zf.Stat()
	if err != nil {
		zf.Close()
		os.Remove(zf.Name())
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	}
	zr, err := zip.NewReader(zf, fi.Size())
	if err != nil {
		zf.Close()
		os.Remove(zf.Name())
		writeErr(w, http.StatusBadRequest, "decrypted payload is not a valid archive")
		return
	}

	var mani Manifest
	rawMani, _ := readZipMember(zr, "manifest.json")
	if len(rawMani) > 0 {
		_ = json.Unmarshal(rawMani, &mani)
	}

	a.mu.Lock()
	a.closeZipLocked()
	a.zipFile = zf
	a.zipPath = zf.Name()
	a.zipReader = zr
	a.manifest = &mani
	a.rawMani = rawMani
	a.mu.Unlock()

	a.handleState(w, r)
}

func (a *App) handleManifest(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	raw := a.rawMani
	a.mu.Unlock()
	if len(raw) == 0 {
		writeErr(w, http.StatusNotFound, "no manifest available")
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write(raw)
}

// handleModel returns a window of a model's serialized records.
func (a *App) handleModel(w http.ResponseWriter, r *http.Request) {
	key := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("key")))
	if key == "" || !strings.Contains(key, ".") {
		writeErr(w, http.StatusBadRequest, "a model key (app.model) is required")
		return
	}
	offset := atoiDefault(r.URL.Query().Get("offset"), 0)
	limit := atoiDefault(r.URL.Query().Get("limit"), 50)
	if limit <= 0 || limit > 1000 {
		limit = 50
	}

	a.mu.Lock()
	zr := a.zipReader
	total := a.modelCountLocked(key)
	a.mu.Unlock()
	if zr == nil {
		writeErr(w, http.StatusBadRequest, "backup is locked")
		return
	}

	parts := strings.SplitN(key, ".", 2)
	member := fmt.Sprintf("data/%s/%s.json", parts[0], parts[1])
	f, err := zr.Open(member)
	if err != nil {
		writeErr(w, http.StatusNotFound, "no data for that model")
		return
	}
	defer f.Close()

	records, err := readRecordWindow(f, offset, limit)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "could not read records")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"key":     key,
		"total":   total,
		"offset":  offset,
		"limit":   limit,
		"records": records,
	})
}

// handleFile streams a stored file (or any zip member) out of the backup.
func (a *App) handleFile(w http.ResponseWriter, r *http.Request) {
	p := strings.TrimSpace(r.URL.Query().Get("path"))
	if p == "" {
		writeErr(w, http.StatusBadRequest, "a path is required")
		return
	}
	a.mu.Lock()
	zr := a.zipReader
	a.mu.Unlock()
	if zr == nil {
		writeErr(w, http.StatusBadRequest, "backup is locked")
		return
	}
	f, err := zr.Open(p)
	if err != nil {
		writeErr(w, http.StatusNotFound, "no such file in backup")
		return
	}
	defer f.Close()
	disposition := "inline"
	if r.URL.Query().Get("download") == "1" {
		disposition = "attachment"
	}
	w.Header().Set("Content-Disposition", fmt.Sprintf("%s; filename=%q", disposition, path.Base(p)))
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	_, _ = io.Copy(w, f)
}

// ── source / state management ────────────────────────────────────────────────

func (a *App) openPath(p string) error {
	abs := p
	if fi, err := os.Stat(abs); err != nil || fi.IsDir() {
		return fmt.Errorf("file not found: %s", p)
	}
	return a.adoptSource(abs, false, p)
}

// adoptSource validates the header of a candidate source and, on success,
// installs it as the active (locked) backup, discarding any previous one.
func (a *App) adoptSource(p string, isTemp bool, displayName string) error {
	f, err := os.Open(p)
	if err != nil {
		return fmt.Errorf("cannot open file: %v", err)
	}
	defer f.Close()
	meta, err := parseHeader(f)
	if err != nil {
		return err
	}

	a.mu.Lock()
	defer a.mu.Unlock()
	a.resetLocked()
	a.srcPath = p
	a.srcIsTemp = isTemp
	a.meta = meta
	_ = displayName
	return nil
}

func (a *App) manifestSummary() map[string]any {
	m := a.manifest
	if m == nil {
		return nil
	}
	return map[string]any{
		"generated_at":     m.GeneratedAt,
		"microsys_version": m.MicrosysVersion,
		"migration_state":  m.MigrationState,
		"models":           m.Models,
		"files":            m.Files,
		"missing_files":    m.MissingFiles,
		"superuser_policy": m.SuperuserPolicy,
	}
}

func (a *App) modelCountLocked(key string) int {
	if a.manifest == nil {
		return 0
	}
	for _, m := range a.manifest.Models {
		if strings.EqualFold(m.Model, key) {
			return m.Count
		}
	}
	return 0
}

// reset clears everything and removes temp files (call without the lock held).
func (a *App) reset() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.resetLocked()
}

func (a *App) resetLocked() {
	a.closeZipLocked()
	if a.srcIsTemp && a.srcPath != "" {
		os.Remove(a.srcPath)
	}
	a.srcPath = ""
	a.srcIsTemp = false
	a.meta = nil
}

func (a *App) closeZipLocked() {
	a.zipReader = nil
	a.manifest = nil
	a.rawMani = nil
	if a.zipFile != nil {
		a.zipFile.Close()
		a.zipFile = nil
	}
	if a.zipPath != "" {
		os.Remove(a.zipPath)
		a.zipPath = ""
	}
}

// ── helpers ──────────────────────────────────────────────────────────────────

func readZipMember(zr *zip.Reader, name string) ([]byte, error) {
	f, err := zr.Open(name)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return io.ReadAll(f)
}

// readRecordWindow streams a Django dumpdata JSON array and returns the records
// in [offset, offset+limit) without buffering the whole file.
func readRecordWindow(r io.Reader, offset, limit int) ([]json.RawMessage, error) {
	dec := json.NewDecoder(r)
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	if d, ok := tok.(json.Delim); !ok || d != '[' {
		return nil, errors.New("unexpected data format")
	}
	out := make([]json.RawMessage, 0, limit)
	idx := 0
	for dec.More() {
		if idx >= offset+limit {
			break
		}
		var raw json.RawMessage
		if err := dec.Decode(&raw); err != nil {
			return nil, err
		}
		if idx >= offset {
			out = append(out, raw)
		}
		idx++
	}
	return out, nil
}

func atoiDefault(s string, def int) int {
	if s == "" {
		return def
	}
	if n, err := strconv.Atoi(s); err == nil {
		return n
	}
	return def
}

func isLocalHost(host string) bool {
	h := host
	if i := strings.LastIndex(h, ":"); i >= 0 {
		h = h[:i]
	}
	h = strings.TrimPrefix(strings.TrimSuffix(h, "]"), "[")
	return h == "127.0.0.1" || h == "localhost" || h == "::1"
}

func randomToken() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "msb-static-token"
	}
	return hex.EncodeToString(b)
}

func openBrowser(url string) {
	var cmd string
	var args []string
	switch runtime.GOOS {
	case "darwin":
		cmd, args = "open", []string{url}
	case "windows":
		cmd, args = "rundll32", []string{"url.dll,FileProtocolHandler", url}
	default:
		cmd, args = "xdg-open", []string{url}
	}
	_ = exec.Command(cmd, args...).Start()
}
