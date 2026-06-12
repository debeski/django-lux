# Imports of the required python modules and libraries
######################################################
from contextlib import contextmanager

from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete, pre_save
from django.utils.timezone import now
from django.apps import apps
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth import get_user_model
from .middleware import get_current_user, get_current_request
from .utils import (
    SENSITIVE_ACTIVITY_MASK,
    get_client_ip,
    is_sensitive_activity_field_name,
    log_user_action,
)

# Models to exclude from activity logging (e.g., internal Django models with non-integer PKs)
# and high-frequency operational tracking models (presence/device churn that updates every
# few minutes and would otherwise flood the activity log).
EXCLUDED_MODELS = [
    'django.contrib.sessions.models.Session',
    'dlux.models.TrustedDevice',
    'dlux.models.UserKnownDevice',
    'dlux.models.UserPresenceSession',
    # Backup/restore runs log a single explicit EXPORT/RESTORE action; their
    # status churn is not user work.
    'dlux.models.ReportBackup',
    'dlux.models.SystemBackup',
    'dlux.models.SystemRestore',
]

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    """Log user login actions."""
    log_user_action(request, "LOGIN", model_name="auth")

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    """Log user logout actions."""
    log_user_action(request, "LOGOUT", model_name="auth")

@receiver(pre_save)
def capture_original_state(sender, instance, **kwargs):
    """Capture state before save to calculate diffs."""
    # Skip log model itself
    UserActivityLog = apps.get_model('dlux', 'UserActivityLog')
    if sender == UserActivityLog:
        return

    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._original_state = {}
            for field in instance._meta.fields:
                try:
                    val = getattr(old_instance, field.name)
                    # Store simple types, skip binary or large text if needed
                    instance._original_state[field.name] = val
                except Exception:
                    pass
                    
            # Check for soft delete restoration or deletion
            instance._was_not_deleted = (getattr(old_instance, 'deleted_at', None) is None)
        except sender.DoesNotExist:
            pass

@receiver(post_save)
def log_save(sender, instance, created, **kwargs):
    """Log create and update actions for all models."""
    # Prevent infinite recursion by skipping the log model itself
    UserActivityLog = apps.get_model('dlux', 'UserActivityLog')
    if sender == UserActivityLog:
        return
    
    # Skip excluded models (like Session)
    if f"{sender.__module__}.{sender.__name__}" in EXCLUDED_MODELS:
        return

    # Skip if instance explicitly requests no logging
    if getattr(instance, 'skip_signal_logging', False):
        return

    # Get the current user from thread locals
    user = get_current_user()
    if not user or not user.is_authenticated:
        return

    update_fields = kwargs.get('update_fields')
    
    # Ignore implicit updates to last_login (handled by user_logged_in signal)
    if update_fields and 'last_login' in update_fields and len(update_fields) == 1:
        return

    # Ignore Profile preference updates alone (often automated)
    if instance._meta.app_label == 'dlux' and instance._meta.object_name == 'Profile':
        if update_fields and 'preferences' in update_fields and len(update_fields) == 1:
            return

    action = "CREATE" if created else "UPDATE"
    details = {}
    
    # Check for soft delete transition
    if not created and getattr(instance, '_was_not_deleted', False) and getattr(instance, 'deleted_at', None):
        action = "DELETE"
    
    # Compare with original state for updates
    if not created and action == "UPDATE" and hasattr(instance, '_original_state'):
        original = instance._original_state
        for field in instance._meta.fields:
            field_name = field.name
            
            # Skip irrelevant fields
            if field_name in ['last_login', 'date_joined', 'updated_at', 'modified_at', 'created_at', 'created_by', 'updated_by', 'deleted_at', 'deleted_by']:
                continue
                
            try:
                new_val = getattr(instance, field_name)
                old_val = original.get(field_name)
                
                if is_sensitive_activity_field_name(field_name):
                    if new_val != old_val:
                        details[field_name] = {
                            'old': SENSITIVE_ACTIVITY_MASK,
                            'new': SENSITIVE_ACTIVITY_MASK,
                        }
                    continue

                if new_val != old_val:
                    # Format values for display
                    if hasattr(new_val, '__str__'): new_val = str(new_val)
                    if hasattr(old_val, '__str__'): old_val = str(old_val)
                    
                    details[field_name] = {'old': old_val, 'new': new_val}
            except Exception:
                pass

    # Normalize Model and Object ID for User/Profile unification
    is_user_entry = False
    target_user_id = None
    # Stable, locale-independent key ("app_label.model_name"). Left None for the unified
    # User/Profile entry (keyed off its "User Profile" label, which reports already exclude).
    model_key = None

    # Use proper class checks instead of string matching
    User = get_user_model()
    Profile = apps.get_model('dlux', 'Profile')

    if isinstance(instance, User):
        is_user_entry = True
        target_user_id = instance.pk
        model_name = "User Profile" # Logical name for both User and Profile
        obj_id = int(instance.pk)
    elif isinstance(instance, Profile):
        is_user_entry = True
        target_user_id = instance.user_id
        model_name = "User Profile"
        obj_id = int(instance.user_id) # Log against the User ID for unification
    else:
        model_name = instance._meta.verbose_name
        model_key = instance._meta.label_lower
        try:
            obj_id = int(instance.pk) if instance.pk is not None else None
        except (ValueError, TypeError):
            obj_id = None

    # Capture initial state for creations (User/Profile)
    if is_user_entry and created:
        for field in instance._meta.fields:
            if field.name in ['password', 'last_login', 'date_joined', 'updated_at', 'modified_at', 'deleted_at', 'deleted_by', 'created_at', 'created_by', 'updated_by', 'preferences']:
                continue
            val = getattr(instance, field.name)
            if val is not None and val != '':
                if is_sensitive_activity_field_name(field.name):
                    details[field.name] = {'old': None, 'new': SENSITIVE_ACTIVITY_MASK}
                else:
                    details[field.name] = {'old': None, 'new': str(val)}

    # Aggressive Grouping: Look for log in the SAME SECOND
    if is_user_entry:
        # Search for a log created by the same actor for the same target in the last 1 second
        recent_log = UserActivityLog.objects.filter(
            created_by=user,
            model_name="User Profile",
            object_id=obj_id,
            created_at__gte=now().replace(microsecond=0) # Round to the current second
        ).order_by('-created_at').first()
        
        if recent_log:
            # Merge details
            if details:
                if not recent_log.details:
                    recent_log.details = {}
                recent_log.details.update(details)
                
                # If current action is CREATE, promote the log to CREATE
                if action == "CREATE":
                    recent_log.action = "CREATE"
                
                recent_log.save()
            return # Skip creating new log entry

    # Use string representation of the object for 'number' or reference
    try:
        obj_str = str(instance)
    except TypeError:
        # Fallback if __str__ returns non-string (e.g. int)
        obj_str = str(instance.pk)

    request = get_current_request()
    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""

    # Determine target scope
    scope = getattr(instance, 'scope', None)
    if not scope and is_user_entry:
        # For User/Profile, if not directly on instance, check profile
        if isinstance(instance, User) and hasattr(instance, 'profile'):
            scope = instance.profile.scope
        elif isinstance(instance, Profile):
            scope = instance.scope # From Profile model directly

    UserActivityLog.safe_log(
        user=user,
        action=action,
        model_name=model_name,
        model_key=model_key,
        object_id=obj_id,
        number=obj_str[:50] if obj_str else None,
        details=details,
        ip_address=ip,
        user_agent=user_agent,
        scope=scope,
    )

@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    """Log delete actions for all models."""
    UserActivityLog = apps.get_model('dlux', 'UserActivityLog')
    if sender == UserActivityLog:
        return
    
    # Skip excluded models (like Session)
    if f"{sender.__module__}.{sender.__name__}" in EXCLUDED_MODELS:
        return

    user = get_current_user()
    if not user or not user.is_authenticated:
        return

    action = "DELETE"
    # Normalize Model and Object ID for User/Profile unification
    is_user_entry = False
    model_key = None
    User = get_user_model()
    Profile = apps.get_model('dlux', 'Profile')

    if isinstance(instance, User):
        is_user_entry = True
        model_name = "User Profile"
        obj_id = int(instance.pk)
    elif isinstance(instance, Profile):
        is_user_entry = True
        model_name = "User Profile"
        obj_id = int(instance.user_id) # Profile's User ID
    else:
        model_name = instance._meta.verbose_name
        model_key = instance._meta.label_lower
        try:
            obj_id = int(instance.pk) if instance.pk is not None else None
        except (ValueError, TypeError):
            obj_id = None

    # Aggressive Grouping for Delete as well
    if is_user_entry:
        recent_log = UserActivityLog.objects.filter(
            created_by=user,
            model_name="User Profile",
            action="DELETE",
            object_id=obj_id,
            created_at__gte=now().replace(microsecond=0)
        ).first()
        if recent_log:
            return # Already logged deletion of this pair

    try:
        obj_str = str(instance)
    except TypeError:
        obj_str = str(instance.pk)

    request = get_current_request()
    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""

    UserActivityLog.safe_log(
        user=user,
        action=action,
        model_name=model_name,
        model_key=model_key,
        object_id=obj_id,
        number=obj_str[:50] if obj_str else None,
        details=None,
        ip_address=ip,
        user_agent=user_agent,
    )

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a Profile for every new User."""
    if created:
        Profile = apps.get_model('dlux', 'Profile')
        profile, _ = Profile.objects.get_or_create(user=instance)
        
        from .models import ScopeSettings, Scope
        settings_obj = ScopeSettings.load()
        skip_scope = bool(getattr(instance, '_dlux_public_registration', False))
        if not skip_scope and settings_obj.is_enabled and getattr(settings_obj, 'auto_create_user_scope', False):
            scope_name = instance.username
            scope, _ = Scope.objects.get_or_create(name=scope_name)
            profile.scope = scope
            profile.save(update_fields=['scope'])

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_connected_profiles(sender, instance, created, **kwargs):
    """
    Dynamically discover all models linked to User via OneToOneField and 
    create profile instances for them with failsafe dummy values if required.
    """
    if not created:
        return

    # Superusers/admins should not get auto-created linked profiles
    if instance.is_superuser:
        return

    from .utils import get_user_linked_models
    from django.db import models
    from django.utils import timezone

    linked_models = get_user_linked_models()
    
    for lm in linked_models:
        model_class = apps.get_model(lm['app_label'], lm['model_name'])
        
        # Skip if somehow already exists
        if model_class.objects.filter(**{lm['field_name']: instance}).exists():
            continue

        dummy_kwargs = {lm['field_name']: instance}
        
        # Introspect fields to populate required ones with dummy data
        for field in model_class._meta.fields:
            if field.name == lm['field_name'] or field.primary_key:
                continue
                
            # If the field has a default or is allowed to be blank/null, skip
            if field.has_default() or field.blank or field.null:
                continue
                
            # If it's an auto-added date/time field (like in ScopedModel)
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                continue

            # It's required. Generate a dummy value based on type.
            if isinstance(field, (models.IntegerField, models.DecimalField, models.FloatField)):
                dummy_kwargs[field.name] = 0
            elif isinstance(field, (models.DateField, models.DateTimeField)):
                if isinstance(field, models.DateTimeField):
                    dummy_kwargs[field.name] = timezone.now()
                else:
                    dummy_kwargs[field.name] = '2007-01-01'
            elif isinstance(field, (models.CharField, models.TextField)):
                if field.choices:
                    # Provide the first choice's key, preferably 'employee' if found
                    choices_keys = [c[0] for c in field.choices]
                    if 'employee' in choices_keys:
                        dummy_kwargs[field.name] = 'employee'
                    else:
                        dummy_kwargs[field.name] = choices_keys[0] if choices_keys else '-'
                else:
                    dummy_kwargs[field.name] = '-'
            elif isinstance(field, models.ForeignKey):
                related_model = field.related_model
                # Try to create a dummy entry
                try:
                    dummy_obj, obj_created = related_model.objects.get_or_create(name='-')
                    dummy_kwargs[field.name] = dummy_obj
                except Exception:
                    # Fallback to the first available instance
                    first_obj = related_model.objects.first()
                    dummy_kwargs[field.name] = first_obj
            elif getattr(models, 'FileField', None) and isinstance(field, getattr(models, 'FileField', type(None))):
                dummy_kwargs[field.name] = ''
        
        # Safety catch for models that require 'name' but we didn't populate it
        if 'name' in [f.name for f in model_class._meta.fields] and 'name' not in dummy_kwargs:
             if not model_class._meta.get_field('name').blank and not model_class._meta.get_field('name').null:
                  dummy_kwargs['name'] = instance.get_full_name() or instance.username or '-'
        
        # Instantiate and save
        try:
            model_class.objects.create(**dummy_kwargs)
        except Exception as e:
            # Silently fail if creation is impossible (e.g. strict DB constraints we couldn't bypass)
            pass


@contextmanager
def suspend_dlux_signals():
    """Temporarily disconnect every Dlux model-signal receiver.

    Used by the full-system restore: deserialized rows must land exactly as
    stored — no activity logging, no original-state capture queries, and no
    auto-created Profiles/linked profiles colliding with the Profile rows that
    are part of the backup itself.
    """
    pairs = [
        (pre_save, capture_original_state, None),
        (post_save, log_save, None),
        (post_delete, log_delete, None),
        (post_save, create_user_profile, settings.AUTH_USER_MODEL),
        (post_save, create_user_connected_profiles, settings.AUTH_USER_MODEL),
    ]
    disconnected = []
    for signal, handler, sender in pairs:
        if signal.disconnect(handler, sender=sender):
            disconnected.append((signal, handler, sender))
    try:
        yield
    finally:
        for signal, handler, sender in disconnected:
            signal.connect(handler, sender=sender)
