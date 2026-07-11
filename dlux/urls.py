# Imports of the required python modules and libraries
######################################################
from django.urls import path
from . import views, utils, api
from django.contrib.auth import views as auth_views

# app_name = 'dlux'

urlpatterns = [
    # Auth URLs (Django defaults - no prefix needed when mounted at root)
    path('accounts/login/', views.CustomLoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/session-ended/', views.session_ended_view, name='session_ended'),
    path('accounts/session-keepalive/', views.session_keepalive_view, name='session_keepalive'),
    path('accounts/register/', views.register_view, name='register'),
    path('accounts/register/sent/', views.register_sent_view, name='register_sent'),
    path('accounts/register/verify/<str:token>/', views.register_verify_view, name='register_verify'),

    # Forgot-password / reset flow (Dlux login-style, gated by forgot_password_enabled)
    path('accounts/password-reset/', views.DluxPasswordResetView.as_view(), name='password_reset'),
    path('accounts/password-reset/sent/', views.DluxPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', views.DluxPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/reset/done/', views.DluxPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('accounts/profile/', views.user_profile, name='user_profile'),
    path('accounts/welcome/', views.initial_user_setup, name='initial_user_setup'),
    path('accounts/profile/sessions/<str:session_key>/revoke/', views.revoke_profile_session, name='revoke_profile_session'),
    path('accounts/profile/device/trust/', views.trust_current_device, name='trust_current_device'),
    path('accounts/profile/edit/<str:pk>/modal/', views.DynamicModalManagerView.as_view(
        model=views.User,
        form_class=views.UserProfileEditForm,
        show_table=False,
    ), name='modal_profile_edit'),
    
    # System URLs (all prefixed with sys/)
    # path('sys/', views.dashboard, name='sys_dashboard'),
    path('sys/setup/', views.system_setup_view, name='system_setup'),
    path('sys/settings/export/', views.export_system_settings_view, name='system_settings_export'),
    path('sys/settings/email/send-test/', views.email_send_test_view, name='email_send_test'),
    path('sys/users/', views.UserListView.as_view(), name='manage_users'),
    path('sys/registrations/', views.pending_registrations_view, name='pending_registrations'),
    path('sys/registrations/<int:pk>/approve/', views.approve_registration_view, name='approve_registration'),
    path('sys/registrations/<int:pk>/reject/', views.reject_registration_view, name='reject_registration'),

    # User Modal CRUD (dedicated route with custom form)
    path('sys/modals/users/', views.DynamicModalManagerView.as_view(
        model=views.User,
        form_class=views.CustomUserCreationForm,
        show_table=False,
    ), name='modal_user'),
    path('sys/modals/users/<str:pk>/', views.DynamicModalManagerView.as_view(
        model=views.User,
        form_class=views.CustomUserChangeForm,
        show_table=False,
    ), name='modal_user_edit'),
    path('sys/modals/users/<str:pk>/permissions/', views.DynamicModalManagerView.as_view(
        model=views.User,
        form_class=views.CustomUserPermissionsForm,
        show_table=False,
    ), name='modal_user_permissions'),
    # User Detail Modal
    path('sys/users/<int:pk>/modal/', views.UserDetailModalView.as_view(), name='user_detail_modal'),
    path('sys/users/<int:pk>/report/', views.user_report_modal_view, name='user_report_modal'),
    path('sys/users/<int:pk>/report.xlsx', views.user_report_xlsx_view, name='user_report_xlsx'),
    # User Reset Password
    path('sys/reset_password/<int:pk>/', views.reset_password, name='reset_password'),
    # User Activity Log URLs
    path('sys/logs/', views.UserActivityLogView.as_view(), name='user_activity_log'),
    path('sys/logs/<int:pk>/details/', views.ActivityLogDetailView.as_view(), name='user_activity_log_detail'),
    # Reports URLs
    path('sys/reports/', views.reports_overview_view, name='reports_overview'),
    path('sys/reports/export.xlsx', views.reports_overview_xlsx_view, name='reports_overview_xlsx'),
    path('sys/reports/backup.zip', views.reports_backup_zip_view, name='reports_backup_zip'),
    path('sys/reports/backup/start/', views.reports_backup_start_view, name='reports_backup_start'),
    path('sys/reports/backup/<str:token>/status/', views.reports_backup_status_view, name='reports_backup_status'),
    path('sys/reports/backup/<str:token>/download/', views.reports_backup_download_view, name='reports_backup_download'),
    # System Backup & Restore URLs (superuser only)
    path('sys/backup/', views.system_backup_page, name='system_backup_page'),
    path('sys/backup/create/', views.system_backup_create_view, name='system_backup_create'),
    path('sys/backup/upload/', views.system_backup_upload_view, name='system_backup_upload'),
    path('sys/backup/status/', views.system_backup_list_status_view, name='system_backup_list_status'),
    path('sys/backup/restore/', views.system_restore_start_view, name='system_restore_start'),
    path('sys/backup/restore/<str:token>/status/', views.system_restore_status_view, name='system_restore_status'),
    path('sys/backup/<str:token>/status/', views.system_backup_status_view, name='system_backup_status'),
    path('sys/backup/<str:token>/download/', views.system_backup_download_view, name='system_backup_download'),
    path('sys/backup/<str:token>/delete/', views.system_backup_delete_view, name='system_backup_delete'),
    # Scope Management URLs
    path('sys/scopes/manage/', views.manage_scopes, name='manage_scopes'),
    path('sys/scopes/form/', views.get_scope_form, name='get_scope_form'),
    path('sys/scopes/form/<int:pk>/', views.get_scope_form, name='get_scope_form'),
    path('sys/scopes/save/', views.save_scope, name='save_scope'),
    path('sys/scopes/save/<int:pk>/', views.save_scope, name='save_scope'),
    path('sys/scopes/delete/<int:pk>/', views.delete_scope, name='delete_scope'),
    path('sys/scopes/<int:pk>/detail/', views.scope_detail, name='scope_detail'),
    path('sys/scopes/<int:pk>/public-registration-default/', views.toggle_scope_public_registration_default, name='toggle_scope_public_registration_default'),
    path('sys/scopes/toggle/', views.toggle_scopes, name='toggle_scopes'),
    path('sys/scopes/toggle-auto/', views.toggle_auto_scopes, name='toggle_auto_scopes'),
    # Permission Group / Preset Management URLs
    path('sys/groups/manage/', views.manage_groups, name='manage_groups'),
    path('sys/groups/form/', views.get_group_form, name='get_group_form'),
    path('sys/groups/form/<int:pk>/', views.get_group_form, name='get_group_form'),
    path('sys/groups/save/', views.save_group, name='save_group'),
    path('sys/groups/save/<int:pk>/', views.save_group, name='save_group'),
    path('sys/groups/<int:pk>/members/', views.group_members, name='group_members'),
    path('sys/groups/<int:pk>/members/save/', views.save_group_members, name='save_group_members'),
    path('sys/groups/<int:pk>/public-registration-default/', views.toggle_group_public_registration_default, name='toggle_group_public_registration_default'),
    # Sections Management URLs
    path('sys/options/', views.options_view, name='options_view'),
    path('sys/options/app-settings/<str:namespace>/', views.app_settings_modal_view, name='dlux_app_settings_modal'),
    path('sys/api/celery-health/', views.celery_health_check_view, name='celery_health_check'),
    path('sys/admin/force-password-change-all/', views.force_password_change_all_view, name='dlux_force_pass_change_all'),
    path('sys/admin/data-reset/preview/', views.data_reset_preview_view, name='dlux_data_reset_preview'),
    path('sys/admin/data-reset/execute/', views.data_reset_execute_view, name='dlux_data_reset_execute'),
    path('search/', views.global_search_view, name='global_search'),
    path('sys/debug/notifications/', views.debug_notifications_view, name='debug_notifications'),
    path('sys/sections/', views.core_models_view, name='manage_sections'),
    path('sys/subsection/add/', views.add_subsection, name='add_subsection'),
    path('sys/subsection/edit/<int:pk>/', views.edit_subsection, name='edit_subsection'),
    path('sys/subsection/delete/<int:pk>/', views.delete_subsection, name='delete_subsection'),
    path('sys/section/delete/', views.delete_section, name='delete_section'),
    path('sys/section/details/', views.get_section_details, name='get_section_details'),
    # 2FA URLs
    path('sys/2fa/verify/enable/', views.verify_otp_view, {'intent': 'enable'}, name='verify_otp_enable'), # Maps to generic enable if needed, or specific
    path('sys/2fa/verify/login/', views.verify_otp_view, {'intent': 'login'}, name='verify_otp_login'),
    path('sys/2fa/verify/', views.verify_otp_view, name='verify_otp_generic'),
    path('sys/2fa/enable/', views.enable_2fa, name='enable_2fa'),
    path('sys/2fa/setup/totp/', views.setup_totp, name='setup_totp'),
    path('sys/2fa/disable/', views.disable_2fa, name='disable_2fa'),
    path('sys/2fa/backup-codes/generate/', views.generate_backup_codes, name='generate_backup_codes'),
    path('sys/2fa/resend/<str:intent>/', views.resend_otp, name='resend_otp'), # Generic resend
    path('sys/2fa/resend/', views.resend_otp, {'intent': 'login'}, name='resend_otp_login'),
    # Sidebar Toggle URL
    path('sys/toggle-sidebar/', utils.toggle_sidebar, name='toggle_sidebar'),
    # Autofill API
    path('sys/api/last-entry/<str:app_label>/<str:model_name>/', api.get_last_entry, name='api_get_last_entry'),
    # model details API
    path('sys/api/details/<str:app_label>/<str:model_name>/empty_schema/', api.get_model_details, {'pk': 'empty_schema'}, name='api_get_empty_schema'),
    path('sys/api/details/<str:app_label>/<str:model_name>/<int:pk>/', api.get_model_details, name='api_get_model_details'),
    # preferences API
    path('sys/api/preferences/update/', api.update_preferences, name='update_preferences'),
    path('sys/api/preferences/reset/', api.reset_preferences, name='reset_preferences'),
    path('sys/api/preferences/app/<str:namespace>/', api.update_app_preference, name='update_app_preference'),
    # System-level app-owned config (superuser only)
    path('sys/api/system-config/app/<str:namespace>/', api.update_app_system_config, name='update_app_system_config'),
    # notifications API
    path('sys/api/notifications/', api.notifications_list, name='notifications_list'),
    path('sys/api/notifications/read-all/', api.notifications_mark_all_read, name='notifications_read_all'),
    path('sys/api/notifications/clear-all/', api.notifications_clear_all, name='notifications_clear_all'),
    path('sys/api/notifications/<int:pk>/read/', api.notification_mark_read, name='notification_mark_read'),
    path('sys/api/notifications/<int:pk>/dismiss/', api.notification_dismiss, name='notification_dismiss'),
    # Generated-Compose DjangoLux updater
    path('sys/api/dlux-update/runtime-health/', views.dlux_update_runtime_health, name='dlux_update_runtime_health'),
    path('sys/api/dlux-update/state/', views.dlux_update_state_view, name='dlux_update_state'),
    path('sys/api/dlux-update/check/', views.dlux_update_check_view, name='dlux_update_check'),
    path('sys/api/dlux-update/apply/', views.dlux_update_apply_view, name='dlux_update_apply'),
    path('sys/api/dlux-update/image/', views.dlux_update_image_view, name='dlux_update_image'),
    path('sys/api/dlux-update/rollback/', views.dlux_update_rollback_view, name='dlux_update_rollback'),
    path('sys/api/dlux-update/runs/<str:token>/', views.dlux_update_run_view, name='dlux_update_run'),
    # Dynamic Modal CRUD
    path('sys/modals/manager/<str:app_label>/<str:model_name>/<str:pk>/', views.DynamicModalManagerView.as_view(), name='modal_manager'),
    path('sys/modals/delete/<str:app_label>/<str:model_name>/<int:pk>/', views.DynamicModalDeleteView.as_view(), name='modal_delete'),
]
