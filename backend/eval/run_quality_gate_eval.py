#!/usr/bin/env python3
"""
Quality-Gate Confusion-Matrix Eval Runner — Issue #152.

Laedt labeled_posts.yaml pro Branche, ruft quality_gate_check() auf,
berechnet Confusion-Matrix, Precision/Recall/F1 und ROC-AUC ueber mehrere Thresholds.

Output:
  eval_results/quality_gate_<timestamp>.json   — Maschinenlesbar
  eval_results/quality_gate_<timestamp>.md     — Markdown-Report

Nutzung:
  python backend/eval/run_quality_gate_eval.py
  python backend/eval/run_quality_gate_eval.py --branchen handwerk,recht
  python backend/eval/run_quality_gate_eval.py --thresholds 40,50,60,70,80,90
  python backend/eval/run_quality_gate_eval.py --min-f1 0.75  # CI-Gate
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml fehlt. pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CORPUS_ROOT = Path(__file__).resolve().parent / "quality_gate_corpus"
_RESULTS_DIR = _REPO_ROOT / "eval_results"

# Stub-Import — Production-Implementation in #146
# Direkter File-Import um services/__init__.py (mit LLM-Deps) zu umgehen.
import importlib.util as _ilu

_stub_path = _REPO_ROOT / "backend" / "services" / "quality_gate_stub.py"
_spec = _ilu.spec_from_file_location("quality_gate_stub", _stub_path)
_stub_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_stub_mod)  # type: ignore[union-attr]
quality_gate_check = _stub_mod.quality_gate_check

BRANCHEN = ["handwerk", "recht", "finanzen", "_generic"]
ROC_THRESHOLDS = [40, 50, 60, 70, 80, 90]


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

def load_labeled_posts(branche: str) -> list[dict[str, Any]]:
    """Laedt labeled_posts.yaml fuer eine Branche. Gibt [] zurueck wenn nicht vorhanden."""
    corpus_file = _CORPUS_ROOT / branche / "labeled_posts.yaml"
    if not corpus_file.exists():
        return []
    with open(corpus_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def classify_outcome(label: str, passed: bool) -> str:
    """Ordnet Label + Gate-Ergebnis einer Confusion-Matrix-Klasse zu.

    label "good" + passed True  -> TP (korrekt akzeptiert)
    label "good" + passed False -> FN (faelschlich abgelehnt)
    label "bad"  + passed False -> TN (korrekt abgelehnt)
    label "bad"  + passed True  -> FP (faelschlich akzeptiert)
    """
    is_positive = label == "good"
    if is_positive and passed:
        return "TP"
    if is_positive and not passed:
        return "FN"
    if not is_positive and not passed:
        return "TN"
    return "FP"  # not is_positive and passed


def compute_metrics(tp: int, fp: int, tn: int, fn: int) -> dict[str, float]:
    """Berechnet Precision, Recall, F1, Accuracy aus CM-Werten."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


# ---------------------------------------------------------------------------
# ROC / AUC helpers
# ---------------------------------------------------------------------------

def compute_roc_points(
    posts: list[dict[str, Any]], branche: str, thresholds: list[int]
) -> list[dict[str, Any]]:
    """Berechnet (FPR, TPR) pro Threshold fuer ROC-Kurve.

    Fuer jedes Threshold-Level wird quality_gate_check mit ueberschriebenem
    Threshold-Verhalten aufgerufen, indem die Stub-Score direkt gecheckt wird.
    """
    # quality_gate_check ist Modul-Global (via importlib geladen)
    roc_points = []
    for threshold in thresholds:
        tp = fp = tn = fn = 0
        for post in posts:
            result = quality_gate_check(post["text"], branche)
            # Fuer ROC: passed = score > threshold (threshold als variable Grenze)
            passed_at_threshold = result["score"] > threshold
            outcome = classify_outcome(post["label"], passed_at_threshold)
            if outcome == "TP":
                tp += 1
            elif outcome == "FP":
                fp += 1
            elif outcome == "TN":
                tn += 1
            else:
                fn += 1

        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        metrics = compute_metrics(tp, fp, tn, fn)
        roc_points.append({
            "threshold": threshold,
            "tpr": round(tpr, 4),
            "fpr": round(fpr, 4),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            **metrics,
        })

    return roc_points


def compute_auc(roc_points: list[dict]) -> float:
    """Trapez-AUC aus (fpr, tpr) Punkten. Sortiert nach fpr aufsteigend."""
    sorted_pts = sorted(roc_points, key=lambda p: p["fpr"])
    auc = 0.0
    for i in range(1, len(sorted_pts)):
        dx = sorted_pts[i]["fpr"] - sorted_pts[i - 1]["fpr"]
        avg_y = (sorted_pts[i]["tpr"] + sorted_pts[i - 1]["tpr"]) / 2
        auc += abs(dx) * avg_y
    return round(auc, 4)


def find_optimal_threshold(roc_points: list[dict]) -> dict:
    """Optimaler Threshold = maximales F1."""
    return max(roc_points, key=lambda p: p["f1"])


# ---------------------------------------------------------------------------
# Per-Branche Eval
# ---------------------------------------------------------------------------

def eval_branche(branche: str, thresholds: list[int]) -> dict[str, Any]:
    """Vollstaendige Eval-Rechnung fuer eine Branche."""
    posts = load_labeled_posts(branche)
    if not posts:
        return {
            "branche": branche,
            "post_count": 0,
            "confusion_matrix": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "metrics": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "accuracy": 0.0},
            "roc_points": [],
            "auc": 0.0,
            "optimal_threshold": None,
            "per_post": [],
            "error": "empty_corpus",
        }

    tp = fp = tn = fn = 0
    per_post_results: list[dict] = []

    for post in posts:
        result = quality_gate_check(post["text"], branche)
        outcome = classify_outcome(post["label"], result["passed"])
        if outcome == "TP":
            tp += 1
        elif outcome == "FP":
            fp += 1
        elif outcome == "TN":
            tn += 1
        else:
            fn += 1
        per_post_results.append({
            "id": post.get("id"),
            "label": post["label"],
            "passed": result["passed"],
            "score": result["score"],
            "violations": result["violations"],
            "outcome": outcome,
        })

    metrics = compute_metrics(tp, fp, tn, fn)
    roc_points = compute_roc_points(posts, branche, thresholds)
    auc = compute_auc(roc_points)
    optimal = find_optimal_threshold(roc_points)

    return {
        "branche": branche,
        "post_count": len(posts),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "metrics": metrics,
        "roc_points": roc_points,
        "auc": auc,
        "optimal_threshold": optimal,
        "per_post": per_post_results,
    }


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def aggregate_results(per_branche: dict[str, dict]) -> dict[str, Any]:
    """Gewichtetes Aggregat aller Branchen-Ergebnisse (gewichtet nach post_count)."""
    total_posts = sum(v["post_count"] for v in per_branche.values())
    if total_posts == 0:
        return {"weighted_f1": 0.0, "weighted_precision": 0.0, "weighted_recall": 0.0,
                "weighted_accuracy": 0.0, "total_posts": 0}

    def wavg(metric_key: str) -> float:
        total = sum(
            v["metrics"][metric_key] * v["post_count"]
            for v in per_branche.values()
            if v["post_count"] > 0
        )
        return round(total / total_posts, 4)

    return {
        "weighted_f1": wavg("f1"),
        "weighted_precision": wavg("precision"),
        "weighted_recall": wavg("recall"),
        "weighted_accuracy": wavg("accuracy"),
        "total_posts": total_posts,
        "branchen_count": len(per_branche),
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def cm_table(cm: dict) -> str:
    """Markdown-Tabelle fuer Confusion-Matrix."""
    tp, fp = cm["tp"], cm["fp"]
    fn, tn = cm["fn"], cm["tn"]
    return (
        "| | Pred: PASS | Pred: FAIL |\n"
        "|---|---|---|\n"
        f"| **True: good** | TP={tp} | FN={fn} |\n"
        f"| **True: bad**  | FP={fp} | TN={tn} |"
    )


def write_markdown_report(results: dict, path: Path) -> None:
    ts = results["timestamp"]
    agg = results["aggregate"]
    lines = [
        f"# Quality-Gate Eval Report",
        f"",
        f"**Timestamp:** {ts}",
        f"**Stub:** quality_gate_stub.py (Production-Implementation: Issue #146)",
        f"",
        f"## Aggregate",
        f"",
        f"| Metrik | Wert |",
        f"|---|---|",
        f"| Weighted F1 | {agg['weighted_f1']:.4f} |",
        f"| Weighted Precision | {agg['weighted_precision']:.4f} |",
        f"| Weighted Recall | {agg['weighted_recall']:.4f} |",
        f"| Weighted Accuracy | {agg['weighted_accuracy']:.4f} |",
        f"| Posts gesamt | {agg['total_posts']} |",
        f"",
        f"## Per-Branche",
        f"",
    ]

    for branche, data in results["per_branche"].items():
        m = data["metrics"]
        opt = data.get("optimal_threshold") or {}
        lines += [
            f"### {branche}",
            f"",
            f"Posts: {data['post_count']}  |  AUC: {data['auc']:.4f}  "
            f"|  Optimaler Threshold: {opt.get('threshold', 'n/a')} (F1={opt.get('f1', 0):.4f})",
            f"",
            cm_table(data["confusion_matrix"]),
            f"",
            f"| Precision | Recall | F1 | Accuracy |",
            f"|---|---|---|---|",
            f"| {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['accuracy']:.4f} |",
            f"",
            f"#### ROC-Punkte",
            f"",
            f"| Threshold | TPR | FPR | F1 |",
            f"|---|---|---|---|",
        ]
        for pt in data["roc_points"]:
            lines.append(
                f"| {pt['threshold']} | {pt['tpr']:.4f} | {pt['fpr']:.4f} | {pt['f1']:.4f} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_eval(
    branchen: list[str] | None = None,
    thresholds: list[int] | None = None,
    min_f1: float = 0.0,
) -> dict[str, Any]:
    """Fuehrt die vollstaendige Eval-Suite aus.

    Args:
        branchen:   Subset der Branchen (None = alle).
        thresholds: Threshold-Liste fuer ROC-Kurve.
        min_f1:     CI-Gate — raise SystemExit(1) wenn aggregate.weighted_f1 < min_f1.

    Returns:
        Ergebnis-Dict (wird auch nach eval_results/ geschrieben).
    """
    branchen = branchen or BRANCHEN
    thresholds = thresholds or ROC_THRESHOLDS

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    per_branche: dict[str, dict] = {}
    for branche in branchen:
        per_branche[branche] = eval_branche(branche, thresholds)

    agg = aggregate_results(per_branche)

    results: dict[str, Any] = {
        "timestamp": ts,
        "stub_warning": (
            "STUB: quality_gate_stub.py — Production-Implementation in Issue #146."
        ),
        "aggregate": agg,
        "per_branche": per_branche,
    }

    # Write outputs
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = _RESULTS_DIR / f"quality_gate_{ts}.json"
    md_path = _RESULTS_DIR / f"quality_gate_{ts}.md"

    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown_report(results, md_path)

    print(f"Results written: {json_path}")
    print(f"Report written:  {md_path}")
    print()
    print(f"=== Aggregate ===")
    print(f"  Weighted F1:        {agg['weighted_f1']:.4f}")
    print(f"  Weighted Precision: {agg['weighted_precision']:.4f}")
    print(f"  Weighted Recall:    {agg['weighted_recall']:.4f}")
    print(f"  Total posts:        {agg['total_posts']}")
    print()

    for branche, data in per_branche.items():
        m = data["metrics"]
        opt = data.get("optimal_threshold") or {}
        print(
            f"  [{branche}] F1={m['f1']:.4f}  AUC={data['auc']:.4f}"
            f"  opt_threshold={opt.get('threshold', 'n/a')}"
        )

    # CI-Gate
    if min_f1 > 0.0 and agg["weighted_f1"] < min_f1:
        print(
            f"\nCHECK FAILED: aggregate.weighted_f1={agg['weighted_f1']:.4f} < min_f1={min_f1}",
            file=sys.stderr,
        )
        sys.exit(1)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quality-Gate Eval Runner (Issue #152)"
    )
    parser.add_argument(
        "--branchen",
        type=str,
        default="",
        help="Komma-separierte Branchen-Liste (default: alle)",
    )
    parser.add_argument(
        "--thresholds",
        type=str,
        default="",
        help="Komma-separierte Threshold-Liste fuer ROC (default: 40,50,60,70,80,90)",
    )
    parser.add_argument(
        "--min-f1",
        type=float,
        default=0.0,
        help="CI-Gate: exit(1) wenn weighted_f1 < Wert (default: 0.0 = kein Gate)",
    )
    args = parser.parse_args()

    branchen = (
        [b.strip() for b in args.branchen.split(",") if b.strip()]
        if args.branchen
        else None
    )
    thresholds = (
        [int(t.strip()) for t in args.thresholds.split(",") if t.strip()]
        if args.thresholds
        else None
    )

    run_eval(branchen=branchen, thresholds=thresholds, min_f1=args.min_f1)


if __name__ == "__main__":
    main()
