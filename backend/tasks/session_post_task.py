"""Session-Close → Post-Generierung (Issue #19, [BLOCKER], M24 / Board 5.5).

Wird von tasks.telegram_task._route_inbound_message beim ECHTEN Session-Close
(active→closed) per Celery enqueued. Fährt P12→P12b aus den im bot_session
gesammelten Roh-Transkripten und sendet den fertigen Post als zweite Nachricht
in den Telegram-Chat des Tenants — „Kunde hat fertigen Text im Chat".

Datenfluss
----------
1. Idempotenz-Gate: existiert bereits ein content_piece für diese Session
   (content_metadata->>'bot_session_id'), → already_generated, kein zweiter Lauf.
2. Session laden (Tenant-Scope = E3-Mandantentrennung); status != 'closed' → skip.
3. Q/A-Paare aus messages[*] bauen (bot = Frage, user_transcript = Antwort).
   0 Paare (Alt-Session ohne Transkripte / leere Session) → skip (Kostenschutz).
4. Aktive Profile (voice/avatar) sync via services.canonical_profiles laden.
5. _run_p12_p12b_pipeline(tenant_id, idea_id=None, …) (idea_id nullable, B13).
6. Content-Piece markieren (bot_session_id) + _send_telegram_message(chat_id, post).

Fail-open & Schicht-3
---------------------
* Jeder Fehlerpfad gibt ein Status-Dict zurück, crasht NICHT (kein Telegram-
  Spam-Retry).
* Geflaggte Posts (Sensitive-Detector) gehen NICHT roh in den Chat — stattdessen
  Review-Hinweis (Review-Queue-Pfad von #83 bleibt intakt).
* Logs tragen NUR IDs/Typen, NIE Transkript-/Post-Fragmente (E2-Konvention).

Die Zusage (Blocker 04./05.08.2026)
-----------------------------------
Bevor dieser Task startet, hat der Bot dem Nutzer bereits einen Post ZUGESAGT:
``p08_service.CLOSE_MESSAGE`` — „Alles klar — ich schreibe ihn. Gleich hier im
Chat." Diese Zusage ist der Vertrag, den der Task einlösen muss.

Am 04.08.2026 hat er sie gebrochen, ohne ein Wort: die Pipeline warf, der Task
kehrte über ``pipeline_exception`` still zurück (belegt am überlebenden
Celery-Ergebnis in Redis, ``date_done`` 19:11:05.120755Z). Der Post lag als
Entwurf in der DB, Louis wartete auf eine Nachricht, die nie kam.

`_generate_post` hat ELF Ausgänge, und keiner sagte dem Nutzer etwas. Deshalb
liegt die Quittung NICHT an den einzelnen Ausgängen, sondern in einer Klammer,
die keiner von ihnen umgehen kann: `generate_post_from_session` ruft
`_ensure_user_notified` über JEDES Ergebnis. Ein zwölfter Ausgang ist damit
automatisch mitversorgt — die frühere Bauweise (Sorgfalt pro Zweig) hat genau
daran versagt.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Telegram-Hardlimit 4096 Zeichen — defensiv kappen.
_TELEGRAM_MAX_CHARS = 4000

# Bekannte Branchen-Keys (Quality-Gate-Schwellenwerte sind daran gebunden).
_KNOWN_BRANCHEN = frozenset({"handwerk", "recht", "finanzen"})

# Tolerantes Teilstring-Mapping: Schlüsselwort (lower) → Branchen-Key.
# Reihenfolge spielt keine Rolle (dict-Reihenfolge nur für Lesbarkeit).
_BRANCHE_KEYWORDS: list[tuple[str, str]] = [
    # Recht / Anwalt / Kanzlei / Steuer
    ("recht", "recht"),
    ("anwalt", "recht"),
    ("kanzlei", "recht"),
    ("notar", "recht"),
    ("jur", "recht"),  # juridisch, juristisch
    # Finanzen / Steuer / Versicherung / Berater
    ("finanz", "finanzen"),
    ("steuer", "finanzen"),
    ("versicher", "finanzen"),
    ("invest", "finanzen"),
    ("bank", "finanzen"),
    # Handwerk / Bau / Gewerk
    ("handwerk", "handwerk"),
    ("bau", "handwerk"),
    ("gewerk", "handwerk"),
    ("installat", "handwerk"),  # Installation, Installateur
    ("elektriker", "handwerk"),
    ("sanitär", "handwerk"),
]


def _resolve_branche(tenant_id: str) -> str:
    """Löst den Branchen-Key für den Quality-Gate auf.

    Lädt customer_context-Profil, extrahiert ``branche`` und normalisiert
    auf einen bekannten Branchen-Key ("handwerk" | "recht" | "finanzen").
    Alles unbekannte / leere / fehlende → "_generic".

    fail-open: jede Exception → "_generic" (darf den Versandpfad nie stören).
    """
    try:
        from services.canonical_profiles import load_active_profile

        payload, _ = load_active_profile("customer_context", tenant_id)
        raw = payload.get("branche") if isinstance(payload, dict) else None

        # branche kann str, list, dict oder None sein — str-Normalisierung
        if isinstance(raw, list):
            # nimm erstes nicht-leeres Element
            raw = next((x for x in raw if isinstance(x, str) and x.strip()), None)
        elif isinstance(raw, dict):
            # z.B. {"name": "Handwerk"} → wert aus "name" oder erstem value
            raw = raw.get("name") or (next(iter(raw.values()), None) if raw else None)

        if not isinstance(raw, str) or not raw.strip():
            return "_generic"

        normalized = raw.strip().lower()

        # Exakter Treffer auf bekannten Key
        if normalized in _KNOWN_BRANCHEN:
            return normalized

        # Toleranter Teilstring-Match (Reihenfolge wie in _BRANCHE_KEYWORDS)
        for keyword, branche_key in _BRANCHE_KEYWORDS:
            if keyword in normalized:
                return branche_key

        return "_generic"

    except Exception as exc:
        logger.debug(
            "session_post_task: _resolve_branche failed — falling back to _generic: %s",
            type(exc).__name__,
        )
        return "_generic"


def _build_qa_pairs(messages: list) -> list[dict]:
    """Baut Q/A-Paare aus bot_session.messages für den P12-Input.

    ⚠️ Ein Eintrag trägt Züge aus ZWEI Runden:

        messages[i]["user_transcript"] = die Antwort, die Runde i auslöste
        messages[i]["bot"]             = die daraus erzeugte NEUE Frage

    Der Nutzertext ist also ÄLTER als der Bot-Text daneben; die Antwort gehört
    an die Frage des VORGÄNGER-Eintrags. Bis zum 06.08.2026 paarte diese
    Funktion beide Felder desselben Eintrags — Frage und Folge vertauscht.

    An Louis' Session 5379b589 nachgemessen ging so sein Einspruch „Ich habe
    doch gerade erklärt, welches Problem wir gelöst haben" als Antwort auf „Wie
    hat der Kunde seine Kontakte denn vorher verwaltet?" in P12, und das
    Abschluss-Angebot („Soll ich ihn schreiben?") wurde als Interviewfrage
    behandelt. Dieselbe Verschiebung saß in `services/p08_service.py`
    (`_get_recent_messages`) und war dort die Ursache für „er versteht meine
    Eingabe erst um +1 Antwort verzögert".

    Einträge ohne Transkript (z.B. der Opener) liefern kein Paar — wohl aber die
    Frage für das nächste. Format wie api.ideas._run_p12_p12b_pipeline erwartet.
    """
    pairs: list[dict] = []
    if not isinstance(messages, list):
        return pairs
    for i, entry in enumerate(messages):
        if not isinstance(entry, dict):
            continue
        answer = (entry.get("user_transcript") or "").strip()
        if not answer:
            continue
        # Die Frage steht im Eintrag DAVOR. Fehlt der (nur bei kaputten Daten —
        # der Opener hat nie ein Transkript), lieber eine leere Frage als eine
        # verschluckte Antwort.
        vorgaenger = messages[i - 1] if i > 0 and isinstance(messages[i - 1], dict) else {}
        question = (vorgaenger.get("bot") or "").strip()
        pairs.append({"question_text": question, "answer_text": answer})
    return pairs


# Rückfall-Texte für den Fall, dass der zugesagte Post nicht im Chat landet.
# Zwei Lagen, weil der Nutzer zwei verschiedene Dinge wissen muss: liegt der
# Post irgendwo (dann hol ihn dir), oder gibt es ihn gar nicht (dann probier's
# nochmal). Ein einziger Allzweck-Satz würde im ersten Fall den fertigen Post
# verschweigen. Der Bot duzt (Entscheidung Louis, 05.08.2026).
_FALLBACK_ENTWURF_LIEGT_BEREIT = (
    "Dein Post ist fertig — ich konnte ihn hier im Chat aber nicht zustellen. "
    "Du findest ihn im Dashboard unter „Entwürfe“."
)
_FALLBACK_KEIN_POST = (
    "Beim Schreiben ist etwas schiefgegangen — ich hab den Post nicht fertig "
    "bekommen. Magst du es gleich nochmal versuchen?"
)


def _ensure_user_notified(session_id: str, tenant_id: str, result: dict) -> dict:
    """Löst die Zusage aus CLOSE_MESSAGE ein — oder nimmt sie zurück.

    Stempelt ``user_notified`` in JEDES Ergebnis:
      True  – der Nutzer hat eine Nachricht in der Hand (den Post selbst, den
              Review-Hinweis oder einen der Rückfall-Texte) ODER es war gar
              keine Zusage offen (``already_generated``: der frühere Lauf hat
              geliefert).
      False – wir schulden eine Nachricht und konnten sie NICHT zustellen.
              Das ist der einzige Zustand, in dem der Nutzer im Dunkeln steht;
              er wird auf ERROR geloggt, damit er sichtbar bleibt.

    Fail-open wie der ganze Task: diese Funktion wirft nie. Sie ist die letzte
    Instanz vor dem Schweigen und darf nicht selbst zur Fehlerquelle werden.
    """
    try:
        # Der Post (oder der Review-Hinweis) ist raus — Zusage eingelöst.
        if result.get("sent") is True:
            result["user_notified"] = True
            return result

        # Zweiter Enqueue derselben Session: der ERSTE Lauf hat geliefert.
        # Hier zu schreiben hieße, dem Nutzer dieselbe Sache zweimal zu sagen.
        if result.get("status") == "already_generated":
            result["user_notified"] = True
            return result

        # Ab hier ist eine Zusage offen. status == "ok" heißt: der Post
        # existiert (er scheiterte erst am Versand) — dann darf der Text ihn
        # nicht totschweigen. Alles andere heißt: es gibt keinen Post.
        text_msg = (
            _FALLBACK_ENTWURF_LIEGT_BEREIT if result.get("status") == "ok" else _FALLBACK_KEIN_POST
        )

        chat_id = _resolve_chat_id(tenant_id)
        if chat_id is None:
            # Kein Kanal — wir KÖNNEN nicht reden. Nicht beschönigen.
            logger.error(
                "session_post_task: Zusage offen, aber kein aktiver Chat-Link "
                "(tenant=%s session=%s reason=%s) — Nutzer bleibt ohne Antwort",
                tenant_id,
                session_id,
                result.get("reason"),
            )
            result["user_notified"] = False
            return result

        from api.telegram import _send_telegram_message

        sent = _send_telegram_message(chat_id, text_msg, tenant_id=tenant_id)
        result["user_notified"] = bool(sent)
        if not sent:
            logger.error(
                "session_post_task: Rückfall-Nachricht nicht zustellbar "
                "(tenant=%s session=%s reason=%s) — Nutzer bleibt ohne Antwort",
                tenant_id,
                session_id,
                result.get("reason"),
            )
        else:
            logger.info(
                "session_post_task: Zusage per Rückfall eingelöst " "(session=%s reason=%s)",
                session_id,
                result.get("reason"),
            )
        return result
    except Exception as exc:
        # E2: nur der Typ, nie str(exc) — Exception-Texte tragen Post-Fragmente.
        logger.error(
            "session_post_task: Quittung selbst fehlgeschlagen " "(tenant=%s session=%s): %s",
            tenant_id,
            session_id,
            type(exc).__name__,
        )
        result["user_notified"] = False
        return result


@celery_app.task(
    name="tasks.session_post_task.generate_post_from_session",
    bind=True,
    max_retries=1,
)
def generate_post_from_session(self, session_id: str, tenant_id: str) -> dict:
    """Generiert beim Session-Close einen Post und sendet ihn in den Chat.

    Dünne Klammer um `_generate_post`: sie garantiert, dass der Nutzer nach
    JEDEM Ausgang eine Antwort bekommt (siehe Modul-Docstring, „Die Zusage").
    Die eigentliche Arbeit — und alle elf Ausgänge — stehen in `_generate_post`.

    Args:
        session_id: bot_session.id der geschlossenen Session.
        tenant_id:  Tenant (für E3-Scope + chat_id-Auflösung).

    Returns ein Status-Dict (für Tests/Observability), immer inklusive
    ``user_notified``. Fail-open: keine Exception verlässt diese Funktion.
    """
    try:
        result = _generate_post(session_id, tenant_id)
    except Exception as exc:
        # _generate_post ist selbst fail-open; das hier ist der Gürtel zum
        # Hosenträger. Ohne ihn würde ein Fehler im Task-Rumpf den Nutzer
        # wieder stumm zurücklassen — genau der Blocker vom 04.08.2026.
        logger.error(
            "session_post_task: Task-Rumpf warf (session=%s): %s",
            session_id,
            type(exc).__name__,
        )
        result = {
            "status": "error",
            "reason": "task_body_exception",
            "exception": type(exc).__name__,
        }
    return _ensure_user_notified(session_id, tenant_id, result)


def _generate_post(session_id: str, tenant_id: str) -> dict:
    """Erzeugt den Post und versucht die Zustellung. Sagt dem Nutzer NICHTS.

    Die Quittung an den Nutzer hängt bewusst NICHT hier, sondern in
    `_ensure_user_notified` — siehe Modul-Docstring.
    """
    # 1. Idempotenz-Gate (zuerst!) — existiert schon ein Piece für diese Session?
    try:
        with sync_session_factory() as db:
            existing = db.execute(
                text(
                    "SELECT 1 FROM content_pieces "
                    "WHERE tenant_id = :tid "
                    "      AND content_metadata->>'bot_session_id' = :sid LIMIT 1"
                ),
                {"tid": tenant_id, "sid": session_id},
            ).fetchone()
        if existing is not None:
            logger.info("session_post_task: session=%s already has a post — skip", session_id)
            return {"status": "already_generated"}
    except Exception as exc:
        # error statt warning (Review #128): dieser Task war vor PR #128 nie
        # in conf.include und lief nie in Produktion — ohne ERROR-Level bleibt
        # ein Ausfall unbemerkt (Sentry greift erst ab ERROR, sentry_config.py).
        logger.error("session_post_task: idempotency gate failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "idempotency_gate_failed"}

    # 2. Session laden (Tenant-Scope im WHERE = E3-Mandantentrennung)
    #    Bug-Fix #36/§2.3: topic_idea_id mitladen (vorher SELECT nur messages,status,mode).
    #    topic_idea_id ist für Steering-Keys (_chosen_hook/_chosen_outline) nötig (Bug c).
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text(
                    "SELECT messages, status, mode, topic_idea_id FROM bot_session "
                    "WHERE id = :id AND tenant_id = :tid LIMIT 1"
                ),
                {"id": session_id, "tid": tenant_id},
            ).fetchone()
    except Exception as exc:
        logger.error("session_post_task: session load failed: %s", type(exc).__name__)
        return {"status": "error", "reason": "session_load_failed"}

    if row is None:
        return {"status": "skipped", "reason": "session_not_found"}

    messages_raw, status, _mode = row[0], row[1], row[2]
    # Check status before accessing optional 4th column (topic_idea_id)
    if status != "closed":
        return {"status": "skipped", "reason": "session_not_closed"}
    # Bug-Fix #36/§2.3: topic_idea_id aus der Session lesen (4. Spalte im SELECT)
    topic_idea_id = str(row[3]) if len(row) > 3 and row[3] is not None else None

    messages_list = (
        json.loads(messages_raw) if isinstance(messages_raw, str) else (messages_raw or [])
    )

    # 3. Q/A-Paare bauen — 0 Paare → skip (Alt-Session ohne Transkripte / leer)
    answers_list = _build_qa_pairs(messages_list)
    if not answers_list:
        logger.info("session_post_task: session=%s has no answer transcripts — skip", session_id)
        return {"status": "skipped", "reason": "no_answers"}

    # 4. Aktive Profile (voice/avatar) sync laden (Fassade, Muster p12_task)
    voice_payload: dict = {}
    avatar_payload: dict = {}
    try:
        from services.canonical_profiles import load_active_profiles

        profiles = load_active_profiles(tenant_id)
        voice_payload = profiles.get("voice_profile", {}).get("payload") or {}
        avatar_payload = profiles.get("audience_avatar", {}).get("payload") or {}
    except Exception as exc:
        logger.warning(
            "session_post_task: profile load failed (continuing empty): %s",
            type(exc).__name__,
        )

    # 5. P12→P12b fahren.
    #    Bug-Fix #36/§2.3 (Bug c): wenn topic_idea_id gesetzt (targeted-Session via P13),
    #    die gewählte Variante als Steering-Keys injizieren
    #    (_chosen_hook / _chosen_outline, Muster api/ideas.py:1496-1499).
    #    P12 packt answers 1:1 in den Prompt-Kontext (p12_task.py:377-383).
    #    Lineage Idee→Post steht dann durchgängig (content_pieces.idea_id-FK).
    effective_idea_id = None
    if topic_idea_id:
        effective_idea_id = topic_idea_id
        try:
            with sync_session_factory() as db:
                idea_row = db.execute(
                    text(
                        "SELECT hook_suggestion, source_context->>'body_outline' AS body_outline "
                        "FROM content_ideas "
                        "WHERE id = CAST(:id AS uuid) AND tenant_id = :tid LIMIT 1"
                    ),
                    {"id": topic_idea_id, "tid": tenant_id},
                ).fetchone()
            if idea_row:
                chosen_hook = idea_row[0] or ""
                chosen_outline = idea_row[1] or ""
                if chosen_hook:
                    answers_list = [
                        {"question_text": "_chosen_hook", "answer_text": chosen_hook},
                        *answers_list,
                    ]
                if chosen_outline:
                    answers_list = [
                        {"question_text": "_chosen_outline", "answer_text": chosen_outline},
                        *answers_list,
                    ]
        except Exception as exc:
            logger.warning(
                "session_post_task: steering key load failed (continuing): %s",
                type(exc).__name__,
            )

    # Lazy-Import wie tasks.backtest_task (vermeidet FastAPI-Importlast/Zyklus im Worker).
    try:
        from api.ideas import _run_p12_p12b_pipeline

        pipeline_result = _run_p12_p12b_pipeline(
            tenant_id, effective_idea_id, answers_list, voice_payload, avatar_payload
        )
    except Exception as exc:
        # Der Typ gehört ins ERGEBNIS, nicht nur ins Log. Grund (Blocker
        # 04.08.2026): der Lauf hinterließ nur `reason='pipeline_exception'`;
        # welche Exception es war, ließ sich nachher NICHT mehr feststellen —
        # die Worker-Logs waren durch den nächsten Deploy (--force-recreate)
        # weg, das Celery-Ergebnis in Redis trug den Typ nicht.
        # KEIN exc_info/str(exc): p12 packt bei Parse-Fehlern den halben Post
        # in die Exception-Message (E2 — Logs tragen nur IDs/Typen).
        logger.error(
            "session_post_task: pipeline raised (session=%s): %s",
            session_id,
            type(exc).__name__,
        )
        return {
            "status": "error",
            "reason": "pipeline_exception",
            "exception": type(exc).__name__,
        }

    if not isinstance(pipeline_result, dict) or pipeline_result.get("status") != "ok":
        reason = (
            pipeline_result.get("reason") or pipeline_result.get("status")
            if isinstance(pipeline_result, dict)
            else "unknown"
        )
        logger.error("session_post_task: pipeline not ok (reason=%s)", reason)
        return {"status": "error", "reason": reason}

    final_post = pipeline_result.get("final_post") or ""
    if not final_post:
        logger.error("session_post_task: pipeline returned ok but final_post was empty")
        return {"status": "error", "reason": "empty_post"}

    p12_run_id = pipeline_result.get("p12_run_id")
    flagged = bool(pipeline_result.get("flagged_for_review"))

    # 6. Content-Piece markieren (bot_session_id) + P12b-Text übernehmen.
    #    Piece über p12_run_id finden (P12 hat es bereits angelegt). Fail-open.
    #    RETURNING id fängt die content_pieces.id für das Action-Keyboard (Schritt 7) —
    #    p12_run_id is None / kein Treffer → content_id bleibt None → Send ohne Keyboard.
    content_id: str | None = None
    try:
        with sync_session_factory() as db:
            if p12_run_id:
                _row = db.execute(
                    text(
                        "UPDATE content_pieces SET "
                        "content_text = :txt, "
                        "content_metadata = content_metadata || CAST(:meta AS jsonb) "
                        "WHERE tenant_id = :tid "
                        "      AND content_metadata->>'p12_run_id' = :rid "
                        "RETURNING id"
                    ),
                    {
                        "txt": final_post,
                        "meta": json.dumps(
                            {"bot_session_id": session_id, "source": "bot_session_close"}
                        ),
                        "tid": tenant_id,
                        "rid": p12_run_id,
                    },
                ).fetchone()
                db.commit()
                content_id = str(_row[0]) if _row else None
    except Exception as exc:
        logger.warning("session_post_task: piece marker update failed: %s", type(exc).__name__)

    # 6b. Quality-Gate — Final-Gate vor Versand (#38 Chunk 3, #81 branche-Auflösung).
    #
    #     branche: _resolve_branche(tenant_id) lädt customer_context-Profil und
    #     normalisiert auf einen bekannten Key ("handwerk"|"recht"|"finanzen");
    #     Fallback "_generic" bei Fehler/unbekanntem Wert (fail-open).
    #
    #     Shadow-Mode (quality_gate_enforce=False, DEFAULT):
    #       Gate läuft immer, Telemetrie wird geloggt, Versandverhalten UNVERÄNDERT.
    #     Enforce-Mode (quality_gate_enforce=True):
    #       not passed → Review-Queue-Pfad (wie geflaggt); passed → normal.
    #     fail-open: jede Exception im Gate → Lauf weiter wie bisher, nie blockieren.
    _gate_info: dict = {"score": None, "passed": None, "enforced": False}
    try:
        from config import settings as _settings
        from services.quality_gate_stub import quality_gate_check as _qg_check

        _branche = _resolve_branche(tenant_id)
        _gate_result = _qg_check(final_post, _branche)
        _gate_enforce = bool(getattr(_settings, "quality_gate_enforce", False))

        logger.info(
            "session_post_task: quality_gate score=%.1f passed=%s violations=%s "
            "threshold=%.1f branche=%s enforce=%s (session=%s)",
            _gate_result["score"],
            _gate_result["passed"],
            _gate_result["violations"],
            _gate_result["threshold"],
            _gate_result["branche"],
            _gate_enforce,
            session_id,
        )

        _gate_info = {
            "score": _gate_result["score"],
            "passed": _gate_result["passed"],
            "enforced": _gate_enforce,
        }

        # Enforce-Mode: schlechter Post → in Review-Queue-Pfad routen (wie geflaggt)
        if _gate_enforce and not _gate_result["passed"]:
            flagged = True
    except Exception as exc:
        # fail-open: Gate-Fehler darf NIEMALS den Versandpfad blockieren
        logger.warning(
            "session_post_task: quality_gate raised — fail-open (session=%s): %s",
            session_id,
            type(exc).__name__,
        )

    # 7. Post in den Chat. Geflaggt → NICHT roh senden (Review-Queue-Pfad #83).
    chat_id = _resolve_chat_id(tenant_id)
    if chat_id is None:
        # ERROR, nicht INFO: eine offene Zusage ohne Kanal ist ein Ausfall,
        # kein Betriebszustand. Auf INFO war dieser Ausgang faktisch unsichtbar.
        logger.error(
            "session_post_task: kein aktiver Chat-Link (tenant=%s session=%s) — "
            "Post gespeichert, nicht gesendet",
            tenant_id,
            session_id,
        )
        return {
            "status": "ok",
            "sent": False,
            "reason": "no_chat_link",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
            "quality_gate": _gate_info,
        }

    try:
        from api.telegram import _send_telegram_message

        if flagged:
            sent = _send_telegram_message(
                chat_id,
                "Dein Post ist fertig, wartet aber noch auf eine kurze Review.",
                tenant_id=tenant_id,
            )
            sent_kind = "review_notice"
        else:
            from api.telegram import _draft_action_keyboard

            _markup = _draft_action_keyboard(content_id) if content_id else None
            sent = _send_telegram_message(
                chat_id,
                final_post[:_TELEGRAM_MAX_CHARS],
                tenant_id=tenant_id,
                reply_markup=_markup,
            )
            sent_kind = "post"
    except Exception as exc:
        logger.error("session_post_task: telegram send failed: %s", type(exc).__name__)
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_failed",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
            "quality_gate": _gate_info,
        }

    if not sent:
        logger.error(
            "session_post_task: Post/Folgefrage konnte nicht an chat …%s gesendet werden"
            " (tenant=%s session=%s kind=%s) — _send_telegram_message returned False",
            str(chat_id)[-4:],
            tenant_id,
            session_id,
            sent_kind,
        )
        return {
            "status": "ok",
            "sent": False,
            "reason": "send_returned_false",
            "flagged_for_review": flagged,
            "p12_run_id": p12_run_id,
            "quality_gate": _gate_info,
        }

    logger.info(
        "session_post_task: post delivered (session=%s kind=%s flagged=%s)",
        session_id,
        sent_kind,
        flagged,
    )
    return {
        "status": "ok",
        "sent": True,
        "sent_kind": sent_kind,
        "flagged_for_review": flagged,
        "p12_run_id": p12_run_id,
        "quality_gate": _gate_info,
    }


def _resolve_chat_id(tenant_id: str) -> int | None:
    """Lookup active Telegram chat_id for a tenant (wiederverwendet #17-Helfer).

    Lazy-Import aus tasks.telegram_task, damit dieses Task-Modul keine
    Modul-Level-Abhängigkeit auf telegram_task (httpx/voice_transcription)
    aufbaut. Fail-open: None bei Fehler / kein aktiver Link.
    """
    try:
        from tasks.telegram_task import _resolve_chat_id as _resolve

        return _resolve(tenant_id)
    except Exception as exc:
        logger.warning("session_post_task: chat_id resolve failed: %s", type(exc).__name__)
        return None
