package main

import "testing"

// TestInlineContentType locks in the open-inline allowlist: viewable types get a
// real MIME so the browser renders them in a new tab, while unknown or active
// content (HTML/SVG/XML, binaries) falls back to a forced download.
func TestInlineContentType(t *testing.T) {
	inline := map[string]string{
		"report.pdf":            "application/pdf",
		"scan_2024.PDF":         "application/pdf",
		"profile_pics/ab12.png": "image/png",
		"photo.JPG":             "image/jpeg",
		"photo.jpeg":            "image/jpeg",
		"anim.gif":              "image/gif",
		"hero.webp":             "image/webp",
		"old.bmp":               "image/bmp",
		"notes.txt":             "text/plain; charset=utf-8",
		"export.csv":            "text/plain; charset=utf-8",
		"data.json":             "application/json; charset=utf-8",
	}
	for name, want := range inline {
		got, ok := inlineContentType(name)
		if !ok {
			t.Errorf("inlineContentType(%q): expected inline, got download", name)
			continue
		}
		if got != want {
			t.Errorf("inlineContentType(%q) = %q, want %q", name, got, want)
		}
	}

	// Active content and unknowns must NOT be inlined — they download instead, so
	// a malicious .dlb can't run script in the viewer's own origin.
	forced := []string{"page.html", "page.htm", "vector.svg", "data.xml", "archive.zip", "blob.bin", "noext"}
	for _, name := range forced {
		if ctype, ok := inlineContentType(name); ok {
			t.Errorf("inlineContentType(%q) = (%q, true), want forced download", name, ctype)
		}
	}
}
