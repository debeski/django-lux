// dlb.go — parsing and decryption of Dlux backup (.dlb) containers.
//
// Container layout (must match dlux/backup.py):
//
//	"DLB1"                4-byte magic
//	u32 (big-endian)      metadata-JSON length
//	metadata JSON         cleartext, non-sensitive (includes the "encryption" block)
//	repeated frames:
//	  u64 (big-endian)    Fernet-token length
//	  Fernet token        one <=32 MB plaintext chunk of the inner ZIP
//
// Key derivation, from the cleartext "encryption" block:
//
//	key_source == "passphrase"      -> seed = the user-supplied passphrase
//	key_source == "django-secret-key" (default) -> seed = the project SECRET_KEY
//	then digest = PBKDF2-HMAC-SHA256(seed, salt, iterations, 32 bytes)
//
//	legacy kdf == "sha256-salt-seed" -> digest = SHA256(salt || SECRET_KEY)
//
// The Fernet key Python uses is base64url(digest); Fernet decodes that back to
// the 32-byte digest, so here the digest IS the key: signing key = digest[:16],
// AES-128 key = digest[16:].
package main

import (
	"bufio"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"hash"
	"io"
)

const (
	dlbMagic                  = "DLB1"
	defaultKDFIterations      = 390000
	maxMetadataLen            = 10 * 1024 * 1024
	fernetVersion        byte = 0x80
)

// ErrBadPassword is returned when the supplied password fails Fernet's HMAC
// check on the first chunk — i.e. wrong passphrase / SECRET_KEY (or corruption).
var ErrBadPassword = errors.New("incorrect password or corrupted backup")

// Encryption mirrors the "encryption" block written by write_dlb_container.
type Encryption struct {
	Scheme             string `json:"scheme"`
	KDF                string `json:"kdf"`
	Salt               string `json:"salt"`
	Iterations         int    `json:"iterations"`
	KeySource          string `json:"key_source"`
	PassphraseRequired bool   `json:"passphrase_required"`
}

// Metadata is the cleartext header of an .dlb file.
type Metadata struct {
	Kind        string `json:"kind"`
	Format      int    `json:"format"`
	CreatedAt   string `json:"created_at"`
	DluxVersion string `json:"dlux_version"`
	Models      int    `json:"models"`
	Rows        int    `json:"rows"`
	Files       int    `json:"files"`
	// MediaIncluded is the v1.2.10+ backup-scope flag (full vs data-only/quick).
	// A pointer keeps it tri-state: nil means a pre-1.2.10 backup that predates the
	// flag, so the viewer reports "unknown" rather than mislabeling it as data-only.
	MediaIncluded      *bool      `json:"media_included"`
	PassphraseRequired bool       `json:"passphrase_required"`
	Encryption         Encryption `json:"encryption"`
}

// parseHeader reads and validates the magic + metadata header, advancing r to
// the first encrypted frame.
func parseHeader(r io.Reader) (*Metadata, error) {
	magic := make([]byte, len(dlbMagic))
	if _, err := io.ReadFull(r, magic); err != nil {
		return nil, errors.New("not a Dlux backup (.dlb) file")
	}
	if string(magic) != dlbMagic {
		return nil, errors.New("not a Dlux backup (.dlb) file")
	}
	var lenBuf [4]byte
	if _, err := io.ReadFull(r, lenBuf[:]); err != nil {
		return nil, errors.New("corrupt backup metadata header")
	}
	n := binary.BigEndian.Uint32(lenBuf[:])
	if n == 0 || n > maxMetadataLen {
		return nil, errors.New("corrupt backup metadata header")
	}
	raw := make([]byte, n)
	if _, err := io.ReadFull(r, raw); err != nil {
		return nil, errors.New("corrupt backup metadata header")
	}
	var meta Metadata
	if err := json.Unmarshal(raw, &meta); err != nil {
		return nil, fmt.Errorf("invalid backup metadata: %w", err)
	}
	if meta.Kind != "dlux-system-backup" {
		return nil, errors.New("unsupported backup kind")
	}
	return &meta, nil
}

// deriveKey computes the 32-byte Fernet digest for the given password.
func deriveKey(enc Encryption, password string) ([]byte, error) {
	salt, err := hex.DecodeString(enc.Salt)
	if err != nil || len(salt) == 0 {
		return nil, errors.New("backup metadata is missing encryption parameters")
	}
	if enc.KDF == "sha256-salt-seed" { // legacy reader, SECRET_KEY only
		sum := sha256.Sum256(append(append([]byte{}, salt...), []byte(password)...))
		return sum[:], nil
	}
	iterations := enc.Iterations
	if iterations <= 0 {
		iterations = defaultKDFIterations
	}
	return pbkdf2SHA256([]byte(password), salt, iterations, 32), nil
}

// decryptToFile reads every encrypted frame from r and writes the recovered
// inner ZIP into dst. The first frame's HMAC failure surfaces as ErrBadPassword.
func decryptToFile(r io.Reader, key []byte, dst io.Writer) error {
	br := bufio.NewReaderSize(r, 1<<20)
	var lenBuf [8]byte
	first := true
	for {
		_, err := io.ReadFull(br, lenBuf[:])
		if err == io.EOF {
			return nil // clean end of frames
		}
		if err != nil {
			return errors.New("truncated backup container")
		}
		n := binary.BigEndian.Uint64(lenBuf[:])
		token := make([]byte, n)
		if _, err := io.ReadFull(br, token); err != nil {
			return errors.New("truncated backup container")
		}
		plain, err := fernetDecrypt(key, token)
		if err != nil {
			if first {
				return ErrBadPassword
			}
			return err
		}
		if _, err := dst.Write(plain); err != nil {
			return err
		}
		first = false
	}
}

// fernetDecrypt decrypts a single Fernet token (base64url, with padding).
func fernetDecrypt(key, token []byte) ([]byte, error) {
	if len(key) != 32 {
		return nil, errors.New("internal: bad key length")
	}
	signingKey := key[:16]
	cryptoKey := key[16:]

	data, err := base64.URLEncoding.DecodeString(string(token))
	if err != nil {
		return nil, ErrBadPassword
	}
	// version(1) + timestamp(8) + iv(16) + ciphertext(>=16) + hmac(32)
	if len(data) < 1+8+16+16+32 || data[0] != fernetVersion {
		return nil, ErrBadPassword
	}
	macOffset := len(data) - 32
	body := data[:macOffset]
	providedMAC := data[macOffset:]

	mac := hmac.New(sha256.New, signingKey)
	mac.Write(body)
	if !hmac.Equal(mac.Sum(nil), providedMAC) {
		return nil, ErrBadPassword
	}

	iv := data[9:25]
	ciphertext := data[25:macOffset]
	if len(ciphertext)%aes.BlockSize != 0 {
		return nil, errors.New("corrupt backup chunk")
	}
	block, err := aes.NewCipher(cryptoKey)
	if err != nil {
		return nil, err
	}
	out := make([]byte, len(ciphertext))
	cipher.NewCBCDecrypter(block, iv).CryptBlocks(out, ciphertext)
	return pkcs7Unpad(out, aes.BlockSize)
}

func pkcs7Unpad(b []byte, blockSize int) ([]byte, error) {
	if len(b) == 0 || len(b)%blockSize != 0 {
		return nil, errors.New("corrupt backup chunk")
	}
	pad := int(b[len(b)-1])
	if pad == 0 || pad > blockSize || pad > len(b) {
		return nil, errors.New("corrupt backup chunk")
	}
	for _, c := range b[len(b)-pad:] {
		if int(c) != pad {
			return nil, errors.New("corrupt backup chunk")
		}
	}
	return b[:len(b)-pad], nil
}

// pbkdf2SHA256 is RFC 2898 PBKDF2 over HMAC-SHA256 (stdlib only).
func pbkdf2SHA256(password, salt []byte, iterations, keyLen int) []byte {
	newPRF := func() hash.Hash { return hmac.New(sha256.New, password) }
	hLen := sha256.Size
	numBlocks := (keyLen + hLen - 1) / hLen
	dk := make([]byte, 0, numBlocks*hLen)
	var idx [4]byte
	for block := 1; block <= numBlocks; block++ {
		binary.BigEndian.PutUint32(idx[:], uint32(block))
		prf := newPRF()
		prf.Write(salt)
		prf.Write(idx[:])
		u := prf.Sum(nil)
		t := make([]byte, len(u))
		copy(t, u)
		for i := 1; i < iterations; i++ {
			prf = newPRF()
			prf.Write(u)
			u = prf.Sum(nil)
			for j := range t {
				t[j] ^= u[j]
			}
		}
		dk = append(dk, t...)
	}
	return dk[:keyLen]
}
