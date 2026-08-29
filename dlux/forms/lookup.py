"""`DluxLookupField`: a ForeignKey a reader searches by name, and may extend.

    counterparty = DluxLookupField(
        queryset=Party.objects.filter(kind='company'),
        create={'kind': 'company', 'subtype': 'supplier'},
    )

That is the whole of it. The queryset a `ModelChoiceField` already carries *is*
the search scope, so searching costs no configuration at all; only creation has
to be spelled out, because what a new row must be is not derivable. Leave
`create` out and the field searches without ever adding.

Everything else — the control, the rows, the near-match panel, the consent, and
saving a record that did not exist — is handled here and in `dlux.patches`.
"""
from django import forms
from django.core.exceptions import ValidationError

from .. import lookup as lookup_matching
from ..widgets import DluxLookupInput


class DluxLookupField(forms.ModelChoiceField):
    """A ModelChoiceField that accepts a name as well as a key.

    A key posted by the control resolves as it always did. A name resolves
    through `dlux.lookup`: an existing record is reused, a near miss is refused
    with what it resembles, and anything else becomes an unsaved instance that
    `dlux.patches` saves just before the form's own object.

    Unsaved rather than created here on purpose: validating a form must never
    write, or a form that fails a later rule leaves a record behind.
    """

    widget = DluxLookupInput

    def __init__(self, *args, create=None, search_field='name',
                 near_ratio=None, boilerplate_share=None, **kwargs):
        #: What a new record must be, or None to search only. The same mapping
        #: that scopes a queryset is usually the right one here, which keeps a
        #: created record findable by the field that created it.
        self.create = dict(create) if isinstance(create, dict) else (
            {} if create is True else None)
        self.search_field = search_field
        super().__init__(*args, **kwargs)
        widget = self.widget
        if isinstance(widget, DluxLookupInput):
            # The control only offers to add when the field can.
            widget.allow_create = self.create is not None
            if near_ratio is not None:
                widget.near_ratio = near_ratio
            if boilerplate_share is not None:
                widget.boilerplate_share = boilerplate_share

    def _records(self):
        return list(self.queryset)

    def _rows(self):
        return [
            {'value': record.pk, 'label': str(getattr(record, self.search_field, record))}
            for record in self._records()
        ]

    def get_bound_field(self, form, field_name):
        """Fill the widget's rows on the way to being rendered.

        Not in `widget_attrs`: that runs inside `Field.__init__`, before
        `ModelChoiceField` has assigned the queryset it would need to read.
        """
        if isinstance(self.widget, DluxLookupInput):
            self.widget.rows = self._rows()
        return super().get_bound_field(form, field_name)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        text = str(value).strip()
        if not text:
            return None
        widget = self.widget

        # A key from the control resolves exactly as a plain ModelChoiceField
        # would, including its "not one of the choices" error.
        if text.isdigit():
            return super().to_python(text)

        records = self._records()
        record, near = lookup_matching.resolve(
            records, text,
            attr=self.search_field,
            allow_new=bool(getattr(widget, 'confirm', False)),
            ratio=getattr(widget, 'near_ratio', lookup_matching.DEFAULT_NEAR_RATIO),
            share=getattr(widget, 'boilerplate_share',
                          lookup_matching.DEFAULT_BOILERPLATE_SHARE),
        )
        if isinstance(widget, DluxLookupInput):
            widget.rows = self._rows()
            widget.typed = text
            widget.near = near

        if record is not None:
            return record
        near_name = str(getattr(near, self.search_field, near)) if near else ''
        if near is not None and self.create is not None:
            raise ValidationError(
                self.error_messages.get('near_match', _near_message()),
                code='near_match',
                params={'name': near_name},
            )
        if self.create is None:
            # A search-only field must not offer to add anything, so a near miss
            # is a suggestion rather than a question: promising "confirm you are
            # adding a new one" here led straight to "no entry called that".
            if near is not None:
                raise ValidationError(
                    self.error_messages.get('did_you_mean', _did_you_mean_message()),
                    code='no_such_record',
                    params={'name': text, 'near': near_name},
                )
            raise ValidationError(
                self.error_messages.get('no_such_record', _missing_message()),
                code='no_such_record',
                params={'name': text},
            )
        # Unsaved: `dlux.patches` writes it immediately before the parent, so a
        # form that fails a later rule never leaves it behind.
        return self.queryset.model(**{self.search_field: text}, **self.create)

    def validate(self, value):
        # ModelChoiceField.validate would reject an unsaved instance for having
        # no primary key; required-ness is all that still applies to one.
        if value is not None and value.pk is None:
            if self.required and not str(getattr(value, self.search_field, '')).strip():
                raise ValidationError(self.error_messages['required'], code='required')
            return
        super().validate(value)


def _near_message():
    from ..translations import get_strings

    return get_strings().get(
        'lookup_near_match_error',
        'A very similar entry already exists: %(name)s. '
        'Pick it, or confirm you are adding a new one.')


def _missing_message():
    from ..translations import get_strings

    return get_strings().get(
        'lookup_no_such_record', 'No entry called %(name)s. Pick one from the list.')


def _did_you_mean_message():
    from ..translations import get_strings

    return get_strings().get(
        'lookup_did_you_mean', 'No entry called %(name)s. Did you mean %(near)s?')
