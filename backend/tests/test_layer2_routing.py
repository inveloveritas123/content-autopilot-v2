"""Tests fuer Schicht-2 deterministisches Routing (Issue #64)."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _extraction(intent, flagged=False, flag_reasons=None, routed_to="ok"):
    return SimpleNamespace(
        intent=intent,
        flagged_for_review=flagged,
        flag_reasons=flag_reasons or [],
        extracted_features={"topic_keywords": ["test"]},
        routed_to=routed_to,
    )


def _active_session(session_id="sess-123"):
    return SimpleNamespace(id=session_id, status="active")


def _inactive_session(session_id="sess-456"):
    return SimpleNamespace(id=session_id, status="closed")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLayer2Routing:
    def setup_method(self):
        """persist_routing_decision wird in allen Tests gepatcht."""
        self._patcher = patch("services.layer2_routing.persist_routing_decision")
        self._patcher.start()

    def teardown_method(self):
        self._patcher.stop()

    def test_flagged_routes_to_reviewer_queue(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("spontaneous_idea", flagged=True, flag_reasons=["pattern:injection"]),
            tenant_id="t1",
        )
        assert result.target == "reviewer_queue"
        assert result.reason == "flagged_in_schicht_1"

    def test_cost_paused_routes_to_paused(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("spontaneous_idea", routed_to="paused_for_cost"),
            tenant_id="t1",
        )
        assert result.target == "paused"
        assert result.reason == "cost_cap_reached"

    def test_answer_to_question_with_active_session_routes_p08(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("answer_to_question"),
            tenant_id="t1",
            current_session=_active_session("sess-abc"),
        )
        assert result.target == "p08_response"
        assert result.payload["session_id"] == "sess-abc"
        assert result.reason == "active_session_response"

    def test_answer_to_question_without_session_routes_reviewer_queue(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("answer_to_question"),
            tenant_id="t1",
            current_session=None,
        )
        assert result.target == "reviewer_queue"
        assert result.reason == "unmapped_intent"

    def test_answer_to_question_inactive_session_routes_reviewer_queue(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("answer_to_question"),
            tenant_id="t1",
            current_session=_inactive_session(),
        )
        assert result.target == "reviewer_queue"
        assert result.reason == "unmapped_intent"

    def test_spontaneous_idea_routes_p10(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("spontaneous_idea"),
            tenant_id="tenant-xyz",
        )
        assert result.target == "p10_extract_post_kernel"
        assert result.payload["tenant_id"] == "tenant-xyz"
        assert result.reason == "spontaneous_idea"

    def test_post_feedback_with_post_id_routes_voice_feedback(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("post_feedback"),
            tenant_id="t1",
            last_post_id="post-999",
        )
        assert result.target == "voice_feedback_api"
        assert result.payload["target_post_id"] == "post-999"
        assert result.reason == "post_feedback"

    def test_post_feedback_without_post_id_routes_reviewer_queue(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("post_feedback"),
            tenant_id="t1",
            last_post_id=None,
        )
        assert result.target == "reviewer_queue"
        assert result.reason == "unmapped_intent"

    def test_question_to_bot_routes_help(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("question_to_bot"),
            tenant_id="t1",
        )
        assert result.target == "help_response"
        assert result.payload["template_key"] == "bot_help"
        assert result.reason == "static_help"

    def test_smalltalk_routes_close_friendly(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("smalltalk"),
            tenant_id="t1",
        )
        assert result.target == "close_friendly"
        assert result.payload["template_key"] == "smalltalk_close"
        assert result.reason == "smalltalk"

    def test_unclassified_routes_reviewer_queue(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("unclassified"),
            tenant_id="t1",
        )
        assert result.target == "reviewer_queue"
        assert result.reason == "unmapped_intent"

    def test_unknown_intent_routes_reviewer_queue(self):
        from services.layer2_routing import route_telegram_intent

        result = route_telegram_intent(
            _extraction("totally_unknown_intent_xyz"),
            tenant_id="t1",
        )
        assert result.target == "reviewer_queue"
        assert result.reason == "unmapped_intent"

    def test_allow_list_blocks_invalid_target(self):
        from services.layer2_routing import RoutingDecision, SecurityException

        with pytest.raises(SecurityException):
            RoutingDecision(target="evil_pipeline")

    def test_routing_decision_payload_contains_features(self):
        from services.layer2_routing import route_telegram_intent

        ext = _extraction("spontaneous_idea")
        result = route_telegram_intent(ext, tenant_id="t-feat")

        assert "features" in result.payload
        assert result.payload["features"] == {"topic_keywords": ["test"]}

    def test_persist_routing_decision_fail_open(self):
        """DB-Fehler in persist_routing_decision wird geschluckt (fail-open)."""
        from services.layer2_routing import RoutingDecision, persist_routing_decision

        decision = RoutingDecision(target="reviewer_queue", reason="test")

        with patch(
            "services.layer2_routing.sync_session_factory", side_effect=Exception("DB down")
        ):
            # Should not raise
            persist_routing_decision("some-log-id", decision)
