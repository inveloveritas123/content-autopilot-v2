# AUDITED-2026-08-19 (louis-telegram-zwei-fehler): neu angelegt, vollstaendig geprueft.
"""Regressionstests fuer die Sackgasse nach einer gescheiterten Post-Generierung.

Der Dialog vom 18.08.2026, 09:03 Uhr (Screenshot des Kunden):

    Bot:    „Beim Schreiben ist etwas schiefgegangen — ich hab den Post nicht
             fertig bekommen. Magst du es gleich nochmal versuchen?"
    Nutzer: „Ja"
    Bot:    „💬 Zu kurz fuers Gedaechtnis. Schreib einfach einen ganzen Satz!"

Zwei getrennte Defekte in EINEM Ablauf:

**Fehler 2 — die Bestaetigung wird als neuer Inhalt missverstanden.**
Der Bot stellt eine Ja/Nein-Frage und haelt danach keinen Zustand, der das
festhaelt. Die Session ist zu diesem Zeitpunkt schon `closed` (p08_service
schliesst sie beim „ja" auf das Abschluss-Angebot), also findet
`_load_active_session` — Filter `status = 'active'` — nichts, und das „Ja"
faellt in die Laengenpruefung (`MIN_TEXT_LEN = 10`). Der Nutzer wird belehrt,
obwohl er exakt das getan hat, wonach der Bot gefragt hatte.

**Die Sackgasse.** Selbst mit durchgelassenem „Ja" gab es keinen Weg zurueck in
die Generierung: `was_already_closed` verhindert einen zweiten Enqueue. Der
angebotene Retry existierte im Text, aber nicht im Code.

Dazu die ursachengerechten Texte: `paused_for_cost`, `tenant_disabled` und
`no_answers` koennen durch Wiederholen nicht besser werden — sie bekamen
trotzdem „Magst du es gleich nochmal versuchen?" und schickten den Nutzer in
eine Schleife, die er nicht gewinnen kann.
"""

from __future__ import annotations

import ast
import importlib.util as _ilu
import os
import sys
from unittest.mock import MagicMock, patch

# Geteilte Stub-Umgebung ZUERST (richtet sqlalchemy/models.base/celery/... ein)
from tests import _telegram_task_env as _env  # noqa: F401
from tests._telegram_task_env import tt

_BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# session_post_task: das ECHTE Modul laden. `_telegram_task_env` registriert
# unter diesem Namen einen MagicMock-Stub (fuer den Trigger-Lazy-Import in
# telegram_task). Erkennbar am fehlenden realen Symbol `_rueckfall_text`.
# Gleiches Vorgehen wie in test_session_post_task.py.
_existing = sys.modules.get("tasks.session_post_task")
if _existing is None or not hasattr(_existing, "_rueckfall_text"):
    _spec = _ilu.spec_from_file_location(
        "tasks.session_post_task",
        os.path.join(_BACKEND_DIR, "tasks", "session_post_task.py"),
    )
    _spt_mod = _ilu.module_from_spec(_spec)
    sys.modules["tasks.session_post_task"] = _spt_mod
    _spec.loader.exec_module(_spt_mod)
    sys.modules["tasks"].session_post_task = _spt_mod

spt = sys.modules["tasks.session_post_task"]


def _echte_klassifikation_an_den_stub_haengen() -> None:
    """Haengt das ECHTE `_classify_confirmation` an den p08-Stub.

    Warum nicht der Stub-Weg: die Ja/Nein-Erkennung ist genau das, was hier
    geprueft wird — ein MagicMock wuerde den Test wertlos machen (er wuerde
    bestehen, egal wie kaputt die Erkennung ist).

    Warum nicht das echte Modul importieren: `services/p08_service.py` zieht
    `pipeline_llm`, `models.base` und `rls` mit; die geteilte Stub-Umgebung
    ersetzt es deshalb bewusst. `_classify_confirmation` ist aber eine REINE
    Funktion (nur `re` + zwei Frozensets). Wir schneiden sie samt ihrer
    Konstanten per AST aus der Datei und fuehren nur diesen Teil aus.
    """
    stub = sys.modules["services.p08_service"]
    if hasattr(stub, "_classify_confirmation"):
        return

    with open(os.path.join(_BACKEND_DIR, "services", "p08_service.py"), encoding="utf-8") as _f:
        quelle = _f.read()
    baum = ast.parse(quelle)
    gebraucht = {
        "_ZUSTIMMUNG",
        "_ABLEHNUNG",
        "_ZUSTIMMUNG_EMOJI",
        "_NUR_BUCHSTABEN",
        "_classify_confirmation",
    }
    knoten = []
    for k in baum.body:
        if isinstance(k, ast.FunctionDef) and k.name in gebraucht:
            knoten.append(k)
        elif isinstance(k, ast.Assign):
            ziele = {t.id for t in k.targets if isinstance(t, ast.Name)}
            if ziele & gebraucht:
                knoten.append(k)

    # EIN gemeinsamer Namensraum fuer globals UND locals: bei getrennten Dicts
    # landen die Konstanten in `locals`, die Funktion sucht sie aber in ihren
    # `globals` — und stirbt beim Aufruf mit NameError.
    raum: dict = {"re": __import__("re")}
    exec(compile(ast.Module(body=knoten, type_ignores=[]), "<p08_ausschnitt>", "exec"), raum)
    assert "_classify_confirmation" in raum, "Ausschnitt hat die Funktion nicht getroffen"
    stub._classify_confirmation = raum["_classify_confirmation"]


_echte_klassifikation_an_den_stub_haengen()


def _ctx(fetchone_val=None, rowcount=1):
    """DB-Kontextmanager-Mock mit steuerbarem fetchone/rowcount."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    res = MagicMock()
    res.fetchone.return_value = fetchone_val
    res.rowcount = rowcount
    ctx.execute.return_value = res
    return ctx


# ---------------------------------------------------------------------------
# Der Marker-Schluessel muss auf beiden Seiten derselbe sein
# ---------------------------------------------------------------------------


def test_marker_schluessel_stimmen_ueberein():
    """session_post_task schreibt ihn, telegram_task liest ihn.

    Bewusst als Test statt als Import: `session_post_task` importiert
    `api.telegram` lazy, ein Modul-Import in telegram_task zoege im Worker
    einen Zyklus. Der Gleichlauf wird deshalb hier festgenagelt — laeuft eine
    der beiden Konstanten weg, ist der Retry stumm und niemand merkt es.
    """
    assert spt.RETRY_MARKER == tt._RETRY_MARKER


# ---------------------------------------------------------------------------
# Ursachengerechte Texte statt eines Allzweck-Satzes
# ---------------------------------------------------------------------------


class TestRueckfallText:
    def test_fertiger_post_verweist_aufs_dashboard_ohne_retry(self):
        """status ok = der Post existiert. Ein Retry wuerde ihn doppelt erzeugen."""
        text, retry = spt._rueckfall_text({"status": "ok", "reason": "send_failed"})
        assert text == spt._FALLBACK_ENTWURF_LIEGT_BEREIT
        assert retry is False

    def test_budget_erschoepft_bietet_keinen_retry_an(self):
        """DER Kern der Sackgasse: bei 412/Budget hilft Wiederholen nie."""
        text, retry = spt._rueckfall_text({"status": "error", "reason": "paused_for_cost"})
        assert text == spt._FALLBACK_BUDGET_ERSCHOEPFT
        assert retry is False
        # Der Nutzer muss erfahren, was zu tun ist — nicht nur, dass es klemmt.
        assert "Robert" in text
        assert "nochmal versuchen" not in text

    def test_kill_switch_bietet_keinen_retry_an(self):
        text, retry = spt._rueckfall_text({"status": "error", "reason": "tenant_disabled"})
        assert text == spt._FALLBACK_ABGESCHALTET
        assert retry is False

    def test_kein_material_erklaert_was_fehlt(self):
        text, retry = spt._rueckfall_text({"status": "skipped", "reason": "no_answers"})
        assert text == spt._FALLBACK_KEIN_MATERIAL
        assert retry is False

    def test_echter_fehler_bietet_den_retry_an(self):
        """Pipeline-Exception (u. a. der TypeError-Bug) — hier hilft ein zweiter Lauf."""
        text, retry = spt._rueckfall_text(
            {"status": "error", "reason": "pipeline_exception", "exception": "TypeError"}
        )
        assert text == spt._FALLBACK_KEIN_POST
        assert retry is True

    def test_leerer_post_bietet_den_retry_an(self):
        _text, retry = spt._rueckfall_text({"status": "error", "reason": "empty_post"})
        assert retry is True

    def test_unbekannter_grund_bietet_den_retry_an(self):
        """Im Zweifel anbieten — lieber ein Versuch zu viel als eine tote Konversation."""
        _text, retry = spt._rueckfall_text({"status": "error", "reason": "voellig_neu"})
        assert retry is True


# ---------------------------------------------------------------------------
# Der Marker wird nur gesetzt, wenn die Frage auch angekommen ist
# ---------------------------------------------------------------------------


class TestMarkerSetzen:
    def _notify(self, result, sent=True, marker_rowcount=1):
        merk = MagicMock(return_value=True)
        with (
            patch.object(spt, "_resolve_chat_id", MagicMock(return_value=4711)),
            patch("api.telegram._send_telegram_message", MagicMock(return_value=sent), create=True),
            patch.object(spt, "_merke_offenes_retry_angebot", merk),
        ):
            out = spt._ensure_user_notified("sess-1", "tenant-1", dict(result))
        return out, merk

    def test_retry_angebot_setzt_den_marker(self):
        out, merk = self._notify({"status": "error", "reason": "pipeline_exception"})
        assert out["user_notified"] is True
        assert out["retry_angeboten"] is True
        merk.assert_called_once_with("sess-1", "tenant-1")

    def test_ohne_retry_angebot_kein_marker(self):
        """Bei Budget/Kill-Switch waere ein Wartezustand eine Luege."""
        out, merk = self._notify({"status": "error", "reason": "paused_for_cost"})
        assert out["retry_angeboten"] is False
        merk.assert_not_called()

    def test_nicht_zugestellte_frage_setzt_keinen_marker(self):
        """Eine Frage, die nie ankam, darf keinen Wartezustand hinterlassen.

        Sonst verschluckt der Bot die naechste echte Nachricht als vermeintliche
        Antwort auf etwas, das der Nutzer nie gelesen hat.
        """
        out, merk = self._notify({"status": "error", "reason": "pipeline_exception"}, sent=False)
        assert out["user_notified"] is False
        merk.assert_not_called()

    def test_gelieferter_post_setzt_keinen_marker(self):
        out, merk = self._notify({"status": "ok", "sent": True})
        assert out["user_notified"] is True
        merk.assert_not_called()


# ---------------------------------------------------------------------------
# Fehler 2: das „Ja" muss ankommen — und etwas ausloesen
# ---------------------------------------------------------------------------


class TestVersuchePostRetry:
    def _run(self, text_content, session_id="sess-1", enqueue=None):
        enqueue_mock = enqueue or MagicMock()
        task_mod = MagicMock()
        task_mod.generate_post_from_session.apply_async = enqueue_mock
        antwort_mock = MagicMock()
        with (
            patch.object(tt, "_lade_offenes_retry_angebot", MagicMock(return_value=session_id)),
            patch.object(tt, "_loesche_retry_angebot", MagicMock()) as loesch,
            patch.object(tt, "_antworte", antwort_mock),
            patch.dict(sys.modules, {"tasks.session_post_task": task_mod}),
        ):
            out = tt.versuche_post_retry("tenant-1", text_content)
        return out, enqueue_mock, loesch, antwort_mock

    def test_ja_startet_den_retry(self):
        """DER Fehler vom 18.08.: „Ja" ist 2 Zeichen und war vorher weg."""
        out, enqueue, loesch, antwort = self._run("Ja")
        assert out is not None
        assert out["reason"] == "post_retry_gestartet"
        enqueue.assert_called_once_with(args=["sess-1", "tenant-1"])
        # Die Frage ist beantwortet — der Wartezustand muss weg.
        loesch.assert_called_once_with("tenant-1", "sess-1")
        # Der Nutzer erfaehrt, dass etwas passiert.
        assert antwort.call_count == 1

    def test_ja_ist_kuerzer_als_die_laengenpruefung(self):
        """Belegt, warum die Weiche VOR dem Kurztext-Gate liegen muss."""
        assert len("Ja") < tt.MIN_TEXT_LEN

    def test_varianten_der_zustimmung(self):
        """Die Formen, die ein Nutzer real tippt — alle EINWORTIG.

        ⛔ Bewusst ohne Mehrwort-Phrasen: `_classify_confirmation` vergleicht
        nur einzelne Tokens (`all(t in _ZUSTIMMUNG for t in tokens)`). Die
        Mehrwort-Eintraege im Set — gemessen „mach das", „leg los",
        „schreib ihn" — greifen deshalb NIE. Nachgemessen am echten Code:
            _classify_confirmation("mach")     -> "zustimmung"
            _classify_confirmation("mach das") -> "weiterer_inhalt"
        Das ist ein Vorbefund im Bestand (an den Hub gemeldet 19.08.2026), NICHT
        Gegenstand dieser Welle. Dieser Test bildet das IST ab, damit er ehrlich
        bleibt; wird der Vorbefund gefixt, gehoeren die Phrasen hier ergaenzt.
        """
        for wort in ("ja", "JA", "klar", "gerne", "ok", "mach", "👍"):
            out, enqueue, _l, _a = self._run(wort)
            assert out is not None, f"{wort!r} nicht als Zustimmung erkannt"
            assert out["reason"] == "post_retry_gestartet", wort
            enqueue.assert_called_once()

    def test_mehrwort_zustimmung_greift_heute_nicht(self):
        """Friert den gemeldeten Vorbefund als bekanntes IST ein.

        Kein Wunschverhalten — eine Messung. Faellt dieser Test eines Tages,
        wurde `_classify_confirmation` repariert; dann gehoert er umgedreht.
        """
        out, enqueue, _l, _a = self._run("mach das")
        assert out is None, "Vorbefund behoben? Dann diesen Test umdrehen."
        enqueue.assert_not_called()

    def test_nein_startet_nichts_und_antwortet_freundlich(self):
        out, enqueue, loesch, antwort = self._run("nein")
        assert out["reason"] == "post_retry_abgelehnt"
        enqueue.assert_not_called()
        # Auch die Ablehnung beendet den Wartezustand.
        loesch.assert_called_once_with("tenant-1", "sess-1")
        assert antwort.call_count == 1

    def test_inhaltliche_antwort_laeuft_normal_weiter(self):
        """Der Nutzer redet weiter statt zu bestaetigen — das ist echter Inhalt.

        None = kein Sonderpfad. Die Nachricht darf hier NICHT verschwinden.
        """
        out, enqueue, loesch, _a = self._run(
            "Nein danke, lass uns lieber ueber das Referenzprojekt in Aachen sprechen."
        )
        assert out is None
        enqueue.assert_not_called()
        # Das Angebot ist trotzdem hinfaellig.
        loesch.assert_called_once_with("tenant-1", "sess-1")

    def test_ohne_offenes_angebot_passiert_nichts(self):
        """Kein Marker → None, damit der normale Pfad unveraendert laeuft."""
        out, enqueue, _l, _a = self._run("Ja", session_id=None)
        assert out is None
        enqueue.assert_not_called()

    def test_enqueue_fehler_laesst_den_nutzer_nicht_im_dunkeln(self):
        """Auch der Fehlerfall des Fehlerfalls sagt etwas — keine stille Sackgasse."""
        out, _e, _l, antwort = self._run(
            "Ja", enqueue=MagicMock(side_effect=RuntimeError("broker"))
        )
        assert out["reason"] == "post_retry_enqueue_failed"
        assert antwort.call_count == 1


# ---------------------------------------------------------------------------
# Das Kurztext-Gate darf die Antwort nicht mehr abfangen
# ---------------------------------------------------------------------------


class TestKurztextGateLaesstDurch:
    def test_process_text_fragt_zuerst_nach_dem_retry(self):
        """Die Weiche liegt VOR der Laengenpruefung — sonst ist „Ja" wieder weg."""
        retry_mock = MagicMock(return_value={"status": "ok", "reason": "post_retry_gestartet"})
        kurz_gate = MagicMock(return_value=False)
        with (
            patch.object(tt, "versuche_post_retry", retry_mock),
            patch.object(tt, "hat_aktives_gespraech", kurz_gate),
        ):
            out = tt._process_text("log-1", "tenant-1", {"text": "Ja"})
        assert out["reason"] == "post_retry_gestartet"
        retry_mock.assert_called_once_with("tenant-1", "Ja")
        # Das Kurztext-Gate darf gar nicht erst befragt worden sein.
        kurz_gate.assert_not_called()

    def test_ohne_offenes_angebot_greift_das_gate_wie_bisher(self):
        """Kein Verhaltensbruch fuer alle anderen kurzen Nachrichten."""
        with (
            patch.object(tt, "versuche_post_retry", MagicMock(return_value=None)),
            patch.object(tt, "hat_aktives_gespraech", MagicMock(return_value=False)),
        ):
            out = tt._process_text("log-1", "tenant-1", {"text": "Ja"})
        assert out["reason"] == "too_short"
