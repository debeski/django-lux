from unittest import TestCase

from microsys_sso.settings import microsys_sso_settings


class MicrosysSSOSettingsTests(TestCase):
    def test_settings_helper_is_idempotent_and_additive(self):
        scope = {
            "DEBUG": True,
            "INSTALLED_APPS": ["django.contrib.auth", "microsys"],
            "MIDDLEWARE": [
                "django.contrib.sessions.middleware.SessionMiddleware",
                "django.contrib.auth.middleware.AuthenticationMiddleware",
            ],
        }

        microsys_sso_settings(scope)
        microsys_sso_settings(scope)

        self.assertEqual(scope["INSTALLED_APPS"].count("microsys_sso"), 1)
        self.assertEqual(scope["INSTALLED_APPS"].count("oauth2_provider"), 1)
        self.assertEqual(scope["MIDDLEWARE"].count("oauth2_provider.middleware.OAuth2TokenMiddleware"), 1)
        self.assertTrue(scope["OAUTH2_PROVIDER"]["OIDC_ENABLED"])
        self.assertEqual(
            scope["OAUTH2_PROVIDER"]["OAUTH2_VALIDATOR_CLASS"],
            "microsys_sso.validators.MicrosysOIDCValidator",
        )
        self.assertTrue(scope["MICROSYS_SSO_PROVIDER"]["allow_localhost_redirects"])

