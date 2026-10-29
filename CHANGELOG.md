# Changelog

This file owns the release history for `django-lux`.

> `django-lux` is the renamed, actively-maintained successor to
> [`django-microsys`](https://github.com/debeski/django-microsys) (now archived).
> Release history prior to v1.0.0 lives in that archived repository.


## Unreleased


- **DLB Large-model Browsing**: Add bounded private temporary indexes for repeated deep pages with streaming fallback; reduce relation-label parser allocations, preserve loading feedback, and isolate asynchronous views from stale responses.

- **Composer Wrapper 5 In The Scaffold**: `startproject` writes Composer wrapper 5 (`start.sh`/`start.ps1`, byte-identical to Composer 1.9.1b1): `./start.sh update` refreshes the Composer deployer before the stack and resident pair, `./start.sh update self` updates only the deployer, and `self update` is a deprecated alias. DjangoLux's own "Composer too old" guidance keeps `./start.sh self update`, which also works on older wrappers; tracked in `docs/deprecation-countdown.md`. No runtime change.
