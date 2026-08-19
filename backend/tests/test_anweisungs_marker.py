"""Der Anweisungs-Marker und sein Auswerter — dieselbe Wahrheit auf beiden Seiten.

Vorgeschichte: der Marker `metadata.intent = "start_instruction"` wurde am 05.08.2026
eingefuehrt, an genau einer Stelle gesetzt und von KEINER gelesen. Ein Etikett ohne
Auswerter ist folgenlos; die Anweisung floss weiter ins Voice-Profil und in den
RAG-Abruf. Diese Datei haelt beide Seiten zusammen.
"""

import asyncio
import json
import os
import re
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
        """Der COALESCE-Rueckfallwert muss der LEERE String sein, kein anderer.

        `metadata` ist nullable — ohne COALESCE ergibt der Vergleich NULL, und eine
        Zeile mit `metadata IS NULL` faellt stumm aus JEDEM Ergebnis (Ausschluss wird
        Loeschung). Ein bloßes „COALESCE( ist da" reicht nicht: ein Rueckfallwert
        gleich `INTENT_START_INSTRUCTION` waere fuer jede solche Zeile
        `'start_instruction' <> 'start_instruction'` → FALSE — derselbe Fehlermodus,
        nur unsichtbar hinter einem vorhandenen COALESCE. Rot, sobald der Rueckfallwert
        von `''` abweicht.
        """
        assert "COALESCE(metadata->>'intent', '')" in SQL_OHNE_ANWEISUNGEN

    def test_fragment_traegt_kein_eigenes_AND(self):
        """`search_similar` fuegt Praedikate in eine Liste und joint mit ' AND '.

        Ein Fragment mit eigenem `AND` erzeugte dort `AND AND`. Rot, sobald es eins traegt.
        """
        assert not SQL_OHNE_ANWEISUNGEN.strip().upper().startswith("AND")

    def test_marker_wert_ist_sql_sicher(self):
        """`INTENT_START_INSTRUCTION` landet an drei Stellen als SQL-LITERAL, nicht als
        gebundener Parameter — ueberall dort, wo `SQL_OHNE_ANWEISUNGEN` (das den Wert
        per f-String traegt) selbst wieder per f-String/Interpolation in `text()`
        eingebettet wird: `services/embedding_service.py::search_similar`,
        `tasks/p06_profile_extractor_task.py::run_for_tenant` und
        `api/memory.py::memory_picker`. Der SETZER (`_markiere_chunk_als_anweisung` in
        `tasks/telegram_task.py`) ist davon NICHT betroffen — er bindet den Wert als
        `:patch`-Parameter, kein Literal. Heute ist der Wert `"start_instruction"` —
        harmlos. Ein kuenftiger Wert mit `'` braeche das SQL-Literal an den drei
        Lesestellen, einer mit `:` den Bindparam-Parser von SQLAlchemys `text()`.
        Billige Versicherung: der Wert bleibt alphanumerisch plus Unterstrich. Rot,
        sobald jemand `'`, `:` oder ein
        anderes SQL-Sonderzeichen in den Marker schmuggelt.
        """
        assert re.fullmatch(r"[A-Za-z0-9_]+", INTENT_START_INSTRUCTION)


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

        # RLS-Kontext (services/rls.py) fuegt vor der Fach-Query ein
        # `SELECT set_config(...)` ein — die Fach-Query steht daher nicht mehr
        # zwingend an Index 0. Struktur pruefen (kommt sie vor?), nicht die Marke.
        alle_sql = [str(c.args[0]) for c in ctx.execute.call_args_list]
        assert any(SQL_OHNE_ANWEISUNGEN in sql for sql in alle_sql), (
            f"Praedikat in keiner der ausgefuehrten Queries: {alle_sql}"
        )


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


def _load_real_api_telegram():
    """Laedt `api/telegram.py` unter einem privaten Modulnamen via Datei-Pfad.

    `sys.modules["api.telegram"]` kann je nach Sammelreihenfolge der Testsuite
    bereits ein Stub sein (siehe `tests/_telegram_task_env.py`), der
    `_memory_search_sync` gar nicht kennt. Ein normaler `import api.telegram`
    waere davon abhaengig, welche Testdatei zuerst lief. Der direkte Datei-Load
    umgeht das und liefert immer das echte Modul, unabhaengig von sonstigem
    sys.modules-Zustand — dasselbe Muster wie in
    `tests/test_telegram_outbound_pertenant.py` und `tests/test_p09_chat_ideas.py`.
    """
    import importlib.util as _ilu

    backend_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    spec = _ilu.spec_from_file_location(
        "test_anweisungs_marker_api_telegram_real",
        os.path.join(backend_dir, "api", "telegram.py"),
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTelegramSucheBleibtUngefiltert:
    """FR-1: `_memory_search_sync` ist eine ANSICHT, kein RAG-Erzeuger.

    Ihr einziger Aufrufer ist der `/such` `/suche` `/erinner`-Zweig in
    `_try_memory_command` — das Ergebnis geht direkt als Telegram-Nachricht an
    den Nutzer. Sie ist das Telegram-Gegenstueck zu `/memory/search` und muss
    wie dieses `include_instructions=True` setzen, sonst waere Markiertes in
    keinem Kanal mehr sichtbar, den Louis taeglich benutzt.
    """

    def test_memory_search_sync_fordert_den_rohbestand_an(self):
        """Rot, sobald `include_instructions=True` aus dem Aufruf entfernt wird.

        `_memory_search_sync` baut vor dem Aufruf eine echte Async-Engine
        (`create_async_engine(_s.database_url)`). Ohne DB-Verbindung ist das
        unschaedlich — SQLAlchemy verbindet lazy erst beim ersten Checkout, und
        `search_similar` ist unten vollstaendig gemockt, macht also nie einen
        echten Checkout. Die einzige Bedingung ist eine PARSEBARE URL in
        `config.settings.database_url`; das wird hier isoliert erzwungen, weil
        andere Testdateien in derselben Suite `config.settings` global und ohne
        Teardown durch ein MagicMock ersetzen (z. B. `test_telegram_webhook.py`),
        was `create_async_engine` sonst mit einer MagicMock-URL zum Scheitern
        braechte — unabhaengig von diesem Fix.
        """
        telegram_mod = _load_real_api_telegram()

        aufrufe = {}

        async def _fake_search_similar(db, **kwargs):
            aufrufe.update(kwargs)
            return []

        with (
            patch(
                "config.settings.database_url",
                "postgresql+asyncpg://autopilot:changeme@localhost:5432/content_autopilot",
            ),
            patch("services.embedding_service.search_similar", _fake_search_similar),
        ):
            telegram_mod._memory_search_sync("t1", "irgendwas")

        assert aufrufe["include_instructions"] is True
