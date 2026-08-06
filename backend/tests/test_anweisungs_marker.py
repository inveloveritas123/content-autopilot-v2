"""Der Anweisungs-Marker und sein Auswerter — dieselbe Wahrheit auf beiden Seiten.

Vorgeschichte: der Marker `metadata.intent = "start_instruction"` wurde am 05.08.2026
eingefuehrt, an genau einer Stelle gesetzt und von KEINER gelesen. Ein Etikett ohne
Auswerter ist folgenlos; die Anweisung floss weiter ins Voice-Profil und in den
RAG-Abruf. Diese Datei haelt beide Seiten zusammen.
"""

import json

from services.anweisungs_marker import (
    INTENT_START_INSTRUCTION,
    MARKER_PATCH_JSON,
    SQL_OHNE_ANWEISUNGEN,
)


class TestMarkerUndAuswerterPassenZusammen:
    def test_der_geschriebene_wert_ist_der_gefilterte_wert(self):
        """Zwei nebeneinander lebende Stringliterale wuerden auseinanderlaufen.

        Rot, sobald jemand den Marker aendert, ohne den Filter mitzuziehen (oder umgekehrt).
        """
        geschrieben = json.loads(MARKER_PATCH_JSON)

        assert geschrieben["intent"] == INTENT_START_INSTRUCTION
        assert f"'{INTENT_START_INSTRUCTION}'" in SQL_OHNE_ANWEISUNGEN

    def test_filter_faengt_chunks_ohne_metadata_nicht_mit_ab(self):
        """`metadata` ist nullable — ohne COALESCE ergibt der Vergleich NULL.

        Eine Zeile mit `metadata IS NULL` faellt dann stumm aus JEDEM Ergebnis, und der
        Filter wird von einem Ausschluss zu einer Loeschung. Rot, sobald COALESCE fehlt.
        """
        assert "COALESCE(" in SQL_OHNE_ANWEISUNGEN

    def test_fragment_traegt_kein_eigenes_AND(self):
        """`search_similar` fuegt Praedikate in eine Liste und joint mit ' AND '.

        Ein Fragment mit eigenem `AND` erzeugte dort `AND AND`. Rot, sobald es eins traegt.
        """
        assert not SQL_OHNE_ANWEISUNGEN.strip().upper().startswith("AND")


class TestSetzerZiehtAusDemModul:
    def test_telegram_task_benutzt_denselben_patch(self):
        """Der Setzer darf den Marker nicht ein zweites Mal buchstabieren.

        Rot, sobald `telegram_task` wieder ein eigenes Literal definiert.
        """
        from tests._telegram_task_env import tt

        assert tt._ANWEISUNGS_MARKER is MARKER_PATCH_JSON
