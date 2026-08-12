"""Forgot-password views — Django's password-reset flow rendered in the Dlux
login-page layout (all login styles, RTL/LTR, per-language strings) and gated
behind the ``forgot_password_enabled`` toggle + verified email readiness.
"""

from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.http import Http404
from django.urls import reverse_lazy

from ..auth.password_reset import (
    DluxPasswordResetForm,
    forgot_password_available,
    reset_email_system_name,
)
from .registration import _public_auth_context


class _ForgotPasswordMixin:
    """Guard the flow and render it in the shared public-auth (login) layout."""

    def dispatch(self, request, *args, **kwargs):
        if not forgot_password_available():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # login_config / hero / language-resolved DLUX_STRINGS, exactly like the
        # register pages, so the reset pages inherit the configured login style.
        context.update(_public_auth_context(self.request))
        return context


class DluxPasswordResetView(_ForgotPasswordMixin, PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/email/password_reset_email.txt'
    subject_template_name = 'registration/email/password_reset_subject.txt'
    form_class = DluxPasswordResetForm
    success_url = reverse_lazy('password_reset_done')

    def dispatch(self, request, *args, **kwargs):
        # Surface the display name to the email template context.
        self.extra_email_context = {'system_name': reset_email_system_name()}
        return super().dispatch(request, *args, **kwargs)


class DluxPasswordResetDoneView(_ForgotPasswordMixin, PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'


class DluxPasswordResetConfirmView(_ForgotPasswordMixin, PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


class DluxPasswordResetCompleteView(_ForgotPasswordMixin, PasswordResetCompleteView):
    template_name = 'registration/password_reset_complete.html'
