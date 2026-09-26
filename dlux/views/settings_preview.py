"""System Settings previews: accept a draft, and render the sample pages.

The pages a preview shows are real — the login page, the configured homepage,
the page behind the Options modal. Tables, forms, modals and components are not
on screen while settings are being edited, so a preview of those renders one of
the sample pages here: ordinary dlux pages built from the same shells, tables,
ribbon and form helpers as any project page. They exist only inside a preview
request; outside one they are a 404.
"""

import datetime

import django_filters
import django_tables2 as tables
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from ..system import preview as settings_preview
from ..tables import DluxTable
from ..translations import get_current_language_code, get_strings

SAMPLE_KINDS = ('table', 'form', 'modal', 'components')


def _reverse(name, *args, **kwargs):
    try:
        return reverse(name, args=args or None, kwargs=kwargs or None)
    except NoReverseMatch:
        return ''


def _preview_targets(draft):
    """Where each kind of preview points. The client adds the token."""
    from ..system.normalizers import normalize_homepage_config

    targets = {
        'login': {'path': _reverse('login'), 'audience': 'anonymous'},
        'home_user': {'path': '/', 'audience': ''},
        'profile': {'path': _reverse('user_profile'), 'audience': ''},
    }
    try:
        homepage = normalize_homepage_config(getattr(draft, 'homepage_config', None) or {})
        default_url = str(homepage.get('default_url') or '').strip()
        if default_url.startswith('/'):
            targets['home_user']['path'] = default_url
    except Exception:
        pass
    if getattr(draft, 'public_root', False):
        public_url = str(getattr(draft, 'public_root_url', '') or '').strip() or '/'
        targets['home_public'] = {'path': public_url if public_url.startswith('/') else '/', 'audience': 'anonymous'}
    for kind in SAMPLE_KINDS:
        targets[f'sample_{kind}'] = {'path': _reverse('system_settings_preview_sample', kind=kind), 'audience': ''}
    return {key: value for key, value in targets.items() if value.get('path')}


@login_required
@require_POST
def system_settings_preview_draft_view(request):
    """Validate an unsaved settings form and hand back a preview token.

    The body is the settings form exactly as it would be submitted, plus
    ``_dlux_preview_kind`` (``system`` or ``app``), ``_dlux_preview_mode``
    (``setup`` for the first-run wizard) and, for app settings,
    ``_dlux_preview_namespace``. An Options step editor adds ``?step=N`` to the
    URL, as its own save does, so only that step is validated. Nothing is saved.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    data = request.POST.copy()
    kind = data.pop('_dlux_preview_kind', [settings_preview.KIND_SYSTEM])[0]
    mode = data.pop('_dlux_preview_mode', [''])[0]
    namespace = data.pop('_dlux_preview_namespace', [''])[0]
    data.pop('csrfmiddlewaretoken', None)
    try:
        step = int(request.GET.get('step'))
    except (TypeError, ValueError):
        step = None
    if kind not in (settings_preview.KIND_SYSTEM, settings_preview.KIND_APP):
        return JsonResponse({'ok': False, 'errors': {'__all__': ['Unknown preview kind.']}}, status=400)

    try:
        if kind == settings_preview.KIND_APP:
            draft = settings_preview.build_app_draft(request, data, namespace=namespace)
        else:
            draft = settings_preview.build_system_draft(request, data, mode=mode, step=step)
    except settings_preview.DraftInvalid as exc:
        return JsonResponse({'ok': False, 'errors': exc.errors}, status=400)

    token = settings_preview.store_draft(request, kind=kind, data=data, mode=mode, namespace=namespace, step=step)
    languages = getattr(draft, 'languages', None) or {}
    return JsonResponse({
        'ok': True,
        'token': token,
        'param': settings_preview.PREVIEW_PARAM,
        'as_param': settings_preview.AS_PARAM,
        'lang_param': settings_preview.LANG_PARAM,
        'language': getattr(draft, 'default_language', '') or 'en',
        'languages': [
            {'code': code, 'name': (meta or {}).get('name', code), 'dir': (meta or {}).get('dir', 'ltr')}
            for code, meta in (languages.items() if isinstance(languages, dict) else [])
        ],
        'targets': _preview_targets(draft),
    })


# ── Sample pages ───────────────────────────────────────────────────────────


def _sample_rows(strings):
    today = datetime.date.today()
    statuses = [
        strings.get('preview_sample_status_active', 'Active'),
        strings.get('preview_sample_status_pending', 'Pending'),
        strings.get('preview_sample_status_closed', 'Closed'),
    ]
    names = [
        strings.get('preview_sample_row_1', 'Quarterly supply contract'),
        strings.get('preview_sample_row_2', 'Office equipment order'),
        strings.get('preview_sample_row_3', 'Annual maintenance visit'),
        strings.get('preview_sample_row_4', 'Staff training programme'),
        strings.get('preview_sample_row_5', 'Archive digitisation batch'),
        strings.get('preview_sample_row_6', 'Network upgrade request'),
        strings.get('preview_sample_row_7', 'Vehicle fleet renewal'),
        strings.get('preview_sample_row_8', 'Public tender publication'),
    ]
    return [
        {
            'number': f'2026/{index + 101}',
            'name': name,
            'status': statuses[index % len(statuses)],
            'date': today - datetime.timedelta(days=index * 9),
            'amount': f'{(index + 3) * 1250:,}.00',
        }
        for index, name in enumerate(names)
    ]


class SamplePreviewTable(DluxTable):
    number = tables.Column()
    name = tables.Column()
    status = tables.Column()
    date = tables.DateColumn()
    amount = tables.Column(attrs={'td': {'class': 'text-end'}})

    class Meta(DluxTable.Meta):
        dlux_actions = False
        orderable = False

    def __init__(self, *args, strings=None, **kwargs):
        super().__init__(*args, **kwargs)
        strings = strings or {}
        labels = {
            'number': strings.get('preview_sample_col_number', 'Number'),
            'name': strings.get('preview_sample_col_name', 'Subject'),
            'status': strings.get('preview_sample_col_status', 'Status'),
            'date': strings.get('preview_sample_col_date', 'Date'),
            'amount': strings.get('preview_sample_col_amount', 'Amount'),
        }
        for name, label in labels.items():
            self.columns[name].column.verbose_name = label


class SamplePreviewFilter(django_filters.FilterSet):
    keyword = django_filters.CharFilter(method='noop')
    year = django_filters.NumberFilter(method='noop')
    status = django_filters.ChoiceFilter(method='noop')
    date_gte = django_filters.DateFilter(method='noop')
    date_lte = django_filters.DateFilter(method='noop')
    is_active = django_filters.BooleanFilter(method='noop')

    class Meta:
        model = get_user_model()
        fields = []

    def __init__(self, *args, strings=None, **kwargs):
        super().__init__(*args, **kwargs)
        strings = strings or {}
        self.filters['status'].extra['choices'] = [
            ('active', strings.get('preview_sample_status_active', 'Active')),
            ('pending', strings.get('preview_sample_status_pending', 'Pending')),
            ('closed', strings.get('preview_sample_status_closed', 'Closed')),
        ]
        self.filters['keyword'].label = strings.get('preview_sample_filter_keyword', 'Search')
        self.filters['year'].label = strings.get('preview_sample_filter_year', 'Year')
        self.filters['status'].label = strings.get('preview_sample_col_status', 'Status')
        self.filters['date_gte'].label = strings.get('preview_sample_col_date', 'Date')
        self.filters['is_active'].label = strings.get('preview_sample_filter_active', 'Active only')

    def noop(self, queryset, name, value):
        return queryset


class SamplePreviewForm(forms.Form):
    """Every widget family a project form is made of, through dlux's normaliser."""

    subject = forms.CharField(max_length=120)
    reference = forms.CharField(max_length=40, required=False)
    category = forms.ChoiceField()
    issued_on = forms.DateField(required=False)
    amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2)
    notes = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, strings=None, **kwargs):
        super().__init__(*args, **kwargs)
        from ..utils import set_field_attrs

        strings = strings or {}
        self.fields['subject'].label = strings.get('preview_sample_col_name', 'Subject')
        self.fields['reference'].label = strings.get('preview_sample_col_number', 'Number')
        self.fields['category'].label = strings.get('preview_sample_field_category', 'Category')
        self.fields['category'].choices = [
            ('', '---------'),
            ('supplies', strings.get('preview_sample_row_1', 'Quarterly supply contract')),
            ('services', strings.get('preview_sample_row_3', 'Annual maintenance visit')),
        ]
        self.fields['issued_on'].label = strings.get('preview_sample_col_date', 'Date')
        self.fields['amount'].label = strings.get('preview_sample_col_amount', 'Amount')
        self.fields['notes'].label = strings.get('preview_sample_field_notes', 'Notes')
        self.fields['is_active'].label = strings.get('preview_sample_status_active', 'Active')
        self.initial.setdefault('subject', strings.get('preview_sample_row_1', 'Quarterly supply contract'))
        set_field_attrs(self)


def _sample_ribbon(request, strings, filterset):
    from ..ribbon import build_action, build_ribbon
    from ..ribbon.tabs import build_ribbon_tabs

    actions = [
        build_action({
            'label': strings.get('preview_sample_action_add', 'Add Record'),
            'icon': 'bi bi-plus-lg',
            'css_class': 'btn btn-primary rounded-pill',
        }, request=request),
        build_action({
            'label': strings.get('preview_sample_action_export', 'Export'),
            'icon': 'bi bi-download',
            'css_class': 'btn btn-outline-primary rounded-pill',
        }, request=request),
    ]
    return build_ribbon(
        filterset,
        request=request,
        title=strings.get('preview_sample_table_title', 'Sample Records'),
        title_icon='bi bi-table',
        subtitle=strings.get('preview_sample_table_subtitle', 'How list pages look with these settings.'),
        primary=('keyword', 'year', 'status'),
        advanced=('date_gte', 'date_lte', 'is_active'),
        actions=[action for action in actions if action is not None],
        tabs=[
            build_ribbon_tabs({
                'param': 'sample_status',
                'items': [
                    {'key': '', 'label': strings.get('preview_sample_tab_all', 'All')},
                    {'key': 'active', 'label': strings.get('preview_sample_status_active', 'Active')},
                    {'key': 'closed', 'label': strings.get('preview_sample_status_closed', 'Closed')},
                ],
            }, request=request, strings=strings),
            # A second strip, so the administrator's nesting choice shows.
            build_ribbon_tabs({
                'param': 'sample_year',
                'relation': 'child',
                'items': [
                    {'key': '', 'label': strings.get('preview_sample_tab_all', 'All')},
                    {'key': '2026', 'label': '2026'},
                    {'key': '2025', 'label': '2025'},
                ],
            }, request=request, strings=strings),
        ],
    )


@login_required
def system_settings_preview_sample_view(request, kind):
    """One of the sample pages. Only reachable inside a settings preview."""
    if not settings_preview.is_preview_request(request) or kind not in SAMPLE_KINDS:
        raise Http404
    strings = get_strings(get_current_language_code(request))
    context = {'DLUX_STRINGS': strings, 'page_title': strings.get('preview_sample_page_title', 'Preview')}

    if kind == 'table':
        from django_tables2 import RequestConfig

        rows = _sample_rows(strings)
        filterset = SamplePreviewFilter(request.GET or None, queryset=get_user_model().objects.none(), strings=strings)
        table = SamplePreviewTable(rows, strings=strings)
        RequestConfig(request, paginate={'per_page': 5}).configure(table)
        context.update({'table': table, 'filter': filterset, 'ribbon': _sample_ribbon(request, strings, filterset),
                        'sample_rows': rows[:3]})
        return render(request, 'dlux/system/preview_samples/table.html', context)

    if kind == 'form':
        context['form'] = SamplePreviewForm(strings=strings)
        return render(request, 'dlux/system/preview_samples/form.html', context)

    if kind == 'modal':
        context['modal_content_url'] = settings_preview.carry_preview(
            reverse('system_settings_preview_sample_modal'), request,
        )
        context['modal_title'] = strings.get('preview_sample_modal_title', 'Edit Record')
        return render(request, 'dlux/system/preview_samples/modal.html', context)

    context['sample_rows'] = _sample_rows(strings)[:3]
    return render(request, 'dlux/system/preview_samples/components.html', context)


@login_required
def system_settings_preview_sample_modal_view(request):
    """The dynamic-modal body the sample modal page opens: a real modal form."""
    if not settings_preview.is_preview_request(request):
        raise Http404
    strings = get_strings(get_current_language_code(request))
    html = render_to_string(
        'dlux/helpers/dynamic_modal_combined.html',
        {
            'form': SamplePreviewForm(strings=strings),
            'table': None,
            'model': None,
            'instance': None,
            'DLUX_STRINGS': strings,
            'hide_form_buttons': False,
        },
        request=request,
    )
    return JsonResponse({'html': html})
