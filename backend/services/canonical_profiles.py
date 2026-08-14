"""
services/canonical_profiles.py — zentrale Lese-Fassade für aktive Louis-Profile.

Ersetzt die verstreuten `SELECT payload ... WHERE is_active=true ORDER BY version
DESC LIMIT 1`-Zugriffe (P12, ideas, voice_drift, brand_voice GET) durch EINE
Stelle mit:
  - deterministischer Aktiv-Row-Auflösung (behebt den Multi-Active-Row-Bug seit
    Projekt-Rows / Migration 032: ohne project_id-Filter zog die alte Query ein
    nichtdeterministisches Profil),
  - Kanonisch-Erkennung über `_meta.prompt_version` (`^p0X-vN.N$` oder `^values-vN.N$`).

Der Resolver-Kern (is_canonical / pick_active) ist dep-frei und unit-testbar;
nur der DB-Zugriff (load_active_profiles) importiert sqlalchemy/models lazy.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Profil-Typ → DB-Tabelle
TABLE_MAP = {
    "customer_context": "tenant_customer_context",  # P01
    "voice_profile": "tenant_voice_profile",  # P03
    "audience_avatar": "tenant_audience_avatar",  # P04
    "customer_values": "tenant_customer_values",  # #43 — Werte-Entität
}

# Erweitert um 'values'-Präfix (Issue #43): values-v1.0 ist gültig,
# bestehende p0X-vN.N bleiben unverändert gültig.
_PROMPT_VERSION_RE = re.compile(r"^(p0[0-9]+|values)-v[0-9]+\.[0-9]+$")


#: Eine Schema-Lücke auf WURZEL-Ebene: ein Pflichtfeld der Nutzlast fehlt komplett.
#: Erzeugt von finalize_canonical() als "schema: (root): '<feld>' is a required property".
#: Lücken in Unterobjekten ("schema: person.rolle: …") zählen NICHT — die Row ist
#: dann inhaltlich unvollständig, aber strukturell kanonisch.
_WURZEL_PFLICHTFELD_LUECKE = re.compile(r"^schema: \(root\): .+ is a required property$")


def is_canonical(payload: dict | None) -> bool:
    """True, wenn der Payload kanonisch ist — Etikett UND Struktur.

    Zwei Bedingungen:
      1. gültige `_meta.prompt_version` (Alt-v2-Rows haben keine)
      2. kein Pflichtfeld der Wurzel fehlt (`_meta.luecken`)

    Bedingung 2 kam am 06.08.2026 dazu. Vorher genügte die prompt_version, und
    genau daran ist der Wächter vorbeigelaufen: Louis' und Erics Avatar-Rows
    trugen ein sauberes "p04-v1.0" und meldeten im selben `_meta` alle acht
    Pflichtfelder als gerissen — das LLM hatte die Prompt-Überschriften als Keys
    geliefert (`IDENTITÄT` statt `identitaet`). Geprüft wurde das Etikett, nicht
    die Ware; P12 schrieb daraufhin zwei Monate lang Posts ohne Avatar.

    Das Signal war die ganze Zeit da — finalize_canonical schreibt es bei jeder
    Erzeugung. Es wurde nur nie gelesen.

    False führt beim Konsumenten zu 'Re-Run empfohlen', nicht zum Abbruch.
    """
    if not isinstance(payload, dict):
        return False
    meta = payload.get("_meta")
    if not isinstance(meta, dict):
        return False
    pv = meta.get("prompt_version")
    if not (isinstance(pv, str) and _PROMPT_VERSION_RE.match(pv)):
        return False

    for luecke in meta.get("luecken") or []:
        if isinstance(luecke, str) and _WURZEL_PFLICHTFELD_LUECKE.match(luecke):
            return False

    return True


def pick_active(rows: list, project_id: str | None = None) -> dict | None:
    """Wählt deterministisch die aktive Row aus Kandidaten.

    rows: Liste von Dicts mit Schlüsseln 'project_id', 'version', 'payload'
          (alle bereits is_active=true für den Tenant).
    Auflösung:
      1. exakter project_id-Match (höchste version), falls project_id gesetzt
      2. globale Row (project_id IS NULL, höchste version)
      3. irgendeine aktive Row (höchste version) — Rückwärtskompatibilität
    """
    if not rows:
        return None

    def _ver(r):
        try:
            return int(r.get("version") or 0)
        except (TypeError, ValueError):
            return 0

    if project_id is not None:
        scoped = [r for r in rows if r.get("project_id") == project_id]
        if scoped:
            return max(scoped, key=_ver)

    global_rows = [r for r in rows if r.get("project_id") is None]
    if global_rows:
        return max(global_rows, key=_ver)

    return max(rows, key=_ver)


def _coerce_payload(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def load_active_profile(profile_type: str, tenant_id: str, project_id: str | None = None):
    """Lädt das aktive Profil eines Typs als (payload, is_canonical_flag).

    profile_type: 'customer_context' | 'voice_profile' | 'audience_avatar'.
    Gibt ({}, False) zurück, wenn keine aktive Row existiert.
    """
    if profile_type not in TABLE_MAP:
        raise KeyError(f"Unbekannter profile_type '{profile_type}'. Erlaubt: {sorted(TABLE_MAP)}")

    # Lazy-Import: hält den Resolver-Kern dep-frei/testbar.
    from sqlalchemy import text

    from models.base import sync_session_factory

    table = TABLE_MAP[profile_type]
    with sync_session_factory() as session:
        result = session.execute(
            text(
                f"SELECT project_id, version, payload FROM {table} "
                f"WHERE tenant_id = :t AND is_active = true"
            ),
            {"t": tenant_id},
        ).fetchall()

    rows = [
        {"project_id": r[0], "version": r[1], "payload": _coerce_payload(r[2])}
        for r in (result or [])
    ]
    chosen = pick_active(rows, project_id=project_id)
    if not chosen:
        return {}, False
    payload = chosen["payload"]
    return payload, is_canonical(payload)


def load_active_profiles(tenant_id: str, project_id: str | None = None) -> dict:
    """Lädt alle drei aktiven Profile auf einmal.

    Returns:
        {profile_type: {"payload": dict, "is_canonical": bool}} für alle drei Typen.
    """
    out = {}
    for ptype in TABLE_MAP:
        payload, canon = load_active_profile(ptype, tenant_id, project_id=project_id)
        out[ptype] = {"payload": payload, "is_canonical": canon}
    return out
