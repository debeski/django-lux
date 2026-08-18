from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dlux.tests.harness import setup_test_environment

setup_test_environment()

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

from dlux.discovery import (
    _classify_route,
    _discover_routes_uncached,
    _is_candidate,
    annotate_sidebar_notification_counts,
    build_default_sidebar_config,
    build_sidebar_navigation,
    discover_routes,
    discover_routes_for,
    discover_sidebar_catalog,
    sanitize_navbar_config,
    sanitize_sidebar_config,
)
from dlux.system.constants import (
    DISCOVERY_PROFILE_LANDING,
    DISCOVERY_PROFILE_NAVBAR,
    DISCOVERY_PROFILE_NAVBAR_ROOT,
    DISCOVERY_PROFILE_SEARCH,
    DISCOVERY_PROFILE_SIDEBAR,
    ROUTE_ACTION_API,
    ROUTE_ACTION_ASYNC,
    ROUTE_ACTION_EDIT,
    ROUTE_ACTION_FORM,
    ROUTE_ACTION_MACHINERY,
    ROUTE_ACTION_PAGE,
)


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

    def test_route_classification_is_feature_agnostic(self):
        self.assertEqual(_classify_route("ajax_search_decrees", "/ajax/search/decrees/", "", None), ROUTE_ACTION_ASYNC)
        self.assertEqual(_classify_route("edit_user", "", "/users/edit/<int:pk>/", None), ROUTE_ACTION_EDIT)
        self.assertEqual(_classify_route("user_update", "", "/users/<int:pk>/update/", None), ROUTE_ACTION_EDIT)
        self.assertEqual(_classify_route("add_chapter", "/chapters/add/", "", None), ROUTE_ACTION_FORM)
        self.assertEqual(_classify_route("chapter_create", "/chapters/create/", "", None), ROUTE_ACTION_FORM)
        self.assertEqual(_classify_route("credit_report", "/finance/credit-report/", "", None), ROUTE_ACTION_PAGE)
        self.assertEqual(_classify_route("set_active_model", "/models/set-active/", "", None), ROUTE_ACTION_MACHINERY)

    def test_ajax_and_async_routes_are_excluded_from_every_profile(self):
        for profile in (
            DISCOVERY_PROFILE_SIDEBAR,
            DISCOVERY_PROFILE_NAVBAR,
            DISCOVERY_PROFILE_NAVBAR_ROOT,
            DISCOVERY_PROFILE_SEARCH,
            DISCOVERY_PROFILE_LANDING,
        ):
            with self.subTest(profile=profile):
                self.assertFalse(_is_candidate(
                    "ajax_search_decrees", "/ajax/search/decrees/", callback=None, profile=profile,
                ))
                self.assertFalse(_is_candidate(
                    "set_active_model", "/models/set-active/", callback=None, profile=profile,
                ))

    def test_form_pages_reach_the_features_that_want_them(self):
        # An `add` page is a real destination: findable in search, placeable in
        # the Nav Bar hierarchy, and pickable (behind the builder toggle) in the
        # sidebar. It is still not a landing page or a Nav Bar root.
        for profile in (DISCOVERY_PROFILE_SIDEBAR, DISCOVERY_PROFILE_NAVBAR, DISCOVERY_PROFILE_SEARCH):
            with self.subTest(profile=profile):
                self.assertTrue(_is_candidate("add_chapter", "/chapters/add/", callback=None, profile=profile))
        for profile in (DISCOVERY_PROFILE_LANDING, DISCOVERY_PROFILE_NAVBAR_ROOT):
            with self.subTest(profile=profile):
                self.assertFalse(_is_candidate("add_chapter", "/chapters/add/", callback=None, profile=profile))

    def test_id_bound_routes_reach_the_navbar_hierarchy_only(self):
        # An edit page cannot be reversed without an id, so every feature that
        # needs a real href drops it; the Nav Bar matches on route name and
        # renders a URL-less node as a non-clickable crumb.
        self.assertTrue(_is_candidate("edit_user", "", callback=None, profile=DISCOVERY_PROFILE_NAVBAR))
        for profile in (
            DISCOVERY_PROFILE_SIDEBAR,
            DISCOVERY_PROFILE_NAVBAR_ROOT,
            DISCOVERY_PROFILE_SEARCH,
            DISCOVERY_PROFILE_LANDING,
        ):
            with self.subTest(profile=profile):
                self.assertFalse(_is_candidate("edit_user", "", callback=None, profile=profile))

    def test_per_feature_opt_out_and_opt_in(self):
        hidden_from_search = SimpleNamespace(dlux_exclude=("search",))
        self.assertFalse(_is_candidate(
            "chapter_list", "/chapters/", callback=hidden_from_search, profile=DISCOVERY_PROFILE_SEARCH,
        ))
        self.assertTrue(_is_candidate(
            "chapter_list", "/chapters/", callback=hidden_from_search, profile=DISCOVERY_PROFILE_SIDEBAR,
        ))

        forced_landing = SimpleNamespace(dlux_include=("landing",))
        self.assertTrue(_is_candidate(
            "add_chapter", "/chapters/add/", callback=forced_landing, profile=DISCOVERY_PROFILE_LANDING,
        ))

        # The released blanket flag still hides a view from everything.
        legacy = SimpleNamespace(sidebar_exclude=True)
        for profile in (DISCOVERY_PROFILE_SIDEBAR, DISCOVERY_PROFILE_NAVBAR, DISCOVERY_PROFILE_SEARCH):
            with self.subTest(profile=profile):
                self.assertFalse(_is_candidate("chapter_list", "/chapters/", callback=legacy, profile=profile))

    def test_global_catalog_keeps_what_profiles_drop(self):
        # The point of the split: discovery itself excludes nothing, so a route a
        # feature rejects is still available to every other feature.
        actions = {entry["action"] for entry in discover_routes(lang_code="en")}
        self.assertIn(ROUTE_ACTION_MACHINERY, actions)
        sidebar_ids = {entry["id"] for entry in discover_routes_for(DISCOVERY_PROFILE_SIDEBAR, lang_code="en")}
        global_ids = {entry["id"] for entry in discover_routes(lang_code="en")}
        self.assertTrue(sidebar_ids < global_ids)

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
        self.assertFalse(_is_candidate("documents:decrees_api", "/v1/decrees/", callback=None))
        self.assertFalse(_is_candidate("documents:api:decree_list", "/v1/decrees/", callback=None))
        self.assertFalse(_is_candidate("documents:decree_list", "/v1/decrees-api/", callback=None))
        # The user-facing page view is still discovered, and a non-API path with
        # "api" only as a substring is not falsely excluded.
        self.assertTrue(_is_candidate("documents:decree_list", "/documents/decrees/", callback=None))
        self.assertTrue(_is_candidate("rapid_report", "/finance/rapid-report/", callback=None))

    def test_discovery_excludes_api_callback_names_without_substring_false_positives(self):
        class ProductsAPIView:
            pass

        class RapidView:
            pass

        self.assertFalse(_is_candidate(
            "documents:products",
            "/documents/products/",
            callback=SimpleNamespace(view_class=ProductsAPIView),
        ))
        self.assertTrue(_is_candidate(
            "documents:rapid_report",
            "/documents/rapid-report/",
            callback=SimpleNamespace(view_class=RapidView),
        ))

    def test_sanitize_sidebar_config_removes_stored_api_routes_and_empty_groups(self):
        sidebar = {
            "home_url_name": "catalog:products_api",
            "entries": [
                {"kind": "item", "id": "catalog:products", "url_name": "catalog:products"},
                {"kind": "item", "id": "catalog:products_api", "url_name": "catalog:products_api"},
                {
                    "kind": "group",
                    "id": "api-only",
                    "items": [{"kind": "item", "id": "catalog:api:stock", "url_name": "catalog:api:stock"}],
                },
                {
                    "kind": "item",
                    "id": "catalog:feed",
                    "url_name": "catalog:feed",
                    "url": "/catalog/feed-api/",
                },
            ],
        }

        sanitized = sanitize_sidebar_config(sidebar, allow_system_items=True)

        self.assertEqual(
            [entry["id"] for entry in sanitized["entries"]],
            ["catalog:products"],
        )
        self.assertIsNone(sanitized["home_url_name"])

    def test_sanitize_navbar_config_removes_stored_api_routes_and_preserves_children(self):
        navbar = {
            "enabled": True,
            "root": {"mode": "route", "url_name": "catalog:products_api"},
            "hierarchy": {
                "nodes": [
                    {
                        "kind": "route",
                        "id": "catalog:api:products",
                        "url_name": "catalog:api:products",
                        "children": [{
                            "kind": "route",
                            "id": "catalog:products",
                            "url_name": "catalog:products",
                        }],
                    },
                    {
                        "kind": "manual",
                        "id": "api-link",
                        "url": "/v1/products-api/",
                        "labels": {"en": "API"},
                    },
                ],
            },
        }

        sanitized = sanitize_navbar_config(navbar)

        self.assertEqual(sanitized["root"], {"mode": "neutral", "url_name": ""})
        self.assertEqual(
            [node["id"] for node in sanitized["hierarchy"]["nodes"]],
            ["catalog:products"],
        )

    @patch("dlux.discovery.routes.reverse", return_value="/staff/api/products/")
    def test_stored_route_with_safe_name_is_removed_when_it_resolves_to_api_path(self, _mock_reverse):
        sidebar = sanitize_sidebar_config({
            "entries": [{"kind": "item", "id": "catalog:feed", "url_name": "catalog:feed"}],
        }, allow_system_items=True)
        navbar = sanitize_navbar_config({
            "root": {"mode": "route", "url_name": "catalog:feed"},
            "hierarchy": {
                "nodes": [{"kind": "route", "id": "catalog:feed", "url_name": "catalog:feed"}],
            },
        })

        self.assertEqual(sidebar["entries"], [])
        self.assertEqual(navbar["root"], {"mode": "neutral", "url_name": ""})
        self.assertEqual(navbar["hierarchy"]["nodes"], [])

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
        users_entry = next(entry for entry in catalog_with_system if entry["id"] == "manage_users")

        self.assertNotIn("manage_sections", default_ids)
        self.assertTrue(
            {"manage_sections", "user_activity_log", "options_view"}.issubset(system_ids)
        )
        self.assertNotIn("user_profile", system_ids)
        self.assertEqual(options_entry["permissions"], ["__dlux_authenticated__"])
        self.assertEqual(users_entry["notification_model_key"], "auth.user")

    def test_sidebar_notification_counts_annotate_items_and_unique_group_totals(self):
        entries = [
            {
                'kind': 'group',
                'id': 'people',
                'items': [
                    {'kind': 'item', 'id': 'users', 'notification_model_key': 'auth.user'},
                    {'kind': 'item', 'id': 'staff', 'notification_model_key': 'auth.user'},
                    {'kind': 'item', 'id': 'profiles', 'notification_model_key': 'dlux.profile'},
                ],
            },
            {'kind': 'item', 'id': 'large', 'notification_model_key': 'project.record'},
        ]

        annotate_sidebar_notification_counts(entries, {
            'auth.user': 2,
            'dlux.profile': 3,
            'project.record': 120,
        })

        self.assertEqual(entries[0]['notification_count'], 5)
        self.assertEqual(entries[0]['notification_model_keys'], ['auth.user', 'dlux.profile'])
        self.assertEqual(entries[0]['items'][0]['notification_display_count'], '2')
        self.assertEqual(entries[1]['notification_display_count'], '99+')

    def test_sidebar_tree_renders_notification_badge_hooks(self):
        entries = [{
            'kind': 'item',
            'id': 'users',
            'url_name': 'manage_users',
            'url': '/sys/users/',
            'label': 'Users',
            'icon': 'bi-people',
            'notification_model_keys': ['auth.user'],
            'notification_count': 3,
            'notification_display_count': '3',
        }]

        html = render_to_string('dlux/sidebar/tree.html', {
            'entries': entries,
            'tree_state': [],
            'sidebar_notification_badges_enabled': True,
            'DLUX_STRINGS': {'sidebar_unread_notifications': 'unread notifications'},
        })

        self.assertIn('data-dlux-sidebar-notification-keys="auth.user"', html)
        self.assertIn('data-dlux-sidebar-notification-badge', html)
        self.assertIn('aria-label="3 unread notifications"', html)
        self.assertNotIn('dlux-sidebar-notification-badge d-none', html)

        disabled_html = render_to_string('dlux/sidebar/tree.html', {
            'entries': entries,
            'tree_state': [],
            'sidebar_notification_badges_enabled': False,
            'DLUX_STRINGS': {'sidebar_unread_notifications': 'unread notifications'},
        })
        self.assertIn('dlux-sidebar-notification-badge d-none', disabled_html)

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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

    @patch("dlux.discovery.render.discover_sidebar_catalog")
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


@override_settings(ROOT_URLCONF='dlux.tests.urls_with_crud_app')
class DiscoveryProfileProjectionTests(SimpleTestCase):
    """The refactor's contract, against a real URLconf rather than stub routes."""

    def setUp(self):
        cache.clear()

    def _ids(self, profile):
        return {
            entry['id']
            for entry in discover_routes_for(profile, lang_code='en', include_system_items=True)
        }

    def test_global_catalog_contains_every_route_shape(self):
        catalog = {entry['id']: entry for entry in discover_routes(lang_code='en')}

        self.assertEqual(catalog['chapter_list']['action'], ROUTE_ACTION_PAGE)
        self.assertEqual(catalog['chapter_add']['action'], ROUTE_ACTION_FORM)
        self.assertEqual(catalog['chapter_edit']['action'], ROUTE_ACTION_EDIT)
        self.assertEqual(catalog['chapter_ajax_search']['action'], ROUTE_ACTION_ASYNC)
        self.assertEqual(catalog['chapter_api_list']['action'], ROUTE_ACTION_API)

        # An id-bound route carries no URL but is catalogued all the same.
        self.assertTrue(catalog['chapter_edit']['requires_args'])
        self.assertEqual(catalog['chapter_edit']['url'], '')
        self.assertEqual(catalog['chapter_edit']['path_template'], '/chapters/<int:pk>/edit/')
        self.assertFalse(catalog['chapter_add']['requires_args'])

    def test_navbar_can_parent_add_and_edit_pages(self):
        navbar_ids = self._ids(DISCOVERY_PROFILE_NAVBAR)

        self.assertIn('chapter_add', navbar_ids)
        self.assertIn('chapter_edit', navbar_ids)
        self.assertIn('chapter_detail', navbar_ids)
        self.assertNotIn('chapter_ajax_search', navbar_ids)
        self.assertNotIn('chapter_api_list', navbar_ids)

    def test_search_finds_add_pages_but_not_id_bound_ones(self):
        search_ids = self._ids(DISCOVERY_PROFILE_SEARCH)

        self.assertIn('chapter_add', search_ids)
        self.assertIn('chapter_list', search_ids)
        self.assertNotIn('chapter_edit', search_ids)
        self.assertNotIn('chapter_ajax_search', search_ids)

    def test_sidebar_offers_add_pages_flagged_for_the_builder_toggle(self):
        catalog = {
            entry['id']: entry
            for entry in discover_sidebar_catalog(lang_code='en', include_system_items=True)
        }

        self.assertTrue(catalog['chapter_add']['is_form_page'])
        self.assertFalse(catalog['chapter_list']['is_form_page'])
        self.assertNotIn('chapter_edit', catalog)

    def test_default_sidebar_never_auto_adds_a_form_page(self):
        config = build_default_sidebar_config(lang_code='en')

        def _ids(entries):
            for entry in entries:
                if entry.get('kind') == 'group':
                    yield from _ids(entry.get('items', []))
                else:
                    yield entry.get('url_name')

        placed = set(_ids(config['entries']))
        self.assertIn('chapter_list', placed)
        self.assertNotIn('chapter_add', placed)

    def test_landing_and_navbar_root_stay_context_free(self):
        for profile in (DISCOVERY_PROFILE_LANDING, DISCOVERY_PROFILE_NAVBAR_ROOT):
            with self.subTest(profile=profile):
                ids = self._ids(profile)
                self.assertIn('chapter_list', ids)
                self.assertNotIn('chapter_add', ids)
                self.assertNotIn('chapter_edit', ids)

    def test_one_global_catalog_backs_every_profile(self):
        # Discovery must walk the URLconf once per language, not once per feature.
        with patch(
            'dlux.discovery.routes._discover_routes_uncached',
            wraps=_discover_routes_uncached,
        ) as walked:
            self._ids(DISCOVERY_PROFILE_SIDEBAR)
            self._ids(DISCOVERY_PROFILE_NAVBAR)
            self._ids(DISCOVERY_PROFILE_SEARCH)
            self._ids(DISCOVERY_PROFILE_LANDING)

        self.assertEqual(walked.call_count, 1)


class DiscoveryBuilderAssetTests(SimpleTestCase):
    """The builders must honour the flags the profiles now emit."""

    @property
    def _setup_js(self):
        # Every script in the wizard's directory, not just main.js. The wizard's
        # JS is being split into modules (builder_model.js holds the pure config
        # transforms), and these assertions are about behaviour that must exist
        # somewhere in the wizard, not about which file currently holds it.
        js_dir = Path(__file__).resolve().parents[1] / 'static' / 'dlux' / 'setup' / 'js'
        return '\n'.join(
            path.read_text(encoding='utf-8') for path in sorted(js_dir.glob('*.js'))
        )

    def test_sidebar_builder_hides_form_pages_until_toggled(self):
        contents = self._setup_js

        self.assertIn('(state.showFormPages || !item.is_form_page)', contents)
        self.assertIn("formToggle: builder.querySelector('[data-builder-form-toggle]')", contents)
        # The flag has to survive catalog normalization or the filter is inert.
        self.assertIn('is_form_page: Boolean(entry.is_form_page),', contents)

    def test_navbar_root_picker_rejects_routes_that_need_context(self):
        contents = self._setup_js

        self.assertIn('if (entry.requires_args || entry.is_form_page) {', contents)

    def test_sidebar_builder_template_renders_the_form_pages_toggle(self):
        contents = render_to_string('dlux/setup/sidebar_builder.html', {
            'mode': 'setup',
            'sidebar_catalog_json': '[]',
            'sidebar_catalog_fallback_json': '[]',
            'sidebar_config_json': '{}',
            'languages_json': '{}',
            'DLUX_STRINGS': {},
        })

        self.assertIn('data-builder-form-toggle', contents)
        self.assertIn('Show form pages', contents)


@override_settings(ROOT_URLCONF='dlux.tests.urls_with_crud_app')
class NavbarRouteLabelMapTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_id_bound_routes_do_not_claim_the_root_path_label(self):
        # The navbar profile carries URL-less routes; keyed naively they all
        # normalize to '/' and the last one wins the root label.
        from dlux.navbar import build_navbar_route_label_map

        labels = build_navbar_route_label_map('en')

        self.assertEqual(labels.get('/chapters'), 'Chapter List')
        self.assertNotIn('Chapter Edit', labels.values())
        self.assertNotIn('Chapter Detail', labels.values())


class HalfBuiltUrlconfTests(SimpleTestCase):
    """A project's urls.py calls `include('dlux.urls')` inside the urlpatterns
    list literal, so dlux code can run while that module exists without
    `urlpatterns`. Resolving a URL then makes Django cache the half-built module
    on the resolver, and every later system check fails with "The included
    URLconf does not appear to have any patterns in it"."""

    def setUp(self):
        cache.clear()

    def test_reverse_is_skipped_while_the_root_urlconf_is_loading(self):
        import sys as _sys
        import types

        from dlux.discovery import _is_api_navigation_route, _root_urlconf_is_loading

        half_built = types.ModuleType('dlux_tests_half_built_urls')  # no urlpatterns
        with patch.dict(_sys.modules, {'dlux_tests_half_built_urls': half_built}):
            with self.settings(ROOT_URLCONF='dlux_tests_half_built_urls'):
                self.assertTrue(_root_urlconf_is_loading())
                with patch('dlux.discovery.routes.reverse') as reverse_spy:
                    _is_api_navigation_route('options_view', '', None)
                    reverse_spy.assert_not_called()

    def test_reverse_still_runs_once_the_urlconf_is_complete(self):
        from dlux.discovery import _is_api_navigation_route, _root_urlconf_is_loading

        self.assertFalse(_root_urlconf_is_loading())
        with patch('dlux.discovery.routes.reverse', return_value='/sys/api/x/') as reverse_spy:
            self.assertTrue(_is_api_navigation_route('some_route', '', None))
            reverse_spy.assert_called_once()

    def test_sanitizing_a_stored_sidebar_is_safe_mid_import(self):
        # This is the exact path: get_system_config() -> sanitize_sidebar_config()
        # -> _is_hidden_sidebar_entry() -> _is_api_navigation_route() -> reverse().
        import sys as _sys
        import types

        half_built = types.ModuleType('dlux_tests_half_built_urls2')
        stored = {
            'home_url_name': None,
            'entries': [{'kind': 'item', 'id': 'catalog:products', 'url_name': 'catalog:products'}],
        }
        with patch.dict(_sys.modules, {'dlux_tests_half_built_urls2': half_built}):
            with self.settings(ROOT_URLCONF='dlux_tests_half_built_urls2'):
                with patch('dlux.discovery.routes.reverse') as reverse_spy:
                    sanitize_sidebar_config(stored, allow_system_items=True)
                    reverse_spy.assert_not_called()
