"""
Eval-Ergebnisse API — /api/eval/

Liefert Quality-Gate Eval-History aus eval_results/*.json fuer das Dashboard.
File-System-Persistenz (DB-Migration als Followup geplant).

Issue #152: Confusion-Matrix / Eval-Infrastruktur.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eval", tags=["Eval"])

# eval_results/ liegt im Repo-Root (zwei Ebenen ueber backend/)
_RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "eval_results"

BRANCHEN = ["handwerk", "recht", "finanzen", "_generic"]


def _load_result_file(path: Path) -> dict | None:
    """Laedt eine einzelne Eval-Result-JSON-Datei. Gibt None bei Fehler zurueck."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Konnte Eval-Result nicht laden: %s — %s", path.name, exc)
        return None


def _list_result_files(limit: int = 50) -> list[Path]:
    """Gibt die neuesten Eval-Result-JSON-Dateien zurueck (absteigend nach Name/Timestamp)."""
    if not _RESULTS_DIR.exists():
        return []
    files = sorted(
        _RESULTS_DIR.glob("quality_gate_*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    return files[:limit]


@router.get("/quality-gate/history")
async def quality_gate_history(
    limit: int = Query(default=30, ge=1, le=100, description="Max. Anzahl Eval-Runs"),
    branche: Optional[str] = Query(
        default=None, description="Filter auf eine Branche (z.B. handwerk)"
    ),
):
    """Liefert die letzten N Quality-Gate Eval-Runs.

    Response-Format pro Run:
    {
      "timestamp": "2026-05-05T12:00:00Z",
      "aggregate": { weighted_f1, weighted_precision, weighted_recall, total_posts },
      "per_branche": {
        "handwerk": { f1, precision, recall, accuracy, auc, optimal_threshold, post_count },
        ...
      }
    }
    """
    result_files = _list_result_files(limit=limit)

    if not result_files:
        return {"runs": [], "latest_timestamp": None, "run_count": 0}

    runs = []
    for path in result_files:
        data = _load_result_file(path)
        if data is None:
            continue

        per_branche_summary: dict[str, dict] = {}
        for b, bdata in data.get("per_branche", {}).items():
            if branche and b != branche:
                continue
            per_branche_summary[b] = {
                "f1": bdata.get("metrics", {}).get("f1", 0.0),
                "precision": bdata.get("metrics", {}).get("precision", 0.0),
                "recall": bdata.get("metrics", {}).get("recall", 0.0),
                "accuracy": bdata.get("metrics", {}).get("accuracy", 0.0),
                "auc": bdata.get("auc", 0.0),
                "post_count": bdata.get("post_count", 0),
                "optimal_threshold": (
                    (bdata.get("optimal_threshold") or {}).get("threshold")
                ),
                "confusion_matrix": bdata.get("confusion_matrix", {}),
            }

        runs.append({
            "timestamp": data.get("timestamp"),
            "aggregate": data.get("aggregate", {}),
            "per_branche": per_branche_summary,
            "stub_warning": data.get("stub_warning"),
        })

    latest_ts = runs[0]["timestamp"] if runs else None

    return {
        "runs": runs,
        "latest_timestamp": latest_ts,
        "run_count": len(runs),
    }


@router.get("/quality-gate/latest")
async def quality_gate_latest():
    """Liefert den neuesten Eval-Run als vollstaendiges Ergebnis-Dict."""
    result_files = _list_result_files(limit=1)
    if not result_files:
        raise HTTPException(status_code=404, detail="Noch kein Eval-Run vorhanden.")
    data = _load_result_file(result_files[0])
    if data is None:
        raise HTTPException(status_code=500, detail="Eval-Result-Datei nicht lesbar.")
    return data
