"""RLS-Wächter — macht fehlenden Tenant-Kontext SICHTBAR statt still.

⛔ WARUM ES DIESE DATEI GIBT — der Vorfall vom 17.08.2026:

Migration 058 aktivierte `FORCE ROW LEVEL SECURITY` auf 43 Tabellen. Die
Policy verlangt `app.tenant_id` oder `app.rls_bypass`. Die App verbindet als
Rolle `autopilot` ohne `rolbypassrls` — also sieht **jede** Session ohne
gesetzten Kontext **null Zeilen**.

Das allein wäre halb so schlimm. Der zweite Teil des Bugs ist die Deutung:
Fast überall wird „0 Zeilen" als „nicht vorhanden" gelesen, und ein
`except: pass` oder ein `if not row: return None` schluckt es. Das Ergebnis
ist von einem korrekten Leerbefund **nicht unterscheidbar**.

Gemessen an der echten Datenbank (Tenant „Louis MVP", identische Query je
einmal ohne und mit Kontext):

    telegram_message_log:  ohne 0  |  mit 59
    bot_session:           ohne 0  |  mit 20
    content_pieces:        ohne 0  |  mit 10
    memory_chunks:         ohne 0  |  mit 57
    setup_pipeline_run:    ohne 0  |  mit 37
    content_ideas:         ohne 0  |  mit  2

Sichtbare Folge beim Kunden: 79 eingehende Telegram-Nachrichten, **0**
ausgehende. Der Bot fand den Chat nicht, weil `tenant_telegram_link` ohne
Kontext leer aussah.

⛔ WARUM EIN WÄCHTER UND NICHT 80 EINZELNE FIXES:

Eine statische Prüfung fand 80 solcher Stellen in 21 Dateien. Jede einzeln zu
patchen hätte drei Probleme:
  1. Es repariert den Bestand, nicht die Klasse — die 81. Stelle entsteht
     morgen wieder.
  2. Jede Stelle braucht eine eigene Entscheidung (Tenant-Kontext vs. Bypass).
     Pauschal überall `bypass` zu setzen, würde die Mandantentrennung faktisch
     abschalten — schlimmer als der Ist-Zustand.
  3. Der stille Charakter bliebe: Wer eine Stelle übersieht, merkt es nicht.

Dieser Wächter dreht genau das um. Er repariert **nichts** automatisch — er
macht den Zustand **laut**. Ein Entwickler, der eine Stelle vergisst, sieht
eine Warnung im Log statt eines falschen Leerbefunds.

⛔ WAS ER BEWUSST NICHT TUT:

- Er setzt KEINEN Kontext automatisch. Das wäre geraten: nur der Aufrufer
  weiß, ob eine Abfrage tenant-gescopet oder legitim cross-tenant ist.
- Er wirft im Normalbetrieb NICHT. Ein Wächter, der Produktion lahmlegt, wird
  abgeschaltet — und dann schützt er gar nichts. Über
  `RLS_GUARD_STRICT=1` lässt er sich in Tests und CI scharf schalten.
- Er greift nur bei SYNC-Sessions. Der Request-Pfad (`get_db`) setzt den
  Kontext bereits; dort gibt es das Problem nicht.
"""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy import event, text

logger = logging.getLogger(__name__)

#: Die Tabellen mit FORCE ROW LEVEL SECURITY (Migrationen 058, 061, 062).
#: Bewusst als Literal und nicht aus der DB gelesen: der Wächter muss auch dann
#: funktionieren, wenn die Verbindung gerade das Problem ist.
RLS_TABELLEN: frozenset[str] = frozenset(
    {
        "backtest_runs", "bot_session", "campaigns", "carousel_templates",
        "company_profile", "content_dna_profiles", "content_ideas",
        "content_performances", "content_pieces", "daily_cost_tenant",
        "deletion_requests", "dialogue_questions", "entrepreneur_answers",
        "hook_library", "idea_selection_logs", "idea_variants", "llm_call_logs",
        "llm_providers", "llm_trace", "memory_chunks", "profile_field_provenance",
        "projects", "quality_metrics", "research_findings", "scheduled_posts",
        "setup_pipeline_run", "source_items", "sources", "telegram_message_log",
        "tenant_audience_avatar", "tenant_bot_config", "tenant_branding",
        "tenant_concurrency", "tenant_customer_context", "tenant_customer_values",
        "tenant_reservoir", "tenant_review_queue", "tenant_telegram_link",
        "tenant_voice_profile", "throttle_events", "voice_drift_observation",
        "voice_feedback", "wizard_session",
    }
)

#: Anweisungen, die selbst den Kontext setzen — sie dürfen den Wächter nicht
#: auslösen, sonst warnt er über seine eigene Lösung.
_KONTEXT_SETZER = re.compile(r"set_config\s*\(\s*'app\.(tenant_id|rls_bypass)'", re.I)

_STRICT = os.environ.get("RLS_GUARD_STRICT", "").strip() in ("1", "true", "yes")

#: Damit ein Dauerläufer das Log nicht flutet: pro Fundstelle einmal warnen.
_gesehen: set[str] = set()


def _tabellen_im_sql(sql: str) -> set[str]:
    """Die RLS-Tabellen, die in diesem Statement vorkommen.

    Bewusst simpel (Wortgrenzen-Suche statt SQL-Parser): der Wächter läuft bei
    JEDEM Statement, er muss billig sein. Ein Fehlalarm durch ein Tabellenwort
    in einem String-Literal ist harmlos — er kostet eine Log-Zeile, keine
    Funktion.
    """
    sql_lower = sql.lower()
    return {t for t in RLS_TABELLEN if re.search(rf"\b{t}\b", sql_lower)}


def _kontext_gesetzt(conn) -> bool:
    """Trägt diese Verbindung einen brauchbaren RLS-Kontext?

    Fail-open: Kann der Wächter es nicht feststellen, meldet er „ja" und hält
    den Mund. Ein Wächter, der bei eigener Unsicherheit Alarm schlägt,
    erzeugt Rauschen — und Rauschen wird ignoriert.
    """
    try:
        row = conn.exec_driver_sql(
            "SELECT COALESCE(NULLIF(current_setting('app.tenant_id', true), ''), '') "
            "|| '|' || COALESCE(current_setting('app.rls_bypass', true), '')"
        ).scalar()
    except Exception:
        return True
    if not row:
        return False
    tenant_teil, _, bypass_teil = str(row).partition("|")
    return bool(tenant_teil) or bypass_teil == "on"


def _melde(sql: str, tabellen: set[str]) -> None:
    stelle = _aufrufer_stelle()
    schluessel = f"{stelle}|{sorted(tabellen)[0]}"
    if schluessel in _gesehen:
        return
    _gesehen.add(schluessel)
    logger.warning(
        "RLS-WAECHTER: Zugriff auf %s OHNE Tenant-Kontext — die Abfrage liefert "
        "0 Zeilen, unabhaengig davon ob Daten existieren. Aufrufer: %s. "
        "Abhilfe: set_rls_tenant_sync(session, tenant_id) fuer tenant-gescopete "
        "Arbeit, set_rls_bypass_sync(session, True) NUR fuer legitim "
        "tenant-uebergreifende Crons.",
        ", ".join(sorted(tabellen)),
        stelle,
    )


def _aufrufer_stelle() -> str:
    """Datei:Zeile des ersten Frames ausserhalb von SQLAlchemy und diesem Modul.

    Ohne diese Angabe wäre die Warnung wertlos — 80 gleiche Zeilen ohne
    Fundort helfen niemandem.
    ⛔ Bewusst kein `exc_info=True` und kein Stack-Dump im Log: dort landen
    sonst Query-Parameter, und die enthalten Kundendaten.
    """
    import traceback

    for frame in reversed(traceback.extract_stack()[:-1]):
        pfad = frame.filename
        if "/sqlalchemy/" in pfad or pfad.endswith("rls_guard.py"):
            continue
        if "/app/" in pfad or "/backend/" in pfad:
            kurz = pfad.split("/app/")[-1].split("/backend/")[-1]
            return f"{kurz}:{frame.lineno}"
    return "unbekannt"


def aktiviere_rls_waechter(engine) -> None:
    """Hängt den Wächter an eine SYNC-Engine.

    Idempotent: mehrfaches Aufrufen registriert den Listener nur einmal.
    """
    if getattr(engine, "_rls_waechter_aktiv", False):
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _pruefe(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        try:
            if _KONTEXT_SETZER.search(statement):
                return
            tabellen = _tabellen_im_sql(statement)
            if not tabellen:
                return
            if _kontext_gesetzt(conn):
                return
            _melde(statement, tabellen)
            if _STRICT:
                raise RlsKontextFehlt(
                    f"Zugriff auf {', '.join(sorted(tabellen))} ohne Tenant-Kontext "
                    f"({_aufrufer_stelle()})"
                )
        except RlsKontextFehlt:
            raise
        except Exception as exc:  # pragma: no cover — der Waechter darf nie stoeren
            logger.debug("RLS-Waechter uebersprungen: %s", type(exc).__name__)

    engine._rls_waechter_aktiv = True
    logger.info("RLS-Waechter aktiv (strict=%s)", _STRICT)


class RlsKontextFehlt(RuntimeError):
    """Nur im Strict-Modus: harte Grenze für Tests und CI."""


__all__ = ["RLS_TABELLEN", "RlsKontextFehlt", "aktiviere_rls_waechter", "text"]
