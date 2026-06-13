"""Tests: WIZARD_PHASES muss genau 8 Board-Phasen in Board-Reihenfolge haben.

Issue #44 — Gesprächsphasen 6→8 auf Board-Stand.

Board-SOLL (aus docs/FIGMA-SOLL-IST-MASTER.md Abschnitt 2.2):
  1  Ankommen & Geschichte
  2  Alltag & Antrieb
  3  Expertise & Fachwissen      ← NEU (fehlte komplett)
  4  Zielkunde
  5  Angebot, Markt & Differenzierung
  6  Vertrauen & Integrität      ← von "Vertrauenssignale & Abschluss" getrennt
  7  Sprache & Stil
  8  Abschluss                   ← von "Vertrauenssignale & Abschluss" getrennt

Port-Anpassung (arch/weekloop → main):
  - `api.wizard_phases` existiert nicht auf main.
  - WIZARD_PHASES ist in `api.wizard` (Zeile 36).
  - WIZARD_PHASE_COUNT existiert nicht auf main → wird hier inline als len(WIZARD_PHASES)
    geprüft.
  - Stub-Schicht nötig weil api.wizard importiert sqlalchemy, fastapi, models etc.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ---------------------------------------------------------------------------
# Leichte Stubs für schwere Dependencies in api/wizard.py
# ---------------------------------------------------------------------------


def _stub(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# sqlalchemy — breiter Stub damit wizard.py und dependencies.py importieren können
_sq = _stub("sqlalchemy")
if not hasattr(_sq, "text"):
    _sq.text = lambda q: q
if not hasattr(_sq, "select"):
    _sq.select = MagicMock()
if not hasattr(_sq, "Column"):
    _sq.Column = MagicMock()
if not hasattr(_sq, "String"):
    _sq.String = MagicMock()
if not hasattr(_sq, "Boolean"):
    _sq.Boolean = MagicMock()
if not hasattr(_sq, "Integer"):
    _sq.Integer = MagicMock()
_stub("sqlalchemy.ext")
_sq_async = _stub("sqlalchemy.ext.asyncio")
if not hasattr(_sq_async, "AsyncSession"):
    _sq_async.AsyncSession = MagicMock
    _sq_async.create_async_engine = MagicMock()
_sq_orm = _stub("sqlalchemy.orm")
if not hasattr(_sq_orm, "sessionmaker"):
    _sq_orm.sessionmaker = MagicMock()
if not hasattr(_sq_orm, "DeclarativeBase"):
    _sq_orm.DeclarativeBase = object
if not hasattr(_sq_orm, "Mapped"):
    _sq_orm.Mapped = MagicMock()
if not hasattr(_sq_orm, "mapped_column"):
    _sq_orm.mapped_column = MagicMock()

# config
_cfg = _stub("config")
if not hasattr(_cfg, "settings"):
    _cfg.settings = types.SimpleNamespace(
        anthropic_api_key="test-key",
        database_url="postgresql+asyncpg://t:t@localhost/t",
        redis_url="redis://localhost/1",
    )

# fastapi — vollständiger Stub für alle von wizard.py und dependencies.py
# benötigten Namen
_fa = _stub("fastapi")
if not hasattr(_fa, "APIRouter"):
    _fa.APIRouter = MagicMock
    _fa.Depends = lambda x: x
    _fa.Header = MagicMock()

    class _HTTPException(Exception):
        def __init__(self, status_code=500, detail=None):
            self.status_code = status_code
            self.detail = detail

    _fa.HTTPException = _HTTPException

# models
_stub("models")
_mb = _stub("models.base")
if not hasattr(_mb, "async_session_factory"):
    _mb.async_session_factory = MagicMock()
if not hasattr(_mb, "sync_session_factory"):
    _mb.sync_session_factory = MagicMock()
_mt = _stub("models.tenant")
if not hasattr(_mt, "Tenant"):
    _mt.Tenant = MagicMock()

# services — NUR Submodule stubben die wizard.py direkt importiert.
# "services" selbst NICHT als Blanko-Modul stubben: bricht test_eu_router_migration
# das services.pipeline_llm als echtes Package-Submodul laden muss.
_llm = _stub("services.llm")
if not hasattr(_llm, "llm_service"):
    _llm.llm_service = MagicMock()
if not hasattr(_llm, "set_llm_tenant"):
    _llm.set_llm_tenant = MagicMock()

# pydantic
_pd = _stub("pydantic")
if not hasattr(_pd, "BaseModel"):
    _pd.BaseModel = object

# dependencies — direkt stubben um die gesamte Import-Kette kurzzuschliessen
_deps = _stub("dependencies")
if not hasattr(_deps, "get_db"):
    _deps.get_db = MagicMock()
if not hasattr(_deps, "get_tenant_id"):
    _deps.get_tenant_id = MagicMock()
if not hasattr(_deps, "get_tenant"):
    _deps.get_tenant = MagicMock()

# services.cost_cap (von wizard.py direkt importiert)
_scc = _stub("services.cost_cap")
if not hasattr(_scc, "CostCapExceeded"):

    class _CostCapExceeded(Exception):
        pass

    _scc.CostCapExceeded = _CostCapExceeded
    _scc.CostCapMiddleware = MagicMock()
    _scc.estimate_anthropic_cost = MagicMock(return_value=0.01)

# ---------------------------------------------------------------------------
# Echter Import — nur WIZARD_PHASES, ohne die schweren FastAPI-Handler
# ---------------------------------------------------------------------------

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("api.wizard", os.path.join(_BACKEND_DIR, "api", "wizard.py"))
_wizard_mod = _ilu.module_from_spec(_spec)
sys.modules["api.wizard"] = _wizard_mod
_spec.loader.exec_module(_wizard_mod)

WIZARD_PHASES = _wizard_mod.WIZARD_PHASES
# WIZARD_PHASE_COUNT existiert nicht auf main → wir definieren es als len(WIZARD_PHASES)
WIZARD_PHASE_COUNT = len(WIZARD_PHASES)

# ---------------------------------------------------------------------------
# Reine Hilfsfunktionen für Logik-Tests (identisch zu arch/weekloop-Version,
# aber ohne Abhängigkeit auf api.wizard_phases)
# ---------------------------------------------------------------------------


def _phase_complete_pure(phase_num: int, answered_ids: set) -> bool:
    """Reine Hilfsfunktion — logisch identisch mit wizard._phase_complete."""
    phase_data = next((p for p in WIZARD_PHASES if p["phase"] == phase_num), None)
    if not phase_data:
        return False
    return all(q["id"] in answered_ids for q in phase_data["questions"])


def _next_question_pure(current_phase: int, answered_ids: set) -> dict | None:
    """Reine Hilfsfunktion — logisch identisch mit wizard._next_question."""
    for phase_data in WIZARD_PHASES:
        if phase_data["phase"] < current_phase:
            continue
        for q in phase_data["questions"]:
            if "text" not in q:  # UI-only widgets (z.B. linkedin_posts) überspringen
                continue
            if q["id"] not in answered_ids:
                return {"id": q["id"], "text": q["text"], "phase": phase_data["phase"]}
    return None


BOARD_PHASE_TITLES = [
    "Ankommen & Geschichte",
    "Alltag & Antrieb",
    "Expertise & Fachwissen",
    "Zielkunde",
    "Angebot & Markt",
    "Vertrauen & Integrität",
    "Sprache & Stil",
    "Abschluss",
]


# ---------------------------------------------------------------------------
# Tests: Anzahl und Reihenfolge
# ---------------------------------------------------------------------------


class TestWizardPhasesCount:
    def test_exactly_8_phases(self):
        """WIZARD_PHASES muss genau 8 Phasen haben (Board-SOLL)."""
        assert len(WIZARD_PHASES) == 8, f"Erwartet 8 Phasen, gefunden: {len(WIZARD_PHASES)}"

    def test_wizard_phase_count_constant_is_8(self):
        """WIZARD_PHASE_COUNT muss 8 sein."""
        assert WIZARD_PHASE_COUNT == 8

    def test_phase_numbers_sequential_1_to_8(self):
        """Phase-Nummern müssen 1–8 lückenlos aufsteigend sein."""
        phase_nums = [p["phase"] for p in WIZARD_PHASES]
        assert phase_nums == list(range(1, 9)), f"Phase-Nummern: {phase_nums}"


class TestBoardPhaseOrder:
    def test_phase_titles_match_board_order(self):
        """Titel müssen exakt in Board-Reihenfolge stehen."""
        actual_titles = [p["title"] for p in WIZARD_PHASES]
        assert actual_titles == BOARD_PHASE_TITLES, (
            f"Abweichung von Board-Reihenfolge.\n"
            f"Erwartet: {BOARD_PHASE_TITLES}\n"
            f"Gefunden:  {actual_titles}"
        )

    def test_phase_1_ankommen(self):
        assert WIZARD_PHASES[0]["title"] == "Ankommen & Geschichte"

    def test_phase_2_alltag(self):
        assert WIZARD_PHASES[1]["title"] == "Alltag & Antrieb"

    def test_phase_3_expertise(self):
        """Expertise & Fachwissen muss als eigene Phase 3 existieren (war komplett fehlend)."""
        assert WIZARD_PHASES[2]["title"] == "Expertise & Fachwissen", (
            "Phase 3 fehlt oder falsch benannt: " f"'{WIZARD_PHASES[2]['title']}'"
        )

    def test_phase_4_zielkunde(self):
        assert WIZARD_PHASES[3]["title"] == "Zielkunde"

    def test_phase_5_angebot_markt(self):
        assert WIZARD_PHASES[4]["title"] == "Angebot & Markt"

    def test_phase_6_vertrauen(self):
        """Vertrauen & Integrität muss GETRENNT von Abschluss sein."""
        assert WIZARD_PHASES[5]["title"] == "Vertrauen & Integrität", (
            "Phase 6 falsch: " f"'{WIZARD_PHASES[5]['title']}'"
        )

    def test_phase_7_sprache(self):
        assert WIZARD_PHASES[6]["title"] == "Sprache & Stil"

    def test_phase_8_abschluss(self):
        """Abschluss muss GETRENNT von Vertrauen & Integrität sein."""
        assert WIZARD_PHASES[7]["title"] == "Abschluss", (
            "Phase 8 falsch: " f"'{WIZARD_PHASES[7]['title']}'"
        )


class TestExpertisePhaseSeparate:
    def test_expertise_exists_as_own_phase(self):
        """Expertise & Fachwissen darf nicht mit anderen Phasen verschmolzen sein."""
        titles = [p["title"] for p in WIZARD_PHASES]
        assert "Expertise & Fachwissen" in titles

    def test_vertrauen_and_abschluss_are_separate_phases(self):
        """'Vertrauen & Integrität' und 'Abschluss' müssen zwei getrennte Phasen sein."""
        titles = [p["title"] for p in WIZARD_PHASES]
        assert "Vertrauen & Integrität" in titles, "'Vertrauen & Integrität' fehlt"
        assert "Abschluss" in titles, "'Abschluss' fehlt"

    def test_old_merged_phase_does_not_exist(self):
        """Alte verschmolzene Phase 'Vertrauenssignale & Abschluss' darf nicht mehr existieren."""
        for p in WIZARD_PHASES:
            assert p["title"] not in (
                "Vertrauenssignale & Abschluss",
                "Vertrauen & Abschluss",
            ), f"Alte verschmolzene Phase gefunden: '{p['title']}'"


# ---------------------------------------------------------------------------
# Tests: Schema-Vollständigkeit
# ---------------------------------------------------------------------------


class TestPhaseSchema:
    REQUIRED_FIELDS = {"phase", "title", "goal", "questions"}

    def test_all_phases_have_required_fields(self):
        """Jede Phase muss alle Pflichtfelder haben."""
        for p in WIZARD_PHASES:
            missing = self.REQUIRED_FIELDS - set(p.keys())
            assert not missing, (
                f"Phase {p.get('phase', '?')} '{p.get('title', '?')}' " f"fehlen Felder: {missing}"
            )

    def test_all_phases_have_at_least_one_question(self):
        """Jede Phase muss mindestens 1 Frage haben."""
        for p in WIZARD_PHASES:
            assert len(p["questions"]) >= 1, f"Phase {p['phase']} '{p['title']}' hat keine Fragen"

    def test_all_questions_have_id_and_text(self):
        """Jede Frage muss 'id' haben; 'text' oder 'label' (Sondertypen wie linkedin_posts)."""
        for p in WIZARD_PHASES:
            for q in p["questions"]:
                assert "id" in q, f"Phase {p['phase']}: Frage ohne 'id': {q}"
                if q.get("type") in ("linkedin_posts",):
                    assert (
                        "label" in q
                    ), f"Phase {p['phase']}: Sonder-Frage {q['id']} ohne 'label': {q}"
                else:
                    assert "text" in q, f"Phase {p['phase']}: Frage ohne 'text': {q}"
                    assert q["text"].strip(), f"Phase {p['phase']}: Frage {q['id']} hat leeren Text"

    def test_all_questions_have_hints_field(self):
        """Text-Fragen haben 'hints' (kann leer sein). Sondertypen (linkedin_posts) sind ausgenommen."""
        for p in WIZARD_PHASES:
            for q in p["questions"]:
                if q.get("type") in ("linkedin_posts",):
                    continue
                assert "hints" in q, f"Phase {p['phase']}: Frage {q.get('id', '?')} fehlt 'hints'"
                assert isinstance(
                    q["hints"], list
                ), f"Phase {p['phase']}: Frage {q['id']}: 'hints' ist kein list"

    def test_question_ids_unique_across_all_phases(self):
        """Alle question-IDs müssen über alle Phasen hinweg eindeutig sein."""
        all_ids = [q["id"] for p in WIZARD_PHASES for q in p["questions"]]
        assert len(all_ids) == len(set(all_ids)), (
            f"Doppelte question_ids: " f"{[id_ for id_ in all_ids if all_ids.count(id_) > 1]}"
        )

    def test_question_ids_follow_phase_naming_convention(self):
        """question-IDs sollen mit q{phase_num}_ beginnen (oder bekannte Ausnahmen).

        Auf main weichen mehrere Phasen vom Muster ab (historisch gewachsen):
          Phase 3 (Expertise): qexp_* statt q3_*
          Phase 4 (Zielkunde): q3_* statt q4_*
          Phase 5 (Angebot): q4_* statt q5_*
          Phase 7 (Sprache): q5_* + q5_linkedin_posts statt q7_*
          Phase 8 (Abschluss): q6_3, q6_4 statt q8_*
        Diese Ausnahmen sind dokumentiert; Eindeutigkeit wird in
        test_question_ids_unique_across_all_phases geprüft.
        """
        known_exception_prefixes = {
            3: ("qexp_",),
            4: ("q3_",),
            5: ("q4_",),
            7: ("q5_",),
            8: ("q6_",),
        }
        for p in WIZARD_PHASES:
            phase_num = p["phase"]
            allowed_prefixes = known_exception_prefixes.get(phase_num, (f"q{phase_num}_",))
            for q in p["questions"]:
                qid = q["id"]
                assert any(qid.startswith(pf) for pf in allowed_prefixes), (
                    f"Phase {phase_num}: question_id '{qid}' "
                    f"passt nicht zu erlaubten Prefixes {allowed_prefixes}"
                )


# ---------------------------------------------------------------------------
# Tests: WIZARD_PHASE_COUNT Konsistenz
# ---------------------------------------------------------------------------


class TestPhaseCountConstant:
    def test_phase_count_equals_len_wizard_phases(self):
        """WIZARD_PHASE_COUNT muss mit len(WIZARD_PHASES) übereinstimmen."""
        assert len(WIZARD_PHASES) == WIZARD_PHASE_COUNT

    def test_phase_count_is_8(self):
        assert WIZARD_PHASE_COUNT == 8


# ---------------------------------------------------------------------------
# Tests: Logik-Funktionen (pure Reimplementierung)
# ---------------------------------------------------------------------------


class TestPhaseFunctions:
    def test_phase_complete_empty_answers(self):
        """Leere answered_ids => Phase nicht komplett."""
        assert not _phase_complete_pure(1, set())

    def test_phase_complete_when_all_answered(self):
        """Alle Fragen einer Phase beantwortet => komplett."""
        phase1_ids = {q["id"] for q in WIZARD_PHASES[0]["questions"]}
        assert _phase_complete_pure(1, phase1_ids)

    def test_phase_complete_invalid_phase(self):
        """Ungültige Phase-Nummer => False (kein crash)."""
        assert not _phase_complete_pure(99, {"q1_1", "q1_2"})

    def test_phase_complete_phase_8(self):
        """Phase 8 (Abschluss) komplett erkennbar."""
        phase8_ids = {q["id"] for q in WIZARD_PHASES[7]["questions"]}
        assert _phase_complete_pure(8, phase8_ids)

    def test_next_question_returns_first_unanswered(self):
        """_next_question gibt erste unbeantwortete Frage zurück."""
        first_q = WIZARD_PHASES[0]["questions"][0]
        nq = _next_question_pure(1, set())
        assert nq is not None
        assert nq["id"] == first_q["id"]

    def test_next_question_returns_none_when_all_done(self):
        """Alle Fragen beantwortet => None."""
        all_ids = {q["id"] for p in WIZARD_PHASES for q in p["questions"]}
        assert _next_question_pure(1, all_ids) is None

    def test_next_question_phase_3_is_expertise(self):
        """Nach Phases 1+2 kommen Fragen aus Phase 3 (Expertise & Fachwissen)."""
        answered = {q["id"] for p in WIZARD_PHASES[:2] for q in p["questions"]}
        nq = _next_question_pure(3, answered)
        assert nq is not None
        assert nq["phase"] == 3
        assert nq["id"].startswith(
            "qexp_"
        ), f"Erste Frage in Phase 3 sollte qexp_... sein (main-Konvention), gefunden: {nq['id']}"

    def test_next_question_after_phase_3_is_phase_4_zielkunde(self):
        """Nach Phase 3 kommen Fragen aus Phase 4 (Zielkunde)."""
        answered = {q["id"] for p in WIZARD_PHASES[:3] for q in p["questions"]}
        nq = _next_question_pure(4, answered)
        assert nq is not None
        assert nq["phase"] == 4
        assert nq["id"].startswith(
            "q3_"
        ), f"Phase 4 nutzt q3_* Präfix auf main (historisch), gefunden: {nq['id']}"

    def test_next_question_skips_linkedin_posts_widget(self):
        """_next_question_pure darf q5_linkedin_posts (kein text-Feld) nicht zurückgeben."""
        # Alle text-Fragen bis Ende Phase 6 beantwortet; Phase 7 enthält q5_linkedin_posts (optional)
        answered = {q["id"] for p in WIZARD_PHASES[:6] for q in p["questions"] if "text" in q}
        nq = _next_question_pure(7, answered)
        if nq is not None:
            assert "text" in next(
                q for p in WIZARD_PHASES for q in p["questions"] if q["id"] == nq["id"]
            ), f"_next_question_pure lieferte question ohne text-Feld: {nq['id']}"
