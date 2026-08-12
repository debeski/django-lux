"""Destructive superuser-only operations, kept together deliberately.

Both are irreversible, gated on `is_superuser`, confirmed with the operator's
password in the UI, and audit-logged. Grouping them means the two most dangerous
operations in the app can be read and tested as a pair rather than found by
grep — `force_password_change` in particular was a private helper inside
`views/general.py`, reachable only through its view.

The views stay in :mod:`dlux.views.general`; this package holds the logic they
call. Both are reached from the Admin panel command rail in
`templates/dlux/system/options.html`.
"""
