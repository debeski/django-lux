"""``ManagedAssetField`` — a file field that stores through the asset manager.

Declaring one is meant to cost what an ``ImageField`` costs::

    class Product(ScopedModel):
        image = ManagedAssetField(kind='image')

That is a ``ForeignKey`` to ``ManagedAsset`` with the defaults already right
(nullable, blank, ``PROTECT`` so an in-use asset cannot be deleted out from
under a record) plus the two things a picker needs to know: which **kind** of
file belongs here, and which **namespace** the asset lives in.

The namespace defaults to the owning model's ``app_label.modelname``, so the
common case names nothing. A field that should also *see* another pool without
writing into it says so::

    image_override = ManagedAssetField(
        kind='image',
        namespace='public_catalog.listing',
        reads=['catalog.product'],
    )

``namespace`` is where uploads land; ``reads`` widens what the picker lists and
never widens what it writes. Both are form-and-picker concerns rather than
column ones, so neither affects the database.

Authorization rides on the same declaration: the upload endpoint is handed a
field identity, resolves it *here* — server-side, never from the request body —
and asks whether the user may change the model that owns the field. If you can
edit the Product, you can add a Product image.
"""
from django.db import models

from .assets import ASSET_NAMESPACE_MAX_LENGTH

#: ``{'app_label.modelname.fieldname': FieldDeclaration}`` — populated as model
#: classes are prepared. The upload endpoint's only source of truth about what a
#: given picker is allowed to write.
_REGISTRY = {}


class FieldDeclaration:
    """What the server knows about one asset field, keyed by its identity."""

    __slots__ = ('identity', 'model', 'field_name', 'kind', 'namespace', 'reads')

    def __init__(self, *, identity, model, field_name, kind, namespace, reads):
        self.identity = identity
        self.model = model
        self.field_name = field_name
        self.kind = kind
        self.namespace = namespace
        self.reads = tuple(reads)

    @property
    def readable_namespaces(self):
        """Everything the picker may list: the write namespace plus the reads."""
        seen = [self.namespace]
        seen.extend(ns for ns in self.reads if ns not in seen)
        return tuple(seen)

    @property
    def change_permission(self):
        opts = self.model._meta
        return f'{opts.app_label}.change_{opts.model_name}'

    @property
    def add_permission(self):
        opts = self.model._meta
        return f'{opts.app_label}.add_{opts.model_name}'

    def user_may_upload(self, user):
        """Whoever may create or edit the record may add its picture.

        Deliberately not a permission of its own: a separate
        ``add_managedasset`` would have to be invented, seeded, and granted in
        every project to every role that already holds ``change_product``, and
        would then be one more thing to forget.
        """
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        return user.has_perm(self.change_permission) or user.has_perm(self.add_permission)


def register_asset_field(declaration):
    _REGISTRY[declaration.identity] = declaration
    return declaration


def get_asset_field(identity):
    """The declaration for ``app_label.modelname.fieldname``, or None.

    Unknown identities return None rather than raising: the caller is an HTTP
    endpoint handling client input, and a missing declaration is a refusal, not
    a server error.
    """
    return _REGISTRY.get(str(identity or '').strip().lower())


def registered_asset_fields():
    return dict(_REGISTRY)


def default_namespace_for_model(model):
    opts = model._meta
    return f'{opts.app_label}.{opts.model_name}'


class ManagedAssetField(models.ForeignKey):
    """A ``ManagedAsset`` reference that carries its own picker configuration."""

    def __init__(self, to=None, on_delete=None, *, kind='image', namespace='', reads=(), **kwargs):
        self.kind = kind
        # Resolved in contribute_to_class once the owning model is known; an
        # explicit value always wins.
        self._declared_namespace = str(namespace or '')
        self.namespace = self._declared_namespace
        self.reads = tuple(reads or ())
        kwargs.setdefault('null', True)
        kwargs.setdefault('blank', True)
        kwargs.setdefault('related_name', '+')
        super().__init__(
            to or 'dlux.ManagedAsset',
            # An asset in use is not deletable. The asset manager surfaces that
            # as "still referenced" rather than cascading a record's picture out
            # from under it.
            on_delete=on_delete or models.PROTECT,
            **kwargs,
        )

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        if cls._meta.abstract:
            return
        self.namespace = self._declared_namespace or default_namespace_for_model(cls)
        opts = cls._meta
        register_asset_field(FieldDeclaration(
            identity=f'{opts.app_label}.{opts.model_name}.{name}'.lower(),
            model=cls,
            field_name=name,
            kind=self.kind,
            namespace=self.namespace,
            reads=self.reads,
        ))

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs['kind'] = self.kind
        # The *declared* value, not the resolved one: a derived namespace must
        # not freeze into migration history, or renaming a model would need a
        # migration to keep a default that is supposed to follow it.
        if self._declared_namespace:
            kwargs['namespace'] = self._declared_namespace
        if self.reads:
            kwargs['reads'] = list(self.reads)
        if kwargs.get('related_name') == '+':
            kwargs.pop('related_name')
        return name, path, args, kwargs

    @property
    def identity(self):
        opts = self.model._meta
        return f'{opts.app_label}.{opts.model_name}.{self.name}'.lower()

    # No `formfield()` override on purpose. Building the picker here would mean
    # `dlux.models` importing `dlux.forms`, which closes a cycle through
    # `dlux.widgets` — the import guard rejects it, and rightly. The form layer
    # owns that direction: `ManagedAssetFormMixin` (or `apply_asset_pickers`)
    # swaps in the configured `AssetPickerField`.


# Re-exported for callers that build a namespace by hand.
__all__ = [
    'ASSET_NAMESPACE_MAX_LENGTH',
    'FieldDeclaration',
    'ManagedAssetField',
    'default_namespace_for_model',
    'get_asset_field',
    'register_asset_field',
    'registered_asset_fields',
]
