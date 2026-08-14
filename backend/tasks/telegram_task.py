"""Telegram-Update-Verarbeitung (Phase 5 Welle 3, Issue #140).

Wird von api.telegram._store_and_dispatch() per Celery enqueued.
Lädt das telegram_message_log-Row, holt Audio/Photo via getFile-API,
transkribiert (Voice) bzw. OCR+Vision (Photo, später Welle 4),
schreibt das Resultat als memory_chunk und persistiert
transcript_text + transcription_model im log-Row.

Defensiv:
- Bei jedem Schritt soft-fail mit logger.warning
- Embedding-Fehler blockieren NICHT (chunk-without-embedding,
  HNSW-Index PARTIAL)
"""

from __future__ import annotations

import asyncio
import logging
import os
import types

import httpx
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models.base import sync_session_factory
from services.anweisungs_marker import MARKER_PATCH_JSON
from services.voice_transcription import (
    TranscriptionError,
    TranscriptionResult,
    TranscriptionUnavailable,
    transcribe_voice,
)
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


# ── helpers ─────────────────────────────────────────────────────────────


def _load_log_row(log_id: str) -> dict | None:
    """Lädt eine telegram_message_log-Zeile als Dict."""
    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT id, tenant_id, message_type, original_payload, "
                "       transcript_text, transcription_model "
                "FROM telegram_message_log WHERE id = :id"
            ),
            {"id": log_id},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "message_type": row.message_type,
        "original_payload": dict(row.original_payload or {}),
        "transcript_text": row.transcript_text,
        "transcription_model": row.transcription_model,
    }


def _update_log_transcript(log_id: str, transcript: str, model: str, confidence: float) -> None:
    with sync_session_factory() as db:
        db.execute(
            text(
                "UPDATE telegram_message_log "
                "SET transcript_text = :t, transcription_model = :m, "
                "    transcription_confidence = :c "
                "WHERE id = :id"
            ),
            {"id": log_id, "t": transcript, "m": model, "c": round(min(max(confidence, 0), 1), 2)},
        )
        db.commit()


def _load_active_session(tenant_id: str) -> object | None:
    """Lädt die aktive bot_session des Tenants (random_smart oder targeted).

    Gibt ein leichtgewichtiges SimpleNamespace(id, status, current_question)
    zurück (KEIN ORM-Model — route_telegram_intent greift nur per
    getattr/str auf id/status zu) oder None, wenn keine aktive Session
    existiert.

    #57: Filter auf mode IN ('random_smart','targeted') erweitert — ohne dies
    umgehen targeted-Antworten still das p08-Routing (p08_service unterstützt
    targeted bereits).

    #62: current_question (letzte bot-Frage aus messages[-1]["bot"]) wird
    mitgeladen, damit Layer-1 die Nutzer-Antwort gegen die tatsächlich
    gestellte Frage klassifizieren kann statt blind zu raten.
    """
    with sync_session_factory() as db:
        row = db.execute(
            text(
                "SELECT id, status, messages FROM bot_session "
                "WHERE tenant_id = :tid AND status = 'active' "
                "      AND mode IN ('random_smart', 'targeted') "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"tid": tenant_id},
        ).fetchone()
    if row is None:
        return None
    current_question = ""
    awaiting_confirmation = False
    messages = row.messages or []
    if isinstance(messages, list) and messages:
        last_entry = messages[-1]
        if isinstance(last_entry, dict):
            current_question = (last_entry.get("bot") or "").strip()
            # Hat der Bot zuletzt ein Abschluss-Angebot gemacht? Dann ist die
            # naechste Nachricht die Bestaetigung — sie MUSS bei p08_response
            # ankommen, auch wenn Schicht 1 ein blosses „ja" als Smalltalk
            # einordnet. Ohne diese Weiche haenge das Gespraech am Ja fest.
            awaiting_confirmation = last_entry.get("next_action") == "offer"
    return types.SimpleNamespace(
        id=row.id,
        status=row.status,
        current_question=current_question,
        awaiting_confirmation=awaiting_confirmation,
    )


#: Kürzester Text, der ausserhalb eines Gespraechs noch als Gedaechtnis-Eintrag
#: durchgeht. Innerhalb eines Gespraechs zaehlt jede Laenge — „ja" ist die
#: vorgesehene Bestaetigung eines Abschluss-Angebots.
MIN_TEXT_LEN = 10


def hat_aktives_gespraech(tenant_id: str) -> bool:
    """True, wenn gerade ein Bot-Gespraech laeuft.

    ⚠️ Gemeinsame Regel fuer BEIDE Kurztext-Filter — `api/telegram.py`
    (vor dem Dispatch) und `_process_text` (danach). Wer nur einen der beiden
    an die Session koppelt, laesst „ja" durch die Vordertuer und verliert es an
    der Hintertuer.

    Fail-open zu False, und die Richtung ist Absicht: bei einem DB-Fehler
    verhaelt sich der Filter wie bisher (Hinweis statt Verarbeitung), statt
    ungeprueft alles durchzulassen.
    """
    try:
        return _load_active_session(tenant_id) is not None
    except Exception as exc:
        logger.warning("Kurztext-Gate: Session-Abfrage fehlgeschlagen: %s", type(exc).__name__)
        return False


def _is_pending_variant_choice(tenant_id: str, text_content: str) -> bool:
    """True nur bei OFFENEM Varianten-Marker UND parsebarem Wahl-Token.

    Beide Bedingungen zusammen. Ein reiner Marker-Check wäre falsch: der Marker
    lebt 24 Stunden (`_P13_CHOICE_WINDOW_HOURS`), ein veralteter würde die Weiche
    kippen und damit ausgerechnet den LLM-Pfad wieder öffnen, den
    `_awaits_user_choice` schließt.

    Token zuerst — reines Regex, spart den DB-Treffer im Normalfall.
    """
    try:
        from tasks.p13_variants_task import _load_pending_idea, _parse_choice_token

        if _parse_choice_token(text_content) is None:
            return False
        return _load_pending_idea(tenant_id) is not None
    except Exception as exc:
        logger.warning("pending variant check failed: %s", type(exc).__name__)
        return False


def _awaits_user_choice(tenant_id: str, text_content: str) -> bool:
    """True = der Nutzer muss entscheiden, was mit der Nachricht passieren soll.

    Ersetzt den LLM-Rateschritt: statt zu klassifizieren, was jemand wollte, fragt
    der Bot nach. Nur wenn ein bestehender Pfad die Nachricht nachweislich
    erwartet, bleibt es beim alten Verhalten.

    Seit P14 (services/p14_entry_service.py) laeuft hinter dieser Weiche bei
    JEDER Nachricht, die sie passiert, ein eigener S2-Aufruf
    (`_versuche_gespraechsstart`) — auch bei denen, die am Ende trotzdem die
    zwei Buttons bekommen. Die Doktrin ("bei Substanz wird gefragt, nicht
    geraten") gilt weiter, nur der Weg dorthin ist jetzt ein anderer.

    Fail-open zu False, und die Richtung ist Absicht: Wirft z. B.
    `_load_active_session`, wissen wir nicht, ob ein Interview läuft. False führt
    zurück in `_route_inbound_message`, das die Session selbst noch einmal lädt —
    eine laufende Antwort geht also nicht verloren. True („im Zweifel fragen")
    wäre hier gefährlicher: es würde die Antwort auf eine offene Interview-Frage
    verwerfen und das Gespräch stehen lassen.
    """
    try:
        if _load_active_session(tenant_id) is not None:
            return False

        from services.chat_intent_heuristics import is_idea_request

        if is_idea_request(text_content):
            return False

        return not _is_pending_variant_choice(tenant_id, text_content)
    except Exception as exc:
        logger.warning("choice gate failed: %s", type(exc).__name__)
        return False


#: Wie viel Text die Quittung zitiert, bevor sie zum Auszug wird.
_QUITTUNG_GRENZE = 80


def _quittungs_zitat(text_content: str, grenze: int = _QUITTUNG_GRENZE) -> str:
    """Der zitierte Teil einer Quittung — nie mitten im Wort, als Auszug erkennbar.

    Die Quittung ist eine Aussage darüber, was im Gedächtnis liegt. Ein harter Schnitt
    bei `grenze` macht daraus eine falsche Aussage: aus „in ein Business-Netzwerk" wurde
    live am 06.08.2026 „in ein Bus…" — ein Wort, das niemand gesagt hat — und der Nutzer
    las daraus, es werde nur sein erster Satz gespeichert. Gespeichert wird immer alles.

    Deshalb zwei Änderungen gegenüber dem harten Schnitt: an der letzten Wortgrenze
    trennen, und den tatsächlichen Umfang danebenstellen, statt ihn zu verschweigen.

    Die Längenangabe zählt den übergebenen Text, nicht den gekürzten — sie soll ja
    gerade sagen, wie viel mehr gespeichert ist als hier steht.
    """
    voll = text_content or ""
    if len(voll) <= grenze:
        return f"„{voll.rstrip()}“"

    kopf = voll[:grenze]
    # Ein einzelnes überlanges Wort hat keine Wortgrenze — dann ist der harte Schnitt
    # die einzige Möglichkeit, und ein leerer Auszug wäre die schlechtere.
    schnitt = kopf.rsplit(" ", 1)[0].rstrip(" ,;:–—-") if " " in kopf else kopf.rstrip()
    return f"„{schnitt}…“ (von {len(voll)} Zeichen)"


def _send_choice_prompt(
    tenant_id: str, chat_id: int, log_id: str, text_content: str, icon: str
) -> bool:
    """Bestätigung plus die zwei Wege. True, wenn zugestellt.

    Kein Rollback nötig, wenn der Versand scheitert: es wurde keine Session
    eröffnet, die als Falle zurückbliebe, und der Memory-Chunk liegt bereits.
    Aber protokollieren statt schlucken — dieser Prompt ist der einzige sichtbare
    Ausgang der Nachricht.
    """
    try:
        from api.telegram import _choice_keyboard, _send_telegram_message

        sent = _send_telegram_message(
            chat_id,
            f"{icon} Notiert: {_quittungs_zitat(text_content)}\n\nWas soll ich damit machen?",
            tenant_id=tenant_id,
            reply_markup=_choice_keyboard(log_id),
        )
    except Exception as exc:
        logger.warning("choice prompt send failed: %s", type(exc).__name__)
        return False
    if not sent:
        logger.warning(
            "telegram_task: Wahl-Prompt nicht zugestellt (tenant=%s, log_id=%s)",
            tenant_id,
            log_id,
        )
    return sent


def _verwerfe_session(session_id: str) -> None:
    """Rollback einer gerade angelegten Session (fail-open).

    Kommt die Eroeffnungsfrage nicht an, bleibt sonst eine UNSICHTBARE Session
    zurueck: `_load_active_session` findet sie, und jede weitere Nachricht des
    Nutzers wird als Antwort auf eine Frage geroutet, die er nie gelesen hat.
    Sessions haben kein TTL.

    Status 'expired', nicht 'closed' — 'closed' stellt in
    `tasks/session_post_task.py` die Post-Generierung scharf.
    """
    try:
        with sync_session_factory() as db:
            db.execute(
                text(
                    "UPDATE bot_session SET status = 'expired', updated_at = NOW() "
                    "WHERE id = :id AND status = 'active'"
                ),
                {"id": session_id},
            )
            db.commit()
    except Exception as exc:
        logger.warning("p14 session rollback failed: %s", type(exc).__name__)


#: Steuerungsmerkmal fuer Nachrichten, die ein Gespraech eroeffnet haben.
#: Bewusst in `metadata`, nicht in `classification` — dort steht eine
#: INHALTLICHE Kategorie, die store_chunk(classify=True) selbst vergibt und die
#: values_backfill_task auswertet.
#:
#: Wert und Auswerter leben in services/anweisungs_marker.py — hier steht nur noch
#: der Zeiger, damit Setzer und Filter nicht auseinanderlaufen koennen.
_ANWEISUNGS_MARKER = MARKER_PATCH_JSON


def _markiere_chunk_als_anweisung(tenant_id: str, log_id: str) -> bool:
    """Markiert die Chunks dieser Nachricht als Steuer-Anweisung (Spec §7).

    Die Nachricht liegt bereits als Memory-Chunk im Gedaechtnis —
    `_store_chunk_async` laeuft VOR allen Weichen. Damit ist der Chunk fuer
    spaetere Konsumenten filterbar. Das Filtern selbst ist NICHT Teil dieser
    Arbeit: heute wird das Merkmal per Default von `search_similar` (RAG),
    von `p06_profile_extractor_task` (Voice-Profil) und von `memory_picker`
    ausgewertet — die eine Wahrheit dazu liegt in
    `services/anweisungs_marker.py`. Hier entsteht nur das Merkmal.

    ⚠️ Adressiert ueber `source_ref`, NICHT ueber die zurueckgegebene Chunk-ID:
    `_store_chunk_async` gibt laut eigenem Docstring nur die ID des ERSTEN
    Chunks zurueck; ein laengerer Text wird gechunkt, und die uebrigen blieben
    unmarkiert.

    Loeschen waere unumkehrbar; der Rohtext liegt ohnehin im
    telegram_message_log. Fail-open: ein Markierungsfehler darf nie ein
    Gespraech verhindern.

    Returns:
        True, wenn das UPDATE durchlief; sonst False.
    """
    try:
        with sync_session_factory() as db:
            db.execute(
                text(
                    "UPDATE memory_chunks "
                    "SET metadata = COALESCE(metadata, CAST('{}' AS jsonb)) "
                    "               || CAST(:patch AS jsonb) "
                    "WHERE tenant_id = :tid AND source_ref = :ref"
                ),
                {
                    "patch": _ANWEISUNGS_MARKER,
                    "tid": tenant_id,
                    "ref": f"telegram_message_log:{log_id}",
                },
            )
            db.commit()
        return True
    except Exception as exc:
        logger.warning("p14 chunk marking failed: %s", type(exc).__name__)
        return False


def _versuche_gespraechsstart(
    tenant_id: str, text_content: str, log_id: str, chat_id: int | None
) -> dict | None:
    """P14 — eine Anweisung wird ein Gespraech. None heisst: weiter zu den Buttons.

    Laeuft NUR, wenn `_awaits_user_choice` True gesagt hat; Session, P13-Wahl und
    P09 sind damit bereits ausgeschlossen (Gate-Reihenfolge der Spec §4).

    Die Antwort des Zuges IST die Eroeffnungsfrage und zugleich messages[0] der
    Session — sie ersetzt den p08_opener-Aufruf, sie kommt nicht obendrauf.

    Jeder Fehler gibt None zurueck: der Aufrufer sendet dann die zwei Buttons.
    Nie Stille, nie eine halbe Session.
    """
    try:
        from services.p14_entry_service import HANDLUNG_GESPRAECH, p14_entry

        entscheidung = p14_entry(tenant_id, text_content)
    except SoftTimeLimitExceeded:
        # Muss vor dem Exception-Katalog stehen — siehe _route_inbound_message.
        raise
    except Exception as exc:
        logger.warning("p14 entry gate failed: %s", type(exc).__name__)
        return None

    if getattr(entscheidung, "handlung", None) != HANDLUNG_GESPRAECH:
        return None

    ziel_chat = chat_id or _resolve_chat_id(tenant_id)
    if ziel_chat is None:
        # Ohne Chat kaeme die Frage nie an. Dann lieber keine Session, die auf
        # eine Antwort wartet, die niemand geben kann.
        logger.warning("p14: kein chat auffindbar (tenant=%s) — kein Gespraechsstart", tenant_id)
        return None

    try:
        from services.p08_service import erzeuge_bot_session

        session_id = erzeuge_bot_session(
            tenant_id=tenant_id,
            mode="targeted",
            topic_idea_id=None,
            frage=entscheidung.antwort,
            # Der Folgeprompt liest messages[0]["category"] als „Thema des
            # Gespraechs" (p08_service.py). Die ausloesende Nachricht sagt darueber
            # mehr als das Steuerwort „targeted".
            category=(text_content or "").strip()[:120] or "targeted",
        )
    except Exception as exc:
        logger.warning("p14 session insert failed: %s", type(exc).__name__)
        return None

    try:
        from api.telegram import _entry_keep_keyboard, _send_telegram_message

        gesendet = _send_telegram_message(
            ziel_chat,
            entscheidung.antwort,
            tenant_id=tenant_id,
            reply_markup=_entry_keep_keyboard(),
        )
    except Exception as exc:
        logger.warning("p14 opener send failed: %s", type(exc).__name__)
        gesendet = False

    if not gesendet:
        # Die Session zuruecknehmen, sonst schluckt sie ab jetzt jede Nachricht.
        _verwerfe_session(session_id)
        return None

    # Fail-open, und zwar hier zusaetzlich: der Vertrag „eine Markierung
    # verhindert nie ein Gespraech" darf nicht davon abhaengen, dass der
    # Aufgerufene sich benimmt.
    try:
        _markiere_chunk_als_anweisung(tenant_id, log_id)
    except Exception as exc:
        logger.warning("p14 chunk marking raised: %s", type(exc).__name__)

    return {
        "routed_to": "p14_gespraech",
        "bot_session_id": session_id,
        "p14_message_sent": True,
    }


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id for a tenant (Issue #17).

    1:1 nach dem Muster random_smart_scheduler._send_opening_question.
    Fail-open: gibt None zurück bei Fehler oder wenn kein aktiver Link.
    E2: nur type(e).__name__ loggen, nie str(exc).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT telegram_chat_id FROM tenant_telegram_link "
                    "WHERE tenant_id = :tid AND status = 'active' LIMIT 1"
                ),
                {"tid": tenant_id},
            ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None
    except Exception as exc:
        logger.warning("_resolve_chat_id failed: %s", type(exc).__name__)
        return None


_FEEDBACK_WINDOW_HOURS = int(os.environ.get("TELEGRAM_FEEDBACK_WINDOW_HOURS", "48"))


def _resolve_last_post(tenant_id: str) -> object | None:
    """Löst den jüngsten Bot-Post (bot_session_close oder post_feedback_regen) auf.

    Zeitfenster: TELEGRAM_FEEDBACK_WINDOW_HOURS (Default 48h).
    Liefert SimpleNamespace(id, summary, bot_session_id) oder None.
    Fail-open (E2): nur type(exc).__name__ loggen. Tenant-gescopet (E3).

    #37: migrationsfrei — nutzt content_metadata->>'source' IN ('bot_session_close',
    'post_feedback_regen'), Marker aus #19 (session_post_task.py:192).
    """
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT id, content_text, content_metadata->>'bot_session_id' AS bot_session_id "
                    "FROM content_pieces "
                    "WHERE tenant_id = :tid "
                    "  AND content_metadata->>'source' IN ('bot_session_close', 'post_feedback_regen') "
                    "  AND created_at > now() - make_interval(hours => :window_hours) "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"tid": tenant_id, "window_hours": _FEEDBACK_WINDOW_HOURS},
            ).fetchone()
        if row is None:
            return None
        return types.SimpleNamespace(
            id=str(row.id),
            summary=(row.content_text or "")[:200],
            bot_session_id=str(row.bot_session_id) if row.bot_session_id else None,
        )
    except Exception as exc:
        logger.warning("_resolve_last_post failed: %s", type(exc).__name__)
        return None


#: Routing-Ziele, die dem Nutzer nachweislich selbst antworten (direkt oder über
#: einen enqueueten Task). Alles andere braucht eine sichtbare Quittung, sonst
#: endet die Nachricht still — der eine Zustand, den dieser Entwurf ausschliesst.
#:
#: Positivliste, nicht Negativliste: ein neues Routing-Ziel ist im Zweifel stumm,
#: und dann soll die Quittung greifen statt zu fehlen.
_ZIELE_MIT_EIGENER_ANTWORT = frozenset(
    {
        "p08_response",
        "p09_ideation",
        "p13_variants",
        "voice_feedback_api",
        "p14_gespraech",
    }
)


#: Flags, mit denen ein Ziel meldet, ob sein antwortender Task wirklich in die
#: Warteschlange kam. Steht eines auf False, hat NIEMAND den Nutzer erreicht —
#: dann braucht es die Quittung, obwohl das Ziel in der Positivliste steht.
_ENQUEUE_FLAGS = ("p13_enqueued", "regen_enqueued")


def _braucht_sichtbare_quittung(routing_info: dict) -> bool:
    """True, wenn nach dem Routing niemand mehr mit dem Nutzer spricht.

    Zwei Bedingungen, nicht eine: das Ziel muss selbst antworten KÖNNEN (Positiv-
    liste) UND sein Task muss tatsächlich enqueued worden sein. Ein gescheiterter
    Enqueue behält den Zielnamen bei — ohne die zweite Prüfung wäre das wieder
    Stille, diesmal im Mechanismus gegen Stille.

    `deduped` bleibt ausgenommen: Doppel-Event auf eine bereits beantwortete
    Nachricht.
    """
    if routing_info.get("deduped"):
        return False
    if routing_info.get("routed_to") not in _ZIELE_MIT_EIGENER_ANTWORT:
        return True
    return any(routing_info.get(flag) is False for flag in _ENQUEUE_FLAGS)


def _route_inbound_message(
    tenant_id: str, text_content: str, log_id: str | None = None
) -> dict | None:
    """Verdrahtet eingehende Antworten mit der Intent-Routing-Pipeline (Issue #16).

    Schritt 1: Idempotenz-Guard — wenn log_id gesetzt und routed_to bereits
               non-NULL → Duplikat, früh return (kein zweiter p08-Call). (#56/#18)
    Schritt 2: aktive Session laden (PRIMÄRES Gate). Keine Session → None.
    Schritt 3: extract_intent_features → route_telegram_intent.
    Schritt 4: Routing-Marker persistieren BEVOR p08_response (at-most-once,
               damit ein Crash mitten in p08 beim Retry nicht erneut routet). (#56)
    Schritt 5: bei target == 'p08_response' → p08_response aufrufen.

    Fail-open: jede Exception wird nur geloggt, Rückgabe None — der bestehende
    Chunk-Return des Callers darf NIEMALS kaputtgehen.

    Returns ein Dict mit Routing-Metadaten (z.B. routed_to, p08_next_action,
    bot_session_id) oder None, wenn nicht geroutet wurde.
    """
    try:
        # #56/#18 Schicht A — Idempotenz-Guard: bereits geroutete Log-Zeile überspringen
        if log_id is not None:
            with sync_session_factory() as db:
                guard_row = db.execute(
                    text("SELECT routed_to FROM telegram_message_log WHERE id = :id"),
                    {"id": log_id},
                ).fetchone()
            if guard_row is not None and guard_row[0] is not None:
                # Bereits geroutet — Celery-Retry oder Doppel-Event → überspringen
                logger.info(
                    "inbound routing deduplicated: log_id=%s already routed_to=%s",
                    log_id,
                    guard_row[0],
                )
                return {"routed_to": guard_row[0], "deduped": True}

        # #36 Gate 2 — P13-Choice: Pending-Marker + strenges Choice-Pattern (≤40 Zeichen).
        # VOR Gate 3 (aktive Session): zwischen Varianten-Nachricht und Wahl kann der
        # random_smart-Scheduler eine Session öffnen — „2" darf nicht als p08-Antwort landen.
        # Strenge Länge (≤40 Zeichen) macht Fehlgriffe auf echte Interview-Antworten
        # praktisch unmöglich; lange Antworten fallen durch zu Gate 3.
        try:
            from tasks.p13_variants_task import _try_p13_variant_choice

            choice_result = _try_p13_variant_choice(tenant_id, text_content)
            if choice_result and isinstance(choice_result, dict):
                if log_id is not None:
                    from services.layer2_routing import (
                        RoutingDecision,
                        persist_routing_decision,
                    )

                    _p13_dec = RoutingDecision("p13_variants", {}, "p13_choice")
                    persist_routing_decision(log_id, _p13_dec)
                return choice_result
        except Exception as exc:
            logger.warning("p13 choice gate failed: %s", type(exc).__name__)
            # Fail-open: weiter mit normalem Flow

        session = _load_active_session(tenant_id)
        if session is None:
            # #36 Gate 4 — P09-Heuristik: vor _resolve_last_post, damit der
            # 48h-Feedback-Pfad (#37) Ideen-Anfragen nicht frisst.
            # Deterministisch, kein LLM-Call (dep-freie Heuristik).
            try:
                from services.chat_intent_heuristics import is_idea_request
                from tasks.p09_chat_ideas_task import deliver_ideas_to_chat

                if is_idea_request(text_content):
                    deliver_ideas_to_chat.apply_async(args=[tenant_id, text_content[:500], log_id])
                    if log_id is not None:
                        # Persist-Marker (at-most-once, Dedup-Guard); fail-open wenn
                        # CHECK-Constraint den p10-Mapped-Wert ablehnt.
                        from services.layer2_routing import (
                            RoutingDecision,
                            persist_routing_decision,
                        )

                        _dec = RoutingDecision("p09_ideation", {}, "p09_heuristic")
                        persist_routing_decision(log_id, _dec)
                    return {"routed_to": "p09_ideation", "p09_enqueued": True}
            except Exception as exc:
                logger.warning("p09 heuristic gate failed: %s", type(exc).__name__)
                # Fail-open: weiter mit normalem Flow

            # #37 — Feedback-Zweig: kein aktives Session-Objekt, aber letzter Post vorhanden?
            last_post = _resolve_last_post(tenant_id)
            if last_post is None:
                # #36 Gate 6 — Own-Idea-Vorfilter: hält heutiges LLM-Kostenprofil —
                # kein Layer1-Call für reine Memory-Inputs.
                # Nur bei is_own_idea-Treffer → Layer1 → Layer2 (spontaneous_idea ohne
                # Session → p13_variants). Kein Treffer → Memory-Default wie bisher.
                try:
                    from services.chat_intent_heuristics import is_own_idea
                    from services.layer1_extraction import extract_intent_features
                    from services.layer2_routing import (
                        persist_routing_decision,
                        route_telegram_intent,
                    )
                    from tasks.p13_variants_task import generate_variants_for_chat

                    if is_own_idea(text_content):
                        extraction = extract_intent_features(
                            transcript=text_content,
                            tenant_id=tenant_id,
                            session_state="no_session",
                        )
                        decision = route_telegram_intent(
                            extraction, tenant_id, current_session=None
                        )
                        if log_id is not None:
                            persist_routing_decision(log_id, decision)
                        if decision.target == "p13_variants":
                            generate_variants_for_chat.apply_async(
                                args=[tenant_id, text_content[:1000], log_id]
                            )
                            return {"routed_to": "p13_variants", "p13_enqueued": True}
                        # reviewer_queue / flagged → Marker bereits gesetzt, kein Chat-Spam
                        return {"routed_to": decision.target}
                except Exception as exc:
                    logger.warning("p13 own-idea gate failed: %s", type(exc).__name__)
                    # Fail-open: Memory-Default
                return None  # Verhalten wie bisher: keine Session, kein Post → None

            from services.layer1_extraction import extract_intent_features
            from services.layer2_routing import persist_routing_decision, route_telegram_intent

            extraction = extract_intent_features(
                transcript=text_content,
                tenant_id=tenant_id,
                session_state="no_session",
                last_post_summary=last_post.summary,
            )
            decision = route_telegram_intent(extraction, tenant_id, last_post_id=last_post.id)
            if log_id is not None:
                persist_routing_decision(log_id, decision)
            if decision.target == "voice_feedback_api":
                try:
                    from tasks.post_feedback_task import regenerate_post_from_feedback

                    regenerate_post_from_feedback.apply_async(
                        args=[last_post.id, tenant_id, text_content, log_id]
                    )
                    return {"routed_to": "voice_feedback_api", "regen_enqueued": True}
                except Exception as exc:
                    logger.warning("feedback regen enqueue failed: %s", type(exc).__name__)
                    return {"routed_to": "voice_feedback_api", "regen_enqueued": False}
            if decision.target == "p13_variants":
                # #36 Gate 5 — P13-Zweig im last_post-Kontext
                try:
                    from tasks.p13_variants_task import generate_variants_for_chat

                    generate_variants_for_chat.apply_async(
                        args=[tenant_id, text_content[:1000], log_id]
                    )
                    return {"routed_to": "p13_variants", "p13_enqueued": True}
                except Exception as exc:
                    logger.warning("p13 variants enqueue failed: %s", type(exc).__name__)
                    return {"routed_to": "p13_variants", "p13_enqueued": False}
            # Andere Targets: Routing-Marker setzen, kein Chat-Spam
            return {"routed_to": decision.target}

        from services.layer1_extraction import extract_intent_features
        from services.layer2_routing import persist_routing_decision, route_telegram_intent

        extraction = extract_intent_features(
            transcript=text_content,
            tenant_id=tenant_id,
            session_state="active",
            current_question=getattr(session, "current_question", ""),
        )
        decision = route_telegram_intent(extraction, tenant_id, current_session=session)

        # #56: Routing-Marker VOR dem LLM-Call setzen (at-most-once für p08_response).
        # Fail-open: persist_routing_decision fängt intern alle Exceptions.
        # Nur p08_response ist CHECK-konform persistierbar (B11); für andere
        # Targets scheitert das UPDATE im Constraint still (fail-open eingebaut).
        if log_id is not None:
            persist_routing_decision(log_id, decision)

        routing_info: dict = {"routed_to": decision.target, "bot_session_id": str(session.id)}

        if decision.target == "p08_response":
            from services.p08_service import p08_response

            # #19: Roh-Transkript durchreichen → p08 persistiert es in
            # bot_session.messages[*].user_transcript für die Post-Generierung
            # (Schicht-3-Grenze bleibt in p08_response gewahrt).
            result = p08_response(
                decision.payload["session_id"],
                decision.payload["features"],
                raw_transcript=text_content,
            )
            routing_info["p08_next_action"] = result.next_action

            # #17 — Folgefrage / Abschluss-Nachricht an den Kunden zurücksenden.
            # Fail-open: Send-Fehler darf den Chunk-Return NICHT kaputtmachen.
            # E2: nur type(exc).__name__ loggen, nie str(exc).
            chat_id = _resolve_chat_id(tenant_id)
            if chat_id is not None and result.message:
                try:
                    from api.telegram import (  # Lazy-Import wie scheduler.py:104
                        _interview_cancel_keyboard,
                        _send_telegram_message,
                    )

                    # C5: Solange das Gespräch weiterläuft, hängt an der Frage ein
                    # sichtbarer Ausgang. An der Abschluss-Nachricht nicht — dann
                    # ist die Session ohnehin zu.
                    #
                    # ⚠️ Diese Annahme war bis 04.08.2026 FALSCH und der Grund,
                    # warum Louis eine Frage ohne Abbrechen-Knopf bekam: `is_closed`
                    # konnte vom Zähler gesetzt sein, während der Text vom LLM eine
                    # frische Frage war. Seither garantiert der Typ es —
                    # `is_closed` ist `outcome is CLOSED`, und CLOSED kann keinen
                    # Fragetext tragen (ResponseResult.__post_init__). Ein Angebot
                    # ist `OFFER`, hält die Session offen und behält den Ausgang.
                    if result.is_closed:
                        sent = _send_telegram_message(chat_id, result.message, tenant_id=tenant_id)
                    else:
                        sent = _send_telegram_message(
                            chat_id,
                            result.message,
                            tenant_id=tenant_id,
                            reply_markup=_interview_cancel_keyboard(),
                        )
                    routing_info["p08_message_sent"] = sent
                    if not sent:
                        logger.warning(
                            "telegram_task: p08-Folgefrage konnte nicht an chat …%s gesendet werden"
                            " (tenant=%s)",
                            str(chat_id)[-4:],
                            tenant_id,
                        )
                except Exception as exc:
                    logger.warning("p08 message send failed: %s", type(exc).__name__)
                    routing_info["p08_message_sent"] = False
            else:
                routing_info["p08_message_sent"] = False

            # #19 — Session-Close → Post-Generierung asynchron triggern.
            # Reihenfolge: erst Abschluss-Text (#17, oben), dann generierter
            # Post (zweite Nachricht, aus session_post_task). Nur ein ECHTER
            # active→closed-Übergang triggert (was_already_closed=False),
            # damit Spät-/Doppel-Events auf eine geschlossene Session P12 nicht
            # erneut feuern. Enqueue fail-open: ein Broker-/Enqueue-Fehler darf
            # den Routing-Return NICHT kaputtmachen. E2: nur Exception-Typ.
            if result.is_closed and not getattr(result, "was_already_closed", False):
                try:
                    from tasks.session_post_task import generate_post_from_session

                    generate_post_from_session.apply_async(
                        args=[str(decision.payload["session_id"]), tenant_id]
                    )
                    routing_info["post_generation_enqueued"] = True
                except Exception as exc:
                    logger.warning("post generation enqueue failed: %s", type(exc).__name__)
                    routing_info["post_generation_enqueued"] = False

        return routing_info
    except SoftTimeLimitExceeded:
        # Muss vor dem Exception-Katalog stehen: SoftTimeLimitExceeded erbt von
        # Exception und würde sonst hier als gewöhnlicher Routing-Fehler enden —
        # der Task liefe scheinbar normal weiter statt sich abwickeln zu lassen.
        raise
    except Exception as exc:
        # E2: nur Exception-Typ loggen, nie str(exc) — könnte Prompt-/PII-Fragmente tragen.
        logger.warning("inbound routing failed: %s", type(exc).__name__)
        return None


def _telegram_get_file(file_id: str, tenant_id: str) -> bytes | None:
    """Lädt Audio/Photo-Bytes vom Telegram-Server via per-Tenant-Bot-Token.

    Telegram-API: getFile(file_id) → file_path → GET file_path.
    Token wird NIEMALS geloggt (E2/D3).

    Args:
        file_id:   Telegram file_id aus dem Update-Payload.
        tenant_id: Tenant-ID zum Token-Lookup via get_tenant_bot_token.
    """
    from services.telegram_token_resolver import get_tenant_bot_token

    token = get_tenant_bot_token(tenant_id)
    if not token:
        logger.warning(
            "_telegram_get_file: kein aktiver Bot-Token für tenant %s — getFile skipped",
            tenant_id,
        )
        return None
    try:
        with httpx.Client(timeout=20) as client:
            r = client.get(f"{TELEGRAM_API_BASE}/bot{token}/getFile", params={"file_id": file_id})
            if r.status_code != 200:
                logger.warning("getFile %s → HTTP %s", file_id[:20], r.status_code)
                return None
            file_path = (r.json().get("result") or {}).get("file_path")
            if not file_path:
                logger.warning("getFile %s lieferte kein file_path", file_id[:20])
                return None
            r2 = client.get(f"{TELEGRAM_API_BASE}/file/bot{token}/{file_path}")
            if r2.status_code != 200:
                logger.warning("download %s → HTTP %s", file_path[:30], r2.status_code)
                return None
            return r2.content
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("Telegram-getFile-Network-Error: %s", type(exc).__name__)
        return None


# ── async helpers ───────────────────────────────────────────────────────


async def _store_chunk_async(
    tenant_id: str,
    source_type: str,
    content_text: str,
    log_id: str,
    metadata: dict,
) -> str | None:
    """Async-Wrapper: chunkt Text via chunker, persistiert alle Chunks.

    Returns die ID des ersten Chunks (fuer Rueckwaertskompatibilitaet).
    Bei mehreren Chunks werden prev/next-Links via store_chunks_multi gesetzt.
    """
    from services.chunker import chunk_text
    from services.embedding_service import store_chunk, store_chunks_multi
    from services.rls import tenant_session

    chunks = chunk_text(content_text, source_type)
    if not chunks:
        # Fallback: direkt speichern ohne Chunking (z.B. text zu kurz)
        # store_chunk wirft ValueError fuer leere Texte — defensiv zurueck
        logger.warning(
            "_store_chunk_async: chunker lieferte 0 Chunks fuer source_type=%s, len=%d — direkt speichern",
            source_type,
            len(content_text),
        )
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with tenant_session(SessionMaker, tenant_id) as db:
                return await store_chunk(
                    db=db,
                    tenant_id=tenant_id,
                    source_type=source_type,
                    content_text=content_text,
                    source_ref=f"telegram_message_log:{log_id}",
                    metadata=metadata,
                    classify=True,
                )
        finally:
            await engine.dispose()

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with tenant_session(SessionMaker, tenant_id) as db:
            ids = await store_chunks_multi(
                db,
                tenant_id=tenant_id,
                source_type=source_type,
                chunks=chunks,
                source_ref=f"telegram_message_log:{log_id}",
                base_metadata=metadata,
                classify=True,
            )
        return ids[0] if ids else None
    finally:
        await engine.dispose()


# ── celery task ─────────────────────────────────────────────────────────


def _dispatch_voice(task, log_id: str, tenant_id: str, payload: dict) -> dict:
    """Voice-Zweig samt Retry-Entscheidung.

    Bewusst eine gewöhnliche Funktion mit `task` als Parameter statt Code im Task-Rumpf:
    Ein Celery-Task mit `bind=True` ist ein Objekt, dessen `__call__` das echte `self`
    selbst einsetzt — ein von Hand übergebener Fake-Task landete als erstes Argument.
    So ist die Retry-Logik ohne Celery-Laufzeit prüfbar.
    """
    try:
        return _process_voice(log_id, tenant_id, payload)
    except TranscriptionUnavailable as exc:
        if task.request.retries < task.max_retries:
            # 30/60/120s — ein einzelner Nachschlag überlebt ein Ratenlimit selten.
            countdown = 30 * 2**task.request.retries
            if task.request.retries == 0:
                # Genau einmal ankündigen, nicht bei jedem Versuch.
                _notify_voice_user(tenant_id, payload, exc.user_message or _VOICE_MSG_BUSY)
            logger.warning(
                "voice vorübergehend gescheitert, Retry %d/%d in %ds: %s",
                task.request.retries + 1,
                task.max_retries,
                countdown,
                exc,
            )
            raise task.retry(exc=exc, countdown=countdown) from exc

        logger.error("voice: Retry-Vorrat erschöpft: %s", exc)
        _notify_voice_user(tenant_id, payload, _VOICE_MSG_GAVE_UP)
        return {"status": "error", "reason": "transcription_unavailable_exhausted"}
    except TranscriptionError as exc:
        # Der Nutzer wurde schon in _process_voice informiert — hier nicht doppeln.
        logger.warning("voice endgültig gescheitert: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}
    except Exception as exc:
        # Letzter Riegel. Alles, was hier ankommt, ist per Definition unerwartet —
        # sonst hätte es eine der beiden Klauseln oben getroffen. Ohne diesen Fang
        # stirbt der Task still und der Absender wartet auf eine Antwort, die nie kommt.
        logger.exception("voice: unerwarteter Fehler")
        _notify_voice_user(tenant_id, payload, _VOICE_MSG_GAVE_UP)
        _alert_admin_voice_failure(tenant_id, f"unerwartet: {exc!r}"[:200], "unexpected")
        return {"status": "error", "reason": "unexpected"}


# 1200s/1260s statt eines globalen Limits in celery_app.conf: Dieser Task bedient
# alle drei message_type-Zweige (voice/photo/text), und sowohl _process_voice als
# auch _process_text laufen am Ende durch _route_inbound_message in
# services/pipeline_llm.py, wo request_timeout = max(300, …) bei max_retries=3
# gilt — ein einzelner Routing-Call darf legitim bis zu 900s dauern (eingefroren
# in tests/test_explicit_choice_callbacks.py:302-311). Der Voice-Erfolgspfad
# durchläuft Transkription UND danach dieses Routing, also addieren sich:
#   ~40s  Telegram-Download   (zwei sequenzielle GETs, je timeout=20)
#   ~186s Transkription       (zwei Adapter in Kette, je 3 × 30s + 1s/2s Backoff = 93s)
#   ~900s Routing             (max(300, …) mit max_retries=3)
#   ------------------------
#   ~1126s realistischer Einzel-Worst-Case
#
# Seit P14 (services/p14_entry_service.py) gilt das nur noch fuer den
# _route_inbound_message-Zweig. _versuche_gespraechsstart laeuft VOR dem
# Routing und schliesst es bei Treffer aus (siehe _process_voice/_process_text)
# — P14 addiert sich also NICHT zu den ~900s Routing, sondern ersetzt sie in
# diesem Zweig durch einen eigenen, vergleichbar teuren Call:
#   P14 (Tier S2, max_tokens=2000): request_timeout = max(300, …) = 300s,
#   max_retries=3 → bis zu 3 × 300s + Backoff (1s + 2s) ≈ 903s.
#   ~40s Download + ~186s Transkription + ~903s P14 ≈ 1129s Einzel-Worst-Case
#   im _awaits_user_choice-Zweig. Vor P14 lag dieser Zweig ohne LLM-Call bei
#   ~226s und hatte ~975s Luft zu soft_time_limit=1200 — jetzt sind es ~70s.
#
# 1200s/1260s liegen knapp über diesem legitimen Worst-Case — kein enges Limit,
# sondern ein Riegel gegen einen echt hängenden Task. Die eigentliche Eindämmung
# des Transkriptions-Beins ist der 30s-httpx-Timeout in
# services/voice_transcription.py; dieses Limit greift nur, wenn trotzdem etwas
# hängen bleibt.
@celery_app.task(
    name="tasks.telegram_task.process_telegram_update",
    bind=True,
    max_retries=3,
    soft_time_limit=1200,
    time_limit=1260,
)
def process_telegram_update(self, log_id: str) -> dict:
    """Verarbeitet eine telegram_message_log-Zeile.

    Returns dict mit Statusinfo. Idempotent: wenn transcript_text
    schon gesetzt, wird kein erneuter Transcribe-Call gemacht — ein Retry
    kann deshalb keine Dopplung erzeugen.
    """
    row = _load_log_row(log_id)
    if row is None:
        logger.warning("telegram_task: log_id=%s nicht gefunden", log_id)
        return {"status": "skipped", "reason": "log_not_found"}

    if row["transcript_text"]:
        logger.info("telegram_task: log_id=%s schon transkribiert — skip", log_id)
        return {"status": "already_processed"}

    tenant_id = row["tenant_id"]
    payload = row["original_payload"]
    message_type = row["message_type"]

    if message_type == "voice":
        return _dispatch_voice(self, log_id, tenant_id, payload)
    elif message_type == "photo":
        return _process_photo(log_id, tenant_id, payload)
    else:
        return _process_text(log_id, tenant_id, payload)


# ── Voice-Fehlermeldungen (Spec §4.2) ───────────────────────────────────
# Produkttext, kein Debug-Output. Die Ursache steht drin, die Technik nicht:
# Ein Nutzer soll erfahren, was er tun kann, nicht welchen Statuscode der Router lieferte.
_VOICE_MSG_NO_FILE = "🎤 Ich konnte die Sprachnachricht nicht lesen — bitte schick sie noch einmal."
_VOICE_MSG_DOWNLOAD = (
    "🎤 Ich konnte die Sprachnachricht nicht laden — ich versuche es gleich noch einmal."
)
_VOICE_MSG_BUSY = (
    "🎤 Der Transkriptionsdienst ist gerade überlastet — ich versuche es gleich noch einmal."
)
_VOICE_MSG_TRANSCRIBE_FAILED = (
    "🎤 Ich konnte die Sprachnachricht nicht transkribieren — bitte schick sie noch einmal."
)
_VOICE_MSG_EMPTY = "🎤 Die Sprachnachricht kam bei mir leer an — bitte schick sie noch einmal."
# Transkript liegt vor, nur das Speichern ist gescheitert — eine der Meldungen oben
# würde etwas anderes behaupten, als tatsächlich passiert ist.
_VOICE_MSG_NOT_SAVED = (
    "🎤 Ich habe deine Sprachnachricht verstanden, konnte sie aber nicht speichern — "
    "bitte schick sie sicherheitshalber noch einmal."
)
# Wenn der Retry-Vorrat aufgebraucht ist: kein weiteres „gleich nochmal" versprechen.
_VOICE_MSG_GAVE_UP = (
    "🎤 Ich konnte deine Sprachnachricht leider nicht verarbeiten. Bitte schick sie noch einmal."
)

_VOICE_ALERT_REDIS_KEY = "voice-asr-alert"


def _notify_voice_user(tenant_id: str, payload: dict, message: str) -> bool:
    """Meldung an den Absender. Fail-open — eine misslungene Meldung darf nichts sprengen.

    Fehlt 'chat' im Payload, wird der Tenant-Chat aufgelöst; ohne beides bleibt nur der
    Betreiber-Alarm (der Nutzer ist dann schlicht nicht adressierbar).

    Die chat_id-Ermittlung sitzt bewusst mit im try: 'chat' kommt aus original_payload,
    einem unvalidierten DB-Feld. Ist 'chat' wahrheitswertig, aber kein Dict (z. B. ein
    kaputter String), würfe `.get("id")` sonst außerhalb jeder Absicherung — und würde
    hier die TranscriptionError/-Unavailable ersetzen, die der Nutzer eigentlich erfahren
    sollte. `if not chat_id: return False` bleibt aber ein eigener Zweig, kein except:
    „kein Chat ermittelbar" ist etwas anderes als „Senden fehlgeschlagen".
    """
    try:
        chat_id = (payload.get("chat") or {}).get("id") or _resolve_chat_id(tenant_id)
        if not chat_id:
            logger.warning("voice failure: kein chat_id ermittelbar (tenant=%s)", tenant_id)
            return False

        from api.telegram import _send_telegram_message

        return _send_telegram_message(int(chat_id), message, tenant_id=tenant_id)
    except Exception as exc:
        logger.warning("voice failure notice send failed: %s", type(exc).__name__)
        return False


def _alert_admin_voice_failure(tenant_id: str, reason: str, category: str) -> None:
    """Betreiber-Alarm, höchstens einmal pro UTC-Tag — entprellt pro Ursache UND Tenant.

    Grundmuster aus services/llm.py::_maybe_send_global_cap_alert, aber NICHT dessen
    globaler Key: dort ist die Kostengrenze eine einzige globale Größe, ein globaler
    Key also richtig. Hier sind es mehrere Ursachen über mehrere Tenants — ein
    gemeinsamer Key ließe einen Bedienfehler (z. B. eine Sprachnachricht ohne file_id)
    frühmorgens den einzigen Alarm-Platz des Tages verbrauchen, und ein echter Ausfall
    später am Tag verschwände spurlos dahinter. `category` ist bewusst ein Literal an
    der Aufrufstelle, nicht aus `reason` abgeleitet — der Fehlertext variiert (jeder
    Router-Body sieht anders aus) und würde damit gar nichts entprellen.
    Fail-open in jedem Fall.
    """
    try:
        if not settings.telegram_admin_chat_id:
            logger.warning(
                "_alert_admin_voice_failure: telegram_admin_chat_id not configured, skipping"
            )
            return

        import datetime as _dt

        import redis as _redis

        today = _dt.datetime.now(_dt.UTC).date().isoformat()
        r = _redis.from_url(settings.redis_url, decode_responses=True)
        try:
            was_set = r.set(
                f"{_VOICE_ALERT_REDIS_KEY}:{category}:{tenant_id}:{today}",
                "1",
                nx=True,
                ex=86400,
            )
        finally:
            r.close()
        if not was_set:
            return

        from api.telegram import _send_admin_telegram_message

        _send_admin_telegram_message(
            int(settings.telegram_admin_chat_id),
            f"⚠️ Sprachnachricht nicht verarbeitet (tenant={tenant_id}): {reason}",
        )
    except Exception as exc:
        logger.warning("voice admin alert failed (non-fatal): %s", exc)


def _process_voice(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Verarbeitet eine Sprachnachricht: Download, Transkription, Speichern, Routing.

    Raises:
        TranscriptionError: fehlende file_id, endgültig gescheiterte Transkription
            oder leeres Transkript — der Nutzer wurde vor dem Raise bereits benachrichtigt.
        TranscriptionUnavailable: Download- oder Transkriptionsfehler, die
            `_dispatch_voice` retryt. Der Nutzer wird erst dort benachrichtigt.
        SoftTimeLimitExceeded: reicht unverändert durch, statt in eines der obigen
            Ergebnisse verpackt zu werden — siehe FIX 2.

    Nur der Erfolgspfad (inkl. des Chunk-Speicher-Fehlers, der als
    ``{"status": "transcribed_no_chunk", ...}`` zurückkommt) liefert das
    annotierte ``dict`` regulär zurück.
    """
    voice_obj: dict = payload.get("voice") or {}
    file_id = voice_obj.get("file_id")
    duration = int(voice_obj.get("duration") or 0)
    mime_type = voice_obj.get("mime_type") or "audio/ogg"

    if not file_id:
        logger.warning("voice ohne file_id, log_id=%s", log_id)
        _notify_voice_user(tenant_id, payload, _VOICE_MSG_NO_FILE)
        _alert_admin_voice_failure(tenant_id, "voice ohne file_id", "no_file_id")
        raise TranscriptionError("voice ohne file_id")

    audio_bytes = _telegram_get_file(file_id, tenant_id)
    if not audio_bytes:
        # Bewusst vorübergehend: _telegram_get_file liefert auch bei endgültigen Ursachen
        # None. Ein endgültiger Fehler dreimal wiederholt kostet drei wirkungslose Aufrufe,
        # ein vorübergehender Fehler endgültig behandelt kostet die Nachricht.
        #
        # Der Nutzertext reist an der Ausnahme mit, statt hier gesendet zu werden: Bei drei
        # Retries würde der Absender sonst dreimal „ich versuche es gleich noch einmal"
        # lesen. Wann er ihn liest, entscheidet _dispatch_voice.
        _alert_admin_voice_failure(tenant_id, "Telegram-Download fehlgeschlagen", "download")
        raise TranscriptionUnavailable(
            "Telegram-Download fehlgeschlagen", user_message=_VOICE_MSG_DOWNLOAD
        )

    try:
        result: TranscriptionResult = transcribe_voice(
            audio_bytes,
            mime_type=mime_type,
            language_hint="de",
            tenant_id=tenant_id,
        )
    except TranscriptionUnavailable as exc:
        logger.warning("transcribe_voice vorübergehend fehlgeschlagen: %s", exc)
        _alert_admin_voice_failure(tenant_id, str(exc)[:200], "transient")
        if not exc.user_message:
            exc.user_message = _VOICE_MSG_BUSY
        raise
    except TranscriptionError as exc:
        logger.warning("transcribe_voice endgültig fehlgeschlagen: %s", exc)
        _notify_voice_user(tenant_id, payload, exc.user_message or _VOICE_MSG_TRANSCRIBE_FAILED)
        _alert_admin_voice_failure(tenant_id, str(exc)[:200], "terminal")
        raise

    transcript = (result.text or "").strip()
    if not transcript:
        _notify_voice_user(tenant_id, payload, _VOICE_MSG_EMPTY)
        _alert_admin_voice_failure(tenant_id, "leeres Transkript", "empty")
        raise TranscriptionError("leeres Transkript")

    _update_log_transcript(log_id, transcript, result.model_id or "unknown", result.confidence)

    channel = payload.get("_channel") or "telegram"
    source_type = "voice_whatsapp" if channel == "whatsapp" else "voice_telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "duration_sec": duration,
        "transcription_confidence": round(min(max(result.confidence, 0), 1), 2),
        "transcription_model": result.model_id,
        "channel": channel,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, source_type, transcript, log_id, chunk_metadata)
        )
    except SoftTimeLimitExceeded:
        # Muss vor dem Exception-Katalog stehen — siehe _route_inbound_message.
        raise
    except Exception as exc:
        logger.warning("store_voice_chunk failed: %s", exc)
        # Ohne diese beiden Zeilen hört der Absender nichts und der Betreiber
        # erfährt nichts — vier Zeilen unterhalb von Code, den dieser Branch
        # gerade umgeschrieben hat, um genau das nie wieder zuzulassen.
        _notify_voice_user(tenant_id, payload, _VOICE_MSG_NOT_SAVED)
        _alert_admin_voice_failure(tenant_id, str(exc)[:200], "chunk")
        return {"status": "transcribed_no_chunk", "reason": str(exc)[:120]}

    chat_id_voice = (payload.get("chat") or {}).get("id")
    result_dict = {
        "status": "ok",
        "transcript_chars": len(transcript),
        "memory_chunk_id": chunk_id,
        "source_type": source_type,
        "channel": channel,
    }

    # PR 2 — Weiche VOR dem Routing: greift sie, entscheidet der Nutzer per Button
    # und es läuft kein LLM-Rateschritt. Nur für Telegram: die Buttons sind ein
    # Inline-Keyboard, das der WhatsApp-Adapter nicht kennt.
    if channel == "telegram" and _awaits_user_choice(tenant_id, transcript):
        # Fallback auf den Tenant-Chat: fehlt „chat" im Payload, wäre die Nachricht
        # sonst ohne jede Reaktion zu Ende — der Zustand, den PR 2 beseitigt hat.
        target_chat = chat_id_voice or _resolve_chat_id(tenant_id)

        # P14 — eine Anweisung ist kein Inhalt. Greift der Zug nicht (oder faellt
        # er aus), bleibt es bei den zwei Buttons: dieselbe Weiche, sichtbarer
        # Ausgang statt Stille.
        gespraech = _versuche_gespraechsstart(tenant_id, transcript, log_id, target_chat)
        if gespraech is not None:
            result_dict.update(gespraech)
            return result_dict

        result_dict["routed_to"] = "awaiting_user_choice"
        result_dict["choice_prompt_sent"] = bool(target_chat) and _send_choice_prompt(
            tenant_id, target_chat, log_id, transcript, "🎤"
        )
        return result_dict

    # Bestätigung an den Nutzer senden
    if chat_id_voice and channel == "telegram":
        try:
            from api.telegram import _send_telegram_message

            _send_telegram_message(
                chat_id_voice,
                f"🎤 Gespeichert: {_quittungs_zitat(transcript)}",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("voice confirmation send failed: %s", type(exc).__name__)

    routing_info = _route_inbound_message(tenant_id, transcript, log_id=log_id)
    if routing_info:
        result_dict.update(routing_info)
    return result_dict


def _process_photo(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Photo-Pipeline (Welle 4): getFile → OCR (+Vision-Stub) → memory_chunk."""
    photos = payload.get("photo") or []
    if not photos:
        return {"status": "skipped", "reason": "no_photo_array"}
    # Telegram liefert Liste verschiedener Auflösungen — nimm die größte
    best = max(photos, key=lambda p: p.get("file_size") or 0)
    file_id = best.get("file_id")
    if not file_id:
        return {"status": "error", "reason": "no_file_id"}

    image_bytes = _telegram_get_file(file_id, tenant_id)
    if not image_bytes:
        return {"status": "error", "reason": "download_failed"}

    from services.photo_pipeline import PhotoProcessingError, process_photo

    caption = (payload.get("caption") or "").strip() or None
    try:
        result = asyncio.run(process_photo(image_bytes, hint=caption))
    except PhotoProcessingError as exc:
        logger.warning("photo pipeline fail: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}
    except Exception as exc:
        logger.warning("photo pipeline unexpected: %s", exc)
        return {"status": "error", "reason": "pipeline_exception"}

    content_text = result["content_text"]
    if caption:
        content_text = f"{caption}\n\n{content_text}"

    channel = payload.get("_channel") or "telegram"
    source_type = "photo_whatsapp" if channel == "whatsapp" else "photo_telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "file_size": best.get("file_size"),
        "width": best.get("width"),
        "height": best.get("height"),
        "ocr_chars": result.get("ocr_chars", 0),
        "ocr_lang": result.get("ocr_lang"),
        "has_description": bool(result.get("description")),
        "caption": caption,
        "channel": channel,
    }

    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, source_type, content_text, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_photo_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    return {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "ocr_chars": result.get("ocr_chars", 0),
        "source_type": source_type,
        "channel": channel,
    }


def _process_photo_stub(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Backwards-Compat-Wrapper, falls noch ein älterer Pfad ihn aufruft."""
    return _process_photo(log_id, tenant_id, payload)


def _process_text(log_id: str, tenant_id: str, payload: dict) -> dict:
    """Text-Nachrichten — speichern als manual_note (kein Wizard-Bridge in dieser Welle).

    Akzeptiert beide Payload-Formate:
    - Telegram:  message["text"] = "..."
    - WhatsApp:  message["text"] = {"body": "..."}
    """
    raw = payload.get("text")
    if isinstance(raw, dict):
        text_content = (raw.get("body") or "").strip()
    elif isinstance(raw, str):
        text_content = raw.strip()
    else:
        text_content = ""
    if not text_content:
        return {"status": "skipped", "reason": "empty_text"}
    if len(text_content) < MIN_TEXT_LEN and not hat_aktives_gespraech(tenant_id):
        # Zweites Kurztext-Gate. Seit 04.08.2026 an dieselbe Session-Bedingung
        # gekoppelt wie das erste in api/telegram.py — „ja" auf ein
        # Abschluss-Angebot muss beide passieren, sonst verschwindet die
        # Bestaetigung zwischen den beiden Filtern.
        #
        # #36 S4 Kurztext-Bypass: „2" als Varianten-Wahl hat len<10 und würde
        # hier normalerweise gestoppt. Wenn ein Pending-Marker existiert und
        # der Text ein gültiges Choice-Token ist, durchlassen.
        # Billig: 1 tenant-scoped SELECT nur wenn Pending-Marker vorhanden;
        # ohne Treffer → too_short wie bisher.
        try:
            from tasks.p13_variants_task import _try_p13_variant_choice

            choice_result = _try_p13_variant_choice(tenant_id, text_content)
            if choice_result and isinstance(choice_result, dict):
                return {"status": "ok", **choice_result}
        except Exception:
            pass  # fail-open: too_short wie bisher
        return {"status": "skipped", "reason": "too_short"}

    # channel-Erkennung: WhatsApp-Adapter schreibt _channel='whatsapp' ins payload
    channel = payload.get("_channel") or "telegram"
    chunk_metadata = {
        "telegram_message_id": payload.get("message_id") or payload.get("id"),
        "channel": channel,
    }
    try:
        chunk_id = asyncio.run(
            _store_chunk_async(tenant_id, "manual_note", text_content, log_id, chunk_metadata)
        )
    except Exception as exc:
        logger.warning("store_text_chunk failed: %s", exc)
        return {"status": "error", "reason": str(exc)[:120]}

    result_dict = {
        "status": "ok",
        "memory_chunk_id": chunk_id,
        "source_type": "manual_note",
        "channel": channel,
    }
    chat_id = (payload.get("chat") or {}).get("id")

    # PR 2 — dieselbe Weiche wie im Voice-Pfad (Louis, 30.07.: Text-Parität).
    if channel == "telegram" and _awaits_user_choice(tenant_id, text_content):
        target_chat = chat_id or _resolve_chat_id(tenant_id)

        gespraech = _versuche_gespraechsstart(tenant_id, text_content, log_id, target_chat)
        if gespraech is not None:
            result_dict.update(gespraech)
            return result_dict

        result_dict["routed_to"] = "awaiting_user_choice"
        result_dict["choice_prompt_sent"] = bool(target_chat) and _send_choice_prompt(
            tenant_id, target_chat, log_id, text_content, "📝"
        )
        return result_dict

    routing_info = _route_inbound_message(tenant_id, text_content, log_id=log_id)
    if routing_info:
        result_dict.update(routing_info)
    else:
        # Kein Routing-Gate hat gegriffen → freier „reinquatschen"-Text (E3/E5, W4c):
        # der Kunde erzählt etwas, ohne einen Post zu wollen. Das soll in seine
        # Persona einfließen → P17-Chat-Observer (async, HITL-Vorschläge, blockiert
        # den Chat-Flow nicht). Nur bei substanziellem Text (Filter im Task).
        try:
            from tasks.p17_chat_observer_task import observe_chat_text

            observe_chat_text.apply_async(
                args=[tenant_id, text_content, f"telegram:{log_id}"], queue="default"
            )
        except Exception:
            pass  # fail-open: Beobachtung ist Kür, kein Blocker

    # F4: kein Routing-Gate hat gegriffen (routing_info is None) ODER das Ziel
    # antwortet nicht selbst (truthy Dict, aber nicht in _ZIELE_MIT_EIGENER_ANTWORT)
    # → Memory-Default-Quittung senden, sonst endet die Nachricht in Stille.
    if (
        channel == "telegram"
        and chat_id
        and (routing_info is None or _braucht_sichtbare_quittung(routing_info))
    ):
        try:
            from api.telegram import _send_telegram_message

            _send_telegram_message(
                chat_id,
                "✅ Gespeichert im Gedächtnis.",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("text confirmation send failed: %s", type(exc).__name__)
    return result_dict
