# Fundemental imports
from django.apps import apps
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

# Project imports
from django.utils.module_loading import import_string
from ..utils import log_user_action
from ..translations import get_strings
from .twofa import get_2fa_config


# Profile View — Displays user profile with stats, activity timeline, and password change
@login_required
def user_profile(request):
    CustomPasswordChangeForm = import_string('microsys.forms.CustomPasswordChangeForm')
    user = request.user
    
    # Use dynamic form
    password_form = CustomPasswordChangeForm(user)
    
    if request.method == 'POST':
        # ... existing POST logic ...
        password_form = CustomPasswordChangeForm(user, request.POST)
        if password_form.is_valid():
            password_form.save()
            log_user_action(request, "UPDATE", instance=user, model_name="password")
            update_session_auth_hash(request, password_form.user)
            s = get_strings()
            messages.success(request, s.get('msg_password_changed', 'Password changed successfully!'))
            return redirect('user_profile')
        else:
            s = get_strings()
            messages.error(request, s.get('msg_form_error', "There was an error with the submitted data"))
            print(password_form.errors)

    # --- Profile Stats & Activity ---
    UserActivityLog = apps.get_model('microsys', 'UserActivityLog')
    
    # 1. Stats
    total_actions = UserActivityLog.objects.filter(created_by=user).count()
    docs_created = UserActivityLog.objects.filter(created_by=user, action='CREATE').count()
    total_edits = UserActivityLog.objects.filter(created_by=user, action='UPDATE').count()
    total_downloads = UserActivityLog.objects.filter(created_by=user, action__in=['DOWNLOAD', 'EXPORT']).count()
    
    # 2. Activity Feeds
    # Split by app ownership:
    # - `system_interactions`: logs related to microsys app models.
    # - `recent_activity`: logs from all other apps.
    def _normalize_model_name(value):
        return str(value).strip().casefold() if value else ""

    microsys_model_names = set()
    try:
        microsys_app = apps.get_app_config('microsys')
        for model in microsys_app.get_models():
            meta = model._meta
            microsys_model_names.update({
                _normalize_model_name(meta.model_name),
                _normalize_model_name(meta.object_name),
                _normalize_model_name(meta.verbose_name),
                _normalize_model_name(meta.verbose_name_plural),
            })
    except LookupError:
        pass

    # Virtual and legacy labels used by microsys logging helpers/signals.
    microsys_model_names.update({
        "auth",
        "user",
        "profile",
        "scope",
        "scopesettings",
        "useractivitylog",
        "user profile",
        "password",
        "preferences",
    })

    def _is_microsys_log(log_entry):
        model_key = _normalize_model_name(log_entry.model_name)
        action_key = _normalize_model_name(log_entry.action)
        if action_key in {"login", "logout"}:
            return True
        if not model_key:
            return False
        if model_key in microsys_model_names:
            return True
        # Support explicit "app_label.ModelName" payloads if logged that way.
        if "." in model_key:
            return model_key.split(".", 1)[0] == "microsys"
        return False

    recent_activity = []
    system_interactions = []
    all_user_logs = UserActivityLog.objects.filter(created_by=user).order_by('-created_at')[:200]

    for log in all_user_logs:
        if _is_microsys_log(log):
            if len(system_interactions) < 5:
                system_interactions.append(log)
        else:
            if len(recent_activity) < 5:
                recent_activity.append(log)
        if len(system_interactions) >= 5 and len(recent_activity) >= 5:
            break

    # 3. Completeness & Health
    completeness = 0
    if user.first_name and user.last_name:
        completeness += 25
    if user.email:
        completeness += 25
        
    # Check profile fields safely
    user_phone = None
    user_pic = None
    if hasattr(user, 'profile'):
        user_phone = user.profile.phone
        user_pic = user.profile.profile_picture
        if user.profile.is_2fa_enabled: # Count 2FA as one item (replacing Pic or adding as bonus?)
             # Let's say we have 4 criteria: Name, Email, Phone, 2FA (Pic is optional/bonus or we restart scale)
             # User requested "only one [2fa method] should count".
             pass 

    # Re-evaluating completeness based on user feedback to include 2FA appropriately
    # Let's do 5 items x 20%: Name, Email, Phone, Picture, 2FA
    completeness = 0
    if user.first_name and user.last_name: completeness += 20
    if user.email: completeness += 20
    if hasattr(user, 'profile'):
        if user.profile.phone: completeness += 20
        if user.profile.profile_picture: completeness += 20
        if user.profile.is_2fa_enabled: completeness += 20
        
    # 4. Health
    account_health = 'good' if user.is_active and user.profile.is_2fa_enabled else 'attention'

    # 5. Missing Definitions
    profile = getattr(user, 'profile', None)
    joined_date = user.date_joined
    last_login_date = user.last_login

    stats = {
        'total_actions': total_actions,
        'docs_created': docs_created,
        'total_edits': total_edits,
        'total_downloads': total_downloads,
        'completeness': completeness, # Passed to template even if not used in cards, used in progress bar
        'health': account_health,     # Used in Health section
    }

    context = {
        'user': request.user, # Ensure user is passed if template uses it directly
        'profile': profile,
        'password_form': password_form,
        'stats': stats,
        'recent_activity': recent_activity,
        'system_interactions': system_interactions,
        'total_actions': total_actions, # If used
        'joined_date': joined_date,     # If used
        'last_login_date': last_login_date, # If used
        'role': 'Admin' if request.user.is_staff else 'User',
        'config_2fa': get_2fa_config(), # Inject 2FA availability
    }

    return render(request, 'microsys/users/profile.html', context)

