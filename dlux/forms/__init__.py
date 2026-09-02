"""Dlux forms.

Facade over the forms package: every name that was importable from the old
`dlux.forms` module is re-exported here, so `from dlux.forms import X` keeps
working for this package and for downstream projects.
"""

from ._shared import (  # noqa: F401
    FONT_CHOICES,
    THEME_CHOICES,
    User,
    _LEGACY_HOME_URL,
    _json_dump,
    logger,
)
from .permissions import (  # noqa: F401
    DLUX_PERMISSION_HELP_TEXTS,
    GroupedPermissionWidget,
    PERMISSION_UI_EXCLUDED_APP_LABELS,
    _apply_assignable_permission_filter,
    _extract_permission_codenames,
    _get_assignable_permission_ids_for_user,
    get_assignable_permissions_queryset,
)
from .builders import (  # noqa: F401
    EMAIL_DEPENDENT_SETTING_FIELDS,
    _TITLEBAR_ACTION_META,
    _bind_choice_selector_widget,
    _boolean_field_checked,
    _build_archive_file_widget,
    _build_file_widget,
    _build_cancel_button_html,
    _build_submit_actions,
    _build_submit_only_actions,
    _build_wizard_actions,
    _get_ui_direction,
    _wrap_modal_action_buttons,
    build_archive_file_field,
    build_asset_field,
    build_file_field,
    build_email_test_control,
    build_email_toggle_field,
    build_settings_toggle_field,
    build_titlebar_actions_order_builder,
)
from .assets import (  # noqa: F401
    AssetPickerField,
    AssetPickerWidget,
    AssetSelection,
)
from .asset_fields import (  # noqa: F401
    ManagedAssetFormMixin,
    apply_asset_pickers,
    apply_asset_selections,
    build_asset_picker,
    managed_asset_fields,
    resolve_asset_selection,
)
from .auth import (  # noqa: F401
    CustomPasswordChangeForm,
    DluxAuthenticationForm,
    DluxPasswordMustChangeMixin,
    ResetPasswordForm,
    _apply_autocomplete_attrs,
)
from .registration import (  # noqa: F401
    PublicRegistrationForm,
)
from .scopes import (  # noqa: F401
    GroupMembersForm,
    GroupPresetForm,
    ScopeForm,
)
from .users import (  # noqa: F401
    ProfileImageWidget,
    CustomUserChangeForm,
    CustomUserCreationForm,
    CustomUserPermissionsForm,
    UserModalForm,
    UserProfileEditForm,
    _attach_is_staff_permission,
    _build_staff_tier_preview_catalog,
    _configure_staff_tier_preview,
    _maybe_add_group_presets_field,
)
from .system_settings import (  # noqa: F401
    EMAIL_CONNECTION_FIELDS,
    SystemSettingsForm,
    _system_settings_sidebar_tools_available,
)

__all__ = [
    'AssetPickerField',
    'AssetPickerWidget',
    'AssetSelection',
    'CustomPasswordChangeForm',
    'CustomUserChangeForm',
    'CustomUserCreationForm',
    'CustomUserPermissionsForm',
    'DLUX_PERMISSION_HELP_TEXTS',
    'DluxAuthenticationForm',
    'DluxPasswordMustChangeMixin',
    'EMAIL_CONNECTION_FIELDS',
    'EMAIL_DEPENDENT_SETTING_FIELDS',
    'FONT_CHOICES',
    'GroupMembersForm',
    'GroupPresetForm',
    'GroupedPermissionWidget',
    'PERMISSION_UI_EXCLUDED_APP_LABELS',
    'ProfileImageWidget',
    'PublicRegistrationForm',
    'ResetPasswordForm',
    'ScopeForm',
    'SystemSettingsForm',
    'THEME_CHOICES',
    'User',
    'UserModalForm',
    'UserProfileEditForm',
    'ManagedAssetFormMixin',
    'apply_asset_pickers',
    'apply_asset_selections',
    'build_asset_picker',
    'build_archive_file_field',
    'build_asset_field',
    'build_file_field',
    'managed_asset_fields',
    'resolve_asset_selection',
    'build_email_test_control',
    'build_email_toggle_field',
    'build_settings_toggle_field',
    'build_titlebar_actions_order_builder',
    'get_assignable_permissions_queryset',
    'logger',
]
from .lookup import DluxLookupField  # noqa: F401
