"""Der Anweisungs-Marker und sein Auswerter — dieselbe Wahrheit auf beiden Seiten.

Vorgeschichte: der Marker `metadata.intent = "start_instruction"` wurde am 05.08.2026
eingefuehrt, an genau einer Stelle gesetzt und von KEINER gelesen. Ein Etikett ohne
Auswerter ist folgenlos; die Anweisung floss weiter ins Voice-Profil und in den
RAG-Abruf. Diese Datei haelt beide Seiten zusammen.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

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


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def all(self):
        return self._rows


class _FakeDb:
    """Faengt das erzeugte SQL ab, statt es auszufuehren.

    Die Zusicherung dieses Plans lautet „der Leser stellt das Praedikat in seine Abfrage".
    Genau das — und nur das — misst dieser Doppelgaenger. Eine echte DB haette hier keinen
    zusaetzlichen Beweiswert: dass Postgres ein `<>` korrekt auswertet, steht nicht in Frage.
    """

    def __init__(self, rows=None):
        self.sql = None
        self.params = None
        self._rows = rows or []

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params
        return _FakeResult(self._rows)


async def _fake_embed(_text):
    return [0.1] * 1536


class TestSearchSimilarFiltertPerDefault:
    def test_ohne_angabe_werden_anweisungen_ausgeschlossen(self):
        """Wer `search_similar` benutzt und nichts angibt, bekommt die gefilterte Sicht.

        Der Default zeigt bewusst in die sichere Richtung: Vergessen fuehrt zu zu WENIG
        Kontext, nicht zu einer stillen Wiederholung des Fehlers.

        Rot, sobald der Default kippt oder das Praedikat fehlt.
        """
        from services.embedding_service import search_similar

        db = _FakeDb()
        with patch("services.embedding_service.embed_text", _fake_embed):
            asyncio.run(search_similar(db, tenant_id="t1", query_text="irgendwas"))

        assert SQL_OHNE_ANWEISUNGEN in db.sql

    def test_ansicht_kann_den_rohbestand_ausdruecklich_anfordern(self):
        """`/memory/search` soll zeigen, was wirklich da liegt — auch das Markierte.

        Rot, sobald `include_instructions=True` den Filter nicht mehr abschaltet.
        """
        from services.embedding_service import search_similar

        db = _FakeDb()
        with patch("services.embedding_service.embed_text", _fake_embed):
            asyncio.run(
                search_similar(
                    db, tenant_id="t1", query_text="irgendwas", include_instructions=True
                )
            )

        assert SQL_OHNE_ANWEISUNGEN not in db.sql

    def test_memory_search_endpunkt_fordert_den_rohbestand_an(self):
        """Die Ansicht muss aktiv opt-outen — sonst erbt sie stumm den Filter.

        Rot, sobald `/memory/search` den Parameter nicht mehr uebergibt.
        """
        from api.memory import memory_search

        aufrufe = {}

        async def _fake_search(db, **kwargs):
            aufrufe.update(kwargs)
            return []

        tenant = SimpleNamespace(id="t1")
        with patch("api.memory.search_similar", _fake_search):
            asyncio.run(
                memory_search(
                    q="irgendwas",
                    limit=10,
                    classification=None,
                    source_types=None,
                    min_similarity=0.0,
                    tenant=tenant,
                    db=_FakeDb(),
                )
            )

        assert aufrufe["include_instructions"] is True
