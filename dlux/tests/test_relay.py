from dlux.tests.harness import setup_test_environment

setup_test_environment()

import base64
import hashlib
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from dlux import relay
from dlux.relay import RelayError, Ticket
from dlux.relay_testing import FakeAgent
from dlux.updater.runtime import RuntimeStore

FIXTURES = Path(__file__).parent / "fixtures"


def page(params, secret):
    return "<html>rates</html>"


class RelayTests(SimpleTestCase):
    def setUp(self):
        self.store = RuntimeStore(tempfile.mkdtemp()).ensure()
        self.agent = FakeAgent(self.store, {
            "finance.cbl_page": page,
            "weather.current": lambda params, secret: {"main.temp": 21.5, "seen_secret": secret},
        }, operations={
            "finance.cbl_page": {"response": "text", "auth": False, "params": []},
            "weather.current": {"response": "json", "auth": True, "params": ["lat", "lon"]},
        })

    def request_files(self):
        return list((relay.relay_root(self.store) / "requests").glob("*.json"))

    def test_no_agent_means_no_capabilities_and_a_message_naming_the_fix(self):
        self.assertEqual(relay.capabilities(self.store), {})
        self.assertFalse(relay.available("finance.cbl_page", self.store))
        with self.assertRaises(RelayError) as caught:
            relay.submit("finance.cbl_page", store=self.store)
        self.assertEqual(caught.exception.code, "agent")
        self.assertIn("agent update", caught.exception.detail)
        self.assertEqual(self.request_files(), [])

    def test_capabilities_go_stale_when_the_agent_stops_answering(self):
        self.agent.publish()
        self.assertTrue(relay.available("finance.cbl_page", self.store))
        path = relay.relay_root(self.store) / "capabilities.json"
        document = json.loads(path.read_text())
        document["updated_at"] = (timezone.now() - timedelta(seconds=relay.CAPABILITIES_MAX_AGE + 5)).isoformat()
        path.write_text(json.dumps(document))
        self.assertEqual(relay.capabilities(self.store), {})
        document.update(updated_at=timezone.now().isoformat(), schema_version=99)
        path.write_text(json.dumps(document))
        self.assertEqual(relay.capabilities(self.store), {})

    def test_unavailable_operations_say_why(self):
        agent = FakeAgent(self.store, {"finance.cbl_page": page}, unapproved=["finance.other"],
                          problems=[{"name": "finance.broken", "reason": "url must start with https://"}])
        agent.publish()
        for name, code in (("finance.other", "unapproved"), ("finance.broken", "invalid"), ("finance.nothing", "unsupported")):
            with self.subTest(name=name), self.assertRaises(RelayError) as caught:
                relay.submit(name, store=self.store)
            self.assertEqual(caught.exception.code, code)
        self.assertIn("approve", relay.submit.__globals__["_why_unavailable"]("finance.other", relay.capabilities(self.store)).detail)

    def test_only_a_store_holder_can_write(self):
        self.agent.publish()
        with self.assertRaises(RelayError) as caught:
            relay.submit("finance.cbl_page")
        self.assertEqual(caught.exception.code, "writer")

    def test_submit_writes_a_bounded_request_naming_the_operation_never_a_url(self):
        self.agent.publish()
        ticket = relay.submit("finance.cbl_page", {"q": "x"}, ttl=999, store=self.store)
        (path,) = self.request_files()
        raw = path.read_bytes()
        request = json.loads(raw)
        self.assertEqual(path.stem, ticket.id)
        self.assertEqual((request["op"], request["params"], request["sealed"], request["schema_version"]),
                         ("finance.cbl_page", {"q": "x"}, None, 1))
        self.assertNotIn(b"http", raw)
        lifetime = (timezone.datetime.fromisoformat(request["expires_at"]) - timezone.datetime.fromisoformat(request["created_at"]))
        self.assertLessEqual(lifetime.total_seconds(), 120)
        self.assertEqual(ticket.digest, hashlib.sha256(raw).hexdigest())

    def test_secrets_are_sealed_and_only_the_agent_reads_them(self):
        self.agent.publish()
        relay.submit("weather.current", {"lat": 1, "lon": 2}, secret="PLAINTEXT-KEY-9", store=self.store)
        (path,) = self.request_files()
        self.assertNotIn(b"PLAINTEXT-KEY-9", path.read_bytes())
        self.assertEqual(json.loads(path.read_text())["sealed"]["key_id"], self.agent.key_id)
        self.agent.step()
        self.assertEqual(self.agent.seen[-1]["secret"], "PLAINTEXT-KEY-9")
        for candidate in relay.relay_root(self.store).rglob("*.json"):
            self.assertNotIn(b"PLAINTEXT-KEY-9", candidate.read_bytes().replace(b'"seen_secret": "PLAINTEXT-KEY-9"', b""), str(candidate))

    def test_a_sealed_secret_is_bound_to_its_request_and_operation(self):
        self.agent.publish()
        key = json.loads((relay.relay_root(self.store) / "public-key.json").read_text())
        sealed = relay.seal("S", "11111111-1111-1111-1111-111111111111", "weather.current", key)
        for oid, op in (("22222222-2222-2222-2222-222222222222", "weather.current"),
                        ("11111111-1111-1111-1111-111111111111", "weather.geocode")):
            with self.assertRaises(Exception):
                self.agent._open(sealed, oid, op)
        self.assertEqual(self.agent._open(sealed, "11111111-1111-1111-1111-111111111111", "weather.current"), "S")

    def test_fetch_round_trip_returns_data_and_tidies_the_result(self):
        self.agent.publish()
        calls = []

        def stepping_sleep(_):
            calls.append(self.agent.step())

        ticket = relay.submit("finance.cbl_page", store=self.store)
        self.assertEqual(relay.wait(ticket, 5, self.store, sleep=stepping_sleep), "<html>rates</html>")
        self.assertEqual(calls, [1])
        self.assertEqual(list((relay.relay_root(self.store) / "results").glob("*.json")), [])

    def test_the_agent_error_code_reaches_the_caller(self):
        class Refused(Exception):
            code = "credentials"

        def refuse(params, secret):
            raise Refused("the server answered 401")

        agent = FakeAgent(self.store, {"finance.cbl_page": refuse})
        agent.publish()
        ticket = relay.submit("finance.cbl_page", store=self.store)
        agent.step()
        with self.assertRaises(RelayError) as caught:
            relay.wait(ticket, 1, self.store)
        self.assertEqual((caught.exception.code, caught.exception.detail), ("credentials", "the server answered 401"))

    def test_waiting_times_out_with_a_useful_message(self):
        self.agent.publish()
        ticket = relay.submit("finance.cbl_page", store=self.store)
        ticks = iter(range(0, 100))
        with self.assertRaises(RelayError) as caught:
            relay.wait(ticket, 2, self.store, sleep=lambda _: None, clock=lambda: next(ticks))
        self.assertEqual(caught.exception.code, "timeout")
        self.assertIn("composer-agent", caught.exception.detail)

    def test_a_result_for_a_different_request_body_is_ignored(self):
        self.agent.publish()
        ticket = relay.submit("finance.cbl_page", store=self.store)
        results = relay.relay_root(self.store) / "results"
        results.mkdir(exist_ok=True)
        (results / f"{ticket.id}.json").write_text(json.dumps({
            "operation_id": ticket.id, "request_digest": "0" * 64, "status": "ok", "data": "forged"}))
        self.assertEqual(relay.read_result(ticket, self.store), {})
        (results / f"{ticket.id}.json").write_text(json.dumps({
            "operation_id": "someone-else", "request_digest": ticket.digest, "status": "ok", "data": "forged"}))
        self.assertEqual(relay.read_result(ticket, self.store), {})

    def test_status_summarises_the_agent(self):
        self.assertFalse(relay.status(self.store)["answering"])
        FakeAgent(self.store, {"finance.cbl_page": page}, unapproved=["x.y"]).publish()
        summary = relay.status(self.store)
        self.assertEqual((summary["answering"], summary["operations"], summary["unapproved"]),
                         (True, ["finance.cbl_page"], ["x.y"]))

    @override_settings(DLUX_UPDATE_RUNTIME_ROOT="/nonexistent/dlux-runtime")
    def test_readers_never_create_directories(self):
        self.assertEqual(relay.capabilities(), {})
        self.assertFalse(Path("/nonexistent").exists())


class SharedFormatTests(SimpleTestCase):
    """The sealed-secret format is shared with Composer through frozen samples."""

    def agent_with_fixture_key(self, fixture):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        agent = FakeAgent(tempfile.mkdtemp(), {})
        agent._private = X25519PrivateKey.from_private_bytes(base64.b64decode(fixture["private_key"]))
        agent._public = agent._private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        agent.key_id = hashlib.sha256(agent._public).hexdigest()[:16]
        return agent

    def test_a_sample_sealed_by_composers_tests_opens_here(self):
        fixture = json.loads((FIXTURES / "relay_sealed.json").read_text())
        agent = self.agent_with_fixture_key(fixture)
        self.assertEqual(agent.key_id, fixture["key_id"])
        self.assertEqual(agent._open(fixture["sealed"], fixture["operation_id"], fixture["op"]), fixture["secret"])

    def test_a_sample_sealed_by_this_code_is_frozen_for_composer(self):
        fixture = json.loads((FIXTURES / "relay_sealed.json").read_text())
        agent = self.agent_with_fixture_key(fixture)
        frozen = json.loads((FIXTURES / "relay_sealed_dlux.json").read_text())
        self.assertEqual(agent._open(frozen["sealed"], frozen["operation_id"], frozen["op"]), frozen["secret"])
        public = {"algorithm": relay.ALGORITHM, "key_id": agent.key_id, "public_key": base64.b64encode(agent._public).decode()}
        fresh = relay.seal(frozen["secret"], frozen["operation_id"], frozen["op"], public)
        self.assertEqual(agent._open(fresh, frozen["operation_id"], frozen["op"]), frozen["secret"])
