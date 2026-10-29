package main

import (
	"encoding/hex"
	"testing"
)

// Expected bytes generated independently by Python hashlib.pbkdf2_hmac("sha256", ...).
func TestPBKDF2MatchesPython(t *testing.T) {
	cases := []struct {
		password, salt     string
		iterations, keyLen int
		want               string
	}{
		{"password", "salt", 1, 32, "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b"},
		{"password", "salt", 2, 32, "ae4d0c95af6b46d32d0adff928f06dd02a303f8ef3c251dfd6e2d85a95474c43"},
		{"password", "salt", 4096, 64, "c5e478d59288c841aa530db6845c4c8d962893a001ce4e11a4963873aa98134af7ad98c1b458ce3fd74ca35beba3cda7b8d1038d6a87071b918f837405f3fe77"},
		{"pass\x00word", "sa\x00lt", 4096, 40, "89b69d0516f829893c696226650a86878c029ac13ee276509d5ae58b6466a72422433a5c04e21eb0"},
		{"كلمة المرور", "ملح", 390000, 32, "acb8c5c8a303176e60a33d24627e618f86a41936e1825c356569d2bda19add71"},
	}
	for _, tc := range cases {
		got := hex.EncodeToString(pbkdf2SHA256([]byte(tc.password), []byte(tc.salt), tc.iterations, tc.keyLen))
		if got != tc.want {
			t.Errorf("iterations=%d length=%d: got %s want %s", tc.iterations, tc.keyLen, got, tc.want)
		}
	}
}
