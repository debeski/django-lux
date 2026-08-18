# Views Package — Re-exports all view functions and classes
# so that `from . import views` and `views.XYZ` in urls.py keeps working.

# System Options / Setup / Service health
from .options import (
    data_reset_execute_view,
    data_reset_preview_view,
    celery_health_check_view,
    debug_notifications_view,
    email_config_apply_view,
    email_health_check_view,
    email_send_test_view,
    export_system_settings_view,
    force_password_change_all_view,
    app_settings_modal_view,
    options_view,
    system_setup_view,
)
from .search import global_search_view
from .scanlink import (
    scanlink_download,
    scanlink_release_upload,
    scanlink_releases_modal,
    scanlink_toggle,
    scanlink_update_manifest,
)
from .settings_import import (
    settings_import_preview_view,
    settings_import_review_view,
    settings_import_apply_view,
    settings_import_revert_view,
)

# Authentication & User Management
from .users import (
    CustomLoginView,
    UserListView,
    UserDetailModalView,
    delete_user,
    reset_password,
    session_ended_view,
    session_keepalive_view,
    user_report_modal_view,
    user_report_xlsx_view,
    User,
)
from ..forms import (
    CustomUserCreationForm,
    CustomUserChangeForm,
    CustomUserPermissionsForm,
    UserModalForm,
    UserProfileEditForm,
)

# 2FA
from .twofa import (
    send_otp,
    verify_otp_logic,
    get_2fa_config,
    verify_otp_view,
    setup_totp,
    enable_2fa,
    disable_2fa,
    resend_otp,
    generate_backup_codes,
)

# Section Management
from .sections import (
    core_models_view,
    add_subsection,
    edit_subsection,
    delete_subsection,
    delete_section,
    get_section_details,
    DynamicModalManagerView,
    DynamicModalDeleteView,
)

from .sidebar import toggle_sidebar  # noqa: F401
from .scopes import (
    manage_scopes,
    get_scope_form,
    save_scope,
    delete_scope,
    scope_detail,
    toggle_scope_public_registration_default,
    toggle_scopes,
    toggle_auto_scopes,
)

# Permission Groups / Presets
from .groups import (
    manage_groups,
    get_group_form,
    save_group,
    group_members,
    save_group_members,
    toggle_group_public_registration_default,
)

# Activity Log
from .activitylog import (
    UserActivityLogView,
    ActivityLogDetailView,
)

# System backup & restore
from .backup import (
    system_backup_create_view,
    system_backup_delete_view,
    system_backup_download_view,
    system_backup_list_status_view,
    system_backup_page,
    system_backup_resume_view,
    system_backup_status_view,
    system_backup_upload_view,
    system_restore_start_view,
    system_restore_list_status_view,
    system_restore_status_view,
)

# Reports
from .reports import (
    reports_backup_download_view,
    reports_backup_start_view,
    reports_backup_status_view,
    reports_backup_zip_view,
    reports_overview_view,
    reports_overview_xlsx_view,
    reports_print_view,
)

# Profile
from .profile import initial_user_setup, revoke_profile_session, trust_current_device, user_profile

# Public registration
from .registration import (
    approve_registration_view,
    pending_registrations_view,
    register_sent_view,
    register_verify_view,
    register_view,
    reject_registration_view,
)

# Forgot-password / reset flow
from .password_reset import (
    DluxPasswordResetCompleteView,
    DluxPasswordResetConfirmView,
    DluxPasswordResetDoneView,
    DluxPasswordResetView,
)

# Inline DjangoLux updater
from .updater import (
    dlux_update_apply_view,
    dlux_update_check_view,
    dlux_update_skip_view,
    dlux_update_image_view,
    dlux_update_rollback_view,
    dlux_update_run_view,
    dlux_update_runtime_health,
    dlux_update_state_view,
)

# Control Panel pairing tile
from .control_link import (
    control_panel_cancel_view,
    control_panel_connect_view,
    control_panel_page,
    control_panel_status_view,
)

from .assets import asset_manager_delete, asset_manager_page
