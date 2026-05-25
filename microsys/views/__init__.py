# Views Package — Re-exports all view functions and classes
# so that `from . import views` and `views.XYZ` in urls.py keeps working.

# General / Dashboard / Preferences
from .general import export_system_settings_view, options_view, system_setup_view

# Authentication & User Management
from .users import (
    CustomLoginView,
    UserListView,
    UserDetailModalView,
    delete_user,
    reset_password,
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
    toggle_scopes,
    toggle_auto_scopes,
)

# Activity Log
from .activitylog import (
    UserActivityLogView,
    ActivityLogDetailView,
)

# Profile
from .profile import revoke_profile_session, trust_current_device, user_profile

# Public registration
from .registration import (
    approve_registration_view,
    pending_registrations_view,
    register_sent_view,
    register_verify_view,
    register_view,
    reject_registration_view,
)
