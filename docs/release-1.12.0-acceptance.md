# DjangoLux 1.12.0 promotion acceptance

The stable candidate promotes the implementation in published `1.12.0b2`
without framework code or dependency changes. It includes b1's deletion changes.

## Published beta acceptance

The existing testbed record documents the pinned inline update to b2, migration
`0026_file_versions`, rollback to the previous runtime release `1.11.1b1` with
the additive migration retained, and successful re-application. The file-history
adoption dry run reported 14 source rows, 14 copies and no conflicts; adoption
was not applied to existing project data.

On 2026-10-17 the remaining editor acceptance ran at `http://localhost:8088`
against the published b2 runtime. The testbed's decrees image does not register
document fields, so a temporary `DocumentsConfig.ready()` registered its three
`pdf_file` fields with `accept=('pdf', 'image')` and widened their in-memory
extension validators. This was a testbed-only overlay, not a consumer release or
a change to either consumer repository. Dedicated `Other` record number
`DLUX-1.12-ACCEPTANCE-20261017` isolated the file mutations from existing records.

Browser acceptance passed:

- The registered editor accepted a PNG through Add From Files and the real
  `/sys/files/convert/` endpoint, adding one PDF page.
- Selecting that landscape image, Rotate and Fit to A4 saved a two-page PDF.
  Independent PDF inspection confirmed the original page's size and the added
  page's portrait A4 media box and rotation transform.
- History downloaded the replaced PDF byte-for-byte, verified with SHA-256.
- The editor had no page overflow at 390×844 and worked at 1440×1000; no browser
  JavaScript exceptions were reported. No screenshots were taken.
- The shipped `ScanLink` and `DluxScan` clients called health, start, status and
  result endpoints, added the returned page and saved a three-page PDF. A busy
  health response displayed an error, added no page and re-enabled Scan.
  Workstation HTTP endpoints were simulated with browser request interception;
  physical TWAIN hardware and real workstation TLS/connectivity were not tested.

The testbed overlay and ScanLink setting are restored after this run. The
acceptance record and files are retained, with the record soft-deleted.

Local scripts, result JSON, PDFs and test logs are retained under
`.xclude/validation/1.12.0-stable-2026-10-17/` (not packaged). The session fixture
there contains an expiring authentication cookie and must not be published.

## Promotion gates

Final local validation passed: 2,856 Python tests (four skips), 70 JavaScript
tests, Django system checks, no migration drift, stable classification (including
published-beta verification), migration policy against `v1.11.1`, wheel/sdist
build and `twine check`. Every packaged `dlux` file other than the release manifest
matches the b2 tag byte-for-byte. An initial suite run was invalidated by editing
the manifest version while it ran; the full suite was rerun on the final candidate
and passed in 138 seconds.

Use `docs/RELEASING.md` for publication. Compare migrations against previous
stable `v1.11.1`, not b2. The local Python environment needs
`SSL_CERT_FILE=/etc/ssl/cert.pem` to verify PyPI through the system CA bundle;
certificate verification stays enabled.

Stable publication does not migrate Archive or Decrees. Each consumer must pin
the stable package and complete its own integration and acceptance separately.
