# Vendored PDF.js

| | |
|---|---|
| Version | PDF.js **6.5.438**, legacy build |
| Source | npm `pdfjs-dist@6.5.438` (`https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.5.438.tgz`) |
| Tarball integrity | `sha512-vg8Pw1x+AFKy4AMDvhuWl5cOYV8d698UoEANoFFhc79hqXDnZQqnOXoxw3HG907WHOg1JYOvLhP756boddFxpA==` (npm registry signature and SLSA provenance attestation verified with `npm audit signatures`) |
| Cross-check | GitHub release `v6.5.438`, `pdfjs-6.5.438-legacy-dist.zip` (sha256 `55138aa33b5f1f6f68809895338b947f395f344eb6381d424b2420d6daa6a844`): its `build/pdf.worker.mjs` and `web/wasm/*_nowasm_fallback.js` are byte-identical to the npm files |
| License | Apache-2.0 (`LICENSE`); the image decoders carry their own licenses in `wasm/6.5.438/` |

## Files

| Here | From the package | sha256 |
|---|---|---|
| `pdf.min.js` | `legacy/build/pdf.min.mjs` | `522ad2c83bc8a0010e7f0cc60d0892b77c8d2bf2c9702dc12288311d94270f42` |
| `pdf.worker.min.js` | `legacy/build/pdf.worker.min.mjs` | `b4c8353ded0d88d2e2009574a29eb4e0c3ff7e942ecdf51ef5f71566a9667f31` |
| `wasm/6.5.438/openjpeg_nowasm_fallback.js` | `wasm/openjpeg_nowasm_fallback.js` | `2855f1590e7fd7abbbf204cd13a5c09d30c92fe2c9313fb72b64aa763fe8b4f3` |
| `wasm/6.5.438/jbig2_nowasm_fallback.js` | `wasm/jbig2_nowasm_fallback.js` | `70150223396487e1ccfef7eac61fc780074ad7fcc9e843b702a8a3bc23107494` |

- **Legacy build.** The modern build targets only the latest Chrome and Firefox
  and calls new built-ins such as `Map.prototype.getOrInsertComputed` directly.
  The legacy build polyfills them and is the one PDF.js supports on Firefox ESR,
  Chrome and Edge 125+, and Safari 18+: the managed browsers DjangoLux runs in.
- **`.js`, not `.mjs`.** Both files are ES modules. They keep a `.js` name
  because nginx's stock `mime.types` has no `.mjs` entry, and a browser refuses a
  module script served as `application/octet-stream`.
- **Image decoders.** JPEG 2000, JBIG2 and CCITT fax images decode through
  `wasm/<version>/`. Only the JavaScript fallbacks are shipped: the WebAssembly
  builds need `'wasm-unsafe-eval'`, which DjangoLux's CSP does not allow, so
  `DluxPdfJs` passes `useWasm: false`. The folder is named for the version
  because PDF.js appends file names to `wasmUrl`, so the `?v=` cache buster
  cannot reach these files.
- **Not shipped:** the WebAssembly files, `quickjs-eval` (PDF scripting),
  `pdf.sandbox`, `pdf.renderer` (off-main-thread drawing, which is opt-in), the
  viewer app, cmaps, standard fonts and ICC profiles.

## Upgrading

1. Download `pdfjs-dist@<version>` from npm, check its `integrity` and
   `npm audit signatures`, and compare it with the GitHub release's
   `-legacy-dist.zip`.
2. Copy the four files above, renaming `.mjs` to `.js`, into a new
   `wasm/<version>/` folder; move the previous version's folder to `.xclude/`.
3. Update this file, `docs/pdf-toolkit.md` and `CHANGELOG.md`.
