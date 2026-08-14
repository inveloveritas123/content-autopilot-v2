"""
Brand Voice Service — Persoenliche Stimme des Unternehmers lernen und anwenden.

Zwei Lernquellen:
1. Bestehende Texte (Posts, E-Mails, Website-Texte)
2. Unternehmer-Antworten (fortlaufend: aus dem Dialog-Workflow)

Der frueher hier gelistete Onboarding-Fragebogen ist entfernt: das Stimmprofil
entsteht ausschliesslich aus dem Setup-Gespraech (Transkript) und entwickelt
sich danach nur automatisch weiter — der Kunde stellt nichts daran ein.

Das Brand-Voice-Profil wird als JSONB im Tenant gespeichert und bei jeder
Content-Generierung als Kontext mitgegeben.
"""

import logging

from services.llm import llm_service

logger = logging.getLogger(__name__)

# ── Brand Voice Analyse aus bestehenden Texten ──────────────────────────────

VOICE_ANALYSIS_SYSTEM = """Du bist ein Sprachwissenschaftler spezialisiert auf persoenliche Schreibstile.
Analysiere die gegebenen Texte und extrahiere ein Brand-Voice-Profil.

Extrahiere:
1. tone: Grundton (z.B. "direkt und bodenstaendig", "akademisch und differenziert")
2. vocabulary_level: einfach / mittel / gehoben / fachsprachlich
3. sentence_style: Wie schreibt die Person? (kurz+knackig, lang+verschachtelt, gemischt)
4. favorite_phrases: Wiederkehrende Redewendungen oder Wortmuster (5-10)
5. emoji_usage: nie / selten / regelmaessig / viel
6. formatting_style: Wie strukturiert die Person? (Absaetze, Listen, Einzeiler)
7. perspective: Ich-Form / Wir-Form / Man-Form / gemischt
8. call_to_action_style: Wie formuliert die Person Handlungsaufforderungen?
9. topics_passion: Worueberredet die Person besonders leidenschaftlich?
10. topics_avoid: Welche Themen/Toene meidet die Person offensichtlich?
11. authenticity_markers: Was macht die Texte einzigartig/wiedererkennbar?
12. linkedin_specific: Besonderheiten im LinkedIn-Stil (Hooks, Hashtags, Laenge)

Antworte NUR als JSON. Kein Markdown, keine Erklaerung."""


async def analyze_voice_from_texts(texts: list[str]) -> dict | None:
    """Analysiere Brand Voice aus einer Liste bestehender Texte."""
    if not texts:
        return None

    combined = "\n\n---\n\n".join(texts[:20])  # Max 20 Texte

    try:
        profile = await llm_service.complete_json(
            prompt=f"Analysiere folgende Texte und erstelle ein Brand-Voice-Profil:\n\n{combined[:12000]}",
            system=VOICE_ANALYSIS_SYSTEM,
            model="claude-sonnet",
        )
        logger.info(f"Voice analysis complete from {len(texts)} texts")
        return profile
    except Exception as e:
        logger.error(f"Voice analysis failed: {e}")
        return None


# ── Brand Voice fortlaufend lernen ──────────────────────────────────────────


async def update_voice_from_answer(
    current_profile: dict,
    answer_text: str,
) -> dict:
    """Aktualisiere das Brand-Voice-Profil basierend auf einer neuen Unternehmer-Antwort.

    Wird nach jeder Antwort im Dialog-Workflow aufgerufen.
    Leichtgewichtig — nur Ergaenzungen, kein komplettes Neuschreiben.
    """
    prompt = f"""Aktuelles Brand-Voice-Profil:
{current_profile}

Neue Antwort des Unternehmers:
"{answer_text}"

Gibt es neue Erkenntnisse zum Schreibstil oder zur Persoenlichkeit?
Wenn ja, gib NUR die zu aendernden/ergaenzenden Felder als JSON zurueck.
Wenn nein, antworte mit {{}}.

Moegliche Updates: neue favorite_phrases, verfeinerte tone-Beschreibung,
neue authenticity_markers."""

    try:
        updates = await llm_service.complete_json(
            prompt=prompt,
            system="Du analysierst Schreibstile. Antworte NUR als JSON mit den Updates.",
            model="gemini-flash",  # Schnell + guenstig fuer inkrementelle Updates
        )
        if updates:
            # Merge: Listen werden ergaenzt, Strings ueberschrieben
            for key, value in updates.items():
                if isinstance(value, list) and isinstance(current_profile.get(key), list):
                    # Deduplizierte Ergaenzung
                    existing = {str(x) for x in current_profile[key]}
                    current_profile[key].extend(x for x in value if str(x) not in existing)
                else:
                    current_profile[key] = value
            logger.info(f"Voice profile updated with {len(updates)} changes")
        return current_profile
    except Exception as e:
        logger.error(f"Voice profile update failed: {e}")
        return current_profile


# ── Voice-Profil als Prompt-Kontext formatieren ─────────────────────────────


def format_voice_for_prompt(profile: dict) -> str:
    """Formatiere das Brand-Voice-Profil als Kontext fuer Content-Generierung.

    Unterstuetzt zwei Formate:
    - v1 (English keys): tone, vocabulary_level, sentence_style, perspective,
      favorite_phrases, formatting_style, emoji_usage, authenticity_markers, topics_avoid
    - P03/Wizard (German keys): tonalitaet, kernthemen, stilprinzipien, wortschatz,
      schreibrhythmus, vermeidungsregeln
    """
    if not profile:
        return ""

    parts = []

    # ── v1 English keys ──────────────────────────────────────────────────────
    if profile.get("tone"):
        parts.append(f"Tonalitaet: {profile['tone']}")
    if profile.get("vocabulary_level"):
        parts.append(f"Sprachniveau: {profile['vocabulary_level']}")
    if profile.get("sentence_style"):
        parts.append(f"Satzstil: {profile['sentence_style']}")
    if profile.get("perspective"):
        parts.append(f"Perspektive: {profile['perspective']}")
    if profile.get("favorite_phrases"):
        phrases = profile["favorite_phrases"][:8]
        parts.append(f"Typische Redewendungen: {', '.join(str(p) for p in phrases)}")
    if profile.get("formatting_style"):
        parts.append(f"Formatierung: {profile['formatting_style']}")
    if profile.get("emoji_usage"):
        parts.append(f"Emoji-Nutzung: {profile['emoji_usage']}")
    if profile.get("authenticity_markers"):
        markers = profile["authenticity_markers"][:5]
        parts.append(f"Wiedererkennungsmerkmale: {', '.join(str(m) for m in markers)}")
    if profile.get("topics_avoid"):
        avoids = profile["topics_avoid"]
        if isinstance(avoids, list):
            parts.append(f"VERMEIDE: {', '.join(str(a) for a in avoids)}")
        else:
            parts.append(f"VERMEIDE: {avoids}")

    # ── P03/Wizard German keys (fallbacks when English keys absent) ──────────
    if not profile.get("tone") and profile.get("tonalitaet"):
        ton = profile["tonalitaet"]
        if isinstance(ton, dict):
            grundton = ton.get("grundton") or ton.get("energie") or ""
            rest = {k: v for k, v in ton.items() if k not in ("grundton",)}
            beschreibung = grundton
            if rest:
                extra = ", ".join(f"{k}: {v}" for k, v in rest.items())
                beschreibung = f"{grundton} ({extra})" if grundton else extra
            if beschreibung:
                parts.append(f"Tonalitaet: {beschreibung}")
        else:
            parts.append(f"Tonalitaet: {ton}")

    if profile.get("kernthemen"):
        themen = profile["kernthemen"]
        if isinstance(themen, list):
            parts.append(f"Kernthemen: {', '.join(str(t) for t in themen)}")
        else:
            parts.append(f"Kernthemen: {themen}")

    if not profile.get("sentence_style") and profile.get("stilprinzipien"):
        stil = profile["stilprinzipien"]
        if isinstance(stil, dict):
            stil_parts = [f"{k}: {v}" for k, v in stil.items()]
            parts.append(f"Stilprinzipien: {', '.join(stil_parts)}")
        else:
            parts.append(f"Stilprinzipien: {stil}")

    if not profile.get("favorite_phrases") and profile.get("wortschatz"):
        ws = profile["wortschatz"]
        if isinstance(ws, dict):
            if ws.get("bevorzugt"):
                bevorzugt = ws["bevorzugt"]
                if isinstance(bevorzugt, list):
                    parts.append(
                        f"Typische Redewendungen: {', '.join(str(w) for w in bevorzugt[:8])}"
                    )
                else:
                    parts.append(f"Typische Redewendungen: {bevorzugt}")
            if ws.get("vermieden"):
                vermieden = ws["vermieden"]
                if isinstance(vermieden, list):
                    parts.append(f"Vermeide Woerter: {', '.join(str(w) for w in vermieden)}")
                else:
                    parts.append(f"Vermeide Woerter: {vermieden}")

    if profile.get("schreibrhythmus"):
        rhythmus = profile["schreibrhythmus"]
        if isinstance(rhythmus, dict):
            rhythmus_parts = [f"{k}: {v}" for k, v in rhythmus.items()]
            parts.append(f"Schreibrhythmus: {', '.join(rhythmus_parts)}")
        else:
            parts.append(f"Schreibrhythmus: {rhythmus}")

    if not profile.get("topics_avoid") and profile.get("vermeidungsregeln"):
        regeln = profile["vermeidungsregeln"]
        if isinstance(regeln, list):
            parts.append(f"VERMEIDE: {', '.join(str(r) for r in regeln)}")
        else:
            parts.append(f"VERMEIDE: {regeln}")

    return "\n".join(parts)
