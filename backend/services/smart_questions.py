"""
Smart-Question-Generator — Das Herzstück des Dialogic MCP Layers.

Generiert 4-6 Interview-Fragen pro Item, die:
1. Auf SPEZIFISCHE Transkript-Stellen referenzieren (mit Zitat)
2. Den Unternehmer zu persönlichen Erfahrungen einladen
3. Auf LinkedIn-würdige Stories/Insights abzielen
4. Format-Vielfalt: story, opinion, how_to, controversy

Strategie:
- Primär: Gemini Flash via LiteLLM (~$0.001/Item)
- Fallback: Template-basierte Fragen aus Analyse-Daten (kein LLM, $0)
"""

import json
import logging
import re

import httpx

from services.llm import BudgetExceededError

logger = logging.getLogger(__name__)


async def generate_smart_questions(
    item_id: str,
    transcript_text: str,
    analysis: dict,
    title: str = "",
    entrepreneur: dict | None = None,
) -> list[dict]:
    """Generiere 4-6 smarte Interview-Fragen für ein Item.

    Args:
        item_id: UUID des SourceItems
        transcript_text: Vollständiges Transkript
        analysis: Analyse-Ergebnis (main_topic, key_insights, hooks etc.)
        title: Titel des Videos/Podcasts
        entrepreneur: Unternehmer-Profil aus Tenant-Settings

    Returns:
        Liste von Fragen: [{question_text, transcript_reference, why_relevant, target_angle, order_index}]
    """
    entrepreneur = entrepreneur or {}

    # Try LLM-based generation first
    questions = await _generate_with_llm(transcript_text, analysis, title, entrepreneur)

    if questions:
        logger.info(f"Smart questions for {item_id}: {len(questions)} generated via LLM")
        return questions

    # Fallback: template-based questions from analysis data
    questions = _generate_from_analysis(analysis, title, entrepreneur)
    logger.info(f"Smart questions for {item_id}: {len(questions)} generated via fallback (no LLM)")
    return questions


async def _generate_with_llm(
    transcript_text: str,
    analysis: dict,
    title: str,
    entrepreneur: dict,
) -> list[dict]:
    """Primärer Pfad: Gemini Flash via LiteLLM."""
    try:
        from config import settings

        # Transcript excerpt for LLM (~600 words to keep cost low)
        words = transcript_text.split()
        transcript_excerpt = " ".join(words[:600])

        industry = entrepreneur.get("industry", "Unternehmertum")
        specialization = entrepreneur.get("specialization", "")
        target_audience = entrepreneur.get("target_audience", "LinkedIn-Entscheider")
        name = entrepreneur.get("name", "der Unternehmer")

        main_topic = analysis.get("main_topic", title)
        insights = analysis.get("key_insights", analysis.get("insights", []))
        insights_str = (
            "\n".join(f"- {i}" for i in insights[:5])
            if insights
            else "- Keine spezifischen Insights"
        )

        prompt = f"""Analysiere diesen Content-Beitrag für {name}, tätig in {industry}{f', spezialisiert auf {specialization}' if specialization else ''}.

TITEL: {title}
TRANSKRIPT-AUSZUG:
{transcript_excerpt}

ANALYSE:
Hauptthema: {main_topic}
Key Insights:
{insights_str}

ZIELGRUPPE DES UNTERNEHMERS: {target_audience}

AUFGABE: Generiere 4-6 Interview-Fragen die:
1. Auf SPEZIFISCHE Aussagen/Momente im Transkript Bezug nehmen (mit kurzem Zitat)
2. Den Unternehmer zu persönlichen Erfahrungen und Meinungen einladen
3. Auf LinkedIn-Posts mit echtem Mehrwert abzielen
4. Im Ton: neugierig, respektvoll, konkret — nicht generisch

Gib AUSSCHLIESSLICH valides JSON zurück, keine Erklärungen:
[
  {{
    "question_text": "Die konkrete Frage an den Unternehmer",
    "transcript_reference": "Kurzes Zitat aus dem Transkript das die Frage auslöst",
    "why_relevant": "Warum diese Frage für LinkedIn-Content wertvoll ist (1 Satz)",
    "target_angle": "story|opinion|how_to|controversy"
  }}
]"""

        api_url = f"{settings.litellm_base_url}/chat/completions"
        payload = {
            "model": "vertex/gemini-2.5-flash-lite@europe-central2",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                api_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.litellm_api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

        # Parse JSON from response
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if not json_match:
            logger.warning("LLM response did not contain JSON array")
            return []

        questions_raw = json.loads(json_match.group())
        questions = []
        for i, q in enumerate(questions_raw[:6]):
            if not q.get("question_text"):
                continue
            questions.append(
                {
                    "question_text": q.get("question_text", ""),
                    "transcript_reference": q.get("transcript_reference"),
                    "why_relevant": q.get("why_relevant"),
                    "target_angle": q.get("target_angle", "story"),
                    "order_index": i,
                }
            )

        return questions if len(questions) >= 2 else []

    except BudgetExceededError:
        raise
    except Exception as e:
        logger.warning(f"LLM smart question generation failed: {e}")
        return []


def _generate_from_analysis(analysis: dict, title: str, entrepreneur: dict) -> list[dict]:
    """Fallback: Template-basierte Fragen aus Analyse-Daten (kein LLM)."""
    questions = []
    idx = 0

    main_topic = analysis.get("main_topic", title or "dieses Thema")
    insights = analysis.get("key_insights", analysis.get("insights", []))
    hooks = analysis.get("hooks", [])
    industry = entrepreneur.get("industry", "Ihrer Branche")

    # Q1: Personal relevance to main topic
    questions.append(
        {
            "question_text": f"Wie erleben Sie das Thema '{main_topic}' in Ihrem Alltag als Unternehmer? Haben Sie eine konkrete Situation, die dieses Thema anschaulich macht?",
            "transcript_reference": None,
            "why_relevant": "Persönliche Erfahrung ist die Basis für authentischen LinkedIn-Content",
            "target_angle": "story",
            "order_index": idx,
        }
    )
    idx += 1

    # Q2: Industry-specific angle
    questions.append(
        {
            "question_text": f"Was bedeutet '{main_topic}' konkret für {industry}? Welche Auswirkung sehen Sie bei Ihren Kunden oder in Ihrem Team?",
            "transcript_reference": None,
            "why_relevant": "Branchenspezifischer Blickwinkel = Differenzierung vom generischen Content",
            "target_angle": "opinion",
            "order_index": idx,
        }
    )
    idx += 1

    # Q3: From first insight (if available)
    if insights and len(insights) > 0:
        insight = str(insights[0])[:150]
        questions.append(
            {
                "question_text": f"Im Beitrag wird erwähnt: '{insight[:100]}...'. Sehen Sie das in Ihrer Praxis auch so — oder erleben Sie das anders?",
                "transcript_reference": insight[:100],
                "why_relevant": "Direkte Reaktion auf konkrete Aussage erzeugt Meinungs-Content mit Substanz",
                "target_angle": "opinion",
                "order_index": idx,
            }
        )
        idx += 1

    # Q4: From second insight (if available)
    if insights and len(insights) > 1:
        insight2 = str(insights[1])[:150]
        questions.append(
            {
                "question_text": f"Sie haben wahrscheinlich schon praktische Erfahrungen mit '{str(main_topic)[:60]}' gesammelt. Welchen einen Rat würden Sie anderen Unternehmern geben, die damit anfangen?",
                "transcript_reference": insight2[:100] if insight2 else None,
                "why_relevant": "Konkreter Rat = How-To-Content mit echtem Mehrwert",
                "target_angle": "how_to",
                "order_index": idx,
            }
        )
        idx += 1

    # Q5: Controversy / contrarian view
    questions.append(
        {
            "question_text": f"Was ist die verbreitetste Fehlannahme über '{main_topic}' in {industry}? Worüber regen Sie sich manchmal auf, wenn Sie sehen wie andere damit umgehen?",
            "transcript_reference": None,
            "why_relevant": "Konträre Meinung erzeugt Engagement und positioniert als Thought Leader",
            "target_angle": "controversy",
            "order_index": idx,
        }
    )
    idx += 1

    # Q6: From hook (if available)
    if hooks:
        hook = str(hooks[0])[:200]
        questions.append(
            {
                "question_text": f"Wenn Sie einem Kunden erklären müssten warum '{main_topic}' für ihn relevant ist — wie würden Sie das in 2-3 Sätzen beschreiben?",
                "transcript_reference": hook[:100] if hook else None,
                "why_relevant": "Kundennahe Erklärung = Content der die Zielgruppe direkt anspricht",
                "target_angle": "how_to",
                "order_index": idx,
            }
        )

    return questions
