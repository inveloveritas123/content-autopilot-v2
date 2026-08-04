"""Wächter gegen Bot-Tokens im Klartext-Log (Befund 04.08.2026, S1).

Belegt: 2486 Zeilen in EINER Stunde celery-worker-Log, INFO-Level, bei jeder
Sprachnachricht:

    HTTP Request: GET https://api.telegram.org/file/bot<ID>:<TOKEN>/voice/… "HTTP/1.1 200 OK"

Zwei unabhängige Ursachen — jede allein hätte gereicht:

1. `setup_logging()` lief nur in `main.py` (FastAPI). Der Celery-Worker hat
   Logging nie konfiguriert: httpx blieb auf INFO UND der `SensitiveDataFilter`
   war dort überhaupt nicht installiert.
2. Selbst mit installiertem Filter wäre der Token durchgekommen: httpx loggt
   `logger.info('HTTP Request: %s %s …', request.method, request.url, …)` —
   `request.url` ist ein `httpx.URL`-OBJEKT, und `_redact` fasste nur
   `isinstance(a, str)` an.

Deshalb prüft diese Datei beide Ebenen getrennt: die Redaktion muss auch dann
greifen, wenn der httpx-Logger eines Tages wieder gesprächig wird.
"""

import logging

import pytest

import logging_config


class _UrlLike:
    """Steht für `httpx.URL`: kein str, trägt den Token erst in `__str__`."""

    def __init__(self, value: str):
        self._value = value

    def __str__(self) -> str:
        return self._value


# Struktur echt, Ziffern/Buchstaben erfunden — Telegram-Token: <bot_id>:<35 Zeichen>.
_FAKE_TOKEN = "8123456789:AAFdummyTokenForTestsOnly_0123456789"
_FAKE_FILE_URL = f"https://api.telegram.org/file/bot{_FAKE_TOKEN}/voice/file_1.oga"


@pytest.fixture
def _logging_state():
    """Sichert den globalen Logging-Zustand.

    `setup_logging()` leert die Root-Handler — ohne Wiederherstellung würde der
    Handler von pytests `caplog` mit verschwinden und nachfolgende Tests in
    anderen Dateien still ihre Log-Assertions verlieren.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_noisy = {name: logging.getLogger(name).level for name in ("httpx", "httpcore")}
    try:
        yield
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        for name, level in saved_noisy.items():
            logging.getLogger(name).setLevel(level)


def _record(msg, *args) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


class TestSensitiveDataFilter:
    def test_url_object_arg_wird_redigiert(self):
        """Der eigentliche Leck-Fall: Token steckt in einem Nicht-String-Argument."""
        record = _record(
            'HTTP Request: %s %s "%s %d %s"',
            "GET",
            _UrlLike(_FAKE_FILE_URL),
            "HTTP/1.1",
            200,
            "OK",
        )

        logging_config.SensitiveDataFilter().filter(record)

        assert _FAKE_TOKEN not in record.getMessage()
        assert "api.telegram.org" in record.getMessage(), "Nur der Token darf weg, nicht die URL"

    def test_string_arg_wird_weiterhin_redigiert(self):
        """Regression: der bisher abgedeckte Fall bleibt abgedeckt."""
        record = _record("Fetching %s", _FAKE_FILE_URL)

        logging_config.SensitiveDataFilter().filter(record)

        assert _FAKE_TOKEN not in record.getMessage()

    def test_zahl_argument_bleibt_zahl(self):
        """%d darf nicht zu Text werden — sonst bricht die Formatierung."""
        record = _record(
            'HTTP Request: %s %s "%s %d %s"', "GET", "https://example.org", "HTTP/1.1", 200, "OK"
        )

        logging_config.SensitiveDataFilter().filter(record)

        assert record.args[3] == 200
        assert isinstance(record.args[3], int)
        assert record.getMessage().endswith('"HTTP/1.1 200 OK"')

    def test_token_als_msg_ohne_args(self):
        """Auch `logger.info(url_objekt)` ohne Formatargumente darf nicht lecken."""
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=_UrlLike(_FAKE_FILE_URL),
            args=(),
            exc_info=None,
        )

        logging_config.SensitiveDataFilter().filter(record)

        assert _FAKE_TOKEN not in record.getMessage()

    def test_dict_args_werden_redigiert(self):
        record = _record("payload %(url)s", {"url": _UrlLike(_FAKE_FILE_URL)})

        logging_config.SensitiveDataFilter().filter(record)

        assert _FAKE_TOKEN not in record.getMessage()


class TestSetupLogging:
    def test_httpx_ist_still(self, _logging_state):
        logging_config.setup_logging()

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_jeder_root_handler_traegt_den_filter(self, _logging_state):
        """Filter gehören an HANDLER, nicht an Logger.

        `Logger.filter()` wird nur auf Records angewandt, die AUF DIESEM Logger
        entstehen — bei Propagation nach oben ruft `callHandlers` die Filter der
        Vorfahren-Logger nicht auf. Ein Filter am Root-Logger würde httpx-Records
        also genau nicht erwischen.
        """
        logging_config.setup_logging()

        handlers = logging.getLogger().handlers
        assert handlers, "setup_logging muss mindestens einen Handler setzen"
        for handler in handlers:
            assert any(
                isinstance(f, logging_config.SensitiveDataFilter) for f in handler.filters
            ), f"Handler {handler!r} ohne Redaktions-Filter"


class TestEchterHttpxPfad:
    """Beweis am Artefakt statt an der Nachbildung.

    `_UrlLike` oben ist eine Nachbildung. Diese Klasse fährt den echten
    `httpx.URL` durch die echte Handler-Kette und liest die tatsächlich
    ausgegebene Zeile — genau der Weg, der am 04.08. 2486-mal geleckt hat.
    """

    def test_echte_httpx_url_leckt_nicht(self):
        import httpx

        record = _record(
            'HTTP Request: %s %s "%s %d %s"',
            "GET",
            httpx.URL(_FAKE_FILE_URL),
            "HTTP/1.1",
            200,
            "OK",
        )

        logging_config.SensitiveDataFilter().filter(record)

        assert _FAKE_TOKEN not in record.getMessage()

    def test_ausgegebene_zeile_enthaelt_keinen_token(self, _logging_state):
        """End-to-End: httpx-Logger → Root-Handler → Stream. Was rauskommt, zählt."""
        import io

        import httpx

        logging_config.setup_logging()
        stream = io.StringIO()
        handler = logging.getLogger().handlers[0]
        handler.setStream(stream)

        httpx_logger = logging.getLogger("httpx")
        # Bewusst auf INFO gezwungen: dieser Test prüft die ZWEITE Verteidigungslinie.
        # Wer die Stummschaltung eines Tages entfernt, darf trotzdem nichts lecken.
        httpx_logger.setLevel(logging.INFO)
        httpx_logger.info(
            'HTTP Request: %s %s "%s %d %s"',
            "GET",
            httpx.URL(_FAKE_FILE_URL),
            "HTTP/1.1",
            200,
            "OK",
        )
        handler.flush()

        ausgabe = stream.getvalue()
        assert ausgabe, "Der Record muss den Handler erreicht haben"
        assert _FAKE_TOKEN not in ausgabe
        assert "***" in ausgabe


def _lade_celery_app_frisch():
    """Lädt `tasks/celery_app.py` unter einem Wegwerf-Namen und gibt die je Signal
    NEU registrierten Empfänger zurück: `{signalname: [empfänger, …]}`.

    Warum nicht einfach `import tasks.celery_app`: `tests/_telegram_task_env.py`
    ersetzt `tasks.celery_app` dauerhaft durch einen Stub in `sys.modules`. Ob
    ein `import` hier das echte Modul oder die Attrappe trifft, hing damit an der
    Reihenfolge der Testdateien — derselbe Befehl lieferte in zwei Läufen
    gegensätzliche Urteile. Ein Test, dessen Ergebnis von der Sammelreihenfolge
    abhängt, bewacht nichts.

    `sys.modules` bleibt unangetastet: der Wegwerf-Name wird nicht eingetragen,
    also sieht kein nachfolgender Test einen anderen Zustand als vorher.
    """
    import importlib.util
    import os

    import celery.signals

    namen = ("setup_logging", "after_setup_logger", "after_setup_task_logger")
    vorher = {n: len(getattr(getattr(celery.signals, n), "receivers", [])) for n in namen}

    pfad = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tasks", "celery_app.py"
    )
    spec = importlib.util.spec_from_file_location("_celery_app_frisch_fuer_test", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)

    return {
        n: list(getattr(getattr(celery.signals, n), "receivers", []))[vorher[n] :] for n in namen
    }


class TestCeleryWorkerLogging:
    """Celery konfiguriert sein Logging selbst — wir härten nur nach."""

    def test_celery_wird_NICHT_uebernommen(self):
        """⚠️ Regressions-Wächter. Ein Empfänger auf `setup_logging` verhindert
        Celerys eigene Konfiguration (celery/app/log.py: `if not receivers:`) —
        und lässt damit Worker UND Beat vollständig verstummen.

        Am Artefakt gemessen (04.08.2026): Beat schrieb vorher 979
        „Sending due task"-Zeilen in 68 Minuten, nach der Übernahme null. Genau
        diese Betriebslogs waren die Grundlage, auf der der Telegram-Fehler
        überhaupt diagnostiziert wurde.
        """
        neue = _lade_celery_app_frisch()

        assert not neue["setup_logging"], (
            "tasks.celery_app darf celery.signals.setup_logging NICHT verbinden — "
            "das schaltet die Betriebslogs von Worker und Beat ab. Nachhärten via "
            "after_setup_logger / after_setup_task_logger."
        )

    def test_beide_after_setup_signale_sind_verbunden(self):
        """`celery.task` trägt `propagate = 0` und eigene Handler — ein Signal
        allein ließe dessen Records ungefiltert durch."""
        neue = _lade_celery_app_frisch()

        assert neue["after_setup_logger"], "after_setup_logger nicht verbunden"
        assert neue["after_setup_task_logger"], "after_setup_task_logger nicht verbunden"

    def test_empfaenger_haertet_die_uebergebenen_handler(self, _logging_state):
        """Der Empfänger muss httpx stummschalten UND den Filter an die Handler
        hängen, die Celery gerade angelegt hat."""
        neue = _lade_celery_app_frisch()
        empfaenger = neue["after_setup_logger"]
        assert empfaenger, "kein Empfänger registriert — siehe vorheriger Test"

        # Nachbau dessen, was Celery uebergibt: ein Logger mit eigenem Handler.
        celery_logger = logging.getLogger("celery_test_nachbau")
        celery_logger.handlers = [logging.StreamHandler()]
        logging.getLogger("httpx").setLevel(logging.INFO)

        for receiver in empfaenger:
            receiver(logger=celery_logger, loglevel=logging.INFO, logfile=None, format="")

        assert logging.getLogger("httpx").level == logging.WARNING
        assert any(
            isinstance(f, logging_config.SensitiveDataFilter)
            for f in celery_logger.handlers[0].filters
        ), "Der von Celery uebergebene Handler blieb ohne Redaktion"

    def test_redaktion_wird_nicht_doppelt_gehaengt(self, _logging_state):
        """Beide Signale feuern nacheinander auf denselben Root-Logger."""
        logger = logging.getLogger("celery_test_doppelt")
        logger.handlers = [logging.StreamHandler()]

        logging_config.install_redaction(logger)
        logging_config.install_redaction(logger)

        filter_anzahl = sum(
            isinstance(f, logging_config.SensitiveDataFilter) for f in logger.handlers[0].filters
        )
        assert filter_anzahl == 1

    def test_echte_zeile_aus_celery_handler_leckt_nicht(self, _logging_state):
        """Beweis am Artefakt: ein von Celery angelegter Handler, nachgehärtet,
        gibt den Token nicht mehr aus."""
        import io

        import httpx

        celery_logger = logging.getLogger("celery_test_ausgabe")
        celery_logger.propagate = False
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        celery_logger.handlers = [handler]
        celery_logger.setLevel(logging.INFO)

        logging_config.install_redaction(celery_logger)

        celery_logger.info(
            'HTTP Request: %s %s "%s %d %s"',
            "GET",
            httpx.URL(_FAKE_FILE_URL),
            "HTTP/1.1",
            200,
            "OK",
        )
        handler.flush()

        ausgabe = stream.getvalue()
        assert ausgabe
        assert _FAKE_TOKEN not in ausgabe
        assert "***" in ausgabe
