"""Authentication domain logic.

Registration rules, password reset eligibility, password strength, login
throttling, device trust and session presence — the parts of the auth surface
that are neither a form nor a view.

Layer first, feature inside: the forms stay in :mod:`dlux.forms.auth` and the
views in :mod:`dlux.views`, exactly as every other feature is arranged. This
package holds only what those two layers call into, so it is a peer of
``dlux.system`` and ``dlux.discovery`` rather than a vertical slice.

Deliberately no blanket re-export: this package never existed as a single
module, so there is no prior surface to preserve, and importers name the module
they need (``from dlux.auth.trust import ...``).

``data_reset`` is not here on purpose — it wipes application data, which is a
destructive admin action; it lives in :mod:`dlux.admin_actions` alongside
``force_password_change``.
"""
