import logging
from typing import Optional

from services.llm import llm_service

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """Du bist ein Content-Analyst. Analysiere dieses Video-Transkript und extrahiere:
1. summary: Executive Summary in 3-5 Saetzen (Deutsch)
2. key_points: Die 5-8 wichtigsten Kernaussagen als Array
3. tags: 5-10 relevante Tags fuer Kategorisierung
4. trend_score: 1-10 wie aktuell/trending ist das Thema (10 = breaking news)
5. content_angles: 3 Vorschlaege fuer Content-Winkel die ein Unternehmen daraus machen koennte
6. hashtags: 5-8 Social-Media-Hashtags mit # Zeichen (deutsch und englisch gemischt)
7. topic_pitch: Ein knackiger Themenvorschlag (1-2 Saetze) fuer einen Newsletter-Beitrag zu diesem Video
8. topic_title: Ein kurzer, praegnanter Titel fuer das Thema (max 8 Woerter)

Antworte NUR als JSON. Kein Markdown, keine Erklaerung."""


async def analyze_transcript(transcript_text: str) -> Optional[dict]:
    """Analyze a transcript using Gemini Flash and return structured analysis."""
    try:
        result = await llm_service.complete_json(
            prompt=f"Analysiere folgendes Transkript:\n\n{transcript_text[:15000]}",
            system=ANALYSIS_SYSTEM_PROMPT,
            model="gemini-flash",
        )
        # Validate expected keys
        expected_keys = {"summary", "key_points", "tags", "trend_score", "content_angles"}
        if not expected_keys.issubset(set(result.keys())):
            missing = expected_keys - set(result.keys())
            logger.warning(f"Analysis missing keys: {missing}")
            for key in missing:
                if key == "trend_score":
                    result[key] = 5
                elif key == "summary":
                    result[key] = "Analyse unvollstaendig"
                elif key == "topic_pitch":
                    result[key] = ""
                elif key == "topic_title":
                    result[key] = ""
                else:
                    result[key] = []

        # Ensure hashtags and topic fields exist
        if "hashtags" not in result:
            result["hashtags"] = [f"#{t}" for t in result.get("tags", [])[:5]]
        if "topic_pitch" not in result:
            result["topic_pitch"] = result.get("summary", "")[:200]
        if "topic_title" not in result:
            result["topic_title"] = ""

        logger.info(f"Analysis complete: {len(result.get('key_points', []))} key points, trend_score={result.get('trend_score')}")
        return result
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return None
