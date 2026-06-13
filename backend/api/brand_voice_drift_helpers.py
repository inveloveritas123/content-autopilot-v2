"""
brand_voice_drift_helpers.py — Dep-freie Hilfslogik für den Drift-Decide-Pfad (Issue #43 Schritt 4).

Extrahiert aus brand_voice.py damit die Kernlogik lokal dep-frei testbar ist
(Py 3.9 venv ohne sqlalchemy/fastapi).

Exports:
    _ENTITY_TABLE     — Whitelist: entity_type → Tabellenname (SQL-sicher, keine User-Inputs)
    get_entity_table  — entity_type → Tabellenname, ValueError für Unbekannte
    apply_drift_changes — Walker: wendet akzeptierte Änderungen auf einen Payload an;
                          unterstützt op:"set" (default) + op:"append"

RÜCKWÄRTSKOMPATIBILITÄT:
    entity_type='voice' (oder kein Argument) → 'tenant_voice_profile'
    = exakt das Literal, das vorher hardkodiert war (brand_voice.py:811/856/870).
    Keine Verhaltensänderung für den voice-Pfad.

SICHERHEIT:
    Tabellennamen fließen AUSSCHLIESSLICH aus _ENTITY_TABLE — nie aus User-Input.
    get_entity_table() wirft ValueError auf alle unbekannten Werte (SQL-Injection-Schutz).
"""

import copy
from typing import Any

# ---------------------------------------------------------------------------
# Whitelist: entity_type → Tabellenname
# Analog zu _PROFILE_TABLE in brand_voice.py (brand_voice.py:88-92).
# Schlüssel-Mapping: 'voice' → 'tenant_voice_profile' (Rückwärtskompatibilität).
# ---------------------------------------------------------------------------

_ENTITY_TABLE: dict[str, str] = {
    "voice": "tenant_voice_profile",
    "values": "tenant_customer_values",
    "avatar": "tenant_audience_avatar",
    "context": "tenant_customer_context",
}


def get_entity_table(entity_type: str | None = "voice") -> str:
    """Gibt den Tabellennamen für einen entity_type zurück.

    Args:
        entity_type: Einer der Schlüssel aus _ENTITY_TABLE.
                     Default 'voice' → Rückwärtskompatibilität mit dem früheren
                     hartkodieren Literal 'tenant_voice_profile'.

    Returns:
        Tabellenname aus _ENTITY_TABLE (SQL-sicher, nur Whitelist-Werte).

    Raises:
        ValueError: Wenn entity_type nicht in _ENTITY_TABLE steht.
                    Caller kann das auf HTTP 422 mappen.
    """
    if entity_type not in _ENTITY_TABLE:
        raise ValueError(
            f"Unbekannter entity_type: {entity_type!r}. " f"Erlaubt: {sorted(_ENTITY_TABLE)}"
        )
    return _ENTITY_TABLE[entity_type]


# ---------------------------------------------------------------------------
# Walker: Drift-Änderungen auf Payload anwenden
# ---------------------------------------------------------------------------


def apply_drift_changes(
    payload: dict,
    changes: list[dict],
    suggested_lookup: dict,
) -> dict:
    """Wendet akzeptierte Drift-Änderungen auf einen Payload an.

    Args:
        payload: Das aktive Profil-Payload (wird NICHT mutiert — Deep-Copy intern).
        changes: Liste von Änderungs-Dicts mit den Schlüsseln:
            - field_path (str): Dot-separierter Pfad, z. B. "tonalitaet.grundton"
                               oder "werte" (für op:"append").
            - op (str, optional): "set" (default) oder "append".
            - new_value (Any): Neuer Wert; None → Fallback auf suggested_lookup.
        suggested_lookup: Dict field_path → Vorgeschlagener Wert (Fallback wenn
                          new_value is None).

    Returns:
        Neues Payload-Dict mit angewendeten Änderungen.

    Raises:
        ValueError: Wenn op:"append" auf ein Nicht-Listen-Feld angewendet wird
                    (Caller mappt auf HTTP 422).

    Notes:
        - op:"set": Setzt den Wert an der Stelle im Dict (Dict-only-Walker,
          keine Array-Indizes). Ungültige Pfade werden still geskippt.
        - op:"append": Hängt new_value an ein Listen-Feld an. Pfad muss direkt
          auf ein list-Feld zeigen. Ungültiger Pfad (Feld nicht vorhanden) →
          silent skip. Feld vorhanden aber kein list-Typ → ValueError.
    """
    new_payload = copy.deepcopy(payload)

    for change in changes:
        field_path: str = change["field_path"]
        op: str = change.get("op") or "set"
        new_value: Any = change.get("new_value")

        # Fallback auf suggested_lookup wenn new_value is None
        if new_value is None:
            new_value = suggested_lookup.get(field_path)

        if op == "set":
            _apply_set(new_payload, field_path, new_value)
        elif op == "append":
            _apply_append(new_payload, field_path, new_value)
        # Unbekannte ops → silent skip (Forward-Kompatibilität)

    return new_payload


def _apply_set(payload: dict, field_path: str, value: Any) -> None:
    """Setzt einen Wert im Payload (Dict-only-Walker, in-place).

    Entspricht der bisherigen Logik in brand_voice.py:833-849.
    Ungültige Pfade werden still geskippt.
    """
    parts = field_path.split(".")
    cursor: Any = payload
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return  # Pfad ungültig → skip
        cursor = cursor[part]
    if not isinstance(cursor, dict) or parts[-1] not in cursor:
        return  # Letztes Segment nicht im Dict → skip
    cursor[parts[-1]] = value


def _apply_append(payload: dict, field_path: str, value: Any) -> None:
    """Hängt einen Wert an ein Listen-Feld an (in-place).

    Navigiert zu field_path (Dict-only). Wenn das Feld nicht existiert → skip.
    Wenn es existiert aber kein list ist → ValueError (Caller mappt auf HTTP 422).
    """
    parts = field_path.split(".")
    cursor: Any = payload
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return  # Pfad ungültig → skip
        cursor = cursor[part]
    if not isinstance(cursor, dict) or parts[-1] not in cursor:
        return  # Feld existiert nicht → skip
    target = cursor[parts[-1]]
    if not isinstance(target, list):
        raise ValueError(
            f"op:append auf '{field_path}' nicht möglich — Feld ist keine Liste "
            f"(Typ: {type(target).__name__})"
        )
    target.append(value)
