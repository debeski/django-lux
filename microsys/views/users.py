# Fundemental imports
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.module_loading import import_string
from django_filters.views import FilterView
from django_tables2 import RequestConfig, SingleTableView
from django.views.generic.detail import DetailView

# Project imports
from ..utils import is_scope_enabled, is_staff, is_superuser, log_user_action, get_client_ip, get_user_linked_models
from ..translations import get_strings
from .twofa import send_otp



User = get_user_model() # Use custom user model


# Authentication — Custom login with 2FA intercept, language injection, and dynamic redirect
class CustomLoginView(LoginView):
    redirect_authenticated_user = True  # Automatically redirect logged-in users

    def form_valid(self, form):
        """
        Intercept login. If 2FA enabled, redirect to OTP verification.
        """
        user = form.get_user()
        
        # Check if 2FA is enabled for this user's profile
        if hasattr(user, 'profile') and user.profile.is_2fa_enabled:
            # 1. Send OTP
            send_otp(self.request, user, intent='login')
            
            # 2. Store user ID in session (partially authenticated)
            self.request.session['pre_2fa_user_id'] = user.pk
            
            # 3. Redirect to verification page
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

        return context

    def get_success_url(self):
        """
        Custom redirect logic to prioritize branding 'home_url'.
        Order: 1. ?next=, 2. MICROSYS_CONFIG['home_url'], 3. settings.LOGIN_REDIRECT_URL
        """
        # 1. Standard Django behavior (checks 'next' param)
        url = self.get_redirect_url()
        if url:
            return url
            
        # 2. Check System Config for home_url
        from microsys.utils import get_system_config
        config_dict = get_system_config()
        home_url = config_dict.get('home_url')
            
        if home_url:
            from django.shortcuts import resolve_url
            try:
                return resolve_url(home_url)
            except:
                return home_url

        # 3. Fallback to settings.LOGIN_REDIRECT_URL
        return getattr(settings, 'LOGIN_REDIRECT_URL', '/sys/')


# User Management — List view with filtering, pagination, and scope-aware queryset
class UserListView(LoginRequiredMixin, UserPassesTestMixin, FilterView, SingleTableView):
    model = User
    table_class = import_string('microsys.tables.UserTable')
    filterset_class = import_string('microsys.filters.UserFilter')  # Set the filter class to apply filtering
    template_name = "microsys/users/manage_users.html"
    paginate_by = 10
    
    # Restrict access to only staff users
    def test_func(self):
        return self.request.user.is_staff

    
    def get_queryset(self):
        # Apply the filter and order by any logic you need
        qs = super().get_queryset().order_by('date_joined')
        # Exclude soft-deleted users by checking profile's deleted_at
        qs = qs.filter(profile__deleted_at__isnull=True)
        
        # Hide superuser entries from non-superusers
        if not self.request.user.is_superuser:
            qs = qs.exclude(is_superuser=True)
            # Restrict to same scope
            if hasattr(self.request.user, 'profile') and self.request.user.profile.scope:
                qs = qs.filter(profile__scope=self.request.user.profile.scope)
        return qs

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs['translations'] = get_strings()
        kwargs['request'] = self.request
        return kwargs

    def get_table(self, **kwargs):
        table = super().get_table(**kwargs)
        # Hide scope column when scopes are off, or when user is already scoped
        if not is_scope_enabled():
            table.exclude = ('scope',)
        elif hasattr(self.request.user, 'profile') and self.request.user.profile.scope and not self.request.user.is_superuser:
            table.exclude = ('scope',)
        return table

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_filter = self.get_filterset(self.filterset_class)
        from ..utils import setup_filter_helper
        setup_filter_helper(user_filter, self.request)
        
        scope_enabled = is_scope_enabled()
        
        context["filter"] = user_filter
        context["users"] = user_filter.qs
        context["scope_enabled"] = scope_enabled
        
        # Disabling scopes is only safe if no users are currently assigned to any scope
        can_toggle_scope = True
        if scope_enabled:
            can_toggle_scope = not User.objects.filter(profile__scope__isnull=False).exists()
        
        context["can_toggle_scope"] = can_toggle_scope

        # Add Reset Password Form for Modal (Dummy user to generate fields)
        if self.request.user.is_authenticated:
            ResetPasswordForm = import_string('microsys.forms.ResetPasswordForm')
            context["form_reset"] = ResetPasswordForm(user=self.request.user)
            
        return context


# User Management — Handles new user creation with scope auto-assignment
@user_passes_test(is_staff)
def create_user(request):
    CustomUserCreationForm = import_string('microsys.forms.CustomUserCreationForm')
    linked_models = get_user_linked_models()
    
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST or None, user=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            # Auto-assign scope for non-superusers
            if not request.user.is_superuser and hasattr(request.user, 'profile') and request.user.profile.scope:
                # This logic is handled inside form.save via passed params.
                pass 
                
            user = form.save() # Saves user + profile
            
            # --- Dynamic Profile Auto-Enrollment ---
            for lm in linked_models:
                checkbox_name = f"create_profile_{lm['app_label']}_{lm['model_name']}"
                if request.POST.get(checkbox_name) == 'on':
                    model_class = apps.get_model(lm['app_label'], lm['model_name'])
                    kwargs = {lm['field_name']: user}
                    
                    # Try to populate 'name' if defined on the model
                    field_names = [f.name for f in model_class._meta.get_fields()]
                    if 'name' in field_names:
                        kwargs['name'] = user.get_full_name() or user.username
                        
                    model_class.objects.get_or_create(**kwargs)
            # ---------------------------------------
            
            return redirect("manage_users")
        else:
            return render(request, "microsys/users/user_form.html", {"form": form, "linked_models": linked_models})
    else:
        form = CustomUserCreationForm(user=request.user)
    
    return render(request, "microsys/users/user_form.html", {"form": form, "linked_models": linked_models})


# User Management — Handles user editing with superuser/scope protection
@user_passes_test(is_staff)
def edit_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    ResetPasswordForm = import_string('microsys.forms.ResetPasswordForm')
    CustomUserChangeForm = import_string('microsys.forms.CustomUserChangeForm')
    # 🚫 Superusers can only be edited by THEMSELVES
    if user.is_superuser and request.user != user:
        messages.error(request, "ليس لديك صلاحية لتعديل هذا الحساب!")
        return redirect('manage_users')


    # Restrict to same scope
    if not request.user.is_superuser:
        user_scope = user.profile.scope if hasattr(user, 'profile') else None
        requester_scope = request.user.profile.scope if hasattr(request.user, 'profile') else None
        
        if requester_scope and user_scope != requester_scope:
             messages.error(request, "ليس لديك صلاحية لتعديل هذا المستخدم!")
             return redirect('manage_users')

    form_reset = ResetPasswordForm(user, data=request.POST or None)

    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=user, user=request.user)
        if form.is_valid():
            user = form.save() # Saves user + profile
            return redirect("manage_users")
        else:
            # Validation errors will be automatically handled by the form object
            return render(request, "microsys/users/user_form.html", {"form": form, "edit_mode": True, "form_reset": form_reset})

    else:
        form = CustomUserChangeForm(instance=user, user=request.user)

    return render(request, "microsys/users/user_form.html", {"form": form, "edit_mode": True, "form_reset": form_reset})


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
        user_scope = user.profile.scope if hasattr(user, 'profile') else None
        requester_scope = request.user.profile.scope if hasattr(request.user, 'profile') else None
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
@user_passes_test(is_staff)
def reset_password(request, pk):
    user = get_object_or_404(User, id=pk)
    ResetPasswordForm = import_string('microsys.forms.ResetPasswordForm')

    # 🚫 Superusers can only have their password reset by THEMSELVES
    if user.is_superuser and request.user != user:
        messages.error(request, "ليس لديك صلاحية لتعديل هذا الحساب!")
        return redirect('manage_users')

    # Restrict to same scope
    if not request.user.is_superuser:
        user_scope = user.profile.scope if hasattr(user, 'profile') else None
        requester_scope = request.user.profile.scope if hasattr(request.user, 'profile') else None
        if requester_scope and user_scope != requester_scope:
             messages.error(request, "ليس لديك صلاحية لتعديل هذا المستخدم!")
             return redirect('manage_users')

    if request.method == "POST":
        form = ResetPasswordForm(user=user, data=request.POST)  # ✅ Correct usage with SetPasswordForm
        if form.is_valid():
            form.save()
            log_user_action(request, "RESET", instance=user, model_name="password")
            return redirect("manage_users")
        else:
            print("Form errors:", form.errors)
            return redirect("edit_user", pk=pk)
    
    return redirect("manage_users")  # Fallback redirect


# User Management — Full-page user detail view with activity log table
class UserDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = User
    template_name = "microsys/users/user_detail.html"

    def test_func(self):
        # only staff can view user detail page
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # self.object is the User instance
        UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
        logs_qs = UserActivityLog.objects.filter(created_by=self.object).order_by('-created_at')
        
        # Create table manually
        UserActivityLogTableNoUser = import_string('microsys.tables.UserActivityLogTableNoUser')
        table = UserActivityLogTableNoUser(logs_qs, translations=get_strings())
        RequestConfig(self.request, paginate={'per_page': 10}).configure(table)
        
        context['table'] = table
        return context


# User Management — Quick-view modal for user details and recent activity
class UserDetailModalView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = User
    context_object_name = 'target_user'
    template_name = 'microsys/users/user_detail_modal.html'

    def test_func(self):
        # only staff can view user detail
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
        
        # Get last 10 logs for this user
        context['recent_logs'] = UserActivityLog.objects.filter(created_by=user).order_by('-created_at')[:10]
        return context


