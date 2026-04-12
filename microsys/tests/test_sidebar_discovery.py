from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

if not settings.configured:
    settings.configure(
        SECRET_KEY='microsys-test-key',
        ALLOWED_HOSTS=['testserver', 'localhost'],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            'crispy_forms',
            'crispy_bootstrap5',
            'django_filters',
            'django_tables2',
            'microsys',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'microsys.middleware.ActivityLogMiddleware',
        ],
        ROOT_URLCONF='microsys.urls',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.request',
                        'django.contrib.auth.context_processors.auth',
                        'django.contrib.messages.context_processors.messages',
                        'microsys.context_processors.microsys_context',
                    ],
                },
            }
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        STATIC_URL='/static/',
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        USE_TZ=True,
        CRISPY_ALLOWED_TEMPLATE_PACKS='bootstrap5',
        CRISPY_TEMPLATE_PACK='bootstrap5',
    )

    import django

    django.setup()

from microsys.discovery import _is_candidate, discover_sidebar_catalog, sanitize_sidebar_config


class SidebarDiscoveryTests(SimpleTestCase):
    def test_discovery_excludes_ajax_and_add_edit_route_names(self):
        self.assertFalse(_is_candidate("ajax_search_decrees", "/ajax/search/decrees/", callback=None))
        self.assertFalse(_is_candidate("ajax-check-duplicate", "/ajax/check-duplicate/", callback=None))
        self.assertFalse(_is_candidate("edit_user", "/users/edit/1/", callback=None))
        self.assertFalse(_is_candidate("user_edit", "/users/1/edit/", callback=None))
        self.assertFalse(_is_candidate("add_chapter", "/chapters/add/", callback=None))
        self.assertFalse(_is_candidate("chapter_add", "/chapters/add/", callback=None))

    def test_discovery_excludes_set_active_model_route_name(self):
        self.assertFalse(_is_candidate("set_active_model", "/models/set-active/", callback=None))

    def test_discovery_does_not_misclassify_credit_routes(self):
        self.assertTrue(_is_candidate("credit_report", "/finance/credit-report/", callback=None))

    def test_sanitize_sidebar_config_hides_system_items_by_default(self):
        sidebar = {
            "home_url_name": None,
            "entries": [
                {
                    "kind": "item",
                    "id": "manage_sections",
                    "url_name": "manage_sections",
                    "label": "Section Management",
                    "icon": "bi-diagram-3",
                    "group_key": "microsys",
                }
            ],
        }

        sanitized = sanitize_sidebar_config(sidebar)

        self.assertEqual(sanitized["entries"], [])

    def test_sanitize_sidebar_config_can_keep_approved_system_items(self):
        sidebar = {
            "home_url_name": None,
            "entries": [
                {
                    "kind": "item",
                    "id": "manage_sections",
                    "url_name": "manage_sections",
                    "label": "Section Management",
                    "icon": "bi-diagram-3",
                    "group_key": "microsys",
                },
                {
                    "kind": "item",
                    "id": "user_profile",
                    "url_name": "user_profile",
                    "label": "Profile",
                    "icon": "bi-person-badge",
                    "group_key": "microsys",
                },
            ],
        }

        sanitized = sanitize_sidebar_config(sidebar, allow_system_items=True)

        self.assertEqual(len(sanitized["entries"]), 1)
        self.assertEqual(sanitized["entries"][0]["url_name"], "manage_sections")

    def test_sanitize_sidebar_config_preserves_sidebar_behavior_flags(self):
        sidebar = {
            "home_url_name": None,
            "entries": [],
            "enable_reorder": False,
            "show_toolbar": False,
        }

        sanitized = sanitize_sidebar_config(sidebar, allow_system_items=True)

        self.assertFalse(sanitized["enable_reorder"])
        self.assertFalse(sanitized["show_toolbar"])

    @patch("microsys.utils.get_system_config", return_value={"default_language": "en", "translations": {}})
    def test_discovery_can_include_only_configurable_system_items(self, _mock_get_system_config):
        default_catalog = discover_sidebar_catalog(lang_code="en")
        catalog_with_system = discover_sidebar_catalog(lang_code="en", include_system_items=True)

        default_ids = {entry["id"] for entry in default_catalog}
        system_ids = {
            entry["id"]
            for entry in catalog_with_system
            if entry.get("group_key") == "microsys"
        }

        self.assertNotIn("manage_sections", default_ids)
        self.assertTrue(
            {"manage_sections", "manage_users", "user_activity_log", "options_view"}.issubset(system_ids)
        )
        self.assertNotIn("user_profile", system_ids)
