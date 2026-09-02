# Fundemental imports
import logging

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from datetime import timedelta

from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.module_loading import import_string
from django_filters.views import FilterView
from django_tables2 import SingleTableView
from django.views.generic.detail import DetailView

# Project imports
from ..system.constants import DEFAULT_HOME_URL
from ..forms import DluxAuthenticationForm
from ..notifications import notify
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
from ..reports.users import build_user_report, build_user_report_xlsx
from ..ribbon import RibbonMixin
from ..translations import get_strings


logger = logging.getLogger('dlux')
User = get_user_model() # Use custom user model


# Authentication — Custom login with 2FA intercept, language injection, and dynamic redirect
class CustomLoginView(LoginView):
    redirect_authenticated_user = True  # Automatically redirect logged-in users
    authentication_form = DluxAuthenticationForm

    def post(self, request, *args, **kwargs):
        """Reject the attempt up front if this IP/username is currently locked out."""
        from ..auth.login_throttle import login_lockout_remaining
        remaining = login_lockout_remaining(request, request.POST.get('username', ''))
        if remaining > 0:
            # Don't flash a toast/notification (it auto-dismisses and pops the
            # notification bar). Render the login page with the exact remaining
            # seconds so the form shows a persistent live countdown notice under
            # the submit button instead. Render the initial message server-side
            # too (progressive enhancement) so the notice is never blank even if
            # the JS is cached/stale — login.js only upgrades it to a live tick.
            s = get_strings()
            template = s.get('login_lockout_countdown', 'Too many failed attempts. Try again in {time}.')
            display = '%02d:%02d' % (remaining // 60, remaining % 60)
            try:
                lockout_message = template.replace('{time}', display)
            except Exception:
                lockout_message = template
            form = self.get_form_class()(request)
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    lockout_remaining=remaining,
                    lockout_message=lockout_message,
                ),
                status=429,
            )
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        """Count the failed password attempt toward the lockout threshold."""
        from ..auth.login_throttle import register_failed_login
        register_failed_login(self.request, self.request.POST.get('username', ''))
        return super().form_invalid(form)

    def form_valid(self, form):
        """
        Intercept login. If 2FA enabled, redirect to OTP verification.
        """
        from ..auth.login_throttle import clear_failed_logins
        clear_failed_logins(self.request, self.request.POST.get('username', ''))
        user = form.get_user()
        
        # Check if 2FA is enabled for this user's profile
        if hasattr(user, 'profile') and user.profile.is_2fa_enabled:
            from django.shortcuts import resolve_url
            from .twofa import get_trusted_device_for_login, prepare_login_2fa_challenge, _sync_session_device_metadata
            from ..auth.trust import enforce_single_active_session
            from dlux.utils import get_system_config, normalize_homepage_config

            trusted_device = get_trusted_device_for_login(self.request, user)
            if trusted_device:
                response = super().form_valid(form)
                _sync_session_device_metadata(self.request, trusted_device=trusted_device)
                enforce_single_active_session(self.request, user)
                return response

            next_url = self.get_redirect_url() or ''
            default_redirect = ''
            if not next_url:
                config_dict = get_system_config()
                if user.is_superuser and not config_dict.get('is_configured', False):
                    default_redirect = resolve_url('system_setup')
                else:
                    home_url = normalize_homepage_config(
                        config_dict.get('homepage_config') or config_dict
                    )['default_url']
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

        # Standard Login (no 2FA): enforce single active session on success too.
        from ..auth.trust import enforce_single_active_session
        response = super().form_valid(form)
        enforce_single_active_session(self.request, user)
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from ..utils import get_system_config
        config = get_system_config()
        allow_lang_override = bool(config.get('allow_user_language_override', True))

        # Only honour ?lang= when the system permits language switching
        lang_param = self.request.GET.get('lang')
        if allow_lang_override and lang_param in config.get('languages', {'ar', 'en'}):
            self.request.session['lang'] = lang_param

        context['DLUX_STRINGS'] = get_strings()
        context['allow_language_override'] = allow_lang_override
        login_cfg = config.get('login', {})
        context['login_config'] = login_cfg
        # Resolve hero message for the current language
        hero = login_cfg.get('hero_message', '')
        if isinstance(hero, dict):
            current_lang = self.request.session.get('lang') or config.get('default_language', 'en')
            hero = hero.get(current_lang) or next(iter(hero.values()), '') if hero else ''
        context['login_hero_message'] = hero
        from ..auth.registration import public_registration_config
        context['public_registration_enabled'] = public_registration_config().get('enabled', False)
        from ..auth.password_reset import forgot_password_available
        context['forgot_password_enabled'] = forgot_password_available()

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
        from dlux.utils import get_system_config, normalize_homepage_config, resolve_user_home_url
        from django.shortcuts import resolve_url
        config_dict = get_system_config()
        if self.request.user.is_superuser and not config_dict.get('is_configured', False):
            return resolve_url('system_setup')

        # 3. Per-user landing page (user_home_url) — only when the admin allows it.
        user_home_url = resolve_user_home_url(self.request.user, config_dict)
        if user_home_url:
            try:
                return resolve_url(user_home_url)
            except Exception:
                return user_home_url

        home_url = normalize_homepage_config(
            config_dict.get('homepage_config') or config_dict
        )['default_url']

        if home_url:
            from django.shortcuts import resolve_url
            try:
                return resolve_url(home_url)
            except:
                return home_url

        # 3. Fallback to settings.LOGIN_REDIRECT_URL
        return getattr(settings, 'LOGIN_REDIRECT_URL', DEFAULT_HOME_URL)


def session_ended_view(request):
    """Anonymous interstitial shown to a browser whose session was force-ended (single
    active-session eviction, or a remote 'sign out this device'). It is a deliberate
    dead-end: a single button back to home — which, when the public home is disabled,
    resolves to the login page."""
    from ..utils import get_system_config, normalize_homepage_config

    config = get_system_config()
    homepage = normalize_homepage_config(config.get('homepage_config') or config)
    if homepage['public']['enabled']:
        home_target = homepage['default_url']
        target_is_login = False
    else:
        home_target = reverse('login')
        target_is_login = True

    return render(request, 'dlux/system/session_ended.html', {
        'DLUX_STRINGS': get_strings(),
        'home_target': home_target,
        'target_is_login': target_is_login,
        'reason': str(request.GET.get('reason') or 'ended').strip(),
    })


@login_required
def session_keepalive_view(request):
    """Lightweight endpoint the inactivity-countdown modal pings when the user
    chooses "Stay signed in". Touching the session lets DluxMiddleware refresh
    ``dlux_last_activity`` on this request, resetting the idle window. Returns the
    live idle window so the client can re-sync its countdown."""
    from ..utils import get_system_config

    config = get_system_config()
    enabled = bool(config.get('inactivity_timeout_enabled', False))
    try:
        minutes = int(config.get('inactivity_timeout_minutes', 10) or 10)
    except (TypeError, ValueError):
        minutes = 10
    # Force a session write so the middleware's throttled activity refresh sticks.
    # Epoch float, matching DluxMiddleware's dlux_last_activity bookkeeping.
    request.session['dlux_last_activity'] = timezone.now().timestamp()
    return JsonResponse({
        'ok': True,
        'inactivity_timeout_enabled': enabled,
        'inactivity_timeout_seconds': max(0, minutes) * 60,
    })


# User Management — List view with filtering, pagination, and scope-aware queryset
class UserListView(RibbonMixin, LoginRequiredMixin, UserPassesTestMixin, FilterView, SingleTableView):
    model = User
    table_class = import_string('dlux.tables.UserTable')
    filterset_class = import_string('dlux.filters.UserFilter')  # Set the filter class to apply filtering
    template_name = "dlux/users/manage_users.html"
    ribbon_title_icon = 'bi bi-people'

    def _ribbon_strings(self):
        from ..translations import get_current_language_code

        return get_strings(get_current_language_code(self.request))

    def get_ribbon_title(self):
        return self._ribbon_strings().get('manage_users', 'User Management')

    def get_ribbon_subtitle(self):
        return self._ribbon_strings().get('manage_users_desc', '')

    def get_ribbon_actions(self):
        s = self._ribbon_strings()
        specs = [{
            'label': s.get('add_user', 'Add New User'),
            'icon': 'bi bi-person-plus-fill',
            'css_class': 'btn btn-primary rounded-pill',
            'attrs': {
                'data-dynamic-modal': reverse('modal_user'),
                'data-modal-title': s.get('add_user', 'Add New User'),
            },
        }]
        if is_scope_enabled() and self.request.user.is_superuser:
            specs.append({
                'label': s.get('manage_scopes_btn', 'Manage Scopes'),
                'icon': 'bi bi-list',
                'css_class': 'btn btn-info rounded-pill',
                'attrs': {'id': 'btn-manage-scopes', 'data-url': reverse('manage_scopes')},
            })
        if self.request.user.has_perm('dlux.manage_groups') or self.request.user.is_superuser:
            specs.append({
                'label': s.get('manage_groups_btn', 'Manage Groups'),
                'icon': 'bi bi-people-fill',
                'css_class': 'btn btn-info rounded-pill',
                'attrs': {'id': 'btn-manage-groups', 'data-url': reverse('manage_groups')},
            })
        from ..ribbon import build_action

        return [build_action(spec, request=self.request) for spec in specs]

    def get_paginate_by(self, queryset):
        # Let django-tables2 own pagination. Applying ListView pagination here
        # causes the table to paginate an already-sliced page subset.
        return None
    
    def test_func(self):
        return user_can_view_user_directory(self.request.user)

    
    def get_queryset(self):
        # Apply the filter and order by any logic you need
        PresenceSession = apps.get_model('dlux', 'UserPresenceSession')
        online_cutoff = timezone.now() - timedelta(minutes=5)
        qs = (
            super().get_queryset()
            .select_related('profile__scope', 'public_registration')
            .prefetch_related('user_permissions__content_type', 'groups__permissions__content_type')
            .annotate(
                is_online=Exists(
                    PresenceSession.objects.filter(
                        user=OuterRef('pk'),
                        last_seen_at__gte=online_cutoff,
                    )
                )
            )
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
        # FilterView already built and bound one; reusing it keeps the ribbon,
        # the table and this view on the same instance.
        user_filter = context.get("filter") or self.get_filterset(self.filterset_class)
        
        scope_enabled = is_scope_enabled()
        
        ScopeSettings = apps.get_model('dlux', 'ScopeSettings')
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
            ResetPasswordForm = import_string('dlux.forms.ResetPasswordForm')
            context["form_reset"] = ResetPasswordForm(user=self.request.user, prefix='reset_password')
            
        return context

# User Management — Soft-deletes a user (deactivate + rename for reuse)
from django.contrib.auth.decorators import permission_required
@permission_required('auth.delete_user', raise_exception=True)
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    s = get_strings()

    # Explicitly prevent self-deletion just in case
    if user == request.user:
        notify.error(s.get('err_cannot_delete_self'), request=request, action='user_delete_self_denied', category='users', metadata={'message_key': 'err_cannot_delete_self'})
        return redirect('manage_users')

    # Prevent deletion of any superuser by a non-superuser
    if user.is_superuser and not request.user.is_superuser:
        notify.error(s.get('err_cannot_delete_superuser'), request=request, action='user_delete_superuser_denied', category='users', metadata={'message_key': 'err_cannot_delete_superuser'})
        return redirect('manage_users')

    # Prevent deletion of the final superuser
    if user.is_superuser and User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
        notify.error(s.get('err_cannot_delete_last_superuser'), request=request, action='user_delete_last_superuser_denied', category='users', metadata={'message_key': 'err_cannot_delete_last_superuser'})
        return redirect('manage_users')

    # Restrict to same scope
    if not request.user.is_superuser:
        user_scope = get_user_scope(user)
        requester_scope = get_user_scope(request.user)
        if requester_scope and user_scope != requester_scope:
            notify.error(s.get('err_no_delete_permission_user'), request=request, action='user_delete_scope_denied', category='users', metadata={'message_key': 'err_no_delete_permission_user'})
            return redirect('manage_users')

    if request.method == "POST":
        # Capture original username for logging
        original_username = user.username
        
        # Soft delete the user
        user.is_active = False
        user.skip_signal_logging = True # Prevent "UPDATE" log
        user.save()
        
        # Soft delete the profile
        Profile = apps.get_model('dlux', 'Profile')
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
    ResetPasswordForm = import_string('dlux.forms.ResetPasswordForm')

    if not can_manage_target_user(request.user, user):
        s = get_strings()
        notify.error(s.get('err_no_edit_permission_user_reset'), request=request, action='user_change_denied', category='users', metadata={'message_key': 'err_no_edit_permission_user_reset'})
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
    template_name = 'dlux/users/user_detail_modal.html'

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
            UserActivityLog = apps.get_model('dlux', 'ActivityLog')
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

    def render_to_response(self, context, **response_kwargs):
        # The dynamic-modal shell consumes the `{html: …}` contract, the same as
        # every sibling action in the user row menu.
        html = render_to_string(self.template_name, context, request=self.request)
        return JsonResponse({'html': html})


@login_required
def user_report_modal_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if not user_can_view_user_report(request.user, target_user):
        raise PermissionDenied

    window = request.GET.get('window') or 'week'
    report = build_user_report(target_user, actor=request.user, window=window)
    context = {
        'DLUX_STRINGS': get_strings(),
        'report': report,
        'target_user': target_user,
        'xlsx_url': reverse('user_report_xlsx', args=[target_user.pk]),
    }
    html = render_to_string('dlux/users/user_report_modal.html', context, request=request)
    return JsonResponse({'html': html})


@login_required
def user_report_xlsx_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if not user_can_view_user_report(request.user, target_user):
        raise PermissionDenied

    window = request.GET.get('window') or 'week'
    report = build_user_report(target_user, actor=request.user, window=window)
    content = build_user_report_xlsx(report, window=window)
    filename = f"dlux-user-report-{target_user.pk}-{report['selected_window']}.xlsx"
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
