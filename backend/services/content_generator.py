import logging
from typing import Optional

from services.llm import llm_service

logger = logging.getLogger(__name__)


async def generate_linkedin_post(
    analysis: dict,
    title: str,
    tone: str = "professionell, informativ, mit persoenlicher Note",
) -> Optional[str]:
    """Generate a LinkedIn post from video analysis."""
    prompt = f"""Erstelle einen LinkedIn-Post basierend auf diesem Video-Summary.

Video-Titel: {title}
Summary: {analysis.get('summary', '')}
Kernaussagen: {', '.join(analysis.get('key_points', [])[:5])}

Tonalitaet: {tone}
Laenge: 150-250 Woerter
Struktur: Hook -> Kernaussage -> Einordnung -> CTA
Hashtags: 3-5 relevante
Sprache: Deutsch

Schreibe NUR den fertigen Post, keine Erklaerungen."""

    try:
        return await llm_service.complete(prompt, model="gemini-flash")
    except Exception as e:
        logger.error(f"LinkedIn post generation failed: {e}")
        return None


async def generate_blog_draft(
    analysis: dict,
    title: str,
    transcript_text: str = "",
    tone: str = "professionell, informativ",
) -> Optional[str]:
    """Generate a blog article draft from video analysis."""
    prompt = f"""Erstelle einen Blog-Artikel-Entwurf basierend auf diesem Video.

Video-Titel: {title}
Summary: {analysis.get('summary', '')}
Kernaussagen: {', '.join(analysis.get('key_points', []))}
Content-Winkel: {', '.join(analysis.get('content_angles', [])[:2])}

Transkript-Auszug (erste 3000 Zeichen):
{transcript_text[:3000]}

Tonalitaet: {tone}
Laenge: 500-800 Woerter
Struktur: Titel -> Einleitung -> 3 Hauptpunkte -> Fazit -> CTA
SEO: Meta-Description + 3 Keywords vorschlagen (am Ende als JSON-Block)
Sprache: Deutsch

Schreibe den kompletten Artikel."""

    try:
        return await llm_service.complete(prompt, model="claude-sonnet")
    except Exception as e:
        logger.error(f"Blog draft generation failed: {e}")
        return None


async def generate_newsletter_snippet(
    analysis: dict,
    title: str,
    video_url: str = "",
) -> Optional[str]:
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
    except Exception as e:
        logger.error(f"Newsletter snippet generation failed: {e}")
        return None


async def generate_all_content(
    analysis: dict,
    title: str,
    transcript_text: str = "",
    video_url: str = "",
    tone: str = "professionell, informativ, mit persoenlicher Note",
) -> dict[str, Optional[str]]:
    """Generate content for all channels."""
    linkedin = await generate_linkedin_post(analysis, title, tone)
    blog = await generate_blog_draft(analysis, title, transcript_text, tone)
    newsletter = await generate_newsletter_snippet(analysis, title, video_url)

    return {
        "linkedin": linkedin,
        "blog": blog,
        "newsletter": newsletter,
    }
