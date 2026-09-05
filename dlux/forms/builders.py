"""Dev-facing layout builders — the documented Dlux form primitives.
See docs/developer-guide.md; these are the sanctioned way to build settings
toggles, email controls, file fields and modal/wizard action bars."""

import json
from crispy_forms.layout import Field, Div, HTML
from crispy_forms.bootstrap import FormActions
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from ..translations import get_current_language_code
from ..utils import normalize_titlebar_actions_order
from ..widgets import DluxFileInput


def _bind_choice_selector_widget(field, widget):
    widget.choices = field.choices
    field.widget = widget


def _get_ui_direction():
    return 'rtl' if get_current_language_code().startswith('ar') else 'ltr'


def _build_cancel_button_html(strings):
    return f"""
    <button type="button" class="btn btn-danger rounded-pill" data-bs-dismiss="modal">
        <i class="bi bi-x-circle text-light me-1 h4"></i> {strings.get('btn_cancel', 'Cancel')}
    </button>
    """


def _wrap_modal_action_buttons(*buttons):
    direction = _get_ui_direction()
    button_html = ''.join(buttons)
    return FormActions(
        HTML(
            f"""
            <div class="d-flex flex-wrap justify-content-end gap-2 dlux-modal-form-actions" dir="{direction}">
                {button_html}
            </div>
            """
        )
    )


def _build_wizard_actions(strings, submit_label, submit_icon):
    direction = _get_ui_direction()
    prev_icon = 'bi-arrow-right-circle' if direction == 'rtl' else 'bi-arrow-left-circle'
    next_icon = 'bi-arrow-left-circle' if direction == 'rtl' else 'bi-arrow-right-circle'

    return _wrap_modal_action_buttons(
        _build_cancel_button_html(strings),
        f"""
        <button type="button" class="btn btn-secondary rounded-pill dlux-btn-prev d-none">
            <i class="bi {prev_icon} text-light me-1 h4"></i> {strings.get('btn_prev', 'Previous')}
        </button>
        """,
        f"""
        <button type="button" class="btn btn-primary rounded-pill dlux-btn-next">
            {strings.get('btn_next', 'Next')} <i class="bi {next_icon} text-light ms-1 h4"></i>
        </button>
        """,
        f"""
        <button type="submit" class="btn btn-success rounded-pill dlux-btn-submit d-none">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )


def _build_submit_actions(strings, submit_label, submit_icon, submit_class='btn btn-success rounded-pill'):
    return _wrap_modal_action_buttons(
        _build_cancel_button_html(strings),
        f"""
        <button type="submit" class="{submit_class}">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )


def _build_submit_only_actions(strings, submit_label, submit_icon, submit_class='btn btn-success rounded-pill'):
    """Modal action bar with just the submit button — no dismiss/cancel. Used by
    surfaces that navigate with an in-modal Back button (e.g. the Groups modal),
    where a Cancel that closes the whole modal is the wrong affordance."""
    return _wrap_modal_action_buttons(
        f"""
        <button type="submit" class="{submit_class}">
            <i class="bi {submit_icon} text-light me-1 h4"></i> {submit_label}
        </button>
        """,
    )


def _build_file_widget(field_label="", show_scan=False, attrs=None):
    return DluxFileInput(attrs=attrs, field_label=field_label, show_scan=show_scan)


def build_file_field(field_name, css_class=None):
    field_kwargs = {'template': 'dlux/forms/crispy_file_field.html'}
    if css_class:
        field_kwargs['css_class'] = css_class
    return Field(field_name, **field_kwargs)


def build_asset_field(field_name, css_class=None):
    """A `ManagedAssetField` in a crispy layout.

    The same wrapper `build_file_field` uses: the asset picker *is* the file
    card, with a library popover added, so it needs no template of its own.
    Kept as a separate name because a layout reads better when it says which
    kind of field it is placing.
    """
    return build_file_field(field_name, css_class=css_class)


# Named for project-archive's document forms, where this widget started. Kept
# importable through v1.x for the host projects still on the old name; removed
# in v1.9.0.
_build_archive_file_widget = _build_file_widget
build_archive_file_field = build_file_field


def _boolean_field_checked(form, field_name):
    field = form.fields[field_name]
    if form.is_bound:
        return bool(field.widget.value_from_datadict(form.data, form.files, form.add_prefix(field_name)))
    if field_name in form.initial:
        return bool(form.initial.get(field_name))
    return bool(field.initial)


EMAIL_DEPENDENT_SETTING_FIELDS = (
    'email_2fa',
    'forgot_password_enabled',
    'public_registration_enabled',
    'notification_email_enabled',
    'notification_email_default',
)


def build_settings_toggle_field(form, field_name, css_class=None, attrs=None, *, fill_height=True):
    bound_field = form[field_name]
    field = bound_field.field
    label = conditional_escape(field.label or field_name.replace('_', ' ').title())
    help_text = str(field.help_text or '').strip()
    help_html = (
        f"<div class='dlux-settings-toggle-field__help small text-muted mt-1'>{conditional_escape(help_text)}</div>"
        if help_text else
        ""
    )
    checked_attr = ' checked' if _boolean_field_checked(form, field_name) else ''
    disabled_attr = ' disabled' if bool(getattr(field, 'disabled', False)) else ''
    # A locked toggle explains itself on hover rather than just being dead.
    lock_reason = str(getattr(field, 'dlux_lock_reason', '') or '').strip()
    lock_attrs = (
        f" data-dlux-tooltip='{conditional_escape(lock_reason)}' aria-disabled='true'"
        if lock_reason else ""
    )
    lock_class = ' dlux-settings-toggle-field--locked dlux-dependent-settings is-disabled' if lock_reason else ''
    height_class = ' h-100' if fill_height else ''
    wrapper_html = mark_safe(
        f"<div class='dlux-settings-toggle-field{lock_class} d-flex justify-content-between align-items-start gap-3 p-3 border rounded bg-light mb-2{height_class}' "
        f"data-dlux-settings-toggle-field='{conditional_escape(field_name)}'{lock_attrs}>"
        f"<div class='dlux-settings-toggle-field__content flex-grow-1'>"
        f"<div class='dlux-settings-toggle-field__label fw-semibold'>{label}</div>"
        f"{help_html}"
        f"</div>"
        f"<div class='dlux-settings-toggle-field__control form-switch'>"
        f"<input class='form-check-input dlux-settings-toggle-field__input' type='checkbox' id='{conditional_escape(bound_field.auto_id)}' "
        f"name='{conditional_escape(bound_field.html_name)}' aria-label='{label}'{checked_attr}{disabled_attr}>"
        f"</div>"
        f"</div>"
    )
    if css_class:
        return Div(HTML(wrapper_html), css_class=css_class, **(attrs or {}))
    return HTML(wrapper_html)


def build_email_test_control(form, send_url, button_label):
    """Recipient input and Send-test button as a single Bootstrap input-group.

    Two grid columns will not stay level here: the field column carries a label
    and help text, so it is taller than the button column, and any vertical
    alignment picks the wrong edge — `end` drops the button below the input,
    `start` lifts it above. An input-group makes them one control, so they are
    level by construction no matter how much text sits above or below.
    """
    bound_field = form['email_config_test_recipient']
    field = bound_field.field
    label = conditional_escape(field.label or 'Send a test email to')
    help_text = str(field.help_text or '').strip()
    help_html = (
        f"<div class='form-text'>{conditional_escape(help_text)}</div>" if help_text else ""
    )
    return Div(
        HTML(
            f"<label class='form-label' for='{conditional_escape(bound_field.auto_id)}'>{label}</label>"
            f"<div class='input-group dlux-email-test-group'>"
            f"{bound_field}"
            f"<button type='button' class='btn btn-outline-primary dlux-email-test-btn' "
            f"data-email-send-test "
            f"data-email-dependent-fields='{','.join(EMAIL_DEPENDENT_SETTING_FIELDS)}' "
            f"data-email-send-test-url='{send_url}'>"
            f"<span class='spinner-border spinner-border-sm me-2 d-none' role='status' "
            f"aria-hidden='true' data-email-send-test-spinner></span>"
            f"{conditional_escape(button_label)}</button>"
            f"</div>"
            f"{help_html}"
        ),
        css_class='col-12',
    )


def build_email_toggle_field(form, field_name, css_class=None, attrs=None):
    bound_field = form[field_name]
    field = bound_field.field
    label = conditional_escape(field.label or field_name.replace('_', ' ').title())
    help_text = str(field.help_text or '').strip()
    help_html = (
        f"<div class='dlux-email-toggle-field__help small text-muted mt-1'>{conditional_escape(help_text)}</div>"
        if help_text else
        ""
    )
    checked_attr = ' checked' if _boolean_field_checked(form, field_name) else ''
    disabled_attr = ' disabled' if bool(getattr(field, 'disabled', False)) else ''
    wrapper_html = mark_safe(
        f"<div class='dlux-email-toggle-field border rounded bg-light px-3 py-2 h-100' "
        f"data-dlux-email-toggle-field='{conditional_escape(field_name)}'>"
        f"<div class='dlux-email-toggle-field__row d-flex align-items-center justify-content-between gap-3'>"
        f"<div class='dlux-email-toggle-field__label fw-semibold'>{label}</div>"
        f"<input class='form-check-input dlux-email-toggle-field__input' type='checkbox' id='{conditional_escape(bound_field.auto_id)}' "
        f"name='{conditional_escape(bound_field.html_name)}' aria-label='{label}'{checked_attr}{disabled_attr}>"
        f"</div>"
        f"{help_html}"
        f"</div>"
    )
    if css_class:
        return Div(HTML(wrapper_html), css_class=css_class, **(attrs or {}))
    return HTML(wrapper_html)


_TITLEBAR_ACTION_META = {
    'search': ('bi-search', 'global_search_placeholder', 'Search'),
    'theme': ('bi-circle-half', 'theme_change', 'Theme'),
    'language': ('bi-translate', 'titlebar_language_switch', 'Language'),
    'notifications': ('bi-bell-fill', 'notifications', 'Notifications'),
    'home': ('bi-house-fill', 'btn_home', 'Home'),
    'profile': ('bi-person-bounding-box', 'profile', 'Profile'),
    'help': ('bi-question-circle-fill', 'help', 'Help'),
    'users': ('bi-people-fill', 'manage_users', 'Users'),
    'activity': ('bi-clock-history', 'activity_log', 'Activity'),
    'reports': ('bi-bar-chart-fill', 'reports_title', 'Reports'),
    'settings': ('bi-gear-fill', 'options_title', 'Settings'),
    'auth': ('bi-box-arrow-right', 'logout', 'Login / Logout'),
}


def build_titlebar_actions_order_builder(order, strings, *, visible=True):
    # `visible` is kept for callers built against the old signature; the builder
    # now renders in both layouts and hides the entries a layout does not offer.
    del visible
    if isinstance(order, str):
        try:
            order = json.loads(order)
        except (TypeError, ValueError, json.JSONDecodeError):
            order = []
    normalized_order = normalize_titlebar_actions_order(order)
    items_html = []
    for action_key in normalized_order:
        icon, label_key, fallback = _TITLEBAR_ACTION_META.get(action_key, ('bi-app', action_key, action_key.title()))
        label = conditional_escape(strings.get(label_key, fallback))
        key = conditional_escape(action_key)
        items_html.append(
            "<div class='dlux-titlebar-action-order-item' "
            f"data-titlebar-action-order-item data-action-key='{key}'>"
            "<span class='dlux-titlebar-action-order-handle' data-titlebar-action-order-handle "
            "draggable='true' role='button' tabindex='-1' aria-label='Reorder'>"
            "<i class='bi bi-grip-vertical' aria-hidden='true'></i></span>"
            f"<span class='dlux-titlebar-action-order-icon'><i class='bi {conditional_escape(icon)}' aria-hidden='true'></i></span>"
            f"<span class='dlux-titlebar-action-order-label'>{label}</span>"
            "<span class='dlux-titlebar-action-order-controls'>"
            "<button type='button' class='btn btn-sm btn-light' data-titlebar-action-move='-1' aria-label='Move up'>"
            "<i class='bi bi-arrow-up-short' aria-hidden='true'></i>"
            "</button>"
            "<button type='button' class='btn btn-sm btn-light' data-titlebar-action-move='1' aria-label='Move down'>"
            "<i class='bi bi-arrow-down-short' aria-hidden='true'></i>"
            "</button>"
            "</span>"
            "</div>"
        )

    hidden_class = ''
    title = conditional_escape(strings.get('titlebar_actions_order_title', 'Titlebar action order'))
    reset_label = conditional_escape(
        strings.get('titlebar_actions_order_reset', 'Reset to the default order')
    )
    help_text = conditional_escape(
        strings.get(
            'titlebar_actions_order_help',
            'Choose the order of the right-side titlebar buttons. Entries the current '
            'layout does not offer are hidden.',
        )
    )
    return mark_safe(
        f"<div class='dlux-titlebar-actions-order-builder border rounded bg-light p-3 mb-3{hidden_class}' "
        "data-titlebar-actions-order-builder>"
        "<div class='d-flex align-items-start justify-content-between gap-3 mb-2'>"
        f"<div><div class='fw-semibold'>{title}</div><div class='small text-muted'>{help_text}</div></div>"
        "<button type='button' class='btn btn-sm btn-light flex-shrink-0' "
        f"data-titlebar-actions-order-reset title='{reset_label}' aria-label='{reset_label}'>"
        "<i class='bi bi-arrow-counterclockwise' aria-hidden='true'></i>"
        "</button>"
        "</div>"
        "<div class='dlux-titlebar-actions-order-list' data-titlebar-actions-order-list>"
        f"{''.join(items_html)}"
        "</div>"
        "</div>"
    )
