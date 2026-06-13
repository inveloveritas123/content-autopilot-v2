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

# Defensiv: ein anderes Test-Modul kann sqlalchemy(-Untermodule) bereits
# UNVOLLSTÄNDIG gestubbt haben (nur den Modul-Namen, ohne AsyncSession etc.).
# Darum Attribute IMMER sicherstellen (nur setzen wenn fehlend → in CI mit echtem
# sqlalchemy werden die echten Attribute nie überschrieben).
_sq = _stub("sqlalchemy")  # get-or-create
if not hasattr(_sq, "text"):
    _sq.text = lambda q: q

_sq_async = _stub("sqlalchemy.ext.asyncio")  # get-or-create
if not hasattr(_sq_async, "AsyncSession"):
    _sq_async.AsyncSession = MagicMock
if not hasattr(_sq_async, "create_async_engine"):
    _sq_async.create_async_engine = MagicMock()
_stub("sqlalchemy.ext")  # get-or-create
_sq_orm = _stub("sqlalchemy.orm")  # get-or-create
if not hasattr(_sq_orm, "sessionmaker"):
    _sq_orm.sessionmaker = MagicMock()

# ---------------------------------------------------------------------------
# config.settings
# ---------------------------------------------------------------------------

if "config" not in sys.modules:
    _cfg = _stub("config")
    _cfg.settings = types.SimpleNamespace(
        telegram_bot_token="test-token",
        database_url="postgresql+asyncpg://t:t@localhost/t",
    )

# ---------------------------------------------------------------------------
# models.base
# ---------------------------------------------------------------------------

if "models" not in sys.modules:
    _stub("models")
if "models.base" not in sys.modules:
    _mb = _stub("models.base")
    _mb.sync_session_factory = MagicMock()

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

# services.llm VOR services-Import stubben (str|None in llm.py bricht Py3.9)
if "services.llm" not in sys.modules:
    _llm = _stub("services.llm")
    _llm.llm_service = MagicMock()

    class _BudgetExceededError(Exception):
        pass

    class _RateLimitExceededError(Exception):
        pass

    _llm.BudgetExceededError = _BudgetExceededError
    _llm.RateLimitExceededError = _RateLimitExceededError

# services.nextcloud VOR services-Import stubben
if "services.nextcloud" not in sys.modules:
    _nc = _stub("services.nextcloud")
    _nc.nextcloud_client = None

# Jetzt services als echtes Paket importieren (damit __path__ gesetzt ist)
import services as _services_pkg

# services.voice_transcription — telegram_task importiert es auf Modulebene
if "services.voice_transcription" not in sys.modules:
    _vt = _stub("services.voice_transcription")

    class _TranscriptionError(Exception):
        pass

    class _TranscriptionResult:
        def __init__(self, text="", model_name="whisper", confidence=0.9):
            self.text = text
            self.model_name = model_name
            self.confidence = confidence

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

# services.layer2_routing — lazy in _route_inbound_message importiert
if "services.layer2_routing" not in sys.modules:
    _l2 = _stub("services.layer2_routing")
    _l2.route_telegram_intent = MagicMock()
    _l2.persist_routing_decision = MagicMock()
_services_pkg.layer2_routing = sys.modules["services.layer2_routing"]

# Sicherstellen, dass route_telegram_intent/persist_routing_decision/RoutingDecision
# immer vorhanden sind (unabhängig davon, welches Testmodul den Stub zuerst anlegt).
# RoutingDecision wird vom P09-Gate (#36) lazy importiert.
_l2_mod = sys.modules["services.layer2_routing"]
if not hasattr(_l2_mod, "persist_routing_decision"):
    _l2_mod.persist_routing_decision = MagicMock()
if not hasattr(_l2_mod, "route_telegram_intent"):
    _l2_mod.route_telegram_intent = MagicMock()
if not hasattr(_l2_mod, "RoutingDecision"):
    def _RoutingDecision(target, payload=None, reason=""):
        return types.SimpleNamespace(target=target, payload=payload or {}, reason=reason)

    _l2_mod.RoutingDecision = _RoutingDecision

# services.p08_service — lazy in _route_inbound_message importiert
if "services.p08_service" not in sys.modules:
    _p08 = _stub("services.p08_service")
    _p08.p08_response = MagicMock()
_services_pkg.p08_service = sys.modules["services.p08_service"]

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
    _api_pkg.__package__ = "api"
if "api.telegram" not in sys.modules:
    _at = _stub("api.telegram")
    _at._send_telegram_message = MagicMock()
# Als Paket-Attribut registrieren (für @patch-Auflösung via getattr)
sys.modules["api"].telegram = sys.modules["api.telegram"]

# ---------------------------------------------------------------------------
# celery + tasks.celery_app
# ---------------------------------------------------------------------------

if "celery" not in sys.modules:
    _stub("celery")


class _FakeCeleryApp:
    def task(self, *a, **kw):
        def deco(fn):
            return fn

        return deco


if "tasks" not in sys.modules:
    _stub("tasks")
# Ensure tasks is a real package (may be a plain ModuleType stub without __path__).
# Without __path__, submodule imports like "from tasks.p03_task import ..." fail.
_tasks_pkg = sys.modules["tasks"]
if not hasattr(_tasks_pkg, "__path__"):
    _tasks_pkg.__path__ = [os.path.join(_BACKEND_DIR, "tasks")]
    _tasks_pkg.__package__ = "tasks"
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
