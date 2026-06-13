"""Tests für _resolve_branche in tasks.session_post_task (Issue #81).

Verifiziert:
- Bekannte Werte werden korrekt auf kanonischen Branchen-Key normalisiert.
- Unbekannte / leere / fehlende Werte → "_generic" (fail-open).
- load_active_profile wirft Exception → "_generic" (fail-open, Versandpfad nie stören).
- Toleranter Teilstring-Match (Rechtsanwaltskanzlei→recht, etc.).

Baut auf dem Stub-Bootstrap-Muster von test_quality_gate_send_wiring.py auf
(geteilte _telegram_task_env, spec_from_file_location für das echte Task-Modul).
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
from unittest.mock import MagicMock, patch

# Geteilte Stub-Umgebung ZUERST — richtet sqlalchemy/config/models.base/celery/
# tasks.telegram_task (real)/api.telegram/services.* konsistent ein.
from tests import _telegram_task_env as _env  # noqa: F401

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# api.ideas — Lazy-Import-Ziel (_run_p12_p12b_pipeline).
import api as _api_pkg

if "api.ideas" not in sys.modules:
    _ai = _stub("api.ideas")
    _ai._run_p12_p12b_pipeline = MagicMock()
_api_pkg.ideas = sys.modules["api.ideas"]

# services.canonical_profiles — Lazy-Import-Ziel.
import services as _services_pkg

if "services.canonical_profiles" not in sys.modules:
    _cp = _stub("services.canonical_profiles")
    _cp.load_active_profiles = MagicMock(
        return_value={
            "voice_profile": {"payload": {}},
            "audience_avatar": {"payload": {}},
        }
    )
    _cp.load_active_profile = MagicMock(return_value=({}, False))
_services_pkg.canonical_profiles = sys.modules["services.canonical_profiles"]

# services.quality_gate_stub — Lazy-Import-Ziel.
if "services.quality_gate_stub" not in sys.modules:
    _qgs = _stub("services.quality_gate_stub")
    _qgs.quality_gate_check = MagicMock(
        return_value={
            "passed": True,
            "score": 80.0,
            "violations": [],
            "threshold": 55.0,
            "branche": "_generic",
        }
    )
    _qgs.clear_config_cache = MagicMock()
_services_pkg.quality_gate_stub = sys.modules["services.quality_gate_stub"]
# _telegram_task_env may have created the stub without clear_config_cache — add it if missing.
if not hasattr(_services_pkg.quality_gate_stub, "clear_config_cache"):
    _services_pkg.quality_gate_stub.clear_config_cache = MagicMock()

# session_post_task: das ECHTE Modul laden.
_existing = sys.modules.get("tasks.session_post_task")
if _existing is None or not hasattr(_existing, "_build_qa_pairs"):
    _spec = _ilu.spec_from_file_location(
        "tasks.session_post_task",
        os.path.join(_BACKEND_DIR, "tasks", "session_post_task.py"),
    )
    _spt_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.session_post_task"] = _spt_mod
    _spec.loader.exec_module(_spt_mod)
    sys.modules["tasks"].session_post_task = _spt_mod

spt = sys.modules["tasks.session_post_task"]

clear_config_cache = _services_pkg.quality_gate_stub.clear_config_cache

# ---------------------------------------------------------------------------
# Helfer: load_active_profile mit gewünschtem branche-Wert mocken
# ---------------------------------------------------------------------------


def _mock_lap(branche_value):
    """Gibt einen patch-Context zurück, der load_active_profile mit branche-Wert stubbt."""
    payload = {} if branche_value is None else {"branche": branche_value}
    return patch(
        "services.canonical_profiles.load_active_profile",
        return_value=(payload, True),
        create=True,
    )


def _mock_lap_raises(exc_class=RuntimeError):
    """Gibt einen patch-Context zurück, der load_active_profile mit Exception stubbt."""
    return patch(
        "services.canonical_profiles.load_active_profile",
        side_effect=exc_class("profile not found"),
        create=True,
    )


# ---------------------------------------------------------------------------
# Tests für _resolve_branche
# ---------------------------------------------------------------------------


class TestResolveBranche:
    """Unit-Tests für die _resolve_branche-Hilfsfunktion."""

    def setup_method(self):
        """Clear cache before each test for isolation."""
        clear_config_cache()

    # ------------------------------------------------------------------
    # Direkte Branchen-Keys (exakter lower()-Match)
    # ------------------------------------------------------------------

    def test_exact_key_recht(self):
        with _mock_lap("recht"):
            assert spt._resolve_branche("t1") == "recht"

    def test_exact_key_handwerk(self):
        with _mock_lap("handwerk"):
            assert spt._resolve_branche("t1") == "handwerk"

    def test_exact_key_finanzen(self):
        with _mock_lap("finanzen"):
            assert spt._resolve_branche("t1") == "finanzen"

    def test_exact_key_case_insensitive(self):
        with _mock_lap("Handwerk"):
            assert spt._resolve_branche("t1") == "handwerk"

    # ------------------------------------------------------------------
    # Teilstring-Match (tolerante Normalisierung)
    # ------------------------------------------------------------------

    def test_rechtsanwaltskanzlei_resolves_to_recht(self):
        """'Rechtsanwaltskanzlei' → 'recht' (enthält 'recht')."""
        with _mock_lap("Rechtsanwaltskanzlei"):
            assert spt._resolve_branche("t1") == "recht"

    def test_anwaltskanzlei_resolves_to_recht(self):
        """'Anwaltskanzlei' → 'recht' (enthält 'kanzlei' UND 'anwalt')."""
        with _mock_lap("Anwaltskanzlei"):
            assert spt._resolve_branche("t1") == "recht"

    def test_handwerksbetrieb_resolves_to_handwerk(self):
        """'Handwerksbetrieb' → 'handwerk' (enthält 'handwerk')."""
        with _mock_lap("Handwerksbetrieb"):
            assert spt._resolve_branche("t1") == "handwerk"

    def test_finanzberatung_resolves_to_finanzen(self):
        """'Finanzberatung' → 'finanzen' (enthält 'finanz')."""
        with _mock_lap("Finanzberatung"):
            assert spt._resolve_branche("t1") == "finanzen"

    def test_steuerberatung_resolves_to_finanzen(self):
        """'Steuerberatung' → 'finanzen' (enthält 'steuer')."""
        with _mock_lap("Steuerberatung"):
            assert spt._resolve_branche("t1") == "finanzen"

    def test_bauunternehmen_resolves_to_handwerk(self):
        """'Bauunternehmen' → 'handwerk' (enthält 'bau')."""
        with _mock_lap("Bauunternehmen"):
            assert spt._resolve_branche("t1") == "handwerk"

    # ------------------------------------------------------------------
    # Unbekannte / leere / fehlende Werte → "_generic"
    # ------------------------------------------------------------------

    def test_unknown_branche_returns_generic(self):
        with _mock_lap("Gastronomie"):
            assert spt._resolve_branche("t1") == "_generic"

    def test_empty_string_returns_generic(self):
        with _mock_lap(""):
            assert spt._resolve_branche("t1") == "_generic"

    def test_whitespace_only_returns_generic(self):
        with _mock_lap("   "):
            assert spt._resolve_branche("t1") == "_generic"

    def test_missing_branche_key_returns_generic(self):
        """Payload ohne 'branche'-Schlüssel → '_generic'."""
        with _mock_lap(None):
            assert spt._resolve_branche("t1") == "_generic"

    def test_none_branche_returns_generic(self):
        """branche=None explizit → '_generic'."""
        with patch(
            "services.canonical_profiles.load_active_profile",
            return_value=({"branche": None}, True),
            create=True,
        ):
            assert spt._resolve_branche("t1") == "_generic"

    # ------------------------------------------------------------------
    # Robustheit: branche als Liste oder Dict
    # ------------------------------------------------------------------

    def test_branche_as_list_uses_first_element(self):
        """branche als Liste → erstes nicht-leeres Element wird ausgewertet."""
        with patch(
            "services.canonical_profiles.load_active_profile",
            return_value=({"branche": ["Rechtsanwaltskanzlei", "Kanzlei"]}, True),
            create=True,
        ):
            assert spt._resolve_branche("t1") == "recht"

    def test_branche_as_empty_list_returns_generic(self):
        with patch(
            "services.canonical_profiles.load_active_profile",
            return_value=({"branche": []}, True),
            create=True,
        ):
            assert spt._resolve_branche("t1") == "_generic"

    def test_branche_as_dict_with_name_key(self):
        """branche als Dict mit 'name'-Schlüssel → normalisiert."""
        with patch(
            "services.canonical_profiles.load_active_profile",
            return_value=({"branche": {"name": "Handwerksbetrieb"}}, True),
            create=True,
        ):
            assert spt._resolve_branche("t1") == "handwerk"

    # ------------------------------------------------------------------
    # fail-open: Exception → "_generic" (Versandpfad darf nie blockiert werden)
    # ------------------------------------------------------------------

    def test_load_active_profile_raises_returns_generic(self):
        """load_active_profile wirft Exception → '_generic' (fail-open)."""
        with _mock_lap_raises(RuntimeError):
            assert spt._resolve_branche("t1") == "_generic"

    def test_load_active_profile_raises_key_error_returns_generic(self):
        with _mock_lap_raises(KeyError):
            assert spt._resolve_branche("t1") == "_generic"

    def test_load_active_profile_raises_value_error_returns_generic(self):
        with _mock_lap_raises(ValueError):
            assert spt._resolve_branche("t1") == "_generic"
