#!/usr/bin/env python
"""
normalisiere_profil_keys.py — Einmal-Reparatur bestehender Profil-Rows.

Hintergrund (Prod-Befund 06.08.2026): P01 und P04 haben für Louis (6cff9601)
und Eric (a34a02c9) die Abschnitts-Überschriften des Prompts als Top-Level-Keys
geliefert — `IDENTITÄT` statt `identitaet`, `1_PERSON` statt `person`. Der Inhalt
darunter war vollständig und kanonisch; nur die Namen stimmten nicht. P12s
`prune()` macht einen exakten Key-Match und traf 0 von 3 Avatar-Feldern, also
entstand jeder Post ohne einen einzigen Avatar-Datenpunkt.

Neue Läufe fängt `finalize_canonical()` ab (es normalisiert vor dem Validieren).
Dieses Skript holt den Bestand nach. Es benennt ausschließlich Top-Level-Keys um
und fasst Werte nicht an — verlustfrei, ohne LLM-Aufruf.

Standard ist der TROCKENLAUF. Geschrieben wird nur mit --schreiben.

    PYTHONPATH=/app python scripts/normalisiere_profil_keys.py
    PYTHONPATH=/app python scripts/normalisiere_profil_keys.py --schreiben
"""

import argparse
import json
import sys

from sqlalchemy import text

from models.base import sync_session_factory
from services.schema_transformer import entferne_geheilte_luecken, normalisiere_top_level_keys

#: Profiltabelle → Schema-Schlüssel, gegen den ihre Keys geprüft werden.
TABELLEN = {
    "tenant_customer_context": "p01",
    "tenant_voice_profile": "p03",
    "tenant_audience_avatar": "p04",
}


def _payload_als_dict(roh) -> dict:
    if isinstance(roh, dict):
        return roh
    if isinstance(roh, str):
        try:
            return json.loads(roh)
        except json.JSONDecodeError:
            return {}
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--schreiben",
        action="store_true",
        help="Änderungen wirklich speichern (ohne dieses Flag nur Trockenlauf)",
    )
    args = ap.parse_args()

    session = sync_session_factory()
    betroffen = 0
    geschrieben = 0

    for tabelle, prompt_key in TABELLEN.items():
        rows = session.execute(
            text(f"select id, tenant_id, is_active, payload from {tabelle}")
        ).fetchall()

        for row_id, tenant_id, is_active, roh in rows:
            payload = _payload_als_dict(roh)
            if not payload:
                continue

            doc, umbenennungen = normalisiere_top_level_keys(prompt_key, payload)

            # Verlustkontrolle direkt nach dem Umbenennen: gleiche Anzahl Felder,
            # und jeder umbenannte Wert ist identisch wiederzufinden.
            assert len(doc) == len(payload), f"Feldzahl weicht ab in {row_id}"
            for alt, neu in umbenennungen:
                assert doc[neu] == payload[alt], f"Wert verändert bei {alt} in {row_id}"

            # Die bei der Erzeugung protokollierten Lücken ziehen nicht von selbst
            # mit. Bleiben sie stehen, meldet is_canonical() die reparierte Row
            # weiter als kaputt — ein Wächter, der grundlos meckert, wird ignoriert.
            doc, geheilt = entferne_geheilte_luecken(prompt_key, doc)

            if not umbenennungen and not geheilt:
                continue

            betroffen += 1
            zustand = "aktiv" if is_active else "inaktiv"
            print(f"\n{tabelle} {str(row_id)[:8]} tenant={str(tenant_id)[:8]} ({zustand})")
            for alt, neu in umbenennungen:
                print(f"    {alt:>26}  ->  {neu}")
            if geheilt:
                print(f"    {len(geheilt)} veraltete Schema-Luecke(n) gestrichen")

            if args.schreiben:
                session.execute(
                    text(f"update {tabelle} set payload = :p where id = :i"),
                    {"p": json.dumps(doc, ensure_ascii=False), "i": str(row_id)},
                )
                geschrieben += 1

    if args.schreiben:
        session.commit()
        print(f"\nGESCHRIEBEN: {geschrieben} Row(s) normalisiert.")
    else:
        print(f"\nTROCKENLAUF: {betroffen} Row(s) wären zu normalisieren.")
        print("Zum Anwenden erneut mit --schreiben aufrufen.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
