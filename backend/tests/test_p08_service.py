"""Tests fuer P08 Conversation Service (Issue #15, #65).

Umgestellt auf call_pipeline_llm-Seam (Issue #15).
- Patch-Target: services.p08_service.call_pipeline_llm (Import-Binding)
- Kein direkter anthropic.Anthropic-Call mehr erlaubt
- Statischer Guard: p08_service.py darf kein 'anthropic.' / 'claude-sonnet-4-6-2' enthalten

Stub-Schicht (analog zu test_pipeline_llm.py):
  services/__init__.py -> services.llm -> config -> str|None (Py 3.10+).
  sqlalchemy nicht im venv installiert.
  Alle schweren Sub-Module werden VOR dem ersten Import gesetzt.
"""

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stubs — MUESSEN vor dem ersten services.* Import gesetzt sein.
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_STUBBED_HERE = []


def _stub_mod(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    _STUBBED_HERE.append(name)
    return mod


# anthropic
if "anthropic" not in sys.modules:
    _am = _stub_mod("anthropic")
    _am.Anthropic = MagicMock
    _am.AsyncAnthropic = MagicMock

# google.generativeai
if "google" not in sys.modules:
    _stub_mod("google")
if "google.generativeai" not in sys.modules:
    _stub_mod("google.generativeai")

# sqlalchemy — not installed in test venv, must be fully stubbed
# p08_service uses: from sqlalchemy import text
if "sqlalchemy" not in sys.modules:
    _sq = _stub_mod("sqlalchemy")
    _sq.text = lambda q: q  # minimal stub: text() returns query string

# services.llm (imported by services/__init__.py — uses str|None syntax)
if "services.llm" not in sys.modules:
    _llm = _stub_mod("services.llm")

    class _BudgetExceededError(Exception):
        pass

    _llm.BudgetExceededError = _BudgetExceededError
    _llm.llm_service = MagicMock()

# services.throttle
if "services.throttle" not in sys.modules:
    _thr = _stub_mod("services.throttle")
    _thr.RateLimitExceededError = Exception

# services.nextcloud (imported by services/__init__.py)
if "services.nextcloud" not in sys.modules:
    _nc = _stub_mod("services.nextcloud")
    _nc.nextcloud_client = None

# config.settings — needed by pipeline_llm._resolve_env_provider
if "config" not in sys.modules:
    _cfg = _stub_mod("config")
    _cfg.settings = types.SimpleNamespace(
        litellm_base_url="https://router.requesty.ai/v1",
        litellm_api_key="test-key",
        requesty_api_key=None,
        database_url="postgresql+asyncpg://test:test@localhost/test",
        sync_database_url="postgresql://test:test@localhost/test",
    )

# services.provider_resolver (used by pipeline_llm._resolve_provider)
if "services.provider_resolver" not in sys.modules:
    _pr = _stub_mod("services.provider_resolver")
    _pr.get_active_provider = lambda task=None: None

# services.model_policy (used by pipeline_llm.resolve_model)
if "services.model_policy" not in sys.modules:
    _mp = _stub_mod("services.model_policy")
    _mp.get_override = lambda key: None

# models.base — sync_session_factory patched in tests; must exist at import time
for _name in [
    "models",
    "models.base",
    "models.llm_provider",
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "cryptography",
    "cryptography.fernet",
]:
    if _name not in sys.modules:
        _stub_mod(_name)

if hasattr(sys.modules.get("models.base", None), "__dict__"):
    sys.modules["models.base"].sync_session_factory = MagicMock()

# ---------------------------------------------------------------------------
# Import pipeline_llm directly (bypass services/__init__.py)
# ---------------------------------------------------------------------------
import importlib.util as _ilu

_pl_spec = _ilu.spec_from_file_location(
    "services.pipeline_llm",
    os.path.join(_BACKEND_DIR, "services", "pipeline_llm.py"),
)
_pl_mod = _ilu.module_from_spec(_pl_spec)
sys.modules["services.pipeline_llm"] = _pl_mod
_pl_spec.loader.exec_module(_pl_mod)

from services.pipeline_llm import (  # noqa: E402
    MODEL_PER_PROMPT,
    PROMPT_MAX_TOKENS,
    PipelineLLMResult,
    resolve_tier,
)

# ---------------------------------------------------------------------------
# Import p08_service directly (bypass services/__init__.py)
# ---------------------------------------------------------------------------
_p08_spec = _ilu.spec_from_file_location(
    "services.p08_service",
    os.path.join(_BACKEND_DIR, "services", "p08_service.py"),
)
_p08_mod = _ilu.module_from_spec(_p08_spec)
sys.modules["services.p08_service"] = _p08_mod
_p08_spec.loader.exec_module(_p08_mod)

# Register p08_service as attribute of the services package so @patch("services.p08_service.*")
# can resolve the target via getattr(services_package, 'p08_service').
import services as _svc_pkg  # noqa: E402
_svc_pkg.p08_service = _p08_mod

# Pollution-Schutz (analog zu test_pipeline_llm.py):
# Stubs die NUR fuer den Import von p08_service benoetigt wurden, entfernen.
# So koennen spaetere Test-Module (z.B. test_pipeline_llm.py) die echten Module laden.
# NICHT entfernen:
#   - services.p08_service, services.pipeline_llm — von @patch benoetigt
#   - services.llm — pipeline_llm.py re-exportiert BudgetExceededError daraus;
#     wenn wir es loeschen, wuerden spaetere Importe von pipeline_llm die echte
#     services.llm laden (die anthropic/config braucht) und crashen.
_DO_NOT_REMOVE = {"services.p08_service", "services.pipeline_llm", "services.llm"}
for _n in list(_STUBBED_HERE):
    if _n not in _DO_NOT_REMOVE:
        sys.modules.pop(_n, None)

p08_opener = _p08_mod.p08_opener
p08_response = _p08_mod.p08_response
p08_close = _p08_mod.p08_close


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_result(message, next_action="vertiefen", quality="gold"):
    """Build a fake PipelineLLMResult that call_pipeline_llm returns."""
    payload = json.dumps({"next_action": next_action, "message": message, "quality": quality})
    return PipelineLLMResult(
        text=payload,
        model_id="anthropic/claude-sonnet-4-6",
        tier="S6",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.00075,
    )


def _make_db_session_row(
    tenant_id="t1",
    mode="targeted",
    messages=None,
    current_question_index=1,
    status="active",
):
    """Build a fake DB row tuple matching the SELECT in p08_response."""
    if messages is None:
        messages = [
            {
                "bot": "Erste Frage?",
                "user_features_summary": None,
                "category": "targeted",
                "question_index": 1,
            }
        ]
    row = MagicMock()
    row.__getitem__ = lambda self, i: (tenant_id, mode, messages, current_question_index, status)[i]
    row.__iter__ = lambda self: iter((tenant_id, mode, messages, current_question_index, status))
    return row


# ---------------------------------------------------------------------------
# #17 Board-Compliance Guard
# ---------------------------------------------------------------------------


class TestBoardCompliance:
    def test_max_questions_targeted_is_board_compliant(self):
        """MAX_QUESTIONS_TARGETED muss == 3 sein (Board 5.2: max 2–3 Rückfragen, Issue #17)."""
        from services import p08_service as _p08_svc
        assert _p08_svc.MAX_QUESTIONS_TARGETED == 3, (
            f"MAX_QUESTIONS_TARGETED ist {_p08_svc.MAX_QUESTIONS_TARGETED}, erwartet 3 (Board 5.2)"
        )

    def test_max_questions_random_smart_unchanged(self):
        """MAX_QUESTIONS_RANDOM_SMART bleibt 3 (nicht von #17 betroffen)."""
        from services import p08_service as _p08_svc
        assert _p08_svc.MAX_QUESTIONS_RANDOM_SMART == 3


# ---------------------------------------------------------------------------
# Static Guard
# ---------------------------------------------------------------------------


class TestStaticGuard:
    def test_no_direct_anthropic_import_in_p08_service(self):
        """p08_service.py must not contain 'import anthropic' or 'anthropic.Anthropic'."""
        p08_path = Path(__file__).resolve().parent.parent / "services" / "p08_service.py"
        source = p08_path.read_text(encoding="utf-8")
        assert "import anthropic" not in source, (
            "p08_service.py darf kein direktes 'import anthropic' enthalten"
        )
        assert "anthropic.Anthropic" not in source, (
            "p08_service.py darf kein 'anthropic.Anthropic' enthalten"
        )

    def test_no_literal_model_id_in_p08_service(self):
        """p08_service.py must not contain a hardcoded Anthropic model-ID string."""
        p08_path = Path(__file__).resolve().parent.parent / "services" / "p08_service.py"
        source = p08_path.read_text(encoding="utf-8")
        assert "claude-sonnet-4-6-2" not in source, (
            "p08_service.py darf keine literale Anthropic Modell-ID enthalten"
        )
        assert "ANTHROPIC_MODEL_ID" not in source, (
            "ANTHROPIC_MODEL_ID muss aus p08_service.py entfernt worden sein"
        )

    def test_p08_uses_seam_import(self):
        """p08_service.py must import call_pipeline_llm from services.pipeline_llm."""
        p08_path = Path(__file__).resolve().parent.parent / "services" / "p08_service.py"
        source = p08_path.read_text(encoding="utf-8")
        assert "from services.pipeline_llm import call_pipeline_llm" in source


# ---------------------------------------------------------------------------
# Tier-Registry Tests (pure)
# ---------------------------------------------------------------------------


class TestP08SeamTierAndKey:
    def test_p08_registered_in_model_per_prompt(self):
        assert "P08" in MODEL_PER_PROMPT
        assert MODEL_PER_PROMPT["P08"] == "S6"

    def test_p08_registered_in_prompt_max_tokens(self):
        assert "P08" in PROMPT_MAX_TOKENS
        assert PROMPT_MAX_TOKENS["P08"] > 0

    def test_p08_resolve_tier_returns_s6(self):
        # Modell-ID dynamisch aus TIER_MODELS (robust gegen EU-/Modellwechsel) —
        # geprueft wird das Routing P08 -> S6, nicht ein hartkodierter Modell-String.
        from services.pipeline_llm import TIER_MODELS

        tier, model_id = resolve_tier("P08")
        assert tier == "S6"
        assert model_id == TIER_MODELS["S6"]


# ---------------------------------------------------------------------------
# P08 Service Tests
# ---------------------------------------------------------------------------


class TestP08Opener:
    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_opener_targeted_mode_creates_session(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """p08_opener in 'targeted' mode creates a bot_session row and returns OpenerResult."""
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Was war dein erster Schritt?")

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
            make_session_ctx(idea_row),
            make_session_ctx(voice_row),
            insert_ctx,
        ]

        result = p08_opener(tenant_id="t1", mode="targeted", topic_idea_id="idea-uuid-123")

        assert result.session_id is not None
        assert len(result.session_id) == 36
        assert result.question_text == "Was war dein erster Schritt?"
        assert result.category == "kategorie"
        insert_ctx.execute.assert_called_once()
        insert_ctx.commit.assert_called_once()
        mock_call_llm.assert_called_once()
        kw = mock_call_llm.call_args.kwargs
        assert kw["prompt_key"] == "P08"
        assert kw["tenant_id"] == "t1"

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    @patch("services.p08_service._select_random_category")
    def test_opener_random_smart_mode_selects_category(
        self, mock_select_cat, mock_load_prompt, mock_call_llm, mock_db_factory
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
        mock_call_llm.return_value = _make_llm_result("Erzaehl mir von deinem ersten Fehler.")

        voice_ctx = MagicMock()
        voice_ctx.__enter__ = MagicMock(return_value=voice_ctx)
        voice_ctx.__exit__ = MagicMock(return_value=False)
        voice_ctx.execute.return_value.fetchone.return_value = None

        insert_ctx = MagicMock()
        insert_ctx.__enter__ = MagicMock(return_value=insert_ctx)
        insert_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [voice_ctx, insert_ctx]

        result = p08_opener(tenant_id="t1", mode="random_smart")

        mock_select_cat.assert_called_once_with("t1")
        assert result.category == "erster_fehler"
        assert result.question_text == "Erzaehl mir von deinem ersten Fehler."
        mock_call_llm.assert_called_once()
        assert mock_call_llm.call_args.kwargs["prompt_key"] == "P08"


class TestP08Response:
    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_uses_only_features_not_transcript(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
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
        mock_call_llm.return_value = _make_llm_result("Welches Produkt hat am meisten ueberrascht?")

        messages = [{"bot": "Erste Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        session_row = _make_db_session_row(messages=messages)
        mock_db_factory.side_effect = [make_ctx(session_row), make_ctx(None), make_ctx(None), make_ctx(None)]

        p08_response(session_id="sess-1", features=features)

        kw = mock_call_llm.call_args.kwargs
        user_content = kw["user_content"]
        assert ORIGINAL_TRANSCRIPT_SECRET not in user_content
        assert "key_insight" in user_content
        assert "Wir haben 3 Produkte" in user_content
        assert kw["prompt_key"] == "P08"

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_closes_on_max_questions(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """When current_question_index >= max, session is closed without LLM call.

        #17: MAX_QUESTIONS_TARGETED is now 3 (Board 5.2). Test uses index=3 (>= 3) to trigger.
        """
        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(mode="targeted", messages=messages, current_question_index=3)

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

        result = p08_response(session_id="sess-max", features={"x": 1})

        assert result.is_closed is True
        assert result.next_action == "close"
        mock_call_llm.assert_not_called()

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_closes_on_leer_quality(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """When LLM returns quality='leer', is_closed must be True."""
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Danke, das reicht.", next_action="vertiefen", quality="leer")

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        mock_db_factory.side_effect = [
            make_ctx(session_row),
            make_ctx(None),
            make_ctx(None),
            make_ctx(None),
            make_ctx(None),
        ]

        result = p08_response(session_id="sess-leer", features={"emotion": "bored"})

        assert result.is_closed is True
        assert result.quality == "leer"
        mock_call_llm.assert_called_once()
        assert mock_call_llm.call_args.kwargs["prompt_key"] == "P08"

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_continues_on_gold_quality(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """When LLM returns quality='gold' and next_action='vertiefen', session stays active."""
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Sehr interessant! Erzaehl mehr.", next_action="vertiefen", quality="gold")

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        mock_db_factory.side_effect = [make_ctx(session_row), make_ctx(None), make_ctx(None)]

        result = p08_response(session_id="sess-gold", features={"insight": "Wachstum von 40%"})

        assert result.is_closed is False
        assert result.quality == "gold"
        assert result.next_action == "vertiefen"
        mock_call_llm.assert_called_once()
        assert mock_call_llm.call_args.kwargs["prompt_key"] == "P08"

    @patch("services.p08_service.sync_session_factory")
    def test_response_to_closed_session_returns_closed(self, mock_db_factory):
        """Responding to an already-closed session returns is_closed=True immediately."""
        session_row = _make_db_session_row(status="closed")

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.execute.return_value.fetchone.return_value = session_row

        mock_db_factory.return_value = ctx

        result = p08_response(session_id="closed-sess", features={"x": 1})

        assert result.is_closed is True
        assert result.next_action == "close"

    # ----------------------------------------------------------------------
    # #19 — Roh-Transkript-Persistenz + was_already_closed-Flag
    # ----------------------------------------------------------------------

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_raw_transcript_stored_in_messages(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """#19a: raw_transcript landet als user_transcript im messages-UPDATE."""
        TRANSCRIPT = "Meine ausfuehrliche Story ueber den Wendepunkt 2019."
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Naechste Frage?", next_action="vertiefen", quality="gold")

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        update_ctx = make_ctx(None)
        mock_db_factory.side_effect = [make_ctx(session_row), make_ctx(None), update_ctx]

        p08_response(session_id="sess-1", features={"k": "v"}, raw_transcript=TRANSCRIPT)

        # Den UPDATE-Aufruf mit dem msgs-JSON finden
        found = False
        for call in update_ctx.execute.call_args_list:
            params = call[0][1] if len(call[0]) > 1 else {}
            msgs = params.get("msgs")
            if msgs and TRANSCRIPT in msgs:
                payload = json.loads(msgs)
                assert any(m.get("user_transcript") == TRANSCRIPT for m in payload)
                found = True
        assert found, "raw_transcript wurde nicht als user_transcript persistiert"

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_raw_transcript_never_in_prompt(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """#19a Schicht-3-Wächter: raw_transcript darf NIE in den P08-Prompt gelangen."""
        SECRET = "GEHEIMER_ROHTEXT_DER_NICHT_AN_DAS_LLM_GEHT"
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Naechste Frage?")

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        mock_db_factory.side_effect = [make_ctx(session_row), make_ctx(None), make_ctx(None)]

        p08_response(session_id="sess-1", features={"key": "value"}, raw_transcript=SECRET)

        user_content = mock_call_llm.call_args.kwargs["user_content"]
        assert SECRET not in user_content

    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_was_already_closed_false_on_real_close(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """#19: regulärer LLM-Close → was_already_closed=False (Trigger erlaubt)."""
        prompt = MagicMock()
        prompt.system_prompt = "system"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Danke, genug!", next_action="close", quality="gold")

        messages = [{"bot": "Frage?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        def make_ctx(fetchone_val=None):
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=ctx)
            ctx.__exit__ = MagicMock(return_value=False)
            ctx.execute.return_value.fetchone.return_value = fetchone_val
            return ctx

        mock_db_factory.side_effect = [make_ctx(session_row), make_ctx(None), make_ctx(None)]

        result = p08_response(session_id="sess-close", features={"x": 1}, raw_transcript="text")

        assert result.is_closed is True
        assert result.was_already_closed is False

    @patch("services.p08_service.sync_session_factory")
    def test_was_already_closed_true_on_closed_session(self, mock_db_factory):
        """#19: Antwort auf bereits geschlossene Session → was_already_closed=True (kein Trigger)."""
        session_row = _make_db_session_row(status="closed")

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        ctx.execute.return_value.fetchone.return_value = session_row
        mock_db_factory.return_value = ctx

        result = p08_response(session_id="closed-sess", features={"x": 1})

        assert result.is_closed is True
        assert result.was_already_closed is True


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

        p08_close(session_id="sess-to-close")

        update_ctx.execute.assert_called_once()
        update_ctx.commit.assert_called_once()
        call_args = update_ctx.execute.call_args
        sql_text = str(call_args[0][0])
        assert "closed" in sql_text or "status" in sql_text


class TestP08OpenerVoiceProfile:
    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_opener_voice_profile_loaded_from_db(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """Voice profile from brand_voice table is passed to LLM prompt."""
        VOICE = "analytisch, praezise, direkt"

        prompt = MagicMock()
        prompt.system_prompt = "sys"
        prompt.user_prompt_template = (
            "voice={voice_profile} mode={mode} topic={topic} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Wie begann alles?")

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

        mock_db_factory.side_effect = [make_ctx(voice_row), insert_ctx]

        with patch("services.p08_service._select_random_category", return_value="erster_fehler"):
            p08_opener(tenant_id="t2", mode="random_smart")

        kw = mock_call_llm.call_args.kwargs
        user_content = kw["user_content"]
        assert VOICE in user_content


class TestP08DbFailure:
    @patch("services.p08_service.sync_session_factory")
    @patch("services.p08_service.call_pipeline_llm")
    @patch("services.p08_service._load_p08_prompt")
    def test_response_db_failure_handled_gracefully(
        self, mock_load_prompt, mock_call_llm, mock_db_factory
    ):
        """If DB call for brand_voice fails, p08_response continues with empty voice_profile."""
        prompt = MagicMock()
        prompt.system_prompt = "sys"
        prompt.user_prompt_template = (
            "mode={mode} topic={topic} voice_profile={voice_profile} "
            "recent_messages={recent_messages} features_json={features_json} "
            "question_index={question_index} max_questions={max_questions}"
        )
        mock_load_prompt.return_value = prompt
        mock_call_llm.return_value = _make_llm_result("Weiter so!", quality="silber")

        messages = [{"bot": "Hallo?", "user_features_summary": None, "category": "targeted", "question_index": 1}]
        session_row = _make_db_session_row(messages=messages, current_question_index=1)

        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(return_value=session_ctx)
        session_ctx.__exit__ = MagicMock(return_value=False)
        session_ctx.execute.return_value.fetchone.return_value = session_row

        failing_ctx = MagicMock()
        failing_ctx.__enter__ = MagicMock(return_value=failing_ctx)
        failing_ctx.__exit__ = MagicMock(return_value=False)
        failing_ctx.execute.side_effect = Exception("DB connection failed")

        update_ctx = MagicMock()
        update_ctx.__enter__ = MagicMock(return_value=update_ctx)
        update_ctx.__exit__ = MagicMock(return_value=False)

        mock_db_factory.side_effect = [session_ctx, failing_ctx, update_ctx]

        result = p08_response(session_id="sess-db-fail", features={"topic": "Wachstum"})

        assert result.session_id == "sess-db-fail"
        mock_call_llm.assert_called_once()
        assert mock_call_llm.call_args.kwargs["prompt_key"] == "P08"
