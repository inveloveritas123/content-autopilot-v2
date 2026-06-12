"""
Tests für das Routing der Setup-Pipeline-Tasks durch den Seam.

Prüft:
1. Policy-Guard: kein Vorkommen von anthropic.Anthropic(, google.generativeai,
   claude-sonnet (als Literal-String) in backend/tasks/p*.py
2. Seam-Nutzung: call_pipeline_llm wird in jedem Task-Modul referenziert
3. Tier-Auflösung: P01/P03/P04/P12/P12B/P12C → S6 (Default)
4. Cost-Pfad bleibt in Tasks (estimate_tier_cost wird importiert, nicht call_pipeline_llm)

Anmerkung zu Test-Grenzen:
  Die Celery-Tasks selbst (run_p01, run_p03, run_p04, run_p12, run_p12b, run_p12c)
  sind NICHT vollständig unit-testbar ohne DB/Celery, weil sie sync_session_factory,
  CostCapMiddleware (async), PromptLoader und die setup_pipeline_run-Tabelle nutzen.
  Der Policy-Guard (statischer Scan) und der Import-Test sind ohne DB testbar.
  Für Integration-Tests müssen DB + Celery verfügbar sein.
"""

import contextlib
import os
import re
import sys

import pytest

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
_TASKS_DIR = os.path.join(_BACKEND_DIR, "tasks")

# Task-Dateien, die den Seam verwenden sollen
_P_TASK_FILES = [
    "p01_task.py",
    "p03_task.py",
    "p04_task.py",
    "p12_task.py",
    "p12b_task.py",
    "p12c_task.py",
]


def _read_task_source(filename: str) -> str:
    path = os.path.join(_TASKS_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Policy-Guard-Tests: statischer Quelltext-Scan
# ---------------------------------------------------------------------------


class TestPolicyGuard:
    """Stellt sicher dass keine verbotenen Direktzugriff-Muster in den Tasks stehen."""

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_no_anthropic_sdk_import(self, filename):
        """Kein 'import anthropic' oder 'anthropic.Anthropic(' in Task-Dateien."""
        source = _read_task_source(filename)
        # Kommentare ausblenden für den Check
        lines_without_comments = _strip_comments(source)

        assert (
            "import anthropic" not in lines_without_comments
        ), f"{filename}: 'import anthropic' gefunden — direkter SDK-Aufruf verboten"
        assert (
            "anthropic.Anthropic(" not in lines_without_comments
        ), f"{filename}: 'anthropic.Anthropic(' gefunden — direkter SDK-Aufruf verboten"

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_no_google_generativeai(self, filename):
        """Kein 'google.generativeai' in Task-Dateien (außer Kommentaren)."""
        source = _read_task_source(filename)
        lines_without_comments = _strip_comments(source)

        assert (
            "google.generativeai" not in lines_without_comments
        ), f"{filename}: 'google.generativeai' gefunden — direkter SDK-Aufruf verboten"

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_no_literal_claude_sonnet_model_id(self, filename):
        """Kein Literal-String 'claude-sonnet' als Modell-ID in Task-Dateien.

        Erlaubt: in Kommentaren (z.B. Docstrings, # Hinweis)
        Verboten: als String-Literal im Code (z.B. model="claude-sonnet-4-6")
        """
        source = _read_task_source(filename)
        lines_without_comments = _strip_comments(source)

        # Suche nach claude-sonnet als String-Literal (in Anführungszeichen)
        pattern = re.compile(r'["\']claude-sonnet["\']|["\']claude-sonnet-\d')
        matches = pattern.findall(lines_without_comments)
        assert not matches, (
            f"{filename}: Literal-Modell-ID 'claude-sonnet*' gefunden: {matches} — "
            "nur Tier-Namen ('S6') erlaubt, Modell-IDs gehören in TIER_MODELS"
        )

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_no_anthropic_model_id_constant(self, filename):
        """Kein ANTHROPIC_MODEL_ID oder VERTEX_MODEL_ID als Konstante."""
        source = _read_task_source(filename)
        lines_without_comments = _strip_comments(source)

        forbidden = ["ANTHROPIC_MODEL_ID", "VERTEX_MODEL_ID", "ANTHROPIC_PRICING_KEY"]
        for forbidden_name in forbidden:
            # Prüfen ob es als Variable-Zuweisung vorkommt (= ...)
            assignment_pattern = re.compile(rf"^{forbidden_name}\s*=", re.MULTILINE)
            assert not assignment_pattern.search(lines_without_comments), (
                f"{filename}: '{forbidden_name} = ...' gefunden — "
                "Modell-IDs dürfen nicht als Task-Konstanten definiert sein"
            )

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_uses_call_pipeline_llm(self, filename):
        """Jede Task-Datei muss call_pipeline_llm importieren oder referenzieren."""
        source = _read_task_source(filename)
        assert "call_pipeline_llm" in source, (
            f"{filename}: 'call_pipeline_llm' nicht gefunden — " "Tasks müssen den Seam nutzen"
        )

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_uses_estimate_tier_cost(self, filename):
        """Jede Task-Datei muss estimate_tier_cost für Cost-Schätzung nutzen."""
        source = _read_task_source(filename)
        assert "estimate_tier_cost" in source, (
            f"{filename}: 'estimate_tier_cost' nicht gefunden — "
            "Tasks müssen den Tier-basierten Cost-Estimator nutzen"
        )


# ---------------------------------------------------------------------------
# Import-Tests: Module müssen importierbar sein (ohne DB)
# ---------------------------------------------------------------------------


class TestTaskModuleImports:
    """Prüft ob Task-Module importierbar sind (statische Analyse)."""

    def test_pipeline_llm_importable(self):
        """services.pipeline_llm muss importierbar sein."""
        sys.path.insert(0, _BACKEND_DIR)
        try:
            import services.pipeline_llm as plm

            assert hasattr(plm, "call_pipeline_llm")
            assert hasattr(plm, "resolve_tier")
            assert hasattr(plm, "estimate_tier_cost")
            assert hasattr(plm, "PipelineLLMResult")
            assert hasattr(plm, "TIER_MODELS")
            assert hasattr(plm, "MODEL_PER_PROMPT")
        finally:
            sys.path.pop(0)

    def test_tier_registry_has_s6(self):
        """TIER_MODELS muss S6 = 'anthropic/claude-sonnet-4-6' enthalten."""
        sys.path.insert(0, _BACKEND_DIR)
        try:
            from services.pipeline_llm import TIER_MODELS

            assert "S6" in TIER_MODELS
            assert TIER_MODELS["S6"] == "anthropic/claude-sonnet-4-6"
        finally:
            sys.path.pop(0)

    def test_model_per_prompt_all_s6(self):
        """Alle Setup-Pipeline-Prompts (P01–P12C) müssen S6 als Default haben."""
        sys.path.insert(0, _BACKEND_DIR)
        try:
            from services.pipeline_llm import MODEL_PER_PROMPT

            for key in ["P01", "P03", "P04", "P12", "P12B", "P12C"]:
                assert (
                    MODEL_PER_PROMPT.get(key) == "S6"
                ), f"{key}: erwartet S6, got {MODEL_PER_PROMPT.get(key)}"
        finally:
            sys.path.pop(0)

    def test_prompt_max_tokens_defined(self):
        """Alle Prompt-Keys müssen max_tokens-Einträge haben."""
        sys.path.insert(0, _BACKEND_DIR)
        try:
            from services.pipeline_llm import PROMPT_MAX_TOKENS

            for key in ["P01", "P03", "P04", "P12", "P12B", "P12C"]:
                assert key in PROMPT_MAX_TOKENS, f"{key} fehlt in PROMPT_MAX_TOKENS"
                assert PROMPT_MAX_TOKENS[key] > 0
        finally:
            sys.path.pop(0)


# ---------------------------------------------------------------------------
# Tier-Auflösungs-Tests mit echtem Modul
# ---------------------------------------------------------------------------


class TestTierResolutionIntegration:
    """Auflösungs-Tests mit dem echten resolve_tier."""

    def setup_method(self):
        sys.path.insert(0, _BACKEND_DIR)

    def teardown_method(self):
        with contextlib.suppress(ValueError):
            sys.path.remove(_BACKEND_DIR)

    def test_p01_resolves_to_s6_by_default(self):
        from services.pipeline_llm import resolve_tier

        tier, model_id = resolve_tier("P01")
        assert tier == "S6"
        assert model_id == "anthropic/claude-sonnet-4-6"

    def test_p03_resolves_to_s6_by_default(self):
        from services.pipeline_llm import resolve_tier

        tier, _ = resolve_tier("P03")
        assert tier == "S6"

    def test_p04_resolves_to_s6_by_default(self):
        from services.pipeline_llm import resolve_tier

        tier, _ = resolve_tier("P04")
        assert tier == "S6"

    def test_p12_resolves_to_s6_by_default(self):
        from services.pipeline_llm import resolve_tier

        tier, _ = resolve_tier("P12")
        assert tier == "S6"

    def test_p12b_resolves_to_s6_by_default(self):
        from services.pipeline_llm import resolve_tier

        tier, _ = resolve_tier("P12B")
        assert tier == "S6"

    def test_p12c_resolves_to_s6_by_default(self):
        from services.pipeline_llm import resolve_tier

        tier, _ = resolve_tier("P12C")
        assert tier == "S6"

    def test_env_override_changes_tier(self, monkeypatch):
        """MODEL_TIER_P01=S1 ändert Tier für P01."""
        monkeypatch.setenv("MODEL_TIER_P01", "S1")
        from services.pipeline_llm import resolve_tier

        tier, _ = resolve_tier("P01")
        assert tier == "S1"

    def test_env_override_only_affects_specified_prompt(self, monkeypatch):
        """MODEL_TIER_P01=S1 beeinflusst nicht P03."""
        monkeypatch.setenv("MODEL_TIER_P01", "S1")
        from services.pipeline_llm import resolve_tier

        tier_p01, _ = resolve_tier("P01")
        tier_p03, _ = resolve_tier("P03")
        assert tier_p01 == "S1"
        assert tier_p03 == "S6"  # P03 bleibt unverändert


# ---------------------------------------------------------------------------
# BUG-1-Fix: Statischer Test — jeder Task hat except BudgetExceededError im Hauptpfad
# ---------------------------------------------------------------------------


class TestBudgetExceededHandling:
    """Statischer Scan: Jeder der 6 Tasks muss BudgetExceededError abfangen
    und 'paused_for_cost' zurückgeben — kein Celery-Retry.

    Hintergrund: call_pipeline_llm() wirft BudgetExceededError bei HTTP 412.
    Ohne diesen Zweig landet der Fehler in 'except Exception' → status='failed'
    + self.retry() oder status='failed' ohne paused_for_cost.
    """

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_task_imports_budget_exceeded_error(self, filename):
        """Jede Task-Datei muss BudgetExceededError importieren."""
        source = _read_task_source(filename)
        assert "BudgetExceededError" in source, (
            f"{filename}: 'BudgetExceededError' nicht gefunden — "
            "Tasks müssen BudgetExceededError abfangen (BUG-1-Fix)"
        )

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_task_has_except_budget_exceeded_branch(self, filename):
        """Jede Task-Datei muss einen 'except BudgetExceededError' Zweig haben."""
        source = _read_task_source(filename)
        assert re.search(r"except\s+BudgetExceededError", source), (
            f"{filename}: kein 'except BudgetExceededError' Zweig gefunden — "
            "BUG-1-Fix nicht angewendet"
        )

    @pytest.mark.parametrize("filename", _P_TASK_FILES)
    def test_task_returns_paused_for_cost_on_budget_exceeded(self, filename):
        """Im BudgetExceededError-Zweig muss 'paused_for_cost' zurückgegeben werden."""
        source = _read_task_source(filename)
        # Prüfe ob 'paused_for_cost' im Quelltext nach 'except BudgetExceededError' vorkommt.
        # Einfacher Heuristik-Check: beide Strings müssen im Modul vorhanden sein.
        assert "paused_for_cost" in source, (
            f"{filename}: 'paused_for_cost' nicht gefunden — "
            "BudgetExceededError-Zweig muss 'paused_for_cost' zurückgeben"
        )
        # Striktere Prüfung: nach 'except BudgetExceededError' muss 'paused_for_cost' folgen
        # (mindestens innerhalb der nächsten 30 Zeilen nach dem except-Zweig)
        lines = source.splitlines()
        found_paused = False
        for i, line in enumerate(lines):
            if re.search(r"except\s+BudgetExceededError", line):
                # Suche in den nächsten 30 Zeilen
                window = "\n".join(lines[i : i + 30])
                if "paused_for_cost" in window:
                    found_paused = True
                    break
        assert found_paused, (
            f"{filename}: 'paused_for_cost' nicht innerhalb von 30 Zeilen nach "
            "'except BudgetExceededError' gefunden"
        )


# ---------------------------------------------------------------------------
# Hilfsfunktion: Kommentare aus Python-Quelltext entfernen
# ---------------------------------------------------------------------------


def _strip_comments(source: str) -> str:
    """Entfernt Python-Kommentare (#...) und Docstrings aus dem Quelltext.

    Für den Policy-Guard: verhindert False-Positives wenn verbotene Strings
    nur in Kommentaren oder Docstrings stehen.
    """
    result_lines = []
    in_multiline = False
    multiline_char = None

    for line in source.splitlines():
        stripped = line.strip()

        # Triple-Quote Docstrings (mehrzeilig) überspringen
        if in_multiline:
            if multiline_char in line:
                in_multiline = False
            continue

        if stripped.startswith('"""') or stripped.startswith("'''"):
            multiline_char = stripped[:3]
            # Endet auf der gleichen Zeile?
            rest = stripped[3:]
            if multiline_char in rest:
                continue  # Einzeiliger Docstring
            in_multiline = True
            continue

        # Zeilweise Kommentare entfernen (# ...)
        # Achtung: '#' in Strings nicht entfernen — einfache Näherung reicht für Policy-Guard
        hash_pos = line.find("#")
        if hash_pos >= 0:
            # Nur entfernen wenn # nicht innerhalb eines Strings
            before = line[:hash_pos]
            # Prüfe ob gerade Anzahl von " und ' vor dem #
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                line = before

        result_lines.append(line)

    return "\n".join(result_lines)
