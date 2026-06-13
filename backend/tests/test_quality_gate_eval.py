"""
Dep-freier F1-Eval-Test fuer den Quality-Gate-Scorer (Issue #38, Chunk 1).

Spiegelt die Harness-Logik aus backend/eval/run_quality_gate_eval.py:
  - Laedt labeled_posts.yaml per Branche via pyyaml
  - Importiert quality_gate_stub.py via importlib (file-import, kein services.__init__)
  - Rechnet Confusion-Matrix + F1 (identische Formeln wie Harness)
  - Asserts: gesamt-F1 >= GESAMT_MIN_F1, je-Branche-F1 >= BRANCHE_MIN_F1

Py3.9-kompatibel. Keine LLM/sqlalchemy/fastapi Abhaengigkeit.
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
_STUB_PATH = _BACKEND_DIR / "services" / "quality_gate_stub.py"
_CORPUS_ROOT = _BACKEND_DIR / "eval" / "quality_gate_corpus"

BRANCHEN = ["_generic", "handwerk", "recht", "finanzen"]

# ---------------------------------------------------------------------------
# F1-Ziele (NIEMALS aufweichen — Scorer verbessern wenn zu niedrig)
# ---------------------------------------------------------------------------
GESAMT_MIN_F1 = 0.90   # Gemessener Wert 2026-06-13: 1.0 — Assertion auf sicheren Wert gesetzt
BRANCHE_MIN_F1 = 0.80  # Je-Branche Minimum

# ---------------------------------------------------------------------------
# File-Import des Scorers (wie der Harness)
# ---------------------------------------------------------------------------


def _load_scorer():
    """Laedt quality_gate_check via file-import ohne services.__init__."""
    assert _STUB_PATH.exists(), f"Scorer nicht gefunden: {_STUB_PATH}"
    spec = importlib.util.spec_from_file_location("quality_gate_stub", _STUB_PATH)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert hasattr(mod, "quality_gate_check"), "quality_gate_check fehlt im Modul"
    return mod.quality_gate_check


quality_gate_check = _load_scorer()


# ---------------------------------------------------------------------------
# Helpers (mirror Harness-Logik)
# ---------------------------------------------------------------------------


def _load_corpus(branche: str) -> list[dict[str, Any]]:
    corpus_file = _CORPUS_ROOT / branche / "labeled_posts.yaml"
    assert corpus_file.exists(), f"Korpus-Datei fehlt: {corpus_file}"
    with open(corpus_file, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, list) and len(data) > 0, f"Leerer Korpus: {branche}"
    return data


def _compute_f1(tp: int, fp: int, _tn: int, fn: int) -> float:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return f1


def _eval_branche(branche: str) -> dict[str, Any]:
    posts = _load_corpus(branche)
    tp = fp = tn = fn = 0
    per_post = []
    for post in posts:
        assert "text" in post, f"Feld 'text' fehlt in {branche}: {post}"
        assert "label" in post, f"Feld 'label' fehlt in {branche}: {post}"
        assert post["label"] in ("good", "bad"), f"Unguelltiges Label: {post['label']}"

        result = quality_gate_check(post["text"], branche)
        passed = result["passed"]
        label = post["label"]

        if label == "good" and passed:
            tp += 1
            outcome = "TP"
        elif label == "good" and not passed:
            fn += 1
            outcome = "FN"
        elif label == "bad" and not passed:
            tn += 1
            outcome = "TN"
        else:
            fp += 1
            outcome = "FP"

        per_post.append(
            {
                "id": post.get("id", "?"),
                "label": label,
                "passed": passed,
                "score": result["score"],
                "outcome": outcome,
                "violations": result["violations"],
            }
        )

    f1 = _compute_f1(tp, fp, tn, fn)
    return {
        "branche": branche,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "f1": f1,
        "per_post": per_post,
        "post_count": len(posts),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignaturStabilitaet:
    """Quality-Gate-Kontrakt: Rueckgabe-Shape + Typen."""

    def test_returns_required_keys(self):
        result = quality_gate_check("Hallo Welt.", "_generic")
        required_keys = {"passed", "score", "violations", "threshold", "branche"}
        assert required_keys <= set(result.keys()), (
            f"Fehlende Keys: {required_keys - set(result.keys())}"
        )

    def test_passed_is_bool(self):
        result = quality_gate_check("Hallo Welt.", "_generic")
        assert isinstance(result["passed"], bool)

    def test_score_is_float_in_range(self):
        result = quality_gate_check("Hallo Welt.", "_generic")
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 100.0

    def test_violations_is_list(self):
        result = quality_gate_check("Hallo Welt.", "_generic")
        assert isinstance(result["violations"], list)

    def test_threshold_is_float(self):
        result = quality_gate_check("Hallo Welt.", "_generic")
        assert isinstance(result["threshold"], float)

    def test_branche_echoed(self):
        for branche in BRANCHEN:
            result = quality_gate_check("Hallo.", branche)
            assert result["branche"] == branche

    def test_empty_post_not_passed(self):
        result = quality_gate_check("", "_generic")
        assert result["passed"] is False
        assert "empty_post" in result["violations"]
        assert result["score"] == 0.0

    def test_whitespace_only_not_passed(self):
        result = quality_gate_check("   \n\n  ", "_generic")
        assert result["passed"] is False


class TestF1ProBranche:
    """F1 je Branche muss >= BRANCHE_MIN_F1 sein."""

    @pytest.mark.parametrize("branche", BRANCHEN)
    def test_branche_f1(self, branche: str):
        result = _eval_branche(branche)
        # Diagnostische Ausgabe bei Fehler
        misclassified = [p for p in result["per_post"] if p["outcome"] in ("FP", "FN")]
        f1 = result["f1"]
        assert f1 >= BRANCHE_MIN_F1, (
            f"[{branche}] F1={f1:.4f} < {BRANCHE_MIN_F1} "
            f"(TP={result['tp']} FP={result['fp']} TN={result['tn']} FN={result['fn']})\n"
            f"Fehlklassifiziert: {misclassified}"
        )


class TestGesamtF1:
    """Gesamt-F1 (gewichtet nach Post-Zahl) muss >= GESAMT_MIN_F1 sein."""

    def test_gesamt_f1(self):
        total_tp = total_fp = total_tn = total_fn = 0
        total_posts = 0

        for branche in BRANCHEN:
            result = _eval_branche(branche)
            total_tp += result["tp"]
            total_fp += result["fp"]
            total_tn += result["tn"]
            total_fn += result["fn"]
            total_posts += result["post_count"]

        gesamt_f1 = _compute_f1(total_tp, total_fp, total_tn, total_fn)
        assert gesamt_f1 >= GESAMT_MIN_F1, (
            f"Gesamt-F1={gesamt_f1:.4f} < {GESAMT_MIN_F1} "
            f"(TP={total_tp} FP={total_fp} TN={total_tn} FN={total_fn}, "
            f"{total_posts} Posts total)"
        )

    def test_no_false_positives_on_spam(self):
        """Spam-Posts (excessive_caps + too_short) duerfen NICHT als 'good' durchgehen."""
        spam_posts = [
            ("JETZT KLICKEN!!! GRATIS ANGEBOT!!!", "_generic"),
            ("KLAGE JETZT!!! SOFORT GELD ZURUECK!!!", "recht"),
            ("REICH WERDEN SCHNELL!!! KRYPTO!!!", "finanzen"),
            ("SUPER ANGEBOT!!! JETZT KAUFEN!!!", "handwerk"),
        ]
        for text, branche in spam_posts:
            result = quality_gate_check(text, branche)
            assert result["passed"] is False, (
                f"Spam-Post wurde faelschlich akzeptiert [{branche}]: {text!r}"
            )

    def test_all_corpus_good_posts_pass(self):
        """Alle als 'good' gelabelten Posts muessen passed=True liefern."""
        failures = []
        for branche in BRANCHEN:
            posts = _load_corpus(branche)
            for post in posts:
                if post["label"] == "good":
                    result = quality_gate_check(post["text"], branche)
                    if not result["passed"]:
                        failures.append(
                            f"[{branche}] {post.get('id', '?')}: "
                            f"score={result['score']:.1f} violations={result['violations']}"
                        )
        assert not failures, "Good-Posts wurden faelschlich abgelehnt:\n" + "\n".join(failures)

    def test_all_corpus_bad_posts_fail(self):
        """Alle als 'bad' gelabelten Posts muessen passed=False liefern."""
        failures = []
        for branche in BRANCHEN:
            posts = _load_corpus(branche)
            for post in posts:
                if post["label"] == "bad":
                    result = quality_gate_check(post["text"], branche)
                    if result["passed"]:
                        failures.append(
                            f"[{branche}] {post.get('id', '?')}: "
                            f"score={result['score']:.1f} violations={result['violations']}"
                        )
        assert not failures, "Bad-Posts wurden faelschlich akzeptiert:\n" + "\n".join(failures)


class TestKorpusIntegritaet:
    """Prueft die Qualitaet des Korpus selbst."""

    @pytest.mark.parametrize("branche", BRANCHEN)
    def test_corpus_has_both_labels(self, branche: str):
        posts = _load_corpus(branche)
        labels = {p["label"] for p in posts}
        assert "good" in labels, f"[{branche}] Kein 'good'-Label im Korpus"
        assert "bad" in labels, f"[{branche}] Kein 'bad'-Label im Korpus"

    @pytest.mark.parametrize("branche", BRANCHEN)
    def test_corpus_min_size(self, branche: str):
        posts = _load_corpus(branche)
        assert len(posts) >= 5, f"[{branche}] Korpus zu klein: {len(posts)} Posts"

    @pytest.mark.parametrize("branche", BRANCHEN)
    def test_corpus_fields(self, branche: str):
        posts = _load_corpus(branche)
        for post in posts:
            assert "text" in post
            assert "label" in post
            assert post["label"] in ("good", "bad")
