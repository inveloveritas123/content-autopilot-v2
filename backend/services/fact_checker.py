import logging

from services.llm import llm_service

logger = logging.getLogger(__name__)

FACT_CHECK_SYSTEM = """Du bist ein Faktenpruefer. Pruefe die folgenden Behauptungen auf ihre Richtigkeit.
Fuer jede Behauptung, gib zurueck:
- claim: Die Behauptung
- status: "confirmed" (belegt), "partially" (teilweise korrekt), oder "unverified" (nicht verifizierbar)
- source: Kurzinfo zur Quelle oder Begruendung

Antworte NUR als JSON-Array. Kein Markdown, keine Erklaerung."""


async def check_facts(key_points: list[str], max_claims: int = 3) -> list[dict] | None:
    """
    Fact-check the top claims from video analysis.
    Uses Claude Sonnet for higher quality.
    """
    if not key_points:
        return []

    claims = key_points[:max_claims]
    claims_text = "\n".join(f"{i+1}. {claim}" for i, claim in enumerate(claims))

    prompt = f"""Pruefe folgende Behauptungen auf ihre Richtigkeit:

{claims_text}

Gib fuer jede Behauptung ein JSON-Objekt mit claim, status und source zurueck.
Antworte als JSON-Array."""

    try:
        result = await llm_service.complete_json(
            prompt=prompt,
            system=FACT_CHECK_SYSTEM,
            model="claude-sonnet",
        )
        if isinstance(result, list):
            logger.info(f"Fact-checked {len(result)} claims")
            return result
        elif isinstance(result, dict) and "claims" in result:
            return result["claims"]
        return [result]
    except Exception as e:
        logger.error(f"Fact check failed: {e}")
        return None
