from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .constants import AUDIT_AUTHORIZE_DENIED, AUDIT_SESSION_REVOKED
from .models import SSOAuditEvent, SSOClientPolicy, SSOSessionState
from .services import can_user_authorize_application

try:
    from oauth2_provider.models import get_application_model
    from oauth2_provider.views import AuthorizationView
except ImportError:  # pragma: no cover - provider dependency is optional outside this package.
    get_application_model = None
    AuthorizationView = None


def user_can_manage_sso_provider(user):
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False))


def user_can_manage_sso_policy(user, policy):
    if user_can_manage_sso_provider(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = policy.memberships.filter(user=user, is_active=True, role="admin").values_list("role", flat=True).first()
    return bool(role)


class DluxAuthorizationView(AuthorizationView or View):
    """DOT authorization endpoint wrapper that applies Dlux SSO client policy."""

    def dispatch(self, request, *args, **kwargs):
        if AuthorizationView is None or get_application_model is None:
            raise ImproperlyConfigured("django-oauth-toolkit is required by django-lux-sso")

        if getattr(request, "user", None) and request.user.is_authenticated:
            client_id = request.GET.get("client_id") or request.POST.get("client_id")
            redirect_uri = request.GET.get("redirect_uri") or request.POST.get("redirect_uri")
            if client_id:
                Application = get_application_model()
                try:
                    application = Application.objects.get(client_id=client_id)
                except Application.DoesNotExist:
                    application = None
                if application is not None:
                    decision = can_user_authorize_application(
                        request.user,
                        application,
                        redirect_uri=redirect_uri,
                    )
                    if not decision.allowed:
                        SSOAuditEvent.objects.create(
                            event_type=AUDIT_AUTHORIZE_DENIED,
                            policy=decision.policy,
                            user=request.user,
                            client_id=client_id,
                            details={"reason": decision.reason, "redirect_uri": redirect_uri or ""},
                        )
                        return HttpResponseForbidden("SSO access denied.")
        return super().dispatch(request, *args, **kwargs)


class SSOProviderDashboardView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Small JSON management surface for the provider dashboard/Options integration."""

    def test_func(self):
        return user_can_manage_sso_provider(self.request.user)

    def get(self, request):
        policies = [
            {
                "id": policy.pk,
                "slug": policy.slug,
                "display_name": policy.display_name,
                "is_active": policy.is_active,
                "allow_all_authenticated": policy.allow_all_authenticated,
                "memberships": policy.memberships.filter(is_active=True).count(),
            }
            for policy in SSOClientPolicy.objects.select_related("application").all()
        ]
        return JsonResponse({"policies": policies})


class SSOClientMembershipView(LoginRequiredMixin, UserPassesTestMixin, View):
    def dispatch(self, request, *args, **kwargs):
        self.policy = get_object_or_404(SSOClientPolicy, pk=kwargs["policy_id"])
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return user_can_manage_sso_policy(self.request.user, self.policy)

    def get(self, request, policy_id):
        memberships = [
            {
                "user_id": membership.user_id,
                "username": membership.user.get_username(),
                "email": membership.user.email,
                "role": membership.role,
                "is_active": membership.is_active,
            }
            for membership in self.policy.memberships.select_related("user").order_by("user__username")
        ]
        return JsonResponse({"policy": self.policy.slug, "memberships": memberships})


@method_decorator(login_required, name="dispatch")
class SSOClientSessionView(View):
    def get(self, request, policy_id):
        policy = get_object_or_404(SSOClientPolicy, pk=policy_id)
        if not user_can_manage_sso_policy(request.user, policy):
            return HttpResponseForbidden("SSO policy access denied.")
        sessions = [
            {
                "id": session.pk,
                "user_id": session.user_id,
                "username": session.user.get_username(),
                "role": session.role,
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat() if session.expires_at else "",
                "revoked_at": session.revoked_at.isoformat() if session.revoked_at else "",
            }
            for session in policy.ssosessionstate_set.select_related("user").all()
        ]
        return JsonResponse({"policy": policy.slug, "sessions": sessions})


@require_POST
@login_required
def revoke_sso_session(request, pk):
    session = get_object_or_404(SSOSessionState.objects.select_related("policy", "user"), pk=pk)
    if request.user != session.user and not user_can_manage_sso_policy(request.user, session.policy):
        return HttpResponseForbidden("SSO session access denied.")
    session.revoke()
    SSOAuditEvent.objects.create(
        event_type=AUDIT_SESSION_REVOKED,
        policy=session.policy,
        user=session.user,
        actor=request.user,
        role=session.role,
        details={"session_id": session.pk},
    )
    return JsonResponse({"status": "revoked", "session_id": session.pk})

