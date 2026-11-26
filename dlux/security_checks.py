"""System check for a project's Content Security Policy.

Generated projects send a nonce-based ``script-src``. Projects generated before
keep whatever their settings say, so ``dlux.W201`` names a policy that still lets
scripts run without a nonce.
"""

from django.conf import settings
from django.core.checks import Tags, Warning, register

WEAK_SCRIPT_SOURCES = ("'unsafe-inline'", "'unsafe-eval'")

HINT = (
    'Set CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"] to [SELF, NONCE] '
    "(from csp.constants import NONCE, SELF). DjangoLux needs neither source. Give "
    'the project\'s own inline <script> tags nonce="{{ request.csp_nonce }}" or move '
    "them to static files, and replace inline on...= handlers and javascript: links "
    "first. See docs/security-dsrp-1.md, Content Security Policy. This warning "
    "becomes an error in DjangoLux 1.20.0."
)


def _sources(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.split()
    return [str(item) for item in value]


def _script_sources():
    """The script sources the enforced policy allows, and the setting naming them."""
    policy = getattr(settings, "CONTENT_SECURITY_POLICY", None)
    if isinstance(policy, dict):
        directives = policy.get("DIRECTIVES") or {}
        for directive in ("script-src", "default-src"):
            sources = _sources(directives.get(directive))
            if sources is not None:
                return sources, f'CONTENT_SECURITY_POLICY["DIRECTIVES"]["{directive}"]'
        return [], ""
    # django-csp 3.x settings.
    for name in ("CSP_SCRIPT_SRC", "CSP_DEFAULT_SRC"):
        sources = _sources(getattr(settings, name, None))
        if sources is not None:
            return sources, name
    return [], ""


@register(Tags.security)
def check_script_src_nonce_only(app_configs=None, **kwargs):
    sources, setting = _script_sources()
    weak = [source for source in WEAK_SCRIPT_SOURCES if source in sources]
    if not weak:
        return []
    return [
        Warning(
            f"{setting} allows {', '.join(weak)}, so injected script can run.",
            hint=HINT,
            id="dlux.W201",
        )
    ]
