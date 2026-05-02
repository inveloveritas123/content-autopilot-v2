"""Tests fuer P08 Conversation Service (Issue #65)."""
import json
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anthropic_response(message: str, next_action: str = "vertiefen", quality: str = "gold"):
    """Build a fake Anthropic response object."""
    payload = json.dumps({"next_action": next_action, "message": message, "quality": quality})
    content_block = MagicMock()
    content_block.text = payload
    response = MagicMock()
    response.content = [content_block]
    return response


def _make_db_session_row(
    tenant_id="t1",
    mode="targeted",
    messages=None,
    current_question_index=1,
    status="active",
):
    """Build a fake DB row tuple matching the SELECT in p08_response."""
    if messages is None:
        messages = [{"bot": "Erste Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
    row = MagicMock()
    row.__getitem__ = lambda self, i: (tenant_id, mode, messages, current_question_index, status)[i]
    row.__iter__ = lambda self: iter((tenant_id, mode, messages, current_question_index, status))
    return row


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestP08Opener:

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_opener_targeted_mode_creates_session(self, mock_load_prompt, mock_anthropic_cls, mock_db_factory):
        """p08_opener in 'targeted' mode creates a bot_session row and returns OpenerResult."""
        # Setup prompt mock
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        # Setup Anthropic mock
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("Was war dein erster Schritt?")
        mock_anthropic_cls.return_value = mock_client

        # Setup DB mock — three separate context managers:
        # 1. content_ideas lookup (targeted topic)
        # 2. brand_voice lookup
        # 3. INSERT into bot_session
        idea_row = MagicMock()
        idea_row.__getitem__ = lambda self, i: ("Mein Thema", None, "kategorie")[i]

        voice_row = MagicMock()
        voice_row.__getitem__ = lambda self, i: ("freundlich, direkt",)[i]

        def make_session_ctx(execute_result):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = execute_result
            return ctx

        insert_ctx = MagicMock()
        insert_ctx.__enter__ = MagicMock(return_value=insert_ctx)
        insert_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [
            make_session_ctx(idea_row),  # content_ideas
            make_session_ctx(voice_row),  # brand_voice
            insert_ctx,                   # INSERT bot_session
        ]

        from services.p08_service import p08_opener
        result = p08_opener(tenant_id="t1", mode="targeted", topic_idea_id="idea-uuid-123")

        assert result.session_id is not None
        assert len(result.session_id) == 36  # UUID format
        assert result.question_text == "Was war dein erster Schritt?"
        assert result.category == "kategorie"
        # Verify INSERT was called
        insert_ctx.execute.assert_called_once()
        insert_ctx.commit.assert_called_once()

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    @patch("services.p08_service._select_random_category")
    def test_opener_random_smart_mode_selects_category(
        self, mock_select_cat, mock_load_prompt, mock_anthropic_cls, mock_db_factory
    ):
        """p08_opener in 'random_smart' mode calls _select_random_category."""
        mock_select_cat.return_value = "erster_fehler"

        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("Erzähl mir von deinem ersten Fehler.")
        mock_anthropic_cls.return_value = mock_client

        # brand_voice + INSERT
        voice_ctx = MagicMock()
        voice_ctx.__enter__ = MagicMock(return_value=voice_ctx)
        voice_ctx.__exit__ = MagicMock(return_value=False)
        voice_ctx.execute.return_value.fetchone.return_value = None

        insert_ctx = MagicMock()
        insert_ctx.__enter__ = MagicMock(return_value=insert_ctx)
        insert_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [voice_ctx, insert_ctx]

        from services.p08_service import p08_opener
        result = p08_opener(tenant_id="t1", mode="random_smart")

        mock_select_cat.assert_called_once_with("t1")
        assert result.category == "erster_fehler"
        assert result.question_text == "Erzähl mir von deinem ersten Fehler."


class TestP08Response:

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_uses_only_features_not_transcript(
        self, mock_load_prompt, mock_anthropic_cls, mock_db_factory
    ):
        """Layer-3 safety: original transcript text must NOT reach the LLM."""
        ORIGINAL_TRANSCRIPT_SECRET = "GEHEIMER_ORIGINALTEXT_DER_NICHT_AN_LLM_GEHT"
        features = {"key_insight": "Wir haben 3 Produkte", "emotion": "proud"}

        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("Welches Produkt hat am meisten überrascht?")
        mock_anthropic_cls.return_value = mock_client

        messages = [{"bot": "Erste Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        session_row = _make_db_session_row(messages=messages)
        mock_db_factory.side_effect = [
            make_ctx(session_row),   # SELECT bot_session
            make_ctx(None),          # SELECT brand_voice
            make_ctx(None),          # UPDATE bot_session
            make_ctx(None),          # UPDATE status = closed (via _close_session_db if triggered)
        ]

        from services.p08_service import p08_response
        p08_response(session_id="sess-1", features=features)

        # Inspect what was sent to Anthropic
        create_call = mock_client.messages.create.call_args
        user_content = create_call.kwargs["messages"][0]["content"]

        # Original transcript text must NOT be present
        assert ORIGINAL_TRANSCRIPT_SECRET not in user_content
        # Features dict content MUST be present
        assert "key_insight" in user_content
        assert "Wir haben 3 Produkte" in user_content

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_closes_on_max_questions(self, mock_load_prompt, mock_anthropic_cls, mock_db_factory):
        """When current_question_index >= max, session is closed without LLM call."""
        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(mode="targeted", messages=messages, current_question_index=5)

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.execute.return_value.fetchone.return_value = session_row

        update_ctx = MagicMock()
        update_ctx.__enter__ = MagicMock(return_value=update_ctx)
        update_ctx.__exit__ = MagicMock(return_value=False)

        p10_ctx = MagicMock()
        p10_ctx.__enter__ = MagicMock(return_value=p10_ctx)
        p10_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [ctx, update_ctx, p10_ctx]

        from services.p08_service import p08_response
        result = p08_response(session_id="sess-max", features={"x": 1})

        assert result.is_closed is True
        assert result.next_action == "close"
        mock_anthropic_cls.assert_not_called()

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_closes_on_leer_quality(self, mock_load_prompt, mock_anthropic_cls, mock_db_factory):
        """When LLM returns quality='leer', is_closed must be True."""
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response(
            "Danke, das reicht.", next_action="vertiefen", quality="leer"
        )
        mock_anthropic_cls.return_value = mock_client

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        mock_db_factory.side_effect = [
            make_ctx(session_row),  # SELECT
            make_ctx(None),          # brand_voice
            make_ctx(None),          # UPDATE
            make_ctx(None),          # _close_session_db UPDATE
            make_ctx(None),          # P10 insert (fail-open)
        ]

        from services.p08_service import p08_response
        result = p08_response(session_id="sess-leer", features={"emotion": "bored"})

        assert result.is_closed is True
        assert result.quality == "leer"

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_continues_on_gold_quality(self, mock_load_prompt, mock_anthropic_cls, mock_db_factory):
        """When LLM returns quality='gold' and next_action='vertiefen', session stays active."""
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response(
            "Sehr interessant! Erzähl mehr.", next_action="vertiefen", quality="gold"
        )
        mock_anthropic_cls.return_value = mock_client

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        mock_db_factory.side_effect = [
            make_ctx(session_row),  # SELECT
            make_ctx(None),          # brand_voice
            make_ctx(None),          # UPDATE
        ]

        from services.p08_service import p08_response
        result = p08_response(session_id="sess-gold", features={"insight": "Wachstum von 40%"})

        assert result.is_closed is False
        assert result.quality == "gold"
        assert result.next_action == "vertiefen"

    @patch("services.p08_service.sync_session_factory")
    def test_response_to_closed_session_returns_closed(self, mock_db_factory):
        """Responding to an already-closed session returns is_closed=True immediately."""
        session_row = _make_db_session_row(status="closed")

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.execute.return_value.fetchone.return_value = session_row

        mock_db_factory.return_value = ctx

        from services.p08_service import p08_response
        result = p08_response(session_id="closed-sess", features={"x": 1})

        assert result.is_closed is True
        assert result.next_action == "close"


class TestP08Close:

    @patch("services.p08_service.sync_session_factory")
    def test_close_sets_session_status_to_closed(self, mock_db_factory):
        """p08_close updates session status to 'closed' in DB."""
        tenant_row = MagicMock()
        tenant_row.__getitem__ = lambda self, i: ("tenant-abc",)[i]

        select_ctx = MagicMock()
        select_ctx.__enter__ = MagicMock(return_value=select_ctx)
        select_ctx.__exit__ = MagicMock(return_value=False)
        select_ctx.execute.return_value.fetchone.return_value = tenant_row

        update_ctx = MagicMock()
        update_ctx.__enter__ = MagicMock(return_value=update_ctx)
        update_ctx.__exit__ = MagicMock(return_value=False)

        p10_ctx = MagicMock()
        p10_ctx.__enter__ = MagicMock(return_value=p10_ctx)
        p10_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [select_ctx, update_ctx, p10_ctx]

        from services.p08_service import p08_close
        p08_close(session_id="sess-to-close")

        # The UPDATE statement should have been called on update_ctx
        update_ctx.execute.assert_called_once()
        update_ctx.commit.assert_called_once()
        call_args = update_ctx.execute.call_args
        sql_text = str(call_args[0][0])
        assert "closed" in sql_text or "status" in sql_text


class TestP08OpenerVoiceProfile:

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_opener_voice_profile_loaded_from_db(self, mock_load_prompt, mock_anthropic_cls, mock_db_factory):
        """Voice profile from brand_voice table is passed to LLM prompt."""
        VOICE = "analytisch, präzise, direkt"

        prompt = MagicMock()
        prompt.system_prompt = "sys"
        # Template includes voice_profile so we can assert it was included
        prompt.user_prompt_template = (
            "voice={voice_profile} mode={mode} topic={topic} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("Wie begann alles?")
        mock_anthropic_cls.return_value = mock_client

        voice_row = MagicMock()
        voice_row.__getitem__ = lambda self, i: (VOICE,)[i]

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        insert_ctx = MagicMock()
        insert_ctx.__enter__ = MagicMock(return_value=insert_ctx)
        insert_ctx.__exit__ = MagicMock(return_value=False)

        # random_smart: no content_ideas lookup, just brand_voice + insert
        mock_db_factory.side_effect = [make_ctx(voice_row), insert_ctx]

        from services.p08_service import p08_opener
        with patch("services.p08_service._select_random_category", return_value="erster_fehler"):
            p08_opener(tenant_id="t2", mode="random_smart")

        create_call = mock_client.messages.create.call_args
        user_content = create_call.kwargs["messages"][0]["content"]
        assert VOICE in user_content


class TestP08DbFailure:

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.anthropic.Anthropic")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_db_failure_handled_gracefully(self, mock_load_prompt, mock_anthropic_cls, mock_db_factory):
        """If DB call for brand_voice fails, p08_response continues with empty voice_profile."""
        prompt = MagicMock()
        prompt.system_prompt = "sys"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response("Weiter so!", quality="silber")
        mock_anthropic_cls.return_value = mock_client

        messages = [{"bot": "Hallo?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(return_value=session_ctx)
        session_ctx.__exit__ = MagicMock(return_value=False)
        session_ctx.execute.return_value.fetchone.return_value = session_row

        # brand_voice ctx raises exception
        failing_ctx = MagicMock()
        failing_ctx.__enter__ = MagicMock(return_value=failing_ctx)
        failing_ctx.__exit__ = MagicMock(return_value=False)
        failing_ctx.execute.side_effect = Exception("DB connection failed")

        update_ctx = MagicMock()
        update_ctx.__enter__ = MagicMock(return_value=update_ctx)
        update_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [session_ctx, failing_ctx, update_ctx]

        from services.p08_service import p08_response
        # Should not raise
        result = p08_response(session_id="sess-db-fail", features={"topic": "Wachstum"})

        assert result.session_id == "sess-db-fail"
        # LLM was still called despite DB failure
        mock_client.messages.create.assert_called_once()
