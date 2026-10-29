# Synthetic encrypted backup

`synthetic-encrypted.dlb` contains 1,100 generated `sample.document` rows with
Arabic titles and nested JSON values. It contains no deployment or user data.

It was generated independently with Python `zipfile`, `hashlib.pbkdf2_hmac`, and
`cryptography.Fernet`. The public test password is `synthetic-password`, the salt
is bytes 0 through 15, and PBKDF2-SHA256 uses 390,000 iterations and a 32-byte key.
The ZIP is split into 2,000-byte plaintext frames before Fernet encryption.

The regression test verifies wrong-password rejection, successful retry,
Unicode records, deep indexed browsing, and unchanged source-file bytes.
