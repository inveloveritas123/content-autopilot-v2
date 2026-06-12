"""
tasks/p03_voice_fallback.py — Voice-Fallback für P03 (Issue #40).

Wenn P03 keine echte Voice-Quelle hat (kein Transkript, keine written_texts,
keine LinkedIn-Posts), wird statt leerer Defaults ein Fallback-Voice-Profil
aus dem vorhandenen Kunden-Kontext + Avatar (Zielgruppe) generiert.

Architektur:
  - _has_voice_source()         — Trigger-Check (rein funktional, testbar)
  - generate_voice_fallback()   — LLM-Aufruf + Payload-Aufbau (Seam-injizierbar)
  - run_p03_voice_fallback()    — Orchestrierung + DB-Write (aufgerufen aus p03_task.py)
  - _load_context_and_avatar()  — DB-Lesezugriff (mockable)

Provenance:
  - source = 'voice_fallback'   (DB-Spalte tenant_voice_profile.source)
  - _meta.is_fallback = True
  - _meta.fallback_source = 'voice_fallback'
  Damit ist das Profil für P12/Fassade wie ein reguläres Voice-Profil lesbar,
  aber als Fallback erkennbar (für späteres Override durch echte Voice-Quelle / P17-Drift).

Scope-Grenze:
  - KEINE echte Web-Recherche (Beta: LLM-Ableitung aus Kontext+Avatar reicht).
  - Web-Recherche-Integration als TODO → Folge-Issue.
  - KEINE Schema-Migration.

E2-Compliance:
  - Kein PII (tenant_id) in Warn-/Error-Logs — nur Präfix (erste 8 Zeichen).
  - Kein roher Kontext/Avatar-Inhalt in Logs.

Fail-open:
  Schlägt die Generierung fehl (LLM-Error, JSON-Parse-Error), gibt
  run_p03_voice_fallback() None zurück und der Aufrufer (p03_task.run_p03) fällt
  auf das bisherige Verhalten (leere Defaults) zurück — kein Crash.
"""

from __future__ import annotations  # Python 3.9-Kompatibilität: str | None Syntax

import json
import logging
import uuid

logger = logging.getLogger("tasks.p03_voice_fallback")


# ---------------------------------------------------------------------------
# Modul-Level-Referenzen für Patchbarkeit in Tests (werden lazy befüllt).
# Jede Funktion die diese nutzt MUSS über den Modul-Scope zugreifen (nicht
# als lokale Variable), damit patch.object(vf, "sync_session_factory", ...)
# die richtige Referenz ersetzt.
# ---------------------------------------------------------------------------

def _lazy_sync_session_factory():
    """Lazy-Wrapper um sync_session_factory — patchbar über vf.sync_session_factory."""
    from models.base import sync_session_factory
    return sync_session_factory()


def _lazy_call_pipeline_llm(**kwargs):
    """Lazy-Wrapper um call_pipeline_llm — patchbar über vf.call_pipeline_llm."""
    from services.pipeline_llm import call_pipeline_llm
    return call_pipeline_llm(**kwargs)


def _lazy_finalize_canonical(prompt_key, payload, meta=None):
    """Lazy-Wrapper um finalize_canonical — patchbar über vf.finalize_canonical."""
    from services.schema_transformer import finalize_canonical
    return finalize_canonical(prompt_key, payload, meta=meta)


def _lazy_build_canonical_meta(*args, **kwargs):
    """Lazy-Wrapper um build_canonical_meta — patchbar über vf.build_canonical_meta."""
    from services.schema_transformer import build_canonical_meta
    return build_canonical_meta(*args, **kwargs)


def _lazy_now_iso() -> str:
    """Lazy-Wrapper um now_iso aus canonical_wiring — patchbar über vf.now_iso."""
    from tasks.canonical_wiring import now_iso
    return now_iso()


# Modul-Level-Aliase (werden von Tests via patch.object ersetzt)
sync_session_factory = _lazy_sync_session_factory
call_pipeline_llm = _lazy_call_pipeline_llm
finalize_canonical = _lazy_finalize_canonical
build_canonical_meta = _lazy_build_canonical_meta
now_iso = _lazy_now_iso

# ---------------------------------------------------------------------------
# Interne Hilfsfunktion: Trigger-Check
# ---------------------------------------------------------------------------


def _has_voice_source(
    transcript: str | None,
    written_texts: list | None,
    linkedin_posts: list | None,
) -> bool:
    """Gibt True zurück, wenn mindestens eine echte Voice-Quelle vorhanden ist.

    Echte Voice-Quellen:
      - transcript: nicht-leerer, nicht-nur-Whitespace-String
      - written_texts: Liste mit mindestens einem nicht-nur-Whitespace-Eintrag
      - linkedin_posts: Liste mit mindestens einem Eintrag

    Alles andere (None, [], nur Whitespace) → False → Fallback wird ausgelöst.
    """
    # Transkript vorhanden?
    if transcript and transcript.strip():
        return True

    # Geschriebene Texte vorhanden (mindestens ein nicht-leerer Eintrag)?
    if written_texts:
        if any(isinstance(t, str) and t.strip() for t in written_texts):
            return True

    # LinkedIn-Posts vorhanden?
    if linkedin_posts:
        return True

    return False


# ---------------------------------------------------------------------------
# DB-Lesezugriff: Kontext + Avatar laden
# ---------------------------------------------------------------------------


def _load_context_and_avatar(
    tenant_id: str,
    project_id: str | None = None,
) -> tuple[dict, dict]:
    """Lädt den aktiven customer_context und audience_avatar aus der DB.

    Gibt ({}, {}) zurück wenn keine Rows vorhanden (fail-open).
    Importiert canonical_profiles lazy um den Kern dep-frei testbar zu halten.
    """
    try:
        from services.canonical_profiles import load_active_profile

        customer_context, _ = load_active_profile(
            "customer_context", tenant_id, project_id=project_id
        )
        audience_avatar, _ = load_active_profile(
            "audience_avatar", tenant_id, project_id=project_id
        )
        return customer_context or {}, audience_avatar or {}
    except Exception as exc:
        tid_prefix = str(tenant_id)[:8]
        logger.warning(
            "[P03-Fallback] Kontext/Avatar-Laden fehlgeschlagen für tenant=%.8s: %s",
            tid_prefix,
            type(exc).__name__,
        )
        return {}, {}


# ---------------------------------------------------------------------------
# Kern-Funktion: Fallback-Voice-Profil generieren
# ---------------------------------------------------------------------------

_FALLBACK_SYSTEM_PROMPT = """Du bist ein Markenstrategie-Experte. Deine Aufgabe ist es,
basierend auf dem Unternehmenskontext und der Zielgruppe eines Unternehmers
einen idealen Ton und ein Voice-Profil abzuleiten.

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt. Kein Markdown, keine Erklärungen.

Das JSON-Objekt soll die Kern-Dimensionen einer Markenstimme enthalten, zum Beispiel:
- sprache: Beschreibung des Sprachstils (z.B. "klar und direkt")
- ton: Emotionaler Ton (z.B. "herzlich und motivierend")
- kommunikationsstil: Wie kommuniziert die Marke (z.B. "persönlich, auf Augenhöhe")
- werte: 3-5 Kernwerte der Marke
- zielgruppen_ansprache: Wie wird die Zielgruppe direkt angesprochen
- typische_formulierungen: 3-5 typische Phrasen oder Formulierungsmuster
- zu_vermeiden: Was der Ton explizit vermeidet

Wichtig: Dies ist ein abgeleitetes Profil (kein echtes Voice-Analyse-Ergebnis).
Markiere das im JSON NICHT — die Provenance wird separat verwaltet."""

_FALLBACK_USER_TEMPLATE = """Bitte leite ein Voice-Profil aus folgendem Unternehmenskontext ab:

<unternehmenskontext>
{customer_context_json}
</unternehmenskontext>

<zielgruppe>
{audience_avatar_json}
</zielgruppe>

Erstelle ein Voice-Profil das authentisch zu diesem Unternehmen und seiner Zielgruppe passt.
Antworte mit reinem JSON."""


def generate_voice_fallback(
    tenant_id: str,
    customer_context: dict,
    audience_avatar: dict,
    call_llm=None,
) -> tuple[dict, dict]:
    """Generiert ein Fallback-Voice-Profil aus Kontext + Avatar über den EU-Seam.

    Args:
        tenant_id:        Tenant-ID (nur für Logging — nie in Klartext im Log).
        customer_context: P01-Payload (Kunden-Kontext).
        audience_avatar:  P04-Payload (Zielgruppen-Avatar).
        call_llm:         Injizierbare LLM-Funktion (Default: call_pipeline_llm).
                          Signature: call_llm(*, prompt_key, system_prompt, user_content,
                                              tenant_id) -> PipelineLLMResult.

    Returns:
        (payload: dict, meta: dict) — payload ist der geparste LLM-Output (oder {});
        meta enthält Provenance-Markierungen und LLM-Metadaten.

    Fail-open:
        Bei jedem Fehler (LLM-Fehler, JSON-Parse-Error) wird ({}, meta_mit_error)
        zurückgegeben. Kein re-raise.
    """
    if call_llm is None:
        # Nutzt den Modul-Level-Alias (patchbar via patch.object(vf, "call_pipeline_llm"))
        call_llm = call_pipeline_llm

    tid_prefix = str(tenant_id)[:8]

    # User-Content aufbauen (kein roher PII — nur strukturierter Kontext)
    try:
        ctx_json = json.dumps(customer_context, ensure_ascii=False, indent=2)
        avatar_json = json.dumps(audience_avatar, ensure_ascii=False, indent=2)
    except Exception:
        ctx_json = "{}"
        avatar_json = "{}"

    user_content = _FALLBACK_USER_TEMPLATE.format(
        customer_context_json=ctx_json,
        audience_avatar_json=avatar_json,
    )

    base_meta = {
        "source": "voice_fallback",
        "is_fallback": True,
        "fallback_source": "voice_fallback",
        # TODO Folge-Issue: Web-Recherche-Integration für echte Zielgruppen-Tone-Research
    }

    try:
        res = call_llm(
            prompt_key="VOICE_FALLBACK",
            system_prompt=_FALLBACK_SYSTEM_PROMPT,
            user_content=user_content,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning(
            "[P03-Fallback] LLM-Call fehlgeschlagen für tenant=%.8s...: %s",
            tid_prefix,
            type(exc).__name__,
        )
        return {}, {**base_meta, "fallback_failed": True, "error": type(exc).__name__}

    # JSON parsen
    try:
        raw_text = res.text.strip()
        # Markdown-Fence entfernen falls vorhanden
        for fence in ("```json", "```"):
            if fence in raw_text:
                start = raw_text.index(fence) + len(fence)
                end = raw_text.find("```", start)
                if end != -1:
                    raw_text = raw_text[start:end].strip()
                    break
        payload = json.loads(raw_text)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "[P03-Fallback] JSON-Parse fehlgeschlagen für tenant=%.8s...: %s",
            tid_prefix,
            type(exc).__name__,
        )
        return {}, {
            **base_meta,
            "fallback_failed": True,
            "error": "json_parse_error",
            "model_id": getattr(res, "model_id", "unknown"),
            "input_tokens": getattr(res, "input_tokens", 0),
            "output_tokens": getattr(res, "output_tokens", 0),
        }

    meta = {
        **base_meta,
        "model_id": res.model_id,
        "input_tokens": res.input_tokens,
        "output_tokens": res.output_tokens,
        "cost_usd": res.cost_usd,
    }

    logger.info(
        "[P03-Fallback] Voice-Fallback generiert für tenant=%.8s...: "
        "input=%d output=%d cost=%.6f USD",
        tid_prefix,
        res.input_tokens,
        res.output_tokens,
        res.cost_usd,
    )

    return payload, meta


# ---------------------------------------------------------------------------
# DB-Write-Helfer
# ---------------------------------------------------------------------------


def _insert_fallback_voice_profile(
    session,
    tenant_id: str,
    payload: dict,
    model_id: str,
    project_id: str | None = None,
) -> str:
    """Schreibt den Fallback-Voice-Payload in tenant_voice_profile."""
    from sqlalchemy import text
    row = session.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
            "FROM tenant_voice_profile WHERE tenant_id = :tenant_id"
        ),
        {"tenant_id": tenant_id},
    ).fetchone()
    next_version = row.next_version if row else 1

    new_id = str(uuid.uuid4())
    session.execute(
        text(  # noqa: F821 — text imported above
            "INSERT INTO tenant_voice_profile "
            "(id, tenant_id, version, is_active, source, payload, "
            "prompt_version_hash, model_id, project_id) "
            "VALUES (:id, :tenant_id, :version, false, :source, "
            "CAST(:payload AS jsonb), :prompt_version_hash, :model_id, :project_id)"
        ),
        {
            "id": new_id,
            "tenant_id": tenant_id,
            "version": next_version,
            "source": "voice_fallback",
            "payload": json.dumps(payload),
            "prompt_version_hash": "voice_fallback",
            "model_id": model_id,
            "project_id": project_id,
        },
    )
    return new_id


# ---------------------------------------------------------------------------
# Orchestrierungs-Funktion (wird von p03_task.run_p03 aufgerufen)
# ---------------------------------------------------------------------------


def run_p03_voice_fallback(
    tenant_id: str,
    transcript: str | None,
    written_texts: list | None,
    linkedin_posts: list | None,
    tenant_name: str | None,
    agentur_id: str | None,
    project_id: str | None = None,
) -> dict | None:
    """Prüft ob ein Fallback nötig ist und generiert + schreibt ihn ggf.

    Gibt None zurück wenn:
      - Echte Voice-Quelle vorhanden (kein Fallback nötig) → regulärer P03-Pfad
      - Fallback-Generierung fehlschlägt (fail-open)

    Gibt ein dict mit Provenance-Info zurück wenn Fallback erfolgreich geschrieben.

    Wird von p03_task.run_p03 VOR dem regulären LLM-Call aufgerufen.
    Ist die Voice-Quelle vorhanden, kehrt diese Funktion mit None zurück
    und der reguläre Pfad läuft unverändert weiter.
    """
    # 1. Trigger-Check: Fallback nur wenn keine echte Voice-Quelle
    if _has_voice_source(transcript, written_texts, linkedin_posts):
        return None

    tid_prefix = str(tenant_id)[:8]
    logger.info(
        "[P03-Fallback] Keine Voice-Quelle für tenant=%.8s... — Fallback wird generiert",
        tid_prefix,
    )

    # 2. Kontext + Avatar laden (für Zielgruppen-Kontext)
    customer_context, audience_avatar = _load_context_and_avatar(tenant_id, project_id)

    # 3. Fallback generieren (über Seam — kein direkter SDK-Aufruf)
    payload, fallback_meta = generate_voice_fallback(
        tenant_id=tenant_id,
        customer_context=customer_context,
        audience_avatar=audience_avatar,
    )

    # Fail-open: Generierung fehlgeschlagen → kein Crash, regulärer Pfad
    if fallback_meta.get("fallback_failed"):
        logger.warning(
            "[P03-Fallback] Generierung fehlgeschlagen für tenant=%.8s..., "
            "fall-back auf leere Defaults",
            tid_prefix,
        )
        return None

    # 4. Kanonischen Payload aufbauen
    # Nutzt Modul-Level-Aliase (patchbar via patch.object) statt lokaler lazy-Imports.
    canonical_meta = build_canonical_meta(
        "p03",
        tenant_id=tenant_id,
        model=fallback_meta.get("model_id", "voice_fallback"),
        generated_at=now_iso(),  # Modul-Level-Alias (patchbar)
        tenant_name=tenant_name,
        agentur_id=agentur_id,
        token_usage={
            "input_tokens": fallback_meta.get("input_tokens", 0),
            "output_tokens": fallback_meta.get("output_tokens", 0),
        },
        llm_meta=None,
    )
    # Provenance in _meta verankern
    canonical_meta["is_fallback"] = True
    canonical_meta["fallback_source"] = "voice_fallback"

    # Payload + kanonische Metadaten zusammenführen
    payload.setdefault("_meta", {})
    payload["_meta"].update(canonical_meta)

    finalized_payload, schema_errors = finalize_canonical("p03", payload, meta=canonical_meta)
    if schema_errors:
        logger.info(
            "[P03-Fallback] %d kanonische Schema-Lücke(n) für tenant=%.8s... in _meta.luecken",
            len(schema_errors),
            tid_prefix,
        )

    # 5. In DB schreiben
    # Nutzt Modul-Level-Alias (patchbar via patch.object(vf, "sync_session_factory"))
    try:
        with sync_session_factory() as session:
            try:
                _insert_fallback_voice_profile(
                    session=session,
                    tenant_id=tenant_id,
                    payload=finalized_payload,
                    model_id=fallback_meta.get("model_id", "voice_fallback"),
                    project_id=project_id,
                )
                session.commit()
            except Exception as db_exc:
                session.rollback()
                logger.warning(
                    "[P03-Fallback] DB-Insert fehlgeschlagen für tenant=%.8s...: %s",
                    tid_prefix,
                    type(db_exc).__name__,
                )
                return None
    except Exception as sess_exc:
        logger.warning(
            "[P03-Fallback] Session-Fehler für tenant=%.8s...: %s",
            tid_prefix,
            type(sess_exc).__name__,
        )
        return None

    logger.info(
        "[P03-Fallback] Fallback-Voice-Profil geschrieben für tenant=%.8s... "
        "(source=voice_fallback, is_fallback=True)",
        tid_prefix,
    )

    return {
        "source": "voice_fallback",
        "is_fallback": True,
        "model_id": fallback_meta.get("model_id"),
        "input_tokens": fallback_meta.get("input_tokens", 0),
        "output_tokens": fallback_meta.get("output_tokens", 0),
        "cost_usd": fallback_meta.get("cost_usd", 0.0),
    }
