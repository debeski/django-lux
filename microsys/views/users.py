# Fundemental imports
import logging

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.module_loading import import_string
from django_filters.views import FilterView
from django_tables2 import SingleTableView
from django.views.generic.detail import DetailView

# Project imports
from ..constants import DEFAULT_HOME_URL
from ..forms import MicrosysAuthenticationForm
from ..utils import (
    can_manage_target_user,
    exclude_global_staff_users,
    get_user_management_tier_state_for_user,
    get_user_scope,
    is_central_staff,
    is_global_staff,
    is_scope_enabled,
    is_staff,
    is_superuser,
    log_user_action,
    user_can_view_activity_log,
    user_can_view_user_report,
    user_can_view_user_directory,
)
from ..user_reports import build_user_report, build_user_report_xlsx
from ..translations import get_strings


logger = logging.getLogger('microsys')
User = get_user_model() # Use custom user model


# Authentication — Custom login with 2FA intercept, language injection, and dynamic redirect
class CustomLoginView(LoginView):
    redirect_authenticated_user = True  # Automatically redirect logged-in users
    authentication_form = MicrosysAuthenticationForm

    def form_valid(self, form):
        """
        Intercept login. If 2FA enabled, redirect to OTP verification.
        """
        user = form.get_user()
        
        # Check if 2FA is enabled for this user's profile
        if hasattr(user, 'profile') and user.profile.is_2fa_enabled:
            from django.shortcuts import resolve_url
            from .twofa import get_trusted_device_for_login, prepare_login_2fa_challenge, _sync_session_device_metadata
            from ..trust import enforce_single_active_trusted_session
            from microsys.utils import get_system_config

            trusted_device = get_trusted_device_for_login(self.request, user)
            if trusted_device:
                response = super().form_valid(form)
                _sync_session_device_metadata(self.request, trusted_device=trusted_device)
                enforce_single_active_trusted_session(self.request, user, trusted_device)
                return response

            next_url = self.get_redirect_url() or ''
            default_redirect = ''
            if not next_url:
                config_dict = get_system_config()
                if user.is_superuser and not config_dict.get('is_configured', False):
                    default_redirect = resolve_url('system_setup')
                else:
                    home_url = config_dict.get('home_url')
                    if home_url:
                        try:
                            default_redirect = resolve_url(home_url)
                        except Exception:
                            default_redirect = home_url
                    else:
                        default_redirect = getattr(settings, 'LOGIN_REDIRECT_URL', DEFAULT_HOME_URL)

            prepare_login_2fa_challenge(
                self.request,
                user,
                next_url=next_url,
                default_redirect=default_redirect,
            )
            return redirect('verify_otp_login')
            
        # Standard Login
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 1. Check for manual language switch via GET param
        lang_param = self.request.GET.get('lang')
        
        # Only set if provided (the helper will read it from session automatically)
        if lang_param in ['ar', 'en']:
            self.request.session['lang'] = lang_param
            
        # 2. Use the smart helper (now handles session automatically)
        context['MS_TRANS'] = get_strings()
        from ..registration import public_registration_config
        context['public_registration_enabled'] = public_registration_config().get('enabled', False)

        return context

    def get_success_url(self):
        """
        Custom redirect logic to prioritize the configured system home URL.
        Order: 1. ?next=, 2. first-launch setup for unconfigured superusers, 3. system-config home_url, 4. settings.LOGIN_REDIRECT_URL
        """
        # 1. Standard Django behavior (checks 'next' param)
        url = self.get_redirect_url()
        if url:
            return url
            
        # 2. Check System Config for home_url
        from microsys.utils import get_system_config
        config_dict = get_system_config()
        if self.request.user.is_superuser and not config_dict.get('is_configured', False):
            from django.shortcuts import resolve_url
            return resolve_url('system_setup')
        home_url = config_dict.get('home_url')
            
        if home_url:
            from django.shortcuts import resolve_url
            try:
                return resolve_url(home_url)
            except:
                return home_url

        # 3. Fallback to settings.LOGIN_REDIRECT_URL
        return getattr(settings, 'LOGIN_REDIRECT_URL', DEFAULT_HOME_URL)


# User Management — List view with filtering, pagination, and scope-aware queryset
class UserListView(LoginRequiredMixin, UserPassesTestMixin, FilterView, SingleTableView):
    model = User
    table_class = import_string('microsys.tables.UserTable')
    filterset_class = import_string('microsys.filters.UserFilter')  # Set the filter class to apply filtering
    template_name = "microsys/users/manage_users.html"

    def get_paginate_by(self, queryset):
        # Let django-tables2 own pagination. Applying ListView pagination here
        # causes the table to paginate an already-sliced page subset.
        return None
    
    def test_func(self):
        return user_can_view_user_directory(self.request.user)

    
    def get_queryset(self):
        # Apply the filter and order by any logic you need
        qs = (
            super().get_queryset()
            .select_related('profile__scope', 'public_registration')
            .prefetch_related('user_permissions__content_type', 'groups__permissions__content_type')
            .order_by('date_joined')
        )
        # Exclude soft-deleted users by checking profile's deleted_at
        qs = qs.filter(profile__deleted_at__isnull=True)
        
        user = self.request.user
        actor_scope = get_user_scope(user)
        
        # Hide superuser entries from non-superusers
        if not user.is_superuser:
            qs = qs.exclude(is_superuser=True)
            
            # Central Staff: can ONLY see scopeless users who are NOT Global Staff
            if is_central_staff(user):
                qs = qs.filter(profile__scope__isnull=True)
                qs = exclude_global_staff_users(qs)
            # Scoped staff: can only see same scope
            elif actor_scope:
                qs = qs.filter(profile__scope=actor_scope)
            elif not is_global_staff(user):
                qs = qs.none()
            # Global Staff: sees all users (no scope filter)
        return qs

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs['translations'] = get_strings()
        kwargs['request'] = self.request
        return kwargs

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        # Hide scope column when scopes are off, or when user is already scoped
        actor_scope = get_user_scope(self.request.user)
        if not is_scope_enabled():
            table.exclude = ('scope',)
        elif actor_scope and not self.request.user.is_superuser:
            table.exclude = ('scope',)
        return table

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_filter = self.get_filterset(self.filterset_class)
        from ..utils import setup_filter_helper
        setup_filter_helper(user_filter, self.request)
        
        scope_enabled = is_scope_enabled()
        
        ScopeSettings = apps.get_model('microsys', 'ScopeSettings')
        settings = ScopeSettings.load()
        auto_scope_enabled = getattr(settings, 'auto_create_user_scope', False)

        context["filter"] = user_filter
        context["users"] = user_filter.qs
        context["scope_enabled"] = scope_enabled
        context["auto_scope_enabled"] = auto_scope_enabled
        
        # Disabling scopes is only safe if no users are currently assigned to any scope
        can_toggle_scope = True
        if scope_enabled:
            can_toggle_scope = not User.objects.filter(profile__scope__isnull=False).exists()
        
        context["can_toggle_scope"] = can_toggle_scope

        # Add Reset Password Form for Modal (Dummy user to generate fields)
        if self.request.user.is_authenticated:
            ResetPasswordForm = import_string('microsys.forms.ResetPasswordForm')
            context["form_reset"] = ResetPasswordForm(user=self.request.user, prefix='reset_password')
            
        return context

# User Management — Soft-deletes a user (deactivate + rename for reuse)
from django.contrib.auth.decorators import permission_required
@permission_required('auth.delete_user', raise_exception=True)
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)

    # Explicitly prevent self-deletion just in case
    if user == request.user:
        messages.error(request, "لا يمكنك حذف حسابك الخاص!")
        return redirect('manage_users')

    # Prevent deletion of any superuser by a non-superuser
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, "ليس لديك صلاحية لحذف المشرفين!")
        return redirect('manage_users')

    # Prevent deletion of the final superuser
    if user.is_superuser and User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
        messages.error(request, "لا يمكن حذف المشرف الرئيسي الأخير للنظام!")
        return redirect('manage_users')

    # Restrict to same scope
    if not request.user.is_superuser:
        user_scope = get_user_scope(user)
        requester_scope = get_user_scope(request.user)
        if requester_scope and user_scope != requester_scope:
             messages.error(request, "ليس لديك صلاحية لحذف هذا المستخدم!")
             return redirect('manage_users')

    if request.method == "POST":
        # Capture original username for logging
        original_username = user.username
        
        # Soft delete the user
        user.is_active = False
        user.skip_signal_logging = True # Prevent "UPDATE" log
        user.save()
        
        # Soft delete the profile
        Profile = apps.get_model('microsys', 'Profile')
        # Use all_objects to include already-deleted profiles
        profile, created = Profile.all_objects.get_or_create(user=user)
        profile.soft_delete()
        
        # Rename username to free it for reuse (e.g. admin -> admin_del, admin_del2)
        base_username = f"{user.username}_del"
        new_username = base_username
        counter = 2
        
        # Check if username_del already exists, increment if needed
        while User.objects.filter(username=new_username).exists():
            new_username = f"{base_username}{counter}"
            counter += 1
        
        user.username = new_username
        user.skip_signal_logging = True # Prevent "UPDATE" log for rename
        user.save()

        # Log the Delete Action with original username
        log_user_action(request, "DELETE", instance=user, model_name="User", number=original_username)

        return redirect("manage_users")
    return redirect("manage_users")  # Redirect instead of rendering a separate page



# User Management — Resets a user's password with superuser/scope protection
@permission_required('auth.change_user', raise_exception=True)
@user_passes_test(is_staff)
def reset_password(request, pk):
    user = get_object_or_404(User, id=pk)
    ResetPasswordForm = import_string('microsys.forms.ResetPasswordForm')

    if not can_manage_target_user(request.user, user):
        messages.error(request, "ليس لديك صلاحية لتعديل هذا المستخدم!", fail_silently=True)
        return redirect('manage_users')

    if request.method == "POST":
        form = ResetPasswordForm(user=user, data=request.POST, prefix='reset_password')  # ✅ Correct usage with SetPasswordForm
        if form.is_valid():
            form.save()
            log_user_action(request, "RESET", instance=user, model_name="password")
            return redirect("manage_users")
        else:
            logger.warning("Password reset validation failed for target user pk=%s", user.pk)
            return redirect("manage_users")
    
    return redirect("manage_users")  # Fallback redirect
# User Management — Quick-view modal for user details and recent activity
class UserDetailModalView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = User
    context_object_name = 'target_user'
    template_name = 'microsys/users/user_detail_modal.html'

    def test_func(self):
        return user_can_view_user_directory(self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_manage_target_user(self.request.user, obj):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        can_view_activity_logs = user_can_view_activity_log(self.request.user)
        recent_logs = []
        if can_view_activity_logs:
            UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
            recent_logs = (
                UserActivityLog._default_manager
                .filter(created_by=user)
                .select_related('created_by__profile__scope')
                .order_by('-created_at')[:10]
            )
        context['can_view_activity_logs'] = can_view_activity_logs
        context['can_view_user_report'] = user_can_view_user_report(self.request.user, user)
        context['recent_logs'] = recent_logs
        context['target_user_management_tier'] = get_user_management_tier_state_for_user(user)
        return context


@login_required
def user_report_modal_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if not user_can_view_user_report(request.user, target_user):
        raise PermissionDenied

    report = build_user_report(target_user)
    context = {
        'MS_TRANS': get_strings(),
        'report': report,
        'target_user': target_user,
        'xlsx_url': reverse('user_report_xlsx', args=[target_user.pk]),
    }
    html = render_to_string('microsys/users/user_report_modal.html', context, request=request)
    return JsonResponse({'html': html})


@login_required
def user_report_xlsx_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if not user_can_view_user_report(request.user, target_user):
        raise PermissionDenied

    report = build_user_report(target_user)
    content = build_user_report_xlsx(report)
    filename = f"microsys-user-report-{target_user.pk}.xlsx"
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
