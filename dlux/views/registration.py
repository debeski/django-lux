from django.contrib.auth import login
from django.contrib.auth.decorators import user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..constants import (
    REGISTRATION_STATUS_PENDING_APPROVAL,
    REGISTRATION_STATUS_PENDING_EMAIL,
)
from ..forms import PublicRegistrationForm
from ..models import PublicRegistration
from ..notifications import notify
from ..registration import (
    create_inactive_registration_user,
    existing_registration_email,
    public_registration_available,
    public_registration_config,
    registration_throttle_allows,
    send_registration_verification_email,
)
from ..translations import get_strings
from ..utils import get_system_config, log_user_action


def _ensure_public_registration():
    if not public_registration_config().get('enabled'):
        raise Http404


def _public_auth_context(request):
    config = get_system_config()
    languages = config.get('localization', {}).get('languages') or config.get('languages', {})
    allow_lang_override = bool(
        config.get('localization', {}).get(
            'allow_user_language_override',
            config.get('allow_user_language_override', True),
        )
    )

    lang_param = request.GET.get('lang')
    if allow_lang_override and lang_param in languages:
        request.session['lang'] = lang_param

    current_lang = (
        request.session.get('lang')
        or config.get('localization', {}).get('default_language')
        or config.get('default_language', 'en')
    )
    default_lang = config.get('localization', {}).get('default_language') or config.get('default_language', 'en')
    if languages and current_lang not in languages:
        current_lang = default_lang if default_lang in languages else 'en'

    login_cfg = config.get('login', {})
    hero = login_cfg.get('hero_message', '')
    if isinstance(hero, dict):
        hero = hero.get(current_lang) or (next(iter(hero.values()), '') if hero else '')
    project_overrides = config.get('localization', {}).get('translations', config.get('translations', None))

    return {
        'login_config': login_cfg,
        'login_hero_message': hero,
        'DLUX_STRINGS': get_strings(current_lang, overrides=project_overrides),
    }


def register_view(request):
    _ensure_public_registration()
    context = _public_auth_context(request)
    if request.method == 'POST':
        if request.POST.get('website'):
            return redirect('register_sent')
        form = PublicRegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            if not public_registration_available():
                form.add_error(None, context['DLUX_STRINGS'].get(
                    'msg_registration_not_configured',
                    "Registration email delivery is not configured.",
                ))
            elif not registration_throttle_allows(request, email):
                return redirect('register_sent')
            elif existing_registration_email(email):
                return redirect('register_sent')
            else:
                registration, token = create_inactive_registration_user(form, request)
                if not send_registration_verification_email(request, registration, token):
                    _safe_error_message(request, context['DLUX_STRINGS'].get(
                        'msg_verification_email_failed',
                        "We could not send the verification email. Please try again later.",
                    ))
                return redirect('register_sent')
    else:
        form = PublicRegistrationForm()
    context['form'] = form
    return render(request, 'registration/register.html', context)


def register_sent_view(request):
    _ensure_public_registration()
    return render(request, 'registration/register_sent.html', _public_auth_context(request))


def register_verify_view(request, token):
    _ensure_public_registration()
    context = _public_auth_context(request)
    token_hash = PublicRegistration.hash_token(token)
    registration = PublicRegistration.objects.filter(
        token_hash=token_hash,
        status=REGISTRATION_STATUS_PENDING_EMAIL,
    ).select_related('user').first()
    if not registration or not registration.token_matches(token):
        return render(request, 'registration/register_verify.html', {**context, 'status': 'invalid'}, status=400)
    if registration.is_expired:
        registration.mark_expired()
        return render(request, 'registration/register_verify.html', {**context, 'status': 'expired'}, status=400)

    registration.mark_verified()
    if registration.user.is_active:
        login(request, registration.user, backend='django.contrib.auth.backends.ModelBackend')
        log_user_action(request, 'REGISTER_VERIFY', instance=registration, details={'status': registration.status})
        return render(request, 'registration/register_verify.html', {**context, 'status': 'activated'})

    return render(request, 'registration/register_verify.html', {**context, 'status': 'pending_approval'})


def _superuser_required(user):
    return getattr(user, 'is_authenticated', False) and getattr(user, 'is_superuser', False)


def _safe_success_message(request, message):
    try:
        notify.success(message, request=request, action='registration_notice', category='registration')
    except Exception:
        pass


def _safe_error_message(request, message):
    try:
        notify.error(message, request=request, action='registration_error', category='registration')
    except Exception:
        pass


@user_passes_test(_superuser_required)
def pending_registrations_view(request):
    registrations = PublicRegistration.objects.filter(
        status=REGISTRATION_STATUS_PENDING_APPROVAL,
    ).select_related('user').order_by('created_at')
    return render(request, 'dlux/registration/pending.html', {'registrations': registrations})


@user_passes_test(_superuser_required)
@require_POST
def approve_registration_view(request, pk):
    registration = get_object_or_404(PublicRegistration, pk=pk, status=REGISTRATION_STATUS_PENDING_APPROVAL)
    registration.approve(request.user)
    log_user_action(request, 'APPROVE', instance=registration, details={'email': registration.email})
    _safe_success_message(request, "Registration approved.")
    return redirect('pending_registrations')


@user_passes_test(_superuser_required)
@require_POST
def reject_registration_view(request, pk):
    registration = get_object_or_404(PublicRegistration, pk=pk, status=REGISTRATION_STATUS_PENDING_APPROVAL)
    registration.reject(request.user)
    log_user_action(request, 'REJECT', instance=registration, details={'email': registration.email})
    _safe_success_message(request, "Registration rejected.")
    return redirect('pending_registrations')
