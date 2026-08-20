"""Deployten Commit-Stand lesen — Grundlage fuer /api/version (SSOT AP3, 21.08.).

Die Datei VERSION liegt beim Deploy neben main.py (vom Deploy-Skript per
`git rev-parse HEAD` geschrieben, dann per COPY . . ins Image aufgenommen).
Fehlt sie, meldet read_version() das explizit statt eine falsche SHA
vorzutaeuschen — belegte Deploy-Luecke vom 20.08.: "alles deployed" war
fuenf Minuten spaeter falsch, niemand konnte es sehen, weil kein
/api/version existierte.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

_UNKNOWN_SHA = "unknown (VERSION-Datei fehlt — kein Deploy-Skript-Build)"


def read_version(backend_dir: Path) -> dict:
    """Liest commit_sha + build_time aus <backend_dir>/VERSION.

    Args:
        backend_dir: Verzeichnis, in dem main.py liegt (nicht das Repo-Root).
    """
    version_file = backend_dir / "VERSION"
    try:
        commit_sha = version_file.read_text().strip()
    except FileNotFoundError:
        return {"commit_sha": _UNKNOWN_SHA, "build_time": None}

    build_time = datetime.fromtimestamp(version_file.stat().st_mtime, tz=UTC).isoformat()
    return {"commit_sha": commit_sha, "build_time": build_time}
