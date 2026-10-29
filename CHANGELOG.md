# Changelog

This file owns the release history for `django-lux`.

> `django-lux` is the renamed, actively-maintained successor to
> [`django-microsys`](https://github.com/debeski/django-microsys) (now archived).
> Release history prior to v1.0.0 lives in that archived repository.


## Unreleased


- **DLB Password Derivation Allocations**: Reuse PBKDF2 HMAC state and digest storage without changing derived keys or iteration counts; add Python-compatible key vectors and synthetic viewer performance benchmarks.
