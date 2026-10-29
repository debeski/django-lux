package main

import (
	"archive/zip"
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Synthetic records contain no deployment data and exercise compressed model streams.
func benchmarkArchive(b *testing.B, count int) ([]byte, int64) {
	b.Helper()
	var records bytes.Buffer
	records.WriteByte('[')
	for i := 0; i < count; i++ {
		if i > 0 {
			records.WriteByte(',')
		}
		fmt.Fprintf(&records, `{"model":"sample.document","pk":%d,"fields":{"title":"Document %d","body":"%s"}}`, i, i, strings.Repeat("Synthetic document text. ", 16))
	}
	records.WriteByte(']')
	var archive bytes.Buffer
	zw := zip.NewWriter(&archive)
	manifest, err := zw.Create("manifest.json")
	if err != nil {
		b.Fatal(err)
	}
	fmt.Fprintf(manifest, `{"models":[{"model":"sample.document","count":%d}],"files":[]}`, count)
	member, err := zw.Create("data/sample/document.json")
	if err != nil {
		b.Fatal(err)
	}
	if _, err = member.Write(records.Bytes()); err != nil {
		b.Fatal(err)
	}
	if err = zw.Close(); err != nil {
		b.Fatal(err)
	}
	return archive.Bytes(), int64(records.Len())
}

func BenchmarkLargeModel(b *testing.B) {
	for _, count := range []int{10000, 100000} {
		b.Run(fmt.Sprintf("rows_%d", count), func(b *testing.B) {
			archive, size := benchmarkArchive(b, count)
			zr, err := zip.NewReader(bytes.NewReader(archive), int64(len(archive)))
			if err != nil {
				b.Fatal(err)
			}
			for _, offset := range []int{0, count - 50} {
				b.Run(fmt.Sprintf("page_at_%d", offset), func(b *testing.B) {
					b.ReportAllocs()
					for i := 0; i < b.N; i++ {
						member, err := zr.Open("data/sample/document.json")
						if err != nil {
							b.Fatal(err)
						}
						rows, err := readRecordWindow(member, offset, 50)
						member.Close()
						if err != nil || len(rows) != 50 {
							b.Fatalf("rows=%d err=%v", len(rows), err)
						}
					}
				})
			}
			b.Run("relation_labels", func(b *testing.B) {
				b.SetBytes(size)
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					member, err := zr.Open("data/sample/document.json")
					if err != nil {
						b.Fatal(err)
					}
					byPK, byNK := map[string]string{}, map[string]string{}
					err = streamLabels(member, ModelSchema{LabelField: "title"}, byPK, byNK)
					member.Close()
					if err != nil || len(byPK) != count {
						b.Fatalf("labels=%d err=%v", len(byPK), err)
					}
				}
			})
			b.Run("inflate_only", func(b *testing.B) {
				b.SetBytes(size)
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					member, err := zr.Open("data/sample/document.json")
					if err != nil {
						b.Fatal(err)
					}
					n, err := io.Copy(io.Discard, member)
					member.Close()
					if err != nil || n != size {
						b.Fatalf("bytes=%d err=%v", n, err)
					}
				}
			})
		})
	}
}

func BenchmarkPasswordDerivation(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		key := pbkdf2SHA256([]byte("synthetic-password"), []byte("synthetic-salt"), defaultKDFIterations, 32)
		if len(key) != 32 {
			b.Fatal("invalid key length")
		}
	}
}

func BenchmarkChainMerge(b *testing.B) {
	base, _ := benchmarkArchive(b, 100000)
	increment, _ := benchmarkArchive(b, 5000)
	// Kept under ignored output for repeatable profiling; no real backup is read.
	dir := filepath.Join(".xclude", "benchmark-chain")
	if err := os.MkdirAll(dir, 0700); err != nil {
		b.Fatal(err)
	}
	paths := []string{filepath.Join(dir, "base.zip"), filepath.Join(dir, "increment.zip")}
	for i, data := range [][]byte{base, increment} {
		if err := os.WriteFile(paths[i], data, 0600); err != nil {
			b.Fatal(err)
		}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if err := mergeChain(paths, io.Discard); err != nil {
			b.Fatal(err)
		}
	}
}
