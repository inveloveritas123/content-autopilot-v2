"""Der Anweisungs-Marker und sein Auswerter — dieselbe Wahrheit auf beiden Seiten.

Vorgeschichte: der Marker `metadata.intent = "start_instruction"` wurde am 05.08.2026
eingefuehrt, an genau einer Stelle gesetzt und von KEINER gelesen. Ein Etikett ohne
Auswerter ist folgenlos; die Anweisung floss weiter ins Voice-Profil und in den
RAG-Abruf. Diese Datei haelt beide Seiten zusammen.
"""

import asyncio
import json
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.anweisungs_marker import (
    INTENT_START_INSTRUCTION,
    MARKER_PATCH_JSON,
    SQL_OHNE_ANWEISUNGEN,
)

# `tests._telegram_task_env` (siehe TestSetzerZiehtAusDemModul unten) legt
# `sys.modules["tasks"]` als pfadloses `types.ModuleType` an, FALLS "tasks" noch nicht
# registriert ist — der `_stub()`-Guard dort ersetzt einen bereits vorhandenen Eintrag
# nicht. Ohne Gegenmassnahme haengt der spaetere `from tasks.p06_profile_extractor_task
# import run_for_tenant` (unten) an der Sammelreihenfolge: laeuft irgendeine Datei mit
# demselben Muster vor dieser hier, bricht der Import mit `ModuleNotFoundError: 'tasks'
# is not a package` (Task-3-Review, 2026-08-07).
#
# Ein Vorwaerm-Import in conftest.py (immer zuerst geladen) wurde geprueft und
# verworfen: er zieht transitiv das ECHTE `config`-Modul (ueber
# tasks.celery_app -> config, models.base -> config) und unterlaeuft damit
# test_admin_auth.py:102 (`if "config" not in sys.modules: ...`) VOR dessen eigenem
# Stub — NameError: `_FakeSettings` in der gesamten Suite. Ein Hand-Loader per
# `importlib.util.spec_from_file_location` muesste denselben Import-Graphen
# (tasks.celery_app, models.base, config, services.*) von Hand nachbauen und bei jeder
# kuenftigen Import-Aenderung in p06 mitgepflegt werden.
#
# Stattdessen: `sys.modules["tasks"]` bekommt ein echtes `__path__`, falls es fehlt —
# genau das Muster, das `_telegram_task_env.py` bereits fuer `models` verwendet
# (Zeile 114-117 dort). Damit loest der normale Python-Importmechanismus
# `tasks.p06_profile_extractor_task` (und dessen eigene Importe) selbst auf, ganz
# gleich ob "tasks" hier zuerst als echtes Paket oder als fremder Stub auftaucht —
# und ganz gleich, was p06 kuenftig zusaetzlich importiert.
if "tasks" not in sys.modules:
    sys.modules["tasks"] = types.ModuleType("tasks")
if not hasattr(sys.modules["tasks"], "__path__"):
    sys.modules["tasks"].__path__ = [
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tasks"))
    ]


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


class TestVoiceProfilScanUeberspringtAnweisungen:
    @patch("tasks.p06_profile_extractor_task.sync_session_factory")
    def test_p06_stellt_das_praedikat_in_seine_abfrage(self, mock_factory):
        """Ohne Filter lernt das Voice-Profil den Klang von Steueranweisungen.

        „Ich will einen neuen LinkedIn-Post machen" ist kein Sprachbeispiel des Nutzers,
        sondern ein Knopfdruck in Worten. Rot, sobald das Praedikat aus dem SELECT faellt.
        """
        from tasks.p06_profile_extractor_task import run_for_tenant

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        # Leeres Ergebnis => run_for_tenant kehrt direkt nach dem ersten SELECT zurueck.
        ctx.execute.return_value.fetchall.return_value = []
        mock_factory.return_value = ctx

        with patch("services.llm.set_llm_tenant"):
            run_for_tenant("tenant-1")

        erstes_sql = str(ctx.execute.call_args_list[0].args[0])
        assert SQL_OHNE_ANWEISUNGEN in erstes_sql


class TestPickerSchlaegtKeineAnweisungenVor:
    def test_picker_stellt_das_praedikat_in_seine_abfrage(self):
        """Der Picker spielt alte Chunks aktiv als „vergessene Erinnerung" zurueck.

        Er laeuft an `search_similar` vorbei und hat eigenes SQL — der Default aus Task 2
        schuetzt ihn also nicht. Ohne Filter bekaeme der Nutzer eine alte Absichts-
        erklaerung als Post-Vorschlag angeboten. Rot, sobald das Praedikat fehlt.
        """
        from api.memory import memory_picker

        db = _FakeDb(rows=[])
        tenant = SimpleNamespace(id="t1")
        asyncio.run(memory_picker(days_min=7, days_max=60, limit=5, tenant=tenant, db=db))

        assert SQL_OHNE_ANWEISUNGEN in db.sql
