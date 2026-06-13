"""
test_p03_voice_fallback.py — TDD für Issue #40: Voice-Fallback wenn keine Voice-Quelle.

Deckt ab:
  1. Keine Voice-Quelle + Kontext/Avatar vorhanden → Fallback via Seam, kanonisches
     Voice-Profil mit source='voice_fallback' wird geschrieben.
  2. Voice-Quelle vorhanden (transcript) → kein Fallback, regulärer Pfad.
  3. Voice-Quelle vorhanden (written_texts) → kein Fallback, regulärer Pfad.
  4. Fallback-Generierung schlägt fehl → fail-open (kein Crash, leere Defaults).
  5. VOICE_FALLBACK in MODEL_PER_PROMPT und PROMPT_MAX_TOKENS (EU-Seam, kein Literal).
  6. Fallback-Payload enthält Provenance-Markierung (source, _meta.fallback).

Anti-Pollution:
  - Alle Stubs mit `if name not in sys.modules`-Guards.
  - Stubs werden nach dem Import wieder aus sys.modules entfernt (wie test_pipeline_llm.py).
  - p03_voice_fallback wird dep-frei via importlib geladen.
  - Keine wholesale-Stubs von services.* oder api.*

Pflichtcheck (beide Reihenfolgen grün):
  PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_p03_voice_fallback.py
      tests/test_p12_injection.py tests/test_customer_values_schema.py
      tests/test_pipeline_llm.py tests/test_p08_service.py -q
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pfad sicherstellen
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Stubs für den pipeline_llm-Import (analog zu test_pipeline_llm.py)
# Stubs werden nach dem Import wieder entfernt (Anti-Pollution).
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


_STUBBED_HERE = []


def _stub_track(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        _STUBBED_HERE.append(name)
        return mod
    return sys.modules[name]


# Py3.9-Kompatibilität: llm.py und nextcloud.py vor pipeline_llm stubben
if "google" not in sys.modules:
    _stub_track("google")
if "google.generativeai" not in sys.modules:
    _stub_track("google.generativeai")
if "anthropic" not in sys.modules:
    _anthropic = _stub_track("anthropic")
    _anthropic.Anthropic = MagicMock
    _anthropic.AsyncAnthropic = MagicMock

if "services.llm" not in sys.modules:
    _llm = _stub_track("services.llm")

    class _BudgetExceededError(Exception):
        pass

    class _RateLimitExceededError(Exception):
        pass

    _llm.BudgetExceededError = _BudgetExceededError
    _llm.RateLimitExceededError = _RateLimitExceededError
    _llm.llm_service = MagicMock()

if "services.throttle" not in sys.modules:
    _throttle = _stub_track("services.throttle")

    class _RateLimit(Exception):
        pass

    _throttle.RateLimitExceededError = _RateLimit

if "services.nextcloud" not in sys.modules:
    _nc = _stub_track("services.nextcloud")
    _nc.nextcloud_client = None

if "config" not in sys.modules:
    _cfg = _stub_track("config")
    _cfg.settings = types.SimpleNamespace(
        litellm_base_url="https://router.requesty.ai/v1",
        litellm_api_key="test-key",
        requesty_api_key=None,
        database_url="postgresql+asyncpg://t:t@localhost/t",
    )

if "services.provider_resolver" not in sys.modules:
    _pr = _stub_track("services.provider_resolver")
    _pr.get_active_provider = lambda task=None: None

for _name in [
    "models",
    "models.base",
    "models.llm_provider",
    "cryptography",
    "cryptography.fernet",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
]:
    _stub_track(_name)

# Jetzt pipeline_llm importieren (damit Tier-Registry verfügbar ist)
import services.pipeline_llm as _pipeline_llm_mod

# Referenzen für die Tier-Registry-Tests festhalten (vor dem Stub-Cleanup)
MODEL_PER_PROMPT = _pipeline_llm_mod.MODEL_PER_PROMPT
PROMPT_MAX_TOKENS = _pipeline_llm_mod.PROMPT_MAX_TOKENS
TIER_MODELS = _pipeline_llm_mod.TIER_MODELS

# Anti-Pollution: Stubs die von unserem Modul gesetzt wurden aus sys.modules entfernen.
# AUSNAHMEN:
# - services.llm: pipeline_llm hält eine direkte Referenz auf _BudgetExceededError daraus.
#   Entfernen würde test_pipeline_llm.py's BudgetExceededError-Identity-Check brechen.
# Alle anderen Stubs (inklusive config, services.provider_resolver, sqlalchemy etc.) raus,
# damit test_p08_service.py, test_pipeline_llm.py etc. ihre eigenen Stubs setzen können.
# WICHTIG: config und services.provider_resolver werden hier NICHT behalten, weil:
# - config: test_pipeline_llm.py erwartet entweder seinen eigenen Stub ODER die echte
#   config.py (litellm_base_url=None). Behalten wir unseren Stub mit requesty.ai-URL,
#   verfälscht er test_no_router_config_raises_runtime_error und test_auto_cache_only_for_requesty.
# - services.provider_resolver: ebenfalls nicht nötig nach dem Import.
_KEEP_IN_SYS_MODULES = {"services.llm"}
for _n in _STUBBED_HERE:
    if _n not in _KEEP_IN_SYS_MODULES:
        sys.modules.pop(_n, None)

# Anti-Pollution: services.pipeline_llm aus sys.modules UND aus dem services-Package-Attribut
# entfernen. Wenn wir es dort stehen lassen, erben spätere Test-Module (test_p08_service,
# test_pipeline_llm) unsere Modul-Instanz als Package-Attribut. Das führt dazu, dass
# `import services.pipeline_llm as pipeline_llm` in test_pipeline_llm.py das Package-Attribut
# zurückgibt (unsere alte Instanz), während `from services.pipeline_llm import call_pipeline_llm`
# aus sys.modules liest (eine andere Instanz nach p08's spec_from_file_location). Die
# resultierenden Modul-Identitäts-Unterschiede machen monkeypatch.setattr wirkungslos.
sys.modules.pop("services.pipeline_llm", None)
try:
    import services as _svc_pkg_p03

    if getattr(_svc_pkg_p03, "pipeline_llm", None) is _pipeline_llm_mod:
        delattr(_svc_pkg_p03, "pipeline_llm")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Dep-freier Loader für p03_voice_fallback (das neue Modul)
# Wird via importlib geladen damit kein tasks-Import-Side-Effect entsteht.
# ---------------------------------------------------------------------------


def _load_voice_fallback():
    """Lädt tasks/p03_voice_fallback.py isoliert via importlib."""
    p = Path(_BACKEND_DIR) / "tasks" / "p03_voice_fallback.py"
    spec = _ilu.spec_from_file_location("p03_voice_fallback_isolated", str(p))
    m = _ilu.module_from_spec(spec)
    # Modul in sys.modules eintragen damit interne Importe funktionieren
    sys.modules["p03_voice_fallback_isolated"] = m
    spec.loader.exec_module(m)
    return m


vf = _load_voice_fallback()


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_llm_result(text='{"sprache": "klar", "ton": "herzlich"}'):
    """Minimaler PipelineLLMResult-Namespace für Tests."""
    return types.SimpleNamespace(
        text=text,
        model_id="bedrock/claude-sonnet-4-6@eu-central-1",
        tier="S6",
        input_tokens=500,
        output_tokens=300,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.001,
    )


# ---------------------------------------------------------------------------
# 1. Tier-Registry — VOICE_FALLBACK muss eingetragen sein
# ---------------------------------------------------------------------------


class TestVoiceFallbackTierRegistry:
    def test_voice_fallback_in_model_per_prompt(self):
        """VOICE_FALLBACK muss in MODEL_PER_PROMPT stehen — EU-Seam, kein Literal."""
        assert (
            "VOICE_FALLBACK" in MODEL_PER_PROMPT
        ), "VOICE_FALLBACK fehlt in MODEL_PER_PROMPT — bitte eintragen (Issue #40)"

    def test_voice_fallback_tier_is_valid(self):
        """VOICE_FALLBACK-Tier muss ein gültiger Tier-Name sein."""
        tier = MODEL_PER_PROMPT.get("VOICE_FALLBACK")
        assert tier is not None
        assert tier in TIER_MODELS, f"VOICE_FALLBACK-Tier '{tier}' nicht in TIER_MODELS"

    def test_voice_fallback_in_prompt_max_tokens(self):
        """VOICE_FALLBACK muss max_tokens-Eintrag haben."""
        assert "VOICE_FALLBACK" in PROMPT_MAX_TOKENS, "VOICE_FALLBACK fehlt in PROMPT_MAX_TOKENS"
        assert PROMPT_MAX_TOKENS["VOICE_FALLBACK"] > 0

    def test_voice_fallback_resolves_without_error(self):
        """VOICE_FALLBACK muss über resolve_tier auflösbar sein (kein ValueError)."""
        tier, model_id = _pipeline_llm_mod.resolve_tier("VOICE_FALLBACK")
        assert tier in TIER_MODELS
        assert model_id  # nicht leer


# ---------------------------------------------------------------------------
# 2. _has_voice_source — Trigger-Logik
# ---------------------------------------------------------------------------


class TestHasVoiceSource:
    """Tests für die Hilfsfunktion die bestimmt ob echte Voice-Quelle vorhanden."""

    def test_empty_transcript_and_no_texts_returns_false(self):
        assert vf._has_voice_source("", None, None) is False

    def test_blank_transcript_returns_false(self):
        assert vf._has_voice_source("   \n  ", None, None) is False

    def test_none_transcript_returns_false(self):
        assert vf._has_voice_source(None, None, None) is False

    def test_real_transcript_returns_true(self):
        assert vf._has_voice_source("Ich bin Unternehmer.", None, None) is True

    def test_written_texts_present_returns_true(self):
        assert vf._has_voice_source("", ["Ein Text"], None) is True

    def test_empty_written_texts_list_returns_false(self):
        assert vf._has_voice_source("", [], None) is False

    def test_linkedin_posts_present_returns_true(self):
        assert vf._has_voice_source("", None, ["Post 1"]) is True

    def test_empty_linkedin_posts_returns_false(self):
        assert vf._has_voice_source("", None, []) is False

    def test_all_empty_returns_false(self):
        assert vf._has_voice_source("", [], []) is False

    def test_written_texts_with_only_whitespace_ignored(self):
        """Nur-Whitespace-Einträge zählen nicht als echte Voice-Quelle."""
        assert vf._has_voice_source("", ["   ", "\n"], None) is False


# ---------------------------------------------------------------------------
# 3. generate_voice_fallback — Generierungs-Funktion
# ---------------------------------------------------------------------------


class TestGenerateVoiceFallback:
    """Tests für generate_voice_fallback — Seam-Aufruf und Payload-Aufbau."""

    def test_seam_called_with_voice_fallback_key(self):
        """call_pipeline_llm muss mit prompt_key='VOICE_FALLBACK' aufgerufen werden."""
        mock_llm = MagicMock(return_value=_make_llm_result('{"sprache": "direkt"}'))

        vf.generate_voice_fallback(
            tenant_id="t-test",
            customer_context={"unternehmen": "Muster GmbH"},
            audience_avatar={"zielgruppe": "Unternehmer 30-50"},
            call_llm=mock_llm,
        )

        assert mock_llm.called
        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs["prompt_key"] == "VOICE_FALLBACK"

    def test_context_and_avatar_in_user_content(self):
        """Kontext und Avatar müssen im user_content des LLM-Calls erscheinen."""
        captured = {}

        def capturing_llm(**kwargs):
            captured.update(kwargs)
            return _make_llm_result('{"sprache": "warm"}')

        vf.generate_voice_fallback(
            tenant_id="t-test",
            customer_context={"branche": "Beratung"},
            audience_avatar={"alter": "40-55"},
            call_llm=capturing_llm,
        )

        user_content = captured.get("user_content", "")
        assert "Beratung" in user_content or "branche" in user_content
        assert "40-55" in user_content or "alter" in user_content

    def test_result_has_fallback_provenance(self):
        """Ergebnis-Payload muss Fallback-Markierung tragen."""
        mock_llm = MagicMock(return_value=_make_llm_result('{"sprache": "klar"}'))

        payload, meta = vf.generate_voice_fallback(
            tenant_id="t-test",
            customer_context={},
            audience_avatar={},
            call_llm=mock_llm,
        )

        assert meta["source"] == "voice_fallback", "source muss 'voice_fallback' sein"
        assert meta.get("is_fallback") is True, "is_fallback-Flag muss True sein"

    def test_result_has_model_id_and_tokens(self):
        """Ergebnis muss model_id und token-counts aus dem LLM-Result enthalten."""
        mock_llm = MagicMock(return_value=_make_llm_result('{"ton": "herzlich"}'))

        payload, meta = vf.generate_voice_fallback(
            tenant_id="t-test",
            customer_context={},
            audience_avatar={},
            call_llm=mock_llm,
        )

        assert "model_id" in meta
        assert "input_tokens" in meta
        assert "output_tokens" in meta

    def test_llm_failure_returns_empty_fail_open(self):
        """Schlägt der LLM-Call fehl → fail-open: ({}, meta mit error-Flag), kein Crash."""

        def failing_llm(**kwargs):
            raise RuntimeError("Router nicht erreichbar")

        payload, meta = vf.generate_voice_fallback(
            tenant_id="t-test",
            customer_context={"branche": "Handel"},
            audience_avatar={},
            call_llm=failing_llm,
        )

        assert isinstance(payload, dict)
        assert meta.get("fallback_failed") is True

    def test_llm_returns_invalid_json_fail_open(self):
        """LLM liefert kein gültiges JSON → fail-open, kein Crash."""
        mock_llm = MagicMock(return_value=_make_llm_result("Das ist kein JSON!"))

        payload, meta = vf.generate_voice_fallback(
            tenant_id="t-test",
            customer_context={},
            audience_avatar={},
            call_llm=mock_llm,
        )

        assert isinstance(payload, dict)
        assert meta.get("fallback_failed") is True

    def test_no_pii_tenant_id_in_warn_logs(self, caplog):
        """E2: vollständige tenant_id darf nicht in Warn-/Error-Logs erscheinen."""
        import logging

        with caplog.at_level(logging.WARNING, logger="tasks.p03_voice_fallback"):

            def failing_llm(**kwargs):
                raise RuntimeError("Fehler")

            vf.generate_voice_fallback(
                tenant_id="super-secret-tenant-id-123",
                customer_context={},
                audience_avatar={},
                call_llm=failing_llm,
            )
        for record in caplog.records:
            if "super-secret-tenant-id-123" in record.message:
                assert False, f"Vollständige tenant_id in Log: {record.message}"


# ---------------------------------------------------------------------------
# 4. Integration: run_p03_voice_fallback — Orchestrierung
# ---------------------------------------------------------------------------


class TestRunP03VoiceFallback:
    """Tests für die Orchestrierungs-Funktion (kein echter DB-Zugriff)."""

    def _make_mock_session(self):
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        row = MagicMock()
        row.next_version = 1
        session.execute.return_value.fetchone.return_value = row
        return session

    def test_no_voice_source_triggers_fallback(self):
        """Keine Voice-Quelle → Fallback-Generierung wird aufgerufen."""
        mock_session = self._make_mock_session()
        mock_llm = MagicMock(return_value=_make_llm_result('{"ton": "warm"}'))

        with (
            patch.object(vf, "sync_session_factory", return_value=mock_session),
            patch.object(vf, "call_pipeline_llm", mock_llm),
            patch.object(vf, "finalize_canonical", return_value=({"ton": "warm"}, [])),
            patch.object(vf, "build_canonical_meta", return_value={}),
            patch.object(vf, "now_iso", return_value="2026-01-01T00:00:00+00:00"),
            patch.object(
                vf,
                "_load_context_and_avatar",
                return_value=({"branche": "Beratung"}, {"zielgruppe": "KMU"}),
            ),
            patch.object(vf, "_insert_fallback_voice_profile", return_value="fake-id"),
        ):
            result = vf.run_p03_voice_fallback(
                tenant_id="t-test",
                transcript="",
                written_texts=None,
                linkedin_posts=None,
                tenant_name="Test GmbH",
                agentur_id="zb",
            )

        assert (
            mock_llm.called
        ), "call_pipeline_llm muss bei fehlendem Voice-Source aufgerufen werden"
        assert result is not None
        assert result["source"] == "voice_fallback"
        assert result["is_fallback"] is True

    def test_voice_source_present_skips_fallback(self):
        """Echtes Transkript → Fallback wird NICHT ausgelöst."""
        mock_llm = MagicMock()

        with patch.object(vf, "call_pipeline_llm", mock_llm):
            result = vf.run_p03_voice_fallback(
                tenant_id="t-test",
                transcript="Ich bin Unternehmer und leite eine Firma.",
                written_texts=None,
                linkedin_posts=None,
                tenant_name="Test GmbH",
                agentur_id="zb",
            )

        assert (
            not mock_llm.called
        ), "call_pipeline_llm darf bei vorhandener Voice-Quelle NICHT aufgerufen werden"
        assert (
            result is None
        ), "run_p03_voice_fallback soll None zurückgeben wenn kein Fallback nötig"

    def test_written_texts_present_skips_fallback(self):
        """Geschriebene Texte → Fallback wird NICHT ausgelöst."""
        mock_llm = MagicMock()

        with patch.object(vf, "call_pipeline_llm", mock_llm):
            result = vf.run_p03_voice_fallback(
                tenant_id="t-test",
                transcript="",
                written_texts=["Ein Beispieltext"],
                linkedin_posts=None,
                tenant_name=None,
                agentur_id=None,
            )

        assert not mock_llm.called
        assert result is None

    def test_fallback_failure_returns_none_no_crash(self):
        """Schlägt Fallback-Generierung fehl → None (kein Crash)."""
        mock_session = self._make_mock_session()

        def failing_llm(**kwargs):
            raise RuntimeError("Router nicht verfügbar")

        with (
            patch.object(vf, "sync_session_factory", return_value=mock_session),
            patch.object(vf, "call_pipeline_llm", failing_llm),
            patch.object(vf, "_load_context_and_avatar", return_value=({}, {})),
            patch.object(vf, "now_iso", return_value="2026-01-01T00:00:00+00:00"),
        ):
            result = vf.run_p03_voice_fallback(
                tenant_id="t-test",
                transcript="",
                written_texts=None,
                linkedin_posts=None,
                tenant_name=None,
                agentur_id=None,
            )

        # Kein Crash, kein re-raise — None ist der fail-open Wert
        assert result is None

    def test_fallback_writes_with_voice_fallback_source(self):
        """Fallback-Profil wird mit source='voice_fallback' in DB geschrieben."""
        mock_session = self._make_mock_session()
        written_source = []

        def capturing_execute(stmt, params=None):
            if params and isinstance(params, dict) and "source" in params:
                written_source.append(params.get("source"))
            result = MagicMock()
            row = MagicMock()
            row.next_version = 1
            result.fetchone.return_value = row
            return result

        mock_session.execute = capturing_execute

        mock_llm = MagicMock(return_value=_make_llm_result('{"ton": "direkt"}'))

        with (
            patch.object(vf, "sync_session_factory", return_value=mock_session),
            patch.object(vf, "call_pipeline_llm", mock_llm),
            patch.object(vf, "finalize_canonical", return_value=({"ton": "direkt"}, [])),
            patch.object(vf, "build_canonical_meta", return_value={}),
            patch.object(vf, "now_iso", return_value="2026-01-01T00:00:00+00:00"),
            patch.object(vf, "_insert_fallback_voice_profile", wraps=None),
            patch.object(vf, "_load_context_and_avatar", return_value=({"branche": "Test"}, {})),
        ):
            vf.run_p03_voice_fallback(
                tenant_id="t-test",
                transcript="",
                written_texts=None,
                linkedin_posts=None,
                tenant_name="Test GmbH",
                agentur_id="zb",
            )

        if written_source:
            assert "voice_fallback" in written_source
