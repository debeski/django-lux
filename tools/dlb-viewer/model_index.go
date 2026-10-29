package main

import (
	"bufio"
	"encoding/json"
	"errors"
	"io"
	"os"
)

const modelIndexBytes = 128 << 20
const modelIndexRows = 1_000_000
const modelIndexCount = 2

var errIndexLimit = errors.New("model exceeds index budget")

type modelIndex struct {
	member  string
	file    *os.File
	offsets []int64
}

func (index *modelIndex) close() {
	index.file.Close()
	os.Remove(index.file.Name())
}

// Indexes hold only offsets in memory; serialized records stay in a private temp file.
func buildModelIndex(r io.Reader, maxBytes int64, maxRows int) (*modelIndex, error) {
	file, err := os.CreateTemp("", "dlbview-model-*.json")
	if err != nil {
		return nil, err
	}
	index := &modelIndex{file: file}
	complete := false
	defer func() {
		if !complete {
			index.close()
		}
	}()
	dec := json.NewDecoder(r)
	token, err := dec.Token()
	if err != nil {
		return nil, err
	}
	if token != json.Delim('[') {
		return nil, errors.New("unexpected data format")
	}
	writer := bufio.NewWriterSize(file, 64<<10)
	var position int64
	var raw json.RawMessage
	for dec.More() {
		if err = dec.Decode(&raw); err != nil {
			return nil, err
		}
		if position+int64(len(raw)) > maxBytes || len(index.offsets) >= maxRows {
			return nil, errIndexLimit
		}
		index.offsets = append(index.offsets, position)
		n, err := writer.Write(raw)
		if err != nil {
			return nil, err
		}
		position += int64(n)
	}
	if _, err = dec.Token(); err != nil {
		return nil, err
	}
	if err = dec.Decode(&raw); err != io.EOF {
		if err == nil {
			err = errors.New("unexpected trailing data")
		}
		return nil, err
	}
	if err := writer.Flush(); err != nil {
		return nil, err
	}
	index.offsets = append(index.offsets, position)
	complete = true
	return index, nil
}

func (index *modelIndex) window(offset, limit int) ([]json.RawMessage, error) {
	rows := make([]json.RawMessage, 0, limit)
	count := len(index.offsets) - 1
	if offset < 0 {
		offset = 0
	}
	if offset >= count {
		return rows, nil
	}
	end := offset + limit
	if end > count || end < offset {
		end = count
	}
	for i := offset; i < end; i++ {
		raw := make(json.RawMessage, index.offsets[i+1]-index.offsets[i])
		if _, err := index.file.ReadAt(raw, index.offsets[i]); err != nil {
			return nil, err
		}
		rows = append(rows, raw)
	}
	return rows, nil
}

// Caller holds a.mu so an archive cannot be closed while its index is built/read.
func (a *App) modelWindow(member string, offset, limit int) ([]json.RawMessage, error) {
	for i, index := range a.modelIndexes {
		if index.member == member {
			// Move the recently used index to the end of the two-entry cache.
			a.modelIndexes = append(append(a.modelIndexes[:i:i], a.modelIndexes[i+1:]...), index)
			return index.window(offset, limit)
		}
	}
	if offset >= 1000 && !a.modelIndexSkipped[member] {
		reader, err := a.zipReader.Open(member)
		if err != nil {
			return nil, err
		}
		if len(a.modelIndexes) == modelIndexCount {
			a.modelIndexes[0].close()
			a.modelIndexes = a.modelIndexes[1:]
		}
		index, err := buildModelIndex(reader, modelIndexBytes, modelIndexRows)
		reader.Close()
		if err == nil {
			index.member = member
			a.modelIndexes = append(a.modelIndexes, index)
			return index.window(offset, limit)
		}
		// Fall back to streaming on size limits or unavailable temp storage.
		if a.modelIndexSkipped == nil {
			a.modelIndexSkipped = map[string]bool{}
		}
		a.modelIndexSkipped[member] = true
	}
	reader, err := a.zipReader.Open(member)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	return readRecordWindow(reader, offset, limit)
}
