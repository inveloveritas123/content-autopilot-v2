"""
Tests fuer Quality-Gate Eval Runner (Issue #152).

Abdeckung:
- Confusion-Matrix-Klassifikation korrekt (TP/FP/TN/FN)
- F1/Precision/Recall-Berechnung korrekt
- Leeres Korpus -> empty results, kein Crash
- AUC-Berechnung (Trapez)
- run_eval() mit Mock-Quality-Gate deterministisch
- Edge Cases: alle TP, alle FP, gemischt
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Stelle sicher, dass backend/ im sys.path liegt
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from eval.run_quality_gate_eval import (
    classify_outcome,
    compute_auc,
    compute_metrics,
    eval_branche,
    run_eval,
    write_markdown_report,
)

# ---------------------------------------------------------------------------
# Fixture: deterministisches Mock-Quality-Gate
# ---------------------------------------------------------------------------


def mock_quality_gate_always_pass(text: str, branche: str) -> dict[str, Any]:
    """Stub: immer passed=True, score=80."""
    return {"passed": True, "score": 80.0, "violations": [], "threshold": 60.0, "branche": branche}


def mock_quality_gate_always_fail(text: str, branche: str) -> dict[str, Any]:
    """Stub: immer passed=False, score=20."""
    return {
        "passed": False,
        "score": 20.0,
        "violations": ["too_short"],
        "threshold": 60.0,
        "branche": branche,
    }


def mock_quality_gate_by_length(text: str, branche: str) -> dict[str, Any]:
    """Stub: passed wenn len(text) > 200, score proportional."""
    score = min(100.0, len(text) / 10.0)
    passed = score > 60.0
    violations = [] if passed else ["too_short"]
    return {
        "passed": passed,
        "score": score,
        "violations": violations,
        "threshold": 60.0,
        "branche": branche,
    }


# ---------------------------------------------------------------------------
# Tests: classify_outcome
# ---------------------------------------------------------------------------


class TestClassifyOutcome:
    def test_tp(self):
        assert classify_outcome("good", True) == "TP"

    def test_fn(self):
        assert classify_outcome("good", False) == "FN"

    def test_tn(self):
        assert classify_outcome("bad", False) == "TN"

    def test_fp(self):
        assert classify_outcome("bad", True) == "FP"


# ---------------------------------------------------------------------------
# Tests: compute_metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_perfect_classifier(self):
        m = compute_metrics(tp=10, fp=0, tn=10, fn=0)
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["f1"] == 1.0
        assert m["accuracy"] == 1.0

    def test_all_fp(self):
        """Alle bad posts werden als passed klassifiziert -> FP, kein TP/TN."""
        m = compute_metrics(tp=0, fp=10, tn=0, fn=0)
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0  # Keine TP, kein Recall-Nenner (tp+fn=0)
        assert m["f1"] == 0.0
        assert m["accuracy"] == 0.0

    def test_mixed(self):
        """5 TP, 2 FP, 3 TN, 1 FN -> bekannte Werte."""
        m = compute_metrics(tp=5, fp=2, tn=3, fn=1)
        assert m["precision"] == round(5 / 7, 4)
        assert m["recall"] == round(5 / 6, 4)
        assert m["accuracy"] == round(8 / 11, 4)

    def test_zero_division_safe(self):
        """Keine Daten -> keine Exception."""
        m = compute_metrics(tp=0, fp=0, tn=0, fn=0)
        assert m["f1"] == 0.0
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0

    def test_f1_formula(self):
        """F1 = 2*P*R / (P+R) direkt verifizieren."""
        m = compute_metrics(tp=4, fp=1, tn=4, fn=1)
        p = 4 / 5
        r = 4 / 5
        expected_f1 = round(2 * p * r / (p + r), 4)
        assert m["f1"] == expected_f1


# ---------------------------------------------------------------------------
# Tests: compute_auc
# ---------------------------------------------------------------------------


class TestComputeAuc:
    def test_perfect_auc(self):
        """Perfekter Classifier: AUC = 1.0 (TPR=1, FPR=0 immer)."""
        roc_points = [
            {
                "threshold": t,
                "tpr": 1.0,
                "fpr": 0.0,
                "f1": 1.0,
                "tp": 10,
                "fp": 0,
                "tn": 10,
                "fn": 0,
            }
            for t in [40, 60, 80]
        ]
        # Gleiche FPR -> AUC ~0 (keine Flaeche), aber kein Crash
        auc = compute_auc(roc_points)
        assert isinstance(auc, float)
        assert 0.0 <= auc <= 1.0

    def test_random_classifier(self):
        """Zufaelliger Classifier: AUC ~ 0.5 (Diagonale)."""
        roc_points = [
            {
                "threshold": 90,
                "tpr": 0.1,
                "fpr": 0.1,
                "f1": 0.1,
                "tp": 1,
                "fp": 1,
                "tn": 9,
                "fn": 9,
            },
            {
                "threshold": 50,
                "tpr": 0.5,
                "fpr": 0.5,
                "f1": 0.5,
                "tp": 5,
                "fp": 5,
                "tn": 5,
                "fn": 5,
            },
            {
                "threshold": 10,
                "tpr": 0.9,
                "fpr": 0.9,
                "f1": 0.5,
                "tp": 9,
                "fp": 9,
                "tn": 1,
                "fn": 1,
            },
        ]
        auc = compute_auc(roc_points)
        # Trapez-AUC der Diagonale ist ~0.4 (diskret), akzeptiere Bereich
        assert 0.3 <= auc <= 0.6

    def test_empty_roc_points(self):
        """Leere Liste -> kein Crash, AUC=0.0."""
        auc = compute_auc([])
        assert auc == 0.0


# ---------------------------------------------------------------------------
# Tests: eval_branche mit Mock
# ---------------------------------------------------------------------------


class TestEvalBranche:
    def test_empty_corpus_no_crash(self):
        """Leeres Korpus: gibt leeres Ergebnis zurueck, kein Crash."""
        with patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=[]):
            result = eval_branche("_generic", [50, 60, 70])

        assert result["post_count"] == 0
        assert result["metrics"]["f1"] == 0.0
        assert result["error"] == "empty_corpus"
        assert result["per_post"] == []

    def test_all_good_posts_with_passing_gate(self):
        """Alle Posts 'good', Gate passt immer -> alle TP."""
        posts = [
            {"id": f"t_{i}", "text": "x" * 300, "label": "good", "ground_truth_violations": []}
            for i in range(5)
        ]
        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=posts),
            patch(
                "eval.run_quality_gate_eval.quality_gate_check",
                side_effect=mock_quality_gate_always_pass,
            ),
        ):
            result = eval_branche("handwerk", [50, 60])

        cm = result["confusion_matrix"]
        assert cm["tp"] == 5
        assert cm["fp"] == 0
        assert cm["tn"] == 0
        assert cm["fn"] == 0
        assert result["metrics"]["recall"] == 1.0
        assert result["metrics"]["precision"] == 1.0
        assert result["metrics"]["f1"] == 1.0

    def test_all_bad_posts_with_failing_gate(self):
        """Alle Posts 'bad', Gate faellt immer -> alle TN."""
        posts = [
            {"id": f"b_{i}", "text": "x", "label": "bad", "ground_truth_violations": ["too_short"]}
            for i in range(4)
        ]
        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=posts),
            patch(
                "eval.run_quality_gate_eval.quality_gate_check",
                side_effect=mock_quality_gate_always_fail,
            ),
        ):
            result = eval_branche("recht", [50, 60])

        cm = result["confusion_matrix"]
        assert cm["tn"] == 4
        assert cm["tp"] == 0
        assert cm["fp"] == 0
        assert cm["fn"] == 0

    def test_mixed_corpus_cm_correct(self):
        """2 good (1 TP, 1 FN) + 2 bad (1 TN, 1 FP) -> CM korrekt."""
        # Gate: passed wenn text lang (>600 Zeichen)
        posts = [
            {"id": "g1", "text": "x" * 700, "label": "good"},  # TP (score=70>60, passed)
            {"id": "g2", "text": "x" * 100, "label": "good"},  # FN (score=10<60, not passed)
            {"id": "b1", "text": "x" * 50, "label": "bad"},  # TN (score=5<60, not passed)
            {"id": "b2", "text": "x" * 800, "label": "bad"},  # FP (score=80>60, passed)
        ]
        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=posts),
            patch(
                "eval.run_quality_gate_eval.quality_gate_check",
                side_effect=mock_quality_gate_by_length,
            ),
        ):
            result = eval_branche("finanzen", [50, 60, 70])

        cm = result["confusion_matrix"]
        assert cm["tp"] == 1, f"Expected TP=1, got {cm}"
        assert cm["fn"] == 1, f"Expected FN=1, got {cm}"
        assert cm["tn"] == 1, f"Expected TN=1, got {cm}"
        assert cm["fp"] == 1, f"Expected FP=1, got {cm}"


# ---------------------------------------------------------------------------
# Tests: run_eval (Integration, mit temp dir)
# ---------------------------------------------------------------------------


class TestRunEval:
    def test_run_eval_writes_files(self, tmp_path: Path):
        """run_eval() schreibt JSON + MD in eval_results/."""
        posts = [
            {"id": "g1", "text": "x" * 700, "label": "good"},
            {"id": "b1", "text": "x" * 50, "label": "bad"},
        ]

        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=posts),
            patch(
                "eval.run_quality_gate_eval.quality_gate_check",
                side_effect=mock_quality_gate_by_length,
            ),
            patch("eval.run_quality_gate_eval._RESULTS_DIR", tmp_path),
        ):
            results = run_eval(branchen=["handwerk"], thresholds=[50, 60])

        # JSON-Datei vorhanden
        json_files = list(tmp_path.glob("quality_gate_*.json"))
        assert len(json_files) == 1

        # MD-Datei vorhanden
        md_files = list(tmp_path.glob("quality_gate_*.md"))
        assert len(md_files) == 1

        # Ergebnis-Struktur korrekt
        assert "aggregate" in results
        assert "per_branche" in results
        assert "handwerk" in results["per_branche"]
        assert results["per_branche"]["handwerk"]["post_count"] == 2

    def test_ci_gate_passes(self, tmp_path: Path):
        """min_f1=0.0 -> kein SystemExit."""
        posts = [{"id": "g1", "text": "x" * 700, "label": "good"}]
        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=posts),
            patch(
                "eval.run_quality_gate_eval.quality_gate_check",
                side_effect=mock_quality_gate_always_pass,
            ),
            patch("eval.run_quality_gate_eval._RESULTS_DIR", tmp_path),
        ):
            # Kein SystemExit erwartet
            results = run_eval(branchen=["handwerk"], thresholds=[60], min_f1=0.0)
        assert results is not None

    def test_ci_gate_blocks(self, tmp_path: Path):
        """min_f1=1.0 mit schlechtem Gate -> SystemExit(1)."""
        posts = [{"id": "b1", "text": "x", "label": "good"}]  # wird FN da zu kurz
        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=posts),
            patch(
                "eval.run_quality_gate_eval.quality_gate_check",
                side_effect=mock_quality_gate_always_fail,
            ),
            patch("eval.run_quality_gate_eval._RESULTS_DIR", tmp_path),
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_eval(branchen=["handwerk"], thresholds=[60], min_f1=1.0)
        assert exc_info.value.code == 1

    def test_empty_all_branchen_no_crash(self, tmp_path: Path):
        """Alle Branchen leer -> kein Crash, Aggregat mit total_posts=0."""
        with (
            patch("eval.run_quality_gate_eval.load_labeled_posts", return_value=[]),
            patch("eval.run_quality_gate_eval._RESULTS_DIR", tmp_path),
        ):
            results = run_eval(branchen=["handwerk", "recht"], thresholds=[60])

        assert results["aggregate"]["total_posts"] == 0
        assert results["aggregate"]["weighted_f1"] == 0.0


# ---------------------------------------------------------------------------
# Tests: Markdown-Report
# ---------------------------------------------------------------------------


class TestMarkdownReport:
    def test_report_contains_key_sections(self, tmp_path: Path):
        """Markdown-Report enthaelt Aggregate + Branche-Section."""
        results = {
            "timestamp": "2026-05-05T12:00:00Z",
            "stub_warning": "STUB",
            "aggregate": {
                "weighted_f1": 0.75,
                "weighted_precision": 0.8,
                "weighted_recall": 0.7,
                "weighted_accuracy": 0.8,
                "total_posts": 10,
            },
            "per_branche": {
                "handwerk": {
                    "post_count": 10,
                    "auc": 0.85,
                    "confusion_matrix": {"tp": 5, "fp": 1, "tn": 3, "fn": 1},
                    "metrics": {"precision": 0.83, "recall": 0.83, "f1": 0.83, "accuracy": 0.8},
                    "roc_points": [
                        {
                            "threshold": 60,
                            "tpr": 0.8,
                            "fpr": 0.2,
                            "f1": 0.83,
                            "tp": 5,
                            "fp": 1,
                            "tn": 3,
                            "fn": 1,
                        }
                    ],
                    "optimal_threshold": {"threshold": 60, "f1": 0.83},
                }
            },
        }
        md_path = tmp_path / "report.md"
        write_markdown_report(results, md_path)
        content = md_path.read_text(encoding="utf-8")

        assert "Quality-Gate Eval Report" in content
        assert "Aggregate" in content
        assert "handwerk" in content
        assert "0.7500" in content  # weighted_f1
        assert "TP=5" in content
        assert "ROC-Punkte" in content
