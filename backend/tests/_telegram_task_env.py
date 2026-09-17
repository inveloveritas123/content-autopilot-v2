# AUDITED-2026-09-17 (zubu-diagnose): Tiefen-Audit, Datei vollstaendig gelesen.
"""Gemeinsame Stub-Umgebung für tasks.telegram_task — KEIN Test-Modul.

Wird von test_telegram_inbound_routing.py und test_idempotency_routing.py
importiert, um den sys.modules-Pollution-Konflikt zwischen den beiden Dateien
zu lösen (Issue #16, #18, #56, #57).

Kernprinzipien
--------------
* tasks.telegram_task wird **genau einmal** via spec_from_file_location geladen
  und in sys.modules["tasks.telegram_task"] eingetragen. Jeder spätere Import
  dieser Umgebung erhält dasselbe Modulobjekt zurück (``tt``).
* ``services`` wird NICHT als Plain-ModuleType gestubbt — das echte Paket-
  verzeichnis bleibt erreichbar, damit test_eu_router_migration.py und
  test_pipeline_llm.py ``import services.pipeline_llm`` erfolgreich ausführen
  können.
* Alle Stubs werden mit ``if name not in sys.modules``-Guards gesetzt, damit
  Wiederholungsimporte idempotent sind.
* Stub-Submodule werden als Attribut des jeweiligen Eltern-Pakets registriert,
  damit ``@patch("services.<sub>.<fn>")`` via ``getattr`` aufgelöst werden kann.

Exportierte Namen
-----------------
  tt                  — das telegram_task-Modulobjekt
  make_extraction     — Helfer: ExtractionResult-Namespace
  make_decision       — Helfer: RoutingDecision-Namespace
  make_p08_result     — Helfer: P08Result-Namespace
  active_session      — Helfer: aktive Bot-Session
  make_guard_db_mock  — Helfer: Mock-DB-Kontext für Idempotenz-Guard-SELECT
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Pfad sicherstellen
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Interner Stub-Helfer — nur wenn noch nicht in sys.modules
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    """Stub-Modul nur anlegen, wenn noch nicht in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# httpx — echtes Modul ist im venv installiert; KEIN Stub.
# test_pipeline_llm.py braucht httpx.HTTPStatusError aus dem echten Modul.
# telegram_task.py importiert httpx ebenfalls — da httpx verfügbar ist,
# brauchen wir keinen Stub.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# sqlalchemy + Untermodule
# ---------------------------------------------------------------------------

# Echtes sqlalchemy importieren (ist im venv installiert). Ein Stub-Modul mit
# nur 'text' wuerde provider_resolver.py brechen (braucht 'select') und
# api/analytics.py (braucht 'func'). Python-Import-Mechanismus nutzt
# sys.modules-Cache — wiederholte Imports sind Noops.
import sqlalchemy
import sqlalchemy.ext
import sqlalchemy.ext.asyncio
import sqlalchemy.orm  # noqa: F401

# ---------------------------------------------------------------------------
# config.settings
# ---------------------------------------------------------------------------

# Echtes config.py bevorzugen (pydantic_settings liest ENV-Vars; alle fehlenden
# Felder haben Defaults). Fallback-Stub nur wenn Import scheitert.
if "config" not in sys.modules:
    try:
        import config as _cfg_real  # noqa: F401
    except Exception:
        _cfg = _stub("config")
        _cfg.settings = types.SimpleNamespace(
            telegram_bot_token="test-token",
            database_url="postgresql+asyncpg://t:t@localhost/t",
            litellm_base_url=None,
            litellm_api_key=None,
            requesty_api_key=None,
            redis_url="redis://localhost:6379/0",
            gemini_api_key="",
            anthropic_api_key="",
            telegram_admin_chat_id=None,
            max_calls_per_tenant_per_hour=100,
            # default_tenant_key für services.crypto (decrypt_secret) — 32+ Zeichen
            default_tenant_key="test-key-32-chars-padded-xxxxxxxx",
        )

# ---------------------------------------------------------------------------
# models.base
# ---------------------------------------------------------------------------

# models als Paket mit __path__ anlegen, damit Submodule (models.llm_provider,
# models.llm_call_log, etc.) via normalen Import gefunden werden koennen.
if "models" not in sys.modules:
    _m = _stub("models")
    _m.__path__ = [os.path.join(_BACKEND_DIR, "models")]
    _m.__package__ = "models"
if "models.base" not in sys.modules:
    _mb = _stub("models.base")
    _mb.sync_session_factory = MagicMock()
    _mb.async_session_factory = MagicMock()
    _mb.Base = MagicMock()
    _mb.async_engine = MagicMock()
    _mb.sync_engine = MagicMock()

# Models-Submodule vorab stubben: ohne diese Stubs würde Python beim Import
# von api.analytics / services.provider_resolver die ECHTEN Dateien laden,
# die `from .base import Base` machen. Mit Base=MagicMock() ergibt das dann
# `class LLMCallLog(MagicMock())` → kaputte MagicMock-Klasse ohne Attribute.
# MagicMock()-Instanzen auto-create Attribute → sqlfunc.date(LLMCallLog.created_at) ok.
if "models.llm_call_log" not in sys.modules:
    _mllc = _stub("models.llm_call_log")
    _mllc.LLMCallLog = MagicMock()
if "models.tenant" not in sys.modules:
    _mten = _stub("models.tenant")
    _mten.Tenant = MagicMock()
if "models.llm_provider" not in sys.modules:
    _mlp = _stub("models.llm_provider")
    _mlp.LLMProvider = MagicMock()

# ---------------------------------------------------------------------------
# services — WICHTIG: NICHT als Plain-ModuleType stubben.
# Das echte Paketverzeichnis muss erreichbar bleiben, damit andere
# Testdateien (test_eu_router_migration, test_pipeline_llm) über normales
# Python-Import auf services.pipeline_llm zugreifen können.
#
# Strategie:
#   1. services.llm und services.nextcloud VOR services-Import stubben
#      (services/__init__.py importiert sie; llm.py nutzt str|None = Py3.10+
#       Syntax die in Py3.9 nicht läuft).
#   2. services als echtes Paket importieren.
#   3. Danach services.voice_transcription/layer1/layer2/p08 als Stubs
#      in sys.modules eintragen UND als Paketat­tribute registrieren.
# ---------------------------------------------------------------------------

# services.llm — echtes Modul laden wenn moeglich (anthropic + google.generativeai
# sind bereits in conftest.py gestubbt; str|None-Syntax ist auf Py3.10+ kein Problem).
# Nur fehlende Stub-Attribute ergaenzen, damit @patch("services.llm.*") weiter klappt.
if "services.llm" not in sys.modules:
    try:
        import services.llm as _llm_real  # noqa: F401
    except Exception:
        _llm = _stub("services.llm")
        _llm.llm_service = MagicMock()

        class _BudgetExceededError(Exception):
            pass

        class _RateLimitExceededError(Exception):
            pass

        _llm.BudgetExceededError = _BudgetExceededError
        _llm.RateLimitExceededError = _RateLimitExceededError
        _llm.LLMService = MagicMock
        _llm.set_llm_tenant = MagicMock()
        _llm._maybe_send_global_cap_alert = MagicMock()

# services.nextcloud VOR services-Import stubben
if "services.nextcloud" not in sys.modules:
    _nc = _stub("services.nextcloud")
    _nc.nextcloud_client = None

# Jetzt services als echtes Paket importieren (damit __path__ gesetzt ist)
import services as _services_pkg

# services.provider_resolver — als Stub + Paket-Attribut registrieren.
# provider_resolver.py braucht models.llm_provider (DB-Modell) at module level;
# in Unit-Tests nutzen wir MagicMock-Stubs. @patch("services.provider_resolver.*")
# braucht das Modul als Attribut von services.
if "services.provider_resolver" not in sys.modules:
    _pr = _stub("services.provider_resolver")
    _pr.get_active_provider = MagicMock(return_value=None)
    _pr.track_cost = MagicMock()
    # llm.py importiert diese Konstanten lazy aus provider_resolver.
    # Werte entsprechen den ENV-Defaults aus provider_resolver.py.
    _pr._DAILY_CAP_USD = 5.0
    _pr._GLOBAL_CAP_USD = 20.0
_services_pkg.provider_resolver = sys.modules["services.provider_resolver"]

# services.voice_transcription — telegram_task importiert es auf Modulebene.
# Das echte Modul hat keine Google/Whisper-Imports auf Modulebene → direkt
# importierbar. telegram_task.py braucht aber 'transcribe_voice' (Compat-Wrapper
# der im echten Modul fehlt) → MagicMock als Attribut ergaenzen.
if "services.voice_transcription" not in sys.modules:
    try:
        import services.voice_transcription as _vt_real

        if not hasattr(_vt_real, "transcribe_voice"):
            _vt_real.transcribe_voice = MagicMock()
    except Exception:
        _vt = _stub("services.voice_transcription")

        class _TranscriptionError(Exception):
            pass

        class _TranscriptionResult:
            def __init__(
                self,
                text="",
                model_name="whisper",
                confidence=0.9,
                model_id=None,
                language_detected=None,
                duration_sec=None,
            ):
                self.text = text
                self.model_name = model_name or model_id or "whisper"
                self.model_id = model_id or model_name or "whisper"
                self.confidence = confidence
                self.language_detected = language_detected or ""
                self.duration_sec = duration_sec or 0.0

        _vt.TranscriptionError = _TranscriptionError
        _vt.TranscriptionResult = _TranscriptionResult
        _vt.transcribe_voice = MagicMock()

# Als Paket-Attribut registrieren (für @patch("services.voice_transcription.*"))
_services_pkg.voice_transcription = sys.modules["services.voice_transcription"]

# services.layer1_extraction — lazy in _route_inbound_message importiert
if "services.layer1_extraction" not in sys.modules:
    _l1 = _stub("services.layer1_extraction")
    _l1.extract_intent_features = MagicMock()
_services_pkg.layer1_extraction = sys.modules["services.layer1_extraction"]

# services.layer2_routing — echtes Modul laden (braucht nur models.base, bereits gestubbt).
# test_layer2_routing.py importiert SecurityException + RoutingDecision direkt aus dem
# echten Modul; ein reiner Stub-MagicMock wuerde die Routing-Logik-Tests brechen.
if "services.layer2_routing" not in sys.modules:
    try:
        import services.layer2_routing as _l2_real  # noqa: F401
    except Exception:
        _l2 = _stub("services.layer2_routing")
        _l2.route_telegram_intent = MagicMock()
        _l2.persist_routing_decision = MagicMock()
_services_pkg.layer2_routing = sys.modules["services.layer2_routing"]

# Attribute sicherstellen — falls Stub-Fallback aktiv oder echtes Modul unvollstaendig.
_l2_mod = sys.modules["services.layer2_routing"]
if not hasattr(_l2_mod, "persist_routing_decision"):
    _l2_mod.persist_routing_decision = MagicMock()
if not hasattr(_l2_mod, "route_telegram_intent"):
    _l2_mod.route_telegram_intent = MagicMock()
if not hasattr(_l2_mod, "RoutingDecision"):

    def _RoutingDecision(target, payload=None, reason=""):
        return types.SimpleNamespace(target=target, payload=payload or {}, reason=reason)

    _l2_mod.RoutingDecision = _RoutingDecision

if not hasattr(_l2_mod, "SecurityException"):

    class _SecurityException(Exception):
        pass

    _l2_mod.SecurityException = _SecurityException

# services.p08_service — lazy in _route_inbound_message UND in
# _versuche_gespraechsstart (P14) importiert.
if "services.p08_service" not in sys.modules:
    _p08 = _stub("services.p08_service")
    _p08.p08_response = MagicMock()
    _p08.erzeuge_bot_session = MagicMock(return_value="sess-p14")
_services_pkg.p08_service = sys.modules["services.p08_service"]
_p08_mod_stub = sys.modules["services.p08_service"]
if not hasattr(_p08_mod_stub, "p08_response"):
    _p08_mod_stub.p08_response = MagicMock()
if not hasattr(_p08_mod_stub, "erzeuge_bot_session"):
    _p08_mod_stub.erzeuge_bot_session = MagicMock(return_value="sess-p14")

# services.p14_entry_service — Lazy-Import im Eingangs-Zug (Spec 05.08.2026).
# Default ist ABLEGEN: das ist der Normalfall und der sichere Default. Tests,
# die einen Gespraechsstart brauchen, patchen ihn explizit.
if "services.p14_entry_service" not in sys.modules:
    _p14 = _stub("services.p14_entry_service")
    _p14.HANDLUNG_GESPRAECH = "gespraech"
    _p14.HANDLUNG_ABLEGEN = "ablegen"
    _p14.ABLEGEN = types.SimpleNamespace(handlung="ablegen", antwort="")
    _p14.p14_entry = MagicMock(return_value=_p14.ABLEGEN)
_services_pkg.p14_entry_service = sys.modules["services.p14_entry_service"]
_p14_mod_stub = sys.modules["services.p14_entry_service"]
if not hasattr(_p14_mod_stub, "p14_entry"):
    _p14_mod_stub.ABLEGEN = types.SimpleNamespace(handlung="ablegen", antwort="")
    _p14_mod_stub.p14_entry = MagicMock(return_value=_p14_mod_stub.ABLEGEN)

# ---------------------------------------------------------------------------
# api.telegram — Lazy-Import in _route_inbound_message (#17).
# Stub-Modul mit _send_telegram_message als MagicMock, damit Tests
# das Attribut via patch("api.telegram._send_telegram_message") ersetzen können.
# ---------------------------------------------------------------------------

# api als PAKET mit echtem __path__ stubben — sonst bricht der Import realer
# Submodule wie `from api.wizard_phases import ...` (test_wizard_phases). Wir stubben
# NUR api.telegram (zieht sonst sqlalchemy), lassen aber die echten Submodule auflösbar.
_api_pkg = _stub("api")
if not hasattr(_api_pkg, "__path__"):
    _api_pkg.__path__ = [os.path.join(_BACKEND_DIR, "api")]
if "api.telegram" not in sys.modules:
    _at = _stub("api.telegram")
    # Neue Signatur: _send_telegram_message(chat_id, text, *, tenant_id) -> bool
    _at._send_telegram_message = MagicMock(return_value=True)
    _at._send_admin_telegram_message = MagicMock()
    _at.dispatch_inbound_update = MagicMock()
    # C5: _route_inbound_message und _start_targeted_session importieren das
    # Abbrechen-Keyboard aus demselben Lazy-Import. Fehlt es am Stub, wirft der
    # Import — und weil der Send in einem try/except sitzt, sähe man nur einen
    # stummen Nicht-Send statt der Ursache. Der Inhalt wird gegen das ECHTE Modul
    # in test_tier1_session_escape.py geprüft, hier zählt nur die Existenz.
    _at._interview_cancel_keyboard = MagicMock(
        return_value={"inline_keyboard": [[{"callback_data": "cmd:session_cancel"}]]}
    )
    # P14: der Ausstieg an der Eroeffnungsantwort. Inhalt wird gegen das ECHTE
    # Modul in test_explicit_choice_callbacks.py geprueft, hier zaehlt die Existenz.
    _at._entry_keep_keyboard = MagicMock(
        return_value={"inline_keyboard": [[{"callback_data": "cmd:entry_keep"}]]}
    )
# Als Paket-Attribut registrieren (für @patch-Auflösung via getattr)
sys.modules["api"].telegram = sys.modules["api.telegram"]

# ---------------------------------------------------------------------------
# services.telegram_token_resolver — Lazy-Import in api.telegram + telegram_task
# ---------------------------------------------------------------------------
if "services.telegram_token_resolver" not in sys.modules:
    _ttr = _stub("services.telegram_token_resolver")
    _ttr.get_tenant_bot_token = MagicMock(return_value="test-tenant-token")
    _ttr.update_last_active = MagicMock()
_services_pkg.telegram_token_resolver = sys.modules["services.telegram_token_resolver"]

# ---------------------------------------------------------------------------
# celery + tasks.celery_app
# ---------------------------------------------------------------------------

if "celery" not in sys.modules:
    _stub("celery")


class _FakeCeleryApp:
    def task(self, *a, **kw):
        _bind = kw.get("bind", False)

        def _make_apply(fn):
            def apply(*call_a, **call_kw):
                pos_args = call_kw.pop("args", call_a[0] if call_a else [])
                kw_args = call_kw.pop("kwargs", {})
                try:
                    if _bind:
                        fake_self = types.SimpleNamespace(
                            request=types.SimpleNamespace(id="fake-task-id")
                        )
                        ret = fn(fake_self, *pos_args, **kw_args)
                    else:
                        ret = fn(*pos_args, **kw_args)
                except Exception as exc:
                    ret = exc
                return types.SimpleNamespace(get=lambda r=ret: r, result=ret)

            return apply

        def deco(fn):
            fn.apply = _make_apply(fn)
            fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
            # Muss mit conftest.py::_FakeCelery.task Schritt halten: tasks.telegram_task
            # wird ueber diesen Loader ODER ueber einen gewoehnlichen `import
            # tasks.telegram_task` geladen, je nachdem welche Testdatei zuerst
            # sys.modules["tasks.telegram_task"] belegt (siehe Modul-Docstring oben).
            # Ohne celery_opts hier waere test_voice_failure_paths.py's Decorator-Test
            # ausschliesslich von der Collection-Reihenfolge abhaengig gruen oder rot.
            fn.celery_opts = kw
            return fn

        if len(a) == 1 and callable(a[0]):
            fn = a[0]
            fn.apply = _make_apply(fn)
            fn.apply_async = lambda *a, **kw: types.SimpleNamespace(id="fake-task-id")
            fn.celery_opts = {}
            return fn
        return deco


if "tasks" not in sys.modules:
    _stub("tasks")
if "tasks.celery_app" not in sys.modules:
    _ca = _stub("tasks.celery_app")
    _ca.celery_app = _FakeCeleryApp()

# tasks.session_post_task — Lazy-Import im Close-Zweig von _route_inbound_message
# (#19). Stub mit generate_post_from_session als MagicMock, damit Tests den
# Enqueue (apply_async) via patch beobachten/auslösen können.
if "tasks.session_post_task" not in sys.modules:
    _spt = _stub("tasks.session_post_task")
    _spt.generate_post_from_session = MagicMock()
# Als Paket-Attribut registrieren (für @patch-Auflösung via getattr)
sys.modules["tasks"].session_post_task = sys.modules["tasks.session_post_task"]

# tasks.post_feedback_task — Lazy-Import im Feedback-Zweig von _route_inbound_message
# (#37). Stub mit regenerate_post_from_feedback als MagicMock, damit Tests den
# Enqueue (apply_async) via patch beobachten/auslösen können.
# Muster: tasks.session_post_task (oben, Zeilen 244-248).
if "tasks.post_feedback_task" not in sys.modules:
    _pft = _stub("tasks.post_feedback_task")
    _pft.regenerate_post_from_feedback = MagicMock()
# Als Paket-Attribut registrieren (für @patch-Auflösung via getattr)
sys.modules["tasks"].post_feedback_task = sys.modules["tasks.post_feedback_task"]

# services.chat_intent_heuristics — Lazy-Import im P09-Gate von _route_inbound_message
# (#36 S2). Echtes dep-freies Modul ist lokal importierbar (nur re + stdlib).
# Stub nur anlegen wenn noch nicht vorhanden, damit das echte Modul Vorrang hat.
if "services.chat_intent_heuristics" not in sys.modules:
    _cih = _stub("services.chat_intent_heuristics")
    _cih.is_idea_request = MagicMock(return_value=False)
    _cih.is_own_idea = MagicMock(return_value=False)
    _cih.extract_topic = MagicMock(return_value=None)
_services_pkg.chat_intent_heuristics = sys.modules["services.chat_intent_heuristics"]
# Attribute sicherstellen (falls Stub zuerst von anderem Testmodul angelegt)
_cih_mod = sys.modules["services.chat_intent_heuristics"]
if not hasattr(_cih_mod, "is_idea_request"):
    _cih_mod.is_idea_request = MagicMock(return_value=False)
if not hasattr(_cih_mod, "is_own_idea"):
    _cih_mod.is_own_idea = MagicMock(return_value=False)
if not hasattr(_cih_mod, "extract_topic"):
    _cih_mod.extract_topic = MagicMock(return_value=None)

# tasks.p09_chat_ideas_task — Lazy-Import im P09-Gate von _route_inbound_message
# (#36 S2). Stub mit deliver_ideas_to_chat als MagicMock.
if "tasks.p09_chat_ideas_task" not in sys.modules:
    _p09t = _stub("tasks.p09_chat_ideas_task")
    _p09t.deliver_ideas_to_chat = MagicMock()
# Als Paket-Attribut registrieren
sys.modules["tasks"].p09_chat_ideas_task = sys.modules["tasks.p09_chat_ideas_task"]
_p09t_mod = sys.modules["tasks.p09_chat_ideas_task"]
if not hasattr(_p09t_mod, "deliver_ideas_to_chat"):
    _p09t_mod.deliver_ideas_to_chat = MagicMock()

# tasks.p13_variants_task — Lazy-Import im P13-Gate von _route_inbound_message
# (#36 S3) und in _is_pending_variant_choice (PR 2). Stub mit den vier lazy
# importierten Namen als MagicMock.
# Defaults: keine offene Varianten-Wahl (None/False) — das ist der Normalzustand,
# und Tests, die eine Wahl brauchen, patchen ihn explizit.
if "tasks.p13_variants_task" not in sys.modules:
    _p13t = _stub("tasks.p13_variants_task")
    _p13t.generate_variants_for_chat = MagicMock()
    _p13t._try_p13_variant_choice = MagicMock(return_value=False)
    _p13t._load_pending_idea = MagicMock(return_value=None)
    _p13t._parse_choice_token = MagicMock(return_value=None)
    _p13t._create_manual_idea = MagicMock(return_value=None)
# Als Paket-Attribut registrieren
sys.modules["tasks"].p13_variants_task = sys.modules["tasks.p13_variants_task"]
_p13t_mod = sys.modules["tasks.p13_variants_task"]
if not hasattr(_p13t_mod, "generate_variants_for_chat"):
    _p13t_mod.generate_variants_for_chat = MagicMock()
if not hasattr(_p13t_mod, "_try_p13_variant_choice"):
    _p13t_mod._try_p13_variant_choice = MagicMock(return_value=False)
if not hasattr(_p13t_mod, "_load_pending_idea"):
    _p13t_mod._load_pending_idea = MagicMock(return_value=None)
if not hasattr(_p13t_mod, "_parse_choice_token"):
    _p13t_mod._parse_choice_token = MagicMock(return_value=None)
if not hasattr(_p13t_mod, "_create_manual_idea"):
    _p13t_mod._create_manual_idea = MagicMock(return_value=None)

# ---------------------------------------------------------------------------
# tasks.telegram_task — genau EINMAL laden; bei Wiederholungsimport wiederverwenden
# ---------------------------------------------------------------------------

if "tasks.telegram_task" not in sys.modules:
    _spec = _ilu.spec_from_file_location(
        "tasks.telegram_task",
        os.path.join(_BACKEND_DIR, "tasks", "telegram_task.py"),
    )
    _tt_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.telegram_task"] = _tt_mod
    _spec.loader.exec_module(_tt_mod)
    # Als Attribut des tasks-Stub-Pakets registrieren (für @patch("tasks.telegram_task.*"))
    sys.modules["tasks"].telegram_task = _tt_mod

#: Das gemeinsam genutzte telegram_task-Modulobjekt.
tt = sys.modules["tasks.telegram_task"]


# ---------------------------------------------------------------------------
# Gemeinsame Helfer (aus beiden Test-Dateien konsolidiert)
# ---------------------------------------------------------------------------


def make_extraction(intent: str = "answer_to_question") -> types.SimpleNamespace:
    """Erzeugt einen ExtractionResult-Namespace für Tests."""
    return types.SimpleNamespace(
        intent=intent,
        session_context="active_response",
        extracted_features={"key_insight": "wir wachsen"},
        flagged_for_review=False,
        flag_reasons=[],
        routed_to="ok",
    )


def make_decision(target: str, payload: dict | None = None) -> types.SimpleNamespace:
    """Erzeugt einen RoutingDecision-Namespace für Tests."""
    return types.SimpleNamespace(target=target, payload=payload or {})


def make_p08_result(
    next_action: str = "vertiefen",
    message: str = "Erzähl mir mehr.",
    is_closed: bool = False,
    quality: str = "gold",
    session_id: str = "sess-1",
    was_already_closed: bool = False,
) -> types.SimpleNamespace:
    """Erzeugt einen P08Result-Namespace für Tests.

    Alle Felder sind überschreibbar, damit Tests Folgefrage- und Abschluss-
    Szenarien (is_closed=True, message='Danke!') direkt parametrisieren können.
    was_already_closed (#19) steuert den Post-Generierungs-Trigger: nur ein
    echter active→closed-Übergang (is_closed=True, was_already_closed=False)
    enqueued den session_post_task.
    """
    return types.SimpleNamespace(
        next_action=next_action,
        message=message,
        quality=quality,
        session_id=session_id,
        is_closed=is_closed,
        was_already_closed=was_already_closed,
    )


def active_session() -> types.SimpleNamespace:
    """Erzeugt eine aktive Bot-Session für Tests."""
    return types.SimpleNamespace(id="sess-1", status="active")


def make_guard_db_mock(routed_to: str | None = None) -> MagicMock:
    """Erzeugt einen Mock-DB-Kontext-Manager für den Idempotenz-Guard-SELECT.

    routed_to=None  → (None,)        — Nachricht noch nicht geroutet (Guard lässt durch).
    routed_to='p08' → ('p08_response',) — bereits geroutet (Guard dedupliziert).
    """
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.execute.return_value.fetchone.return_value = (routed_to,)
    return mock_db
