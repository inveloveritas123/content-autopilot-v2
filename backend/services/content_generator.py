# AUDITED-PARTIAL-2026-08-19 (louis-telegram-zwei-fehler): alle vier join()-Prompt-Pfade geprueft und entschaerft; LLM-Aufrufe/Parser nicht beurteilt.
"""
Content Generator — Erstellt LinkedIn-Posts, Blog-Drafts und Newsletter-Snippets.

WICHTIG: Zwei Modi:
1. QUICK MODE (bestehend): Direkt aus Analyse → Post (fuer schnelle Entwuerfe)
2. DIALOG MODE (neu): Aus Analyse + Unternehmer-Antworten → authentischer Post

Der Dialog-Mode ist der Kern des Kunden-Konzepts:
"Ein KI-System, das dem Unternehmer nicht das Denken abnimmt — sondern die Arbeit."
"""

import logging

from services.analysis_normalize import join_analysis_list
from services.brand_voice import format_voice_for_prompt
from services.llm import BudgetExceededError, llm_service

logger = logging.getLogger(__name__)


# ── DIALOG MODE: Post aus Unternehmer-Antworten ─────────────────────────────

DIALOG_POST_SYSTEM = """Du bist ein LinkedIn-Ghostwriter der im Namen eines Unternehmers schreibt.

DEINE AUFGABE: Aus den Antworten des Unternehmers einen authentischen LinkedIn-Post erstellen.
Der Post muss klingen als haette der Unternehmer ihn SELBST geschrieben.

REGELN:
- Nutze die WORTE und FORMULIERUNGEN des Unternehmers wo moeglich
- Ergaenze Struktur und Feinschliff, aber veraendere nicht die Kernaussage
- Hook muss in den ersten 2 Zeilen zum Weiterlesen motivieren
- Kein "Ich habe kuerzlich ein spannendes Video gesehen" — die Quelle ist unsichtbar
- Der Post steht fuer sich allein, ohne Bezug zum Quell-Video
- Laenge: 150-300 Woerter (je nach Inhalt)
- Am Ende: 3-5 relevante Hashtags
- Kein Emoji-Spam (max 2-3 wenn passend)

STRUKTUR-OPTIONEN (waehle passend zum Angle):
- Hook → Story → Erkenntnis → CTA
- Hook → These → Begruendung → Gegenargument → Fazit → CTA
- Hook → 3 Punkte → Zusammenfassung → CTA
- Hook → Frage → Persoenliche Antwort → CTA

Schreibe NUR den fertigen Post, keine Erklaerungen."""


async def generate_linkedin_post_from_dialog(
    idea: dict,
    answers: list[dict],
    analysis: dict,
    voice_profile: dict | None = None,
    variants: int = 2,
) -> list[str] | None:
    """Generiere LinkedIn-Post-Varianten aus Unternehmer-Antworten.

    Dies ist der KERN des dialogischen Workflows.
    """
    # Brand Voice Kontext aufbauen
    voice_context = ""
    if voice_profile:
        voice_context = (
            f"\n\nBRAND VOICE DES UNTERNEHMERS:\n{format_voice_for_prompt(voice_profile)}"
        )

    # Antworten formatieren
    qa_block = "\n".join(
        f"Frage: {a.get('question_text', a.get('question', ''))}\nAntwort: {a.get('answer_text', a.get('answer', ''))}"
        for a in answers
    )

    prompt = f"""Erstelle {variants} verschiedene LinkedIn-Post-Varianten.

CONTENT-IDEE:
Titel: {idea.get('title', '')}
Angle: {idea.get('angle', '')}
Hook-Vorschlag: {idea.get('hook_suggestion', '')}

ANTWORTEN DES UNTERNEHMERS:
{qa_block}

HINTERGRUND (aus Video-Analyse, NICHT im Post erwaehnen):
{analysis.get('summary', '')}
Kernaussagen: {join_analysis_list(analysis, 'key_points', limit=3)}
{voice_context}

Trenne die {variants} Varianten mit "---VARIANTE---".
Jede Variante ist ein komplett eigenstaendiger Post."""

    try:
        result = await llm_service.complete(
            prompt=prompt,
            system=DIALOG_POST_SYSTEM,
            model="claude-sonnet",
        )
        # Varianten aufteilen
        posts = [v.strip() for v in result.split("---VARIANTE---") if v.strip()]
        if not posts:
            posts = [result.strip()]
        logger.info(f"Generated {len(posts)} LinkedIn post variants from dialog")
        return posts
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.error(f"Dialog post generation failed: {e}")
        return None


# ── QUICK MODE: Direkt aus Analyse (bestehende Funktionalitaet) ─────────────


async def generate_linkedin_post(
    analysis: dict,
    title: str,
    tone: str = "professionell, informativ, mit persoenlicher Note",
    voice_profile: dict | None = None,
    routing_override: dict | None = None,
) -> str | None:
    """Generate a LinkedIn post from video analysis (Quick Mode)."""
    voice_context = ""
    if voice_profile:
        voice_context = f"\nBrand Voice:\n{format_voice_for_prompt(voice_profile)}"

    prompt = f"""Erstelle einen LinkedIn-Post basierend auf diesem Video-Summary.

Video-Titel: {title}
Summary: {analysis.get('summary', '')}
Kernaussagen: {join_analysis_list(analysis, 'key_points', limit=5)}

Tonalitaet: {tone}
Laenge: 150-250 Woerter
Struktur: Hook -> Kernaussage -> Einordnung -> CTA
Hashtags: 3-5 relevante
Sprache: Deutsch
{voice_context}

Schreibe NUR den fertigen Post, keine Erklaerungen."""

    try:
        return await llm_service.complete(
            prompt,
            model="gemini-flash",
            purpose="post_generation",
            routing_override=routing_override,
        )
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.error(f"LinkedIn post generation failed: {e}")
        return None


async def generate_blog_draft(
    analysis: dict,
    title: str,
    transcript_text: str = "",
    tone: str = "professionell, informativ",
    voice_profile: dict | None = None,
) -> str | None:
    """Generate a blog article draft from video analysis."""
    voice_context = ""
    if voice_profile:
        voice_context = f"\nBrand Voice:\n{format_voice_for_prompt(voice_profile)}"

    prompt = f"""Erstelle einen Blog-Artikel-Entwurf basierend auf diesem Video.

Video-Titel: {title}
Summary: {analysis.get('summary', '')}
Kernaussagen: {join_analysis_list(analysis, 'key_points')}
Content-Winkel: {join_analysis_list(analysis, 'content_angles', limit=2)}

Transkript-Auszug (erste 3000 Zeichen):
{transcript_text[:3000]}

Tonalitaet: {tone}
Laenge: 500-800 Woerter
Struktur: Titel -> Einleitung -> 3 Hauptpunkte -> Fazit -> CTA
SEO: Meta-Description + 3 Keywords vorschlagen (am Ende als JSON-Block)
Sprache: Deutsch
{voice_context}

Schreibe den kompletten Artikel."""

    try:
        return await llm_service.complete(prompt, model="claude-sonnet")
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.error(f"Blog draft generation failed: {e}")
        return None


async def generate_newsletter_snippet(
    analysis: dict,
    title: str,
    video_url: str = "",
) -> str | None:
    """Generate a newsletter snippet from video analysis."""
    prompt = f"""Erstelle einen Newsletter-Abschnitt fuer einen woechentlichen Branchen-Newsletter.

Video-Titel: {title}
Summary: {analysis.get('summary', '')}
Link: {video_url}

Laenge: 80-120 Woerter
Struktur: Headline -> 2-3 Saetze Zusammenfassung -> "Mehr erfahren"-Link
Sprache: Deutsch

Schreibe NUR den fertigen Newsletter-Abschnitt."""

    try:
        return await llm_service.complete(prompt, model="gemini-flash")
    except BudgetExceededError:
        raise
    except Exception as e:
        logger.error(f"Newsletter snippet generation failed: {e}")
        return None


async def generate_all_content(
    analysis: dict,
    title: str,
    transcript_text: str = "",
    video_url: str = "",
    tone: str = "professionell, informativ, mit persoenlicher Note",
    voice_profile: dict | None = None,
    routing_override: dict | None = None,
) -> dict[str, str | None]:
    """Generate content for all channels (Quick Mode)."""
    linkedin = await generate_linkedin_post(
        analysis, title, tone, voice_profile, routing_override=routing_override
    )
    blog = await generate_blog_draft(analysis, title, transcript_text, tone, voice_profile)
    newsletter = await generate_newsletter_snippet(analysis, title, video_url)

    return {
        "linkedin": linkedin,
        "blog": blog,
        "newsletter": newsletter,
    }
