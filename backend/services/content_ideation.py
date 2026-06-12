"""
Content Ideation Service — Kern des dialogischen Workflows.

Aufgabe: Aus einer Transkript-Analyse gezielte Content-Ideen generieren,
inklusive Fragen fuer den Unternehmer.

Pipeline:
1. Analyse lesen (summary, key_points, content_angles, tags)
2. Content-Ideen generieren (5-10 pro Video, verschiedene Angles)
3. Pro Idee 2-3 Fragen formulieren, die persoenliche Erfahrung hervorrufen
4. Ideen nach LinkedIn-Relevanz bewerten und priorisieren

Philosophie: "Nicht das Denken abnehmen — die Arbeit."
"""

import logging

from services.llm import BudgetExceededError, llm_service

logger = logging.getLogger(__name__)

# ── Schritt 1: Content-Ideen aus Analyse generieren ─────────────────────────

IDEATION_SYSTEM_PROMPT = """Du bist ein erfahrener LinkedIn-Content-Stratege fuer den Mittelstand und Handwerk.
Deine Aufgabe: Aus einer Video-Analyse gezielte Content-Ideen fuer einen Unternehmer ableiten.

WICHTIG: Du schreibst KEINE Posts. Du generierst IDEEN, die der Unternehmer mit seiner eigenen
Perspektive fuellen wird.

KRITISCH: Wenn ein Branchenkontext angegeben ist, MUSST du alle Ideen darauf zuschneiden.
Ideen muessen zur Branche des Unternehmers passen — KEINE generischen CIO/Enterprise-Inhalte
wenn der Unternehmer im Handwerk, Bau, KMU oder Mittelstand taetig ist.

Jede Idee braucht:
- title: Praegnanter Arbeitstitel (max 10 Woerter)
- description: Was ist der Kern der Idee? Warum ist sie relevant fuer DIESE Branche? (2-3 Saetze)
- angle: Einer von: meinung, howto, story, kontroverse, statistik, trend
- hook_suggestion: Ein Vorschlag fuer den Post-Einstieg (1 Satz, passt zur Branche)
- relevance_score: 1-10 wie relevant ist das fuer die Zielgruppe des Unternehmers
- source_quotes: 1-2 relevante Zitate aus dem Transkript die als Basis dienen

Generiere 5-8 verschiedene Ideen mit unterschiedlichen Angles.
Bevorzuge Ideen die:
- Direkt zur Branche und Zielgruppe des Unternehmers passen
- Diskussionen in der jeweiligen Branche ausloesen
- Praktischen Mehrwert fuer die spezifische Zielgruppe bieten
- Persoenliche Stories aus dem Alltag des Unternehmers ermoeglichen

Antworte NUR als JSON-Array. Kein Markdown, keine Erklaerung."""


async def generate_content_ideas(
    analysis: dict,
    title: str,
    transcript_excerpt: str = "",
    industry_context: str = "",
    brand_context: str = "",
) -> list[dict] | None:
    """Generiere Content-Ideen aus einer Transkript-Analyse."""
    context_parts = []
    if industry_context:
        context_parts.append(industry_context)
    if brand_context:
        context_parts.append(f"Brand Voice:\n{brand_context}")
    industry_block = (
        f"""
UNTERNEHMER-KONTEXT (PFLICHT — alle Ideen MUESSEN dazu passen):
{chr(10).join(context_parts)}
"""
        if context_parts
        else ""
    )

    prompt = f"""Analysiere folgendes Video und generiere Content-Ideen fuer LinkedIn.
{industry_block}
Video-Titel: {title}
Summary: {analysis.get('summary', '')}
Kernaussagen: {', '.join(analysis.get('key_points', []))}
Content-Winkel: {', '.join(analysis.get('content_angles', []))}
Tags: {', '.join(analysis.get('tags', []))}
Trend-Score: {analysis.get('trend_score', 5)}/10

Transkript-Auszug (erste 5000 Zeichen):
{transcript_excerpt[:5000]}

Generiere 5-8 Content-Ideen als JSON-Array.
Stelle sicher dass ALLE Ideen zur Branche/Zielgruppe des Unternehmers passen."""

    try:
        ideas = await llm_service.complete_json(
            prompt=prompt,
            system=IDEATION_SYSTEM_PROMPT,
            model="claude-sonnet",  # Claude fuer kreative Qualitaet
        )
        # Sicherstellen dass es eine Liste ist
        if isinstance(ideas, dict) and "ideas" in ideas:
            ideas = ideas["ideas"]
        if not isinstance(ideas, list):
            logger.warning(f"Unexpected ideas format: {type(ideas)}")
            return None

        # Validierung und Defaults
        validated = []
        for i, idea in enumerate(ideas):
            validated.append(
                {
                    "title": idea.get("title", f"Idee {i+1}"),
                    "description": idea.get("description", ""),
                    "angle": idea.get("angle", "meinung"),
                    "hook_suggestion": idea.get("hook_suggestion", ""),
                    "relevance_score": min(10, max(1, float(idea.get("relevance_score", 5)))),
                    "source_quotes": idea.get("source_quotes", []),
                }
            )

        # Nach Relevanz sortieren
        validated.sort(key=lambda x: x["relevance_score"], reverse=True)
        logger.info(f"Generated {len(validated)} content ideas for '{title}'")
        return validated

    except BudgetExceededError:
        raise
    except Exception as e:
        logger.error(f"Content ideation failed: {e}")
        return None


# ── Schritt 2: Fragen fuer den Unternehmer generieren ───────────────────────

QUESTION_SYSTEM_PROMPT = """Du bist ein erfahrener Interview-Coach fuer Unternehmer.
Deine Aufgabe: Zu einer Content-Idee gezielte Fragen formulieren, die der Unternehmer
kurz und authentisch beantworten kann.

REGELN fuer gute Fragen:
- KEINE Ja/Nein-Fragen
- KEINE Wissensfragen (die kann Google beantworten)
- Fragen nach PERSOENLICHER Erfahrung, Meinung, Entscheidungen
- Kurz formuliert (max 20 Woerter pro Frage)
- So formuliert, dass die Antwort natuerlich in einen LinkedIn-Post fliesst
- 2-3 Fragen pro Idee, nicht mehr

Jede Frage hat:
- question: Die eigentliche Frage
- purpose: Warum stellen wir diese Frage? (intern, sieht der Unternehmer nicht)
- example_answer: Ein kurzes Beispiel wie eine gute Antwort aussehen koennte (2-3 Saetze)

Antworte NUR als JSON-Array. Kein Markdown, keine Erklaerung."""


async def generate_entrepreneur_questions(
    idea: dict,
    brand_context: str = "",
) -> list[dict] | None:
    """Generiere gezielte Fragen fuer den Unternehmer zu einer Content-Idee."""
    prompt = f"""Formuliere 2-3 gezielte Fragen fuer einen Unternehmer zu dieser Content-Idee:

Idee: {idea.get('title', '')}
Beschreibung: {idea.get('description', '')}
Angle: {idea.get('angle', '')}
Hook-Vorschlag: {idea.get('hook_suggestion', '')}
Quell-Zitate: {', '.join(idea.get('source_quotes', []))}

{f'Kontext zum Unternehmer (Branche/Ton beachten): {brand_context}' if brand_context else ''}

Die Fragen sollen:
- Persoenliche Erfahrungen aus der EIGENEN Branche hervorrufen
- Praxisnah und konkret sein (nicht abstrakt/theoretisch)
- Leicht in 2-3 Saetzen beantwortbar sein

Antworte als JSON-Array."""

    try:
        questions = await llm_service.complete_json(
            prompt=prompt,
            system=QUESTION_SYSTEM_PROMPT,
            model="claude-sonnet",  # Claude fuer empathische Fragen
        )
        if isinstance(questions, dict) and "questions" in questions:
            questions = questions["questions"]
        if not isinstance(questions, list):
            logger.warning(f"Unexpected questions format: {type(questions)}")
            return None

        # Validierung
        validated = []
        for q in questions[:3]:  # Max 3 Fragen
            validated.append(
                {
                    "question": q.get("question", ""),
                    "purpose": q.get("purpose", ""),
                    "example_answer": q.get("example_answer", ""),
                }
            )

        logger.info(f"Generated {len(validated)} questions for idea '{idea.get('title', '')}'")
        return validated

    except BudgetExceededError:
        raise
    except Exception as e:
        logger.error(f"Question generation failed: {e}")
        return None


# ── Schritt 3: Kompletter Ideation-Pipeline-Lauf ────────────────────────────


async def run_ideation_pipeline(
    analysis: dict,
    title: str,
    transcript_excerpt: str = "",
    industry_context: str = "",
    brand_context: str = "",
) -> list[dict] | None:
    """Fuehre die komplette Ideation-Pipeline aus:
    Analyse → Ideen → Fragen pro Idee.

    Gibt eine Liste von Ideen zurueck, jede mit entrepreneur_questions.
    """
    # Schritt 1: Ideen generieren (mit vollem Voice-Kontext)
    ideas = await generate_content_ideas(
        analysis=analysis,
        title=title,
        transcript_excerpt=transcript_excerpt,
        industry_context=industry_context,
        brand_context=brand_context,
    )
    if not ideas:
        return None

    # Schritt 2: Pro Idee Fragen generieren
    enriched_ideas = []
    for idea in ideas:
        questions = await generate_entrepreneur_questions(
            idea=idea,
            brand_context=brand_context,
        )
        idea["entrepreneur_questions"] = questions or []
        enriched_ideas.append(idea)

    logger.info(f"Ideation pipeline complete: {len(enriched_ideas)} ideas with questions")
    return enriched_ideas
