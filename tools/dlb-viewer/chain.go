// chain.go — incremental backup chains.
//
// A Dlux full backup is the base of a chain (sequence 0); each incremental
// stores only rows whose content changed since its parent, the primary keys
// deleted since (deleted/<app>/<model>.json), and media with new storage names.
// Every member's cleartext header carries its chain identity, and members are
// linked by fingerprints: a member's parent_root equals its parent's root.
//
// The viewer shows an incremental as the full state at that point whenever it
// can find the members before it — inside a chain ZIP (the server's "Download
// chain") or next to the opened file — by merging base and increments into
// one temporary archive. Opened alone it shows just the changes ("delta" mode)
// and says so.
package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// ChainInfo mirrors the "chain" block of a member's header and manifest.
type ChainInfo struct {
	ID         string `json:"id"`
	Sequence   int    `json:"sequence"`
	Token      string `json:"token"`
	Parent     string `json:"parent"`
	Root       string `json:"root"`
	ParentRoot string `json:"parent_root"`
	Kind       string `json:"kind"`
}

const (
	chainModeFull  = ""      // a full backup, or a pre-chain one
	chainModeChain = "chain" // an increment merged with the members before it
	chainModeDelta = "delta" // an increment shown on its own
)

type chainMember struct {
	path string
	meta *Metadata
}

func (m *Metadata) isIncrement() bool {
	return m != nil && m.Chain != nil && m.Chain.Sequence > 0
}

func headerOf(p string) (*Metadata, error) {
	f, err := os.Open(p)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return parseHeader(f)
}

// orderChain walks back from target along parent_root -> root links and returns
// the member paths base -> target. A candidate that merely shares a chain id
// and sequence number is never picked unless its root matches.
func orderChain(target chainMember, candidates []chainMember) ([]string, error) {
	seq := target.meta.Chain.Sequence
	bySeq := map[int][]chainMember{}
	for _, c := range candidates {
		if c.meta.Chain == nil || c.meta.Chain.ID != target.meta.Chain.ID || c.path == target.path {
			continue
		}
		if c.meta.Chain.Sequence < seq {
			bySeq[c.meta.Chain.Sequence] = append(bySeq[c.meta.Chain.Sequence], c)
		}
	}
	ordered := []chainMember{target}
	for pos := seq - 1; pos >= 0; pos-- {
		wanted := ordered[0].meta.Chain.ParentRoot
		var match *chainMember
		for i := range bySeq[pos] {
			if bySeq[pos][i].meta.Chain.Root == wanted {
				match = &bySeq[pos][i]
				break
			}
		}
		if match == nil {
			if len(bySeq[pos]) > 0 {
				return nil, fmt.Errorf("member %d of the chain does not belong to this increment", pos)
			}
			return nil, fmt.Errorf("member %d of the chain is missing", pos)
		}
		ordered = append([]chainMember{*match}, ordered...)
	}
	paths := make([]string, len(ordered))
	for i, m := range ordered {
		paths[i] = m.path
	}
	return paths, nil
}

// siblingChain finds the members before target among the .dlb files in its folder.
func siblingChain(targetPath string, meta *Metadata) ([]string, error) {
	dir := filepath.Dir(targetPath)
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var candidates []chainMember
	for _, e := range entries {
		if e.IsDir() || !strings.EqualFold(filepath.Ext(e.Name()), ".dlb") {
			continue
		}
		p := filepath.Join(dir, e.Name())
		if m, err := headerOf(p); err == nil {
			candidates = append(candidates, chainMember{p, m})
		}
	}
	return orderChain(chainMember{targetPath, meta}, candidates)
}

// isZipFile reports whether p starts with a ZIP local-file header.
func isZipFile(p string) bool {
	f, err := os.Open(p)
	if err != nil {
		return false
	}
	defer f.Close()
	sig := make([]byte, 4)
	if _, err := io.ReadFull(f, sig); err != nil {
		return false
	}
	return bytes.Equal(sig, []byte("PK\x03\x04"))
}

// extractChainZip unpacks the .dlb members of a chain ZIP into temp files and
// returns them base -> newest, the newest member's header, and every temp path
// written (for cleanup, also on error).
func extractChainZip(p string) ([]string, *Metadata, []string, error) {
	zr, err := zip.OpenReader(p)
	if err != nil {
		return nil, nil, nil, errors.New("not a Dlux backup (.dlb) or backup chain (.zip) file")
	}
	defer zr.Close()
	var temps []string
	var members []chainMember
	for _, f := range zr.File {
		if !strings.EqualFold(filepath.Ext(f.Name), ".dlb") {
			continue
		}
		rc, err := f.Open()
		if err != nil {
			return nil, nil, temps, err
		}
		tmp, err := os.CreateTemp("", "dlbview-member-*.dlb")
		if err != nil {
			rc.Close()
			return nil, nil, temps, err
		}
		temps = append(temps, tmp.Name())
		_, err = io.Copy(tmp, rc)
		rc.Close()
		tmp.Close()
		if err != nil {
			return nil, nil, temps, err
		}
		meta, err := headerOf(tmp.Name())
		if err != nil {
			return nil, nil, temps, fmt.Errorf("%s: %v", f.Name, err)
		}
		members = append(members, chainMember{tmp.Name(), meta})
	}
	if len(members) == 0 {
		return nil, nil, temps, errors.New("the ZIP holds no .dlb backups")
	}
	sort.Slice(members, func(i, j int) bool { return seqOf(members[i].meta) > seqOf(members[j].meta) })
	target := members[0]
	if !target.meta.isIncrement() {
		return []string{target.path}, target.meta, temps, nil
	}
	paths, err := orderChain(target, members[1:])
	if err != nil {
		return nil, nil, temps, err
	}
	return paths, target.meta, temps, nil
}

func seqOf(m *Metadata) int {
	if m == nil || m.Chain == nil {
		return 0
	}
	return m.Chain.Sequence
}

// ── merging ──────────────────────────────────────────────────────────────────

type memberManifest struct {
	raw          map[string]json.RawMessage
	Models       []ManifestModel              `json:"models"`
	Files        []map[string]json.RawMessage `json:"files"`
	MissingFiles []map[string]json.RawMessage `json:"missing_files"`
	GeneratedAt  string                       `json:"generated_at"`
}

func fileEntryKey(entry map[string]json.RawMessage) (string, string, string) {
	model := strings.ToLower(rawScalarString(entry["model"]))
	pk := rawScalarString(entry["pk"])
	return model + "\x00" + pk + "\x00" + rawScalarString(entry["field"]), model, pk
}

// mergeChain writes the state at the last member into out: base records, then
// each increment's records upserted by primary key and its deleted keys
// removed; the newest copy of every stored file; and a manifest describing the
// merged result.
func mergeChain(zipPaths []string, out io.Writer) error {
	readers := make([]*zip.ReadCloser, 0, len(zipPaths))
	defer func() {
		for _, r := range readers {
			r.Close()
		}
	}()
	manifests := make([]memberManifest, 0, len(zipPaths))
	for _, p := range zipPaths {
		zr, err := zip.OpenReader(p)
		if err != nil {
			return err
		}
		readers = append(readers, zr)
		raw, err := readZipMember(&zr.Reader, "manifest.json")
		if err != nil {
			return errors.New("a chain member has no manifest")
		}
		var mm memberManifest
		if err := json.Unmarshal(raw, &mm); err != nil {
			return err
		}
		if err := json.Unmarshal(raw, &mm.raw); err != nil {
			return err
		}
		manifests = append(manifests, mm)
	}

	var order []string
	seen := map[string]bool{}
	for _, mm := range manifests {
		for _, m := range mm.Models {
			key := strings.ToLower(m.Model)
			if !seen[key] {
				seen[key] = true
				order = append(order, key)
			}
		}
	}

	zw := zip.NewWriter(out)
	counts := map[string]int{}
	alive := map[string]map[string]bool{}
	for _, key := range order {
		parts := strings.SplitN(key, ".", 2)
		if len(parts) != 2 {
			continue
		}
		dataName := fmt.Sprintf("data/%s/%s.json", parts[0], parts[1])
		deletedName := fmt.Sprintf("deleted/%s/%s.json", parts[0], parts[1])
		var keys []string
		records := map[string]json.RawMessage{}
		for i, zr := range readers {
			if f, err := zr.Open(dataName); err == nil {
				err = eachRecord(f, func(pk string, raw json.RawMessage) {
					if _, ok := records[pk]; !ok {
						keys = append(keys, pk)
					}
					records[pk] = raw
				})
				f.Close()
				if err != nil {
					return fmt.Errorf("%s: %v", dataName, err)
				}
			}
			if i == 0 {
				continue
			}
			if raw, err := readZipMember(&zr.Reader, deletedName); err == nil {
				var gone []string
				if err := json.Unmarshal(raw, &gone); err != nil {
					return fmt.Errorf("%s: %v", deletedName, err)
				}
				for _, pk := range gone {
					delete(records, pk)
				}
			}
		}
		w, err := zw.Create(dataName)
		if err != nil {
			return err
		}
		live := map[string]bool{}
		io.WriteString(w, "[")
		n := 0
		for _, pk := range keys {
			raw, ok := records[pk]
			if !ok || live[pk] {
				continue
			}
			if n > 0 {
				io.WriteString(w, ", ")
			}
			w.Write(raw)
			live[pk] = true
			n++
		}
		io.WriteString(w, "]\n")
		counts[key] = n
		alive[key] = live
	}

	type placed struct {
		entry  map[string]json.RawMessage
		member int
	}
	pickFiles := func(list func(memberManifest) []map[string]json.RawMessage) ([]string, map[string]placed) {
		var keys []string
		chosen := map[string]placed{}
		for i, mm := range manifests {
			for _, entry := range list(mm) {
				k, model, pk := fileEntryKey(entry)
				if !alive[model][pk] {
					continue
				}
				if _, ok := chosen[k]; !ok {
					keys = append(keys, k)
				}
				chosen[k] = placed{entry, i}
			}
		}
		return keys, chosen
	}
	fileKeys, files := pickFiles(func(mm memberManifest) []map[string]json.RawMessage { return mm.Files })
	missingKeys, missing := pickFiles(func(mm memberManifest) []map[string]json.RawMessage { return mm.MissingFiles })

	written := map[string]bool{}
	mergedFiles := make([]map[string]json.RawMessage, 0, len(fileKeys))
	for _, k := range fileKeys {
		item := files[k]
		name := rawScalarString(item.entry["path"])
		if name == "" || written[name] {
			continue
		}
		for _, f := range readers[item.member].File {
			if f.Name == name {
				if err := zw.Copy(f); err != nil {
					return err
				}
				written[name] = true
				mergedFiles = append(mergedFiles, item.entry)
				break
			}
		}
	}
	mergedMissing := make([]map[string]json.RawMessage, 0, len(missingKeys))
	for _, k := range missingKeys {
		if _, stored := files[k]; !stored {
			mergedMissing = append(mergedMissing, missing[k].entry)
		}
	}

	manifest := map[string]any{}
	for k, v := range manifests[len(manifests)-1].raw {
		manifest[k] = v
	}
	models := make([]ManifestModel, 0, len(order))
	for _, key := range order {
		models = append(models, ManifestModel{Model: key, Count: counts[key]})
	}
	manifest["models"] = models
	manifest["files"] = mergedFiles
	manifest["missing_files"] = mergedMissing
	manifest["chain_view"] = map[string]any{
		"members":           len(manifests),
		"base_generated_at": manifests[0].GeneratedAt,
	}
	mw, err := zw.Create("manifest.json")
	if err != nil {
		return err
	}
	enc := json.NewEncoder(mw)
	enc.SetIndent("", "  ")
	if err := enc.Encode(manifest); err != nil {
		return err
	}
	return zw.Close()
}

// eachRecord streams a dumpdata JSON array, handing each record and its pk to fn.
func eachRecord(r io.Reader, fn func(pk string, raw json.RawMessage)) error {
	dec := json.NewDecoder(r)
	tok, err := dec.Token()
	if err != nil {
		return err
	}
	if d, ok := tok.(json.Delim); !ok || d != '[' {
		return errors.New("unexpected data format")
	}
	for dec.More() {
		var raw json.RawMessage
		if err := dec.Decode(&raw); err != nil {
			return err
		}
		var head struct {
			PK json.RawMessage `json:"pk"`
		}
		if err := json.Unmarshal(raw, &head); err != nil {
			return err
		}
		fn(rawScalarString(head.PK), raw)
	}
	return nil
}
