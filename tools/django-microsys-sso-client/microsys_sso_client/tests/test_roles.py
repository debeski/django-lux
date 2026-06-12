from types import SimpleNamespace
from unittest import TestCase

from microsys_sso_client.roles import apply_role_mapping, extract_role, is_role_allowed


class RoleMappingTests(TestCase):
    def test_extracts_nested_microsys_role_claim(self):
        self.assertEqual(extract_role({"microsys_sso": {"role": "Admin"}}), "admin")

    def test_extracts_flat_microsys_role_claim(self):
        self.assertEqual(extract_role({"microsys_sso_role": "Staff"}), "staff")

    def test_only_portable_roles_are_allowed(self):
        self.assertTrue(is_role_allowed("admin", {"required_roles": ["admin"]}))
        self.assertFalse(is_role_allowed("owner", {"required_roles": ["owner"]}))

    def test_admin_role_never_becomes_superuser(self):
        user = SimpleNamespace(is_staff=False, is_superuser=False)

        apply_role_mapping(user, "admin", {"sync_is_staff": True, "staff_roles": ["admin"], "groups": {}})

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
