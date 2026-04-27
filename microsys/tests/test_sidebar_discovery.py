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

from microsys.discovery import _is_candidate, build_sidebar_navigation, discover_sidebar_catalog, sanitize_sidebar_config


class _StubUser:
    def __init__(self, *, is_authenticated=True, is_staff=False, is_superuser=False, permissions=None, scope=None):
        self.is_authenticated = is_authenticated
        self.is_staff = is_staff
        self.is_superuser = is_superuser
        self._permissions = set(permissions or [])
        self.scope = scope

    def has_perm(self, permission):
        return permission in self._permissions


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
            "show_icons": False,
            "density": "roomy",
            "allow_user_density": False,
            "collapse_mode": "icons",
        }

        sanitized = sanitize_sidebar_config(sidebar, allow_system_items=True)

        self.assertFalse(sanitized["enable_reorder"])
        self.assertFalse(sanitized["show_toolbar"])
        self.assertFalse(sanitized["show_icons"])
        self.assertEqual(sanitized["density"], "roomy")
        self.assertFalse(sanitized["allow_user_density"])
        self.assertEqual(sanitized["collapse_mode"], "hidden")

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
            {"manage_sections", "user_activity_log", "options_view"}.issubset(system_ids)
        )
        self.assertNotIn("user_profile", system_ids)

    @patch("microsys.discovery.discover_sidebar_catalog")
    @patch("microsys.utils.get_system_config")
    def test_build_sidebar_navigation_renders_saved_system_sidebar_items(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "options_view",
                        "url_name": "options_view",
                        "label": "Options",
                        "icon": "bi-gear",
                        "group_key": "microsys",
                    }
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = [
            {
                "kind": "item",
                "id": "options_view",
                "url_name": "options_view",
                "url": "/sys/options/",
                "label": "Options",
                "icon": "bi-gear",
                "permissions": ["__ms_options_view__"],
                "permissions_explicit": True,
                "group_key": "microsys",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions={"__ms_options_view__"}),
            request_path="/sys/options/",
        )

        self.assertEqual([entry["url_name"] for entry in navigation["entries"]], ["options_view"])
        self.assertTrue(navigation["entries"][0]["active"])

    @patch("microsys.discovery.discover_sidebar_catalog")
    @patch("microsys.utils.get_system_config")
    def test_build_sidebar_navigation_hides_manage_users_without_directory_access(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "manage_users",
                        "url_name": "manage_users",
                        "label": "Users",
                        "icon": "bi-people",
                        "group_key": "microsys",
                    }
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = [
            {
                "kind": "item",
                "id": "manage_users",
                "url_name": "manage_users",
                "url": "/sys/users/",
                "label": "Users",
                "icon": "bi-people",
                "permissions": ["__ms_user_directory__"],
                "permissions_explicit": True,
                "group_key": "microsys",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions=set(), scope="test-scope"),
            request_path="/sys/users/",
        )

        self.assertEqual(navigation["entries"], [])

    @patch("microsys.discovery.discover_sidebar_catalog")
    @patch("microsys.utils.get_system_config")
    def test_build_sidebar_navigation_shows_manage_users_for_staff_with_view_permission(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "manage_users",
                        "url_name": "manage_users",
                        "label": "Users",
                        "icon": "bi-people",
                        "group_key": "microsys",
                    }
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = [
            {
                "kind": "item",
                "id": "manage_users",
                "url_name": "manage_users",
                "url": "/sys/users/",
                "label": "Users",
                "icon": "bi-people",
                "permissions": ["__ms_user_directory__"],
                "permissions_explicit": True,
                "group_key": "microsys",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions={"auth.view_user"}),
            request_path="/sys/users/",
        )

        self.assertEqual([entry["url_name"] for entry in navigation["entries"]], ["manage_users"])
        self.assertTrue(navigation["entries"][0]["active"])

    @patch("microsys.discovery.discover_sidebar_catalog")
    @patch("microsys.utils.get_system_config")
    def test_build_sidebar_navigation_renders_saved_grouped_sidebar_items(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "group",
                        "id": "admin-group",
                        "label": "Admin",
                        "icon": "bi-folder2-open",
                        "items": [
                            {
                                "kind": "item",
                                "id": "options_view",
                                "url_name": "options_view",
                                "label": "Options",
                                "icon": "bi-gear",
                                "group_key": "microsys",
                            }
                        ],
                    }
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = [
            {
                "kind": "item",
                "id": "options_view",
                "url_name": "options_view",
                "url": "/sys/options/",
                "label": "Options",
                "icon": "bi-gear",
                "permissions": ["__ms_options_view__"],
                "permissions_explicit": True,
                "group_key": "microsys",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions={"__ms_options_view__"}),
            request_path="/sys/options/",
        )

        self.assertEqual(len(navigation["entries"]), 1)
        self.assertEqual(navigation["entries"][0]["kind"], "group")
        self.assertEqual(navigation["entries"][0]["items"][0]["url_name"], "options_view")

    @patch("microsys.discovery.discover_sidebar_catalog")
    @patch("microsys.utils.get_system_config")
    def test_build_sidebar_navigation_falls_back_to_system_sidebar_for_stale_override(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "options_view",
                        "url_name": "options_view",
                        "label": "Options",
                        "icon": "bi-gear",
                        "group_key": "microsys",
                    }
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = [
            {
                "kind": "item",
                "id": "options_view",
                "url_name": "options_view",
                "url": "/sys/options/",
                "label": "Options",
                "icon": "bi-gear",
                "permissions": ["__ms_options_view__"],
                "permissions_explicit": True,
                "group_key": "microsys",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions={"__ms_options_view__"}),
            sidebar_override={
                "entries": [
                    {
                        "kind": "item",
                        "id": "options_view",
                        "url_name": "missing:view",
                        "label": "Broken override",
                        "icon": "bi-exclamation-triangle",
                    }
                ]
            },
        )

        self.assertEqual([entry["url_name"] for entry in navigation["entries"]], ["options_view"])

    @patch("microsys.discovery.discover_sidebar_catalog")
    @patch("microsys.utils.get_system_config")
    def test_build_sidebar_navigation_hides_explicit_empty_permission_items_from_staff(self, mock_get_system_config, mock_discover_sidebar_catalog):
        """Items with explicitly empty permissions are hidden from non-superusers."""
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "no_perms_view",
                        "url_name": "no_perms_view",
                        "label": "No Perms View",
                        "icon": "bi-lock",
                        "group_key": "app",
                    }
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = [
            {
                "kind": "item",
                "id": "no_perms_view",
                "url_name": "no_perms_view",
                "url": "/no-perms/",
                "label": "No Perms View",
                "icon": "bi-lock",
                "permissions": [],
                "permissions_explicit": True,  # Explicitly set to empty
                "group_key": "app",
                "group_label": "App",
                "group_icon": "bi-grid-1x2",
            }
        ]

        # Staff user should not see items with explicitly empty permissions
        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions=set()),
            request_path="/no-perms/",
        )

        self.assertEqual(navigation["entries"], [])
