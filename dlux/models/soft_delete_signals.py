"""Signals sent when ScopedModel rows are soft-deleted or restored.

A leaf module (only `django.dispatch`), so the model layer can announce the
change without importing the features that react to it. Senders are the model
classes; `ScopedModel` and `ScopedQuerySet` only gather the arguments when a
receiver is connected for that model.
"""

from django.dispatch import Signal

#: kwargs: ``pks`` (list), ``deleted_at``, ``deleted_by_id``
soft_deleted = Signal()
#: kwargs: ``deleted_at_by_pk`` ({pk: the deleted_at the row had})
restored = Signal()
