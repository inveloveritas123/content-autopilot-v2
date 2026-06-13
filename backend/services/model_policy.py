"""
services/model_policy.py — globale Pipeline-Modell-Policy (datei-basiert, dep-frei).

Gibt Robert die "absolute Hoheit" über die Modellwahl pro Pipeline-Phase
(SOLL-IST-2026-06-12-wiring.md §5):
  - Der OFFIZIELLE Default pro Phase bleibt im Code (MODEL_PER_PROMPT/TIER_MODELS,
    Single Source of Truth — "hardgecoded in den MD-Files/ADR-0008").
  - Ein TEST-Override pro Phase ist eine BELIEBIGE Requesty-Modell-ID
    (z.B. 'google/gemini-2.5-flash-lite-preview-06-17'), global gültig.

Speicher: eine JSON-Datei (kein DB-Schema → kein Robert-Checkpoint nötig,
hot-reload via mtime). Pfad:
  1. Env MODEL_POLICY_PATH
  2. <CONTENT_TRUTH_OVERLAY_PATH>/pipeline_model_policy.json
  3. <repo>/data/pipeline_model_policy.json (Fallback)

Dep-frei (nur json/os/pathlib) → via importlib testbar ohne services/__init__.
"""

from __future__ import annotations  # Python 3.9-Kompatibilität: str | None Syntax

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Prozess-Cache mit mtime-Invalidierung (hot-reload bei Datei-Änderung)
_CACHE: dict = {"mtime": None, "data": None, "path": None}


def _policy_path() -> Path:
    env_path = os.environ.get("MODEL_POLICY_PATH", "").strip()
    if env_path:
        return Path(env_path)
    overlay = os.environ.get("CONTENT_TRUTH_OVERLAY_PATH", "").strip()
    if overlay:
        return Path(overlay) / "pipeline_model_policy.json"
    return Path(__file__).parent.parent.parent / "data" / "pipeline_model_policy.json"


def _empty() -> dict:
    return {"overrides": {}}


def load_policy() -> dict:
    """Liest die globale Policy. Hot-reload via mtime. Wirft NIE (fail-open auf leer).

    Returns:
        {"overrides": {"P01": "<model-id>", ...}} — Phasen-Keys upper-case.
    """
    path = _policy_path()
    try:
        if not path.exists():
            return _empty()
        mtime = path.stat().st_mtime
        if _CACHE["data"] is not None and _CACHE["mtime"] == mtime and _CACHE["path"] == str(path):
            return _CACHE["data"]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = _empty()
        ov = data.get("overrides")
        data["overrides"] = (
            {str(k).upper(): v for k, v in ov.items() if v} if isinstance(ov, dict) else {}
        )
        _CACHE.update(mtime=mtime, data=data, path=str(path))
        return data
    except Exception as exc:  # pragma: no cover - defensiver Fallback
        logger.warning("model_policy.load_policy fehlgeschlagen (fail-open): %s", exc)
        return _empty()


def get_override(prompt_key: str) -> str | None:
    """Liefert die Test-Override-Modell-ID für eine Phase oder None."""
    return load_policy().get("overrides", {}).get(prompt_key.upper()) or None


def set_override(prompt_key: str, model_id: str | None) -> dict:
    """Setzt/entfernt den Test-Override für eine Phase. Atomarer Write.

    Args:
        prompt_key: Phase, z.B. 'P01'.
        model_id:   Beliebige Requesty-Modell-ID; None/'' entfernt den Override.

    Returns:
        Die neue, vollständige Policy.
    """
    path = _policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_policy()
    overrides = dict(data.get("overrides", {}))
    key = prompt_key.upper()
    if model_id:
        overrides[key] = str(model_id).strip()
    else:
        overrides.pop(key, None)
    data = {"overrides": overrides}

    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    _CACHE.update(mtime=None, data=None, path=None)  # invalidate
    logger.info("model_policy: Override %s → %s", key, model_id or "(entfernt)")
    return data
