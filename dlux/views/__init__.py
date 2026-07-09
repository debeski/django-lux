# Views Package — Re-exports all view functions and classes
# so that `from . import views` and `views.XYZ` in urls.py keeps working.

# General / Dashboard / Preferences
from .general import (
    debug_notifications_view,
    email_send_test_view,
    export_system_settings_view,
    force_password_change_all_view,
    global_search_view,
    options_view,
    system_setup_view,
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
    system_backup_status_view,
    system_backup_upload_view,
    system_restore_start_view,
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

# Inline DjangoLux updater
from .updater import (
    dlux_update_apply_view,
    dlux_update_check_view,
    dlux_update_image_view,
    dlux_update_rollback_view,
    dlux_update_run_view,
    dlux_update_runtime_health,
    dlux_update_state_view,
)
