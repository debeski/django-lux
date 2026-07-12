from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.cache import cache
from django.test import SimpleTestCase

from dlux.discovery import _is_candidate, build_sidebar_navigation, discover_sidebar_catalog, sanitize_sidebar_config


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
    def setUp(self):
        cache.clear()

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

    def test_discovery_excludes_api_namespace_and_path(self):
        # API counterparts of page views (e.g. a `<app>_api` / `api` namespace
        # and/or an `/api/` path) reuse the page's inferred label, so they would
        # otherwise surface as duplicate, non-navigable sidebar/landing entries.
        self.assertFalse(_is_candidate("documents_api:decree_list", "/api/decrees/", callback=None))
        self.assertFalse(_is_candidate("api:decree_list", "/v1/decrees/", callback=None))
        self.assertFalse(_is_candidate("documents:decree_list", "/api/decrees/", callback=None))
        # The user-facing page view is still discovered, and a non-API path with
        # "api" only as a substring is not falsely excluded.
        self.assertTrue(_is_candidate("documents:decree_list", "/documents/decrees/", callback=None))
        self.assertTrue(_is_candidate("rapid_report", "/finance/rapid-report/", callback=None))

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
                    "group_key": "dlux",
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
                    "group_key": "dlux",
                },
                {
                    "kind": "item",
                    "id": "user_profile",
                    "url_name": "user_profile",
                    "label": "Profile",
                    "icon": "bi-person-badge",
                    "group_key": "dlux",
                },
            ],
        }

        sanitized = sanitize_sidebar_config(sidebar, allow_system_items=True)

        self.assertEqual(len(sanitized["entries"]), 1)
        self.assertEqual(sanitized["entries"][0]["url_name"], "manage_sections")

    def test_sanitize_sidebar_config_preserves_sidebar_behavior_flags(self):
        sidebar = {
            "enabled": False,
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

        self.assertFalse(sanitized["enabled"])
        self.assertFalse(sanitized["enable_reorder"])
        self.assertFalse(sanitized["show_toolbar"])
        self.assertFalse(sanitized["show_icons"])
        self.assertEqual(sanitized["density"], "roomy")
        self.assertFalse(sanitized["allow_user_density"])
        self.assertEqual(sanitized["collapse_mode"], "hidden")

    def test_build_sidebar_navigation_returns_empty_when_sidebar_disabled(self):
        with patch("dlux.utils.get_system_config", return_value={
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "enabled": False,
                "entries": [{"id": "options_view", "url_name": "options_view"}],
            },
        }):
            navigation = build_sidebar_navigation(
                user=_StubUser(is_authenticated=True, permissions={"__dlux_authenticated__"}),
            )

        self.assertEqual(navigation["entries"], [])
        self.assertEqual(navigation["auto_items"], [])
        self.assertEqual(navigation["extra_groups"], [])

    @patch("dlux.utils.get_system_config", return_value={"default_language": "en", "translations": {}})
    def test_discovery_can_include_only_configurable_system_items(self, _mock_get_system_config):
        default_catalog = discover_sidebar_catalog(lang_code="en")
        catalog_with_system = discover_sidebar_catalog(lang_code="en", include_system_items=True)

        default_ids = {entry["id"] for entry in default_catalog}
        system_ids = {
            entry["id"]
            for entry in catalog_with_system
            if entry.get("group_key") == "dlux"
        }
        options_entry = next(entry for entry in catalog_with_system if entry["id"] == "options_view")

        self.assertNotIn("manage_sections", default_ids)
        self.assertTrue(
            {"manage_sections", "user_activity_log", "options_view"}.issubset(system_ids)
        )
        self.assertNotIn("user_profile", system_ids)
        self.assertEqual(options_entry["permissions"], ["__dlux_authenticated__"])

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
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
                        "group_key": "dlux",
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
                "permissions": ["__dlux_authenticated__"],
                "permissions_explicit": True,
                "group_key": "dlux",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(),
            request_path="/sys/options/",
        )

        self.assertEqual([entry["url_name"] for entry in navigation["entries"]], ["options_view"])
        self.assertTrue(navigation["entries"][0]["active"])

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
    def test_build_sidebar_navigation_applies_per_language_label_override(self, mock_get_system_config, mock_discover_sidebar_catalog):
        # Item overrides EN + AR explicitly; leaves FR unset to test fall-through.
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "options_view",
                        "url_name": "options_view",
                        "labels": {"en": "My Options", "ar": "خياراتي"},
                        "icon": "bi-gear",
                        "group_key": "dlux",
                    }
                ],
            },
        }

        def _catalog(lang_code=None, include_system_items=False):
            # The auto-discovered label itself follows the requested language.
            auto = "الخيارات" if str(lang_code or "").startswith("ar") else "Options"
            return [{
                "kind": "item", "id": "options_view", "url_name": "options_view",
                "url": "/sys/options/", "label": auto, "icon": "bi-gear",
                "permissions": ["__dlux_authenticated__"], "permissions_explicit": True,
                "group_key": "dlux", "group_label": "System", "group_icon": "bi-sliders",
            }]
        mock_discover_sidebar_catalog.side_effect = _catalog

        en_nav = build_sidebar_navigation(lang_code="en", user=_StubUser(), request_path="/x/")
        self.assertEqual(en_nav["entries"][0]["label"], "My Options")

        cache.clear()
        ar_nav = build_sidebar_navigation(lang_code="ar", user=_StubUser(), request_path="/x/")
        self.assertEqual(ar_nav["entries"][0]["label"], "خياراتي")

        # No override for French → fall through to the auto-translated catalog label.
        cache.clear()
        fr_nav = build_sidebar_navigation(lang_code="fr", user=_StubUser(), request_path="/x/")
        self.assertEqual(fr_nav["entries"][0]["label"], "Options")

    def test_sanitize_sidebar_config_preserves_per_language_labels(self):
        config = {
            "entries": [
                {
                    "kind": "item",
                    "id": "options_view",
                    "url_name": "options_view",
                    "labels": {"EN ": " My Options ", "ar": "خياراتي", "bad": ""},
                }
            ],
        }
        sanitized = sanitize_sidebar_config(config, allow_system_items=True)
        labels = sanitized["entries"][0]["labels"]
        # Codes normalized/lowercased, values trimmed, empty labels dropped.
        self.assertEqual(labels, {"en": "My Options", "ar": "خياراتي"})

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
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
                        "group_key": "dlux",
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
                "permissions": ["__dlux_user_directory__"],
                "permissions_explicit": True,
                "group_key": "dlux",
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

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
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
                        "group_key": "dlux",
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
                "permissions": ["__dlux_user_directory__"],
                "permissions_explicit": True,
                "group_key": "dlux",
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

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
    def test_build_sidebar_navigation_reuses_cached_render_base_without_stale_active_state(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {"kind": "item", "id": "options_view", "url_name": "options_view"},
                    {"kind": "item", "id": "manage_users", "url_name": "manage_users"},
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
                "icon": "bi-link",
                "permissions": ["__dlux_authenticated__"],
                "permissions_explicit": True,
                "group_key": "core",
                "group_label": "Core",
                "group_icon": "bi-grid",
            },
            {
                "kind": "item",
                "id": "manage_users",
                "url_name": "manage_users",
                "url": "/sys/users/",
                "label": "Users",
                "icon": "bi-link",
                "permissions": ["__dlux_authenticated__"],
                "permissions_explicit": True,
                "group_key": "core",
                "group_label": "Core",
                "group_icon": "bi-grid",
            },
        ]

        first = build_sidebar_navigation(lang_code="en", user=_StubUser(is_superuser=True), request_path="/sys/options/")
        second = build_sidebar_navigation(lang_code="en", user=_StubUser(is_superuser=True), request_path="/sys/users/")

        self.assertEqual(mock_discover_sidebar_catalog.call_count, 1)
        self.assertTrue(first["entries"][0]["active"])
        self.assertFalse(first["entries"][1]["active"])
        self.assertFalse(second["entries"][0]["active"])
        self.assertTrue(second["entries"][1]["active"])

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
    def test_build_sidebar_navigation_cache_keeps_user_permissions_separate(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {"kind": "item", "id": "manage_users", "url_name": "manage_users"},
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
                "permissions": ["__dlux_user_directory__"],
                "permissions_explicit": True,
                "group_key": "dlux",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        denied = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions=set(), scope="scope-a"),
            request_path="/sys/users/",
        )
        allowed = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(is_staff=True, permissions={"auth.view_user"}, scope="scope-a"),
            request_path="/sys/users/",
        )

        self.assertEqual(denied["entries"], [])
        self.assertEqual([entry["url_name"] for entry in allowed["entries"]], ["manage_users"])

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
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
                                "group_key": "dlux",
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
                "permissions": ["__dlux_authenticated__"],
                "permissions_explicit": True,
                "group_key": "dlux",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(),
            request_path="/sys/options/",
        )

        self.assertEqual(len(navigation["entries"]), 1)
        self.assertEqual(navigation["entries"][0]["kind"], "group")
        self.assertEqual(navigation["entries"][0]["items"][0]["url_name"], "options_view")

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
    def test_build_sidebar_navigation_exact_match_wins_over_parent_prefix(self, mock_get_system_config, mock_discover_sidebar_catalog):
        mock_get_system_config.return_value = {
            "default_language": "en",
            "translations": {},
            "sidebar": {
                "entries": [
                    {
                        "kind": "item",
                        "id": "archive-index",
                        "url": "/archive/",
                        "permissions": ["__dlux_authenticated__"],
                    },
                    {
                        "kind": "group",
                        "id": "archive-group",
                        "label": "Archive",
                        "items": [
                            {
                                "kind": "item",
                                "id": "archive-decree-list",
                                "url": "/archive/decrees/",
                                "permissions": ["__dlux_authenticated__"],
                            },
                        ],
                    },
                ],
            },
        }
        mock_discover_sidebar_catalog.return_value = []

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(),
            request_path="/archive/decrees/",
        )

        self.assertFalse(navigation["entries"][0]["active"])
        self.assertTrue(navigation["entries"][1]["items"][0]["active"])
        self.assertTrue(navigation["entries"][1]["has_active"])

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
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
                        "group_key": "dlux",
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
                "permissions": ["__dlux_authenticated__"],
                "permissions_explicit": True,
                "group_key": "dlux",
                "group_label": "System",
                "group_icon": "bi-sliders",
            }
        ]

        navigation = build_sidebar_navigation(
            lang_code="en",
            user=_StubUser(),
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

    @patch("dlux.discovery.discover_sidebar_catalog")
    @patch("dlux.utils.get_system_config")
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
