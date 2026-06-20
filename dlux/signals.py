# Imports of the required python modules and libraries
######################################################
from contextlib import contextmanager
from datetime import timedelta

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
    log_audit_event,
    log_user_action,
)
from .utils.activity_log import (
    LOG_FORCED_EXCLUDED_MODEL_KEYS,
    LOG_IDENTITY_MODEL_KEY,
    get_active_log_config,
    is_model_logging_enabled,
    resolve_log_category,
)

# Sentinel action used for the action-independent "is this model fully enabled?" fast path
# (skips diff capture / old-state fetch for models disabled at the master/section/model level).
_LOG_NOOP_ACTION = '__noop__'

# Rolling window for unifying a user's identity rows (User + Profile) into one "User
# Profile" entry. A rolling window — rather than the old `created_at >=
# now().replace(microsecond=0)` calendar-second check — eliminates the boundary bug where
# two saves a few ms apart straddled a second and double-logged.
_IDENTITY_MERGE_WINDOW_SECONDS = 2


def _resolve_identity_user_pk(instance):
    """Return the User pk this instance's changes should unify under (User or Profile),
    else None. Cheap — reads only *_id attributes, no DB."""
    try:
        User = get_user_model()
        if isinstance(instance, User):
            return instance.pk
        Profile = apps.get_model('dlux', 'Profile')
        if isinstance(instance, Profile):
            return getattr(instance, 'user_id', None)
    except Exception:
        pass
    return None


def _is_identity_model(model_cls):
    """True for the User and dlux Profile models (logged as one unified identity entry)."""
    try:
        User = get_user_model()
        Profile = apps.get_model('dlux', 'Profile')
        return issubclass(model_cls, (User, Profile))
    except Exception:
        return False


# User identity (User + Profile) is a core dlux component — logged under the 'system'
# category and gated by the synthetic 'User accounts' toggle in the system section.
LOG_IDENTITY_CATEGORY = 'system'


def _model_event_allowed_fast(model_cls, log_config):
    """Action-independent gate: master/section/model-level enabled. Identity models (User +
    Profile) are gated by the synthetic 'User accounts' toggle under the system section."""
    if _is_identity_model(model_cls):
        return is_model_logging_enabled(LOG_IDENTITY_CATEGORY, LOG_IDENTITY_MODEL_KEY, _LOG_NOOP_ACTION, log_config)
    real_key = model_cls._meta.label_lower
    category = resolve_log_category(None, model=model_cls, model_key=real_key)
    return is_model_logging_enabled(category, real_key, _LOG_NOOP_ACTION, log_config)

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    """Log successful login as an audit event."""
    log_audit_event(request, 'login_success', "LOGIN", model_name="auth")

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    """Log logout as an audit event."""
    log_audit_event(request, 'logout', "LOGOUT", model_name="auth")

@receiver(pre_save)
def capture_original_state(sender, instance, **kwargs):
    """Capture state before save to calculate diffs."""
    # Skip log model itself
    UserActivityLog = apps.get_model('dlux', 'ActivityLog')
    if sender == UserActivityLog:
        return
    # Cheap correctness-floor skip only (no config/DB load on pre_save). Full config gating
    # happens in log_save/log_delete; capturing old state for a disabled model is harmless.
    if sender._meta.label_lower in LOG_FORCED_EXCLUDED_MODEL_KEYS:
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
    UserActivityLog = apps.get_model('dlux', 'ActivityLog')
    if sender == UserActivityLog:
        return

    # Skip if instance explicitly requests no logging
    if getattr(instance, 'skip_signal_logging', False):
        return

    # Get the current user from thread locals
    user = get_current_user()
    if not user or not user.is_authenticated:
        return

    # Config-driven gating (replaces the old hardcoded EXCLUDED_MODELS list). Fully-disabled
    # models are skipped here; per-action gating happens after the action is finalized.
    log_config = get_active_log_config()
    if not _model_event_allowed_fast(sender, log_config):
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

    # Normalize Model and Object ID for User/Profile/satellite identity unification.
    is_user_entry = False
    # Stable, locale-independent key ("app_label.model_name"). Left None for the unified
    # identity entry (keyed off its "User Profile" label, which reports already exclude).
    model_key = None

    identity_pk = _resolve_identity_user_pk(instance)
    if identity_pk is not None:
        is_user_entry = True
        model_name = "User Profile"  # Unified logical name for User + Profile + satellites
        obj_id = int(identity_pk)
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

    # Grouping: fold this identity change into a recent unified entry within a rolling
    # window (deterministic — no calendar-second boundary bug).
    if is_user_entry:
        recent_log = UserActivityLog.objects.filter(
            created_by=user,
            model_name="User Profile",
            object_id=obj_id,
            created_at__gte=now() - timedelta(seconds=_IDENTITY_MERGE_WINDOW_SECONDS),
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

    # Per-action gating (action is now finalized, incl. soft-delete). Identity rows are gated
    # by the synthetic 'User accounts' key under the system section.
    if is_user_entry:
        if not is_model_logging_enabled(LOG_IDENTITY_CATEGORY, LOG_IDENTITY_MODEL_KEY, action, log_config):
            return
    else:
        category = resolve_log_category(action, model=type(instance), model_key=model_key)
        if not is_model_logging_enabled(category, model_key, action, log_config):
            return

    # Use string representation of the object for 'number' or reference
    try:
        obj_str = str(instance)
    except TypeError:
        # Fallback if __str__ returns non-string (e.g. int)
        obj_str = str(instance.pk)

    request = get_current_request()
    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""

    # Determine target scope. For an identity entry (User/Profile/satellite) the scope may
    # live on the instance's own `scope` (Profile/satellite) or on the related profile (User).
    scope = getattr(instance, 'scope', None)
    if not scope and is_user_entry:
        profile = getattr(instance, 'profile', None)
        if profile is not None:
            scope = getattr(profile, 'scope', None)

    activity_log = UserActivityLog.safe_log(
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
        category=LOG_IDENTITY_CATEGORY if is_user_entry else None,
    )
    if hasattr(instance, 'scope') and hasattr(instance, 'created_at'):
        try:
            from .notifications import notify_model_event

            notify_model_event(
                instance,
                action.lower(),
                details=details,
                activity_log=activity_log,
                request=request,
                user=user,
            )
        except Exception:
            pass

@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    """Log delete actions for all models."""
    UserActivityLog = apps.get_model('dlux', 'ActivityLog')
    if sender == UserActivityLog:
        return

    user = get_current_user()
    if not user or not user.is_authenticated:
        return

    log_config = get_active_log_config()
    if not _model_event_allowed_fast(sender, log_config):
        return

    action = "DELETE"
    # Normalize Model and Object ID for User/Profile/satellite identity unification.
    is_user_entry = False
    model_key = None

    identity_pk = _resolve_identity_user_pk(instance)
    if identity_pk is not None:
        is_user_entry = True
        model_name = "User Profile"
        obj_id = int(identity_pk)
    else:
        model_name = instance._meta.verbose_name
        model_key = instance._meta.label_lower
        try:
            obj_id = int(instance.pk) if instance.pk is not None else None
        except (ValueError, TypeError):
            obj_id = None

    # Grouping for delete: collapse the unified identity deletion within a rolling window.
    if is_user_entry:
        recent_log = UserActivityLog.objects.filter(
            created_by=user,
            model_name="User Profile",
            action="DELETE",
            object_id=obj_id,
            created_at__gte=now() - timedelta(seconds=_IDENTITY_MERGE_WINDOW_SECONDS),
        ).first()
        if recent_log:
            return # Already logged deletion of this identity

    # Per-action gating. Identity rows gated by the synthetic 'User accounts' key (system).
    if is_user_entry:
        if not is_model_logging_enabled(LOG_IDENTITY_CATEGORY, LOG_IDENTITY_MODEL_KEY, action, log_config):
            return
    else:
        category = resolve_log_category(action, model=type(instance), model_key=model_key)
        if not is_model_logging_enabled(category, model_key, action, log_config):
            return

    try:
        obj_str = str(instance)
    except TypeError:
        obj_str = str(instance.pk)

    request = get_current_request()
    ip = get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""

    scope = getattr(instance, 'scope', None)
    activity_log = UserActivityLog.safe_log(
        user=user,
        action=action,
        model_name=model_name,
        model_key=model_key,
        object_id=obj_id,
        number=obj_str[:50] if obj_str else None,
        details=None,
        ip_address=ip,
        user_agent=user_agent,
        scope=scope,
        category=LOG_IDENTITY_CATEGORY if is_user_entry else None,
    )
    if hasattr(instance, 'scope') and hasattr(instance, 'created_at'):
        try:
            from .notifications import notify_model_event

            notify_model_event(
                instance,
                action.lower(),
                details=None,
                activity_log=activity_log,
                request=request,
                user=user,
            )
        except Exception:
            pass

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
    User = get_user_model()
    pairs = [
        (pre_save, capture_original_state, None),
        (post_save, log_save, None),
        (post_delete, log_delete, None),
        (post_save, create_user_profile, User),
        (post_save, create_user_connected_profiles, User),
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
