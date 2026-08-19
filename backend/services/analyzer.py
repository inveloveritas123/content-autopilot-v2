# AUDITED-2026-08-19 (louis-telegram-zwei-fehler): Tiefen-Audit, Datei vollstaendig gelesen; Validierungsluecke bei Listen-Elementtypen gefunden und geschlossen.
import logging

from services.llm import BudgetExceededError, llm_service

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """Du bist ein Content-Analyst. Analysiere den folgenden Inhalt und extrahiere:
1. summary: Executive Summary in 3-5 Sätzen (Deutsch)
2. key_points: Die 5-8 wichtigsten Kernaussagen als Array
3. tags: 5-10 relevante Tags fuer Kategorisierung
4. trend_score: 1-10 wie aktuell/trending ist das Thema (10 = breaking news)
5. content_angles: 3 Vorschlaege fuer Content-Winkel die ein Unternehmer daraus machen koennte
6. hashtags: 5-8 Social-Media-Hashtags mit # Zeichen (deutsch und englisch gemischt)
7. topic_pitch: Ein knackiger Themenvorschlag (1-2 Saetze) fuer einen LinkedIn-Beitrag
8. topic_title: Ein kurzer, praegnanter Titel fuer das Thema (max 8 Woerter)
9. controversial_takes: 2-3 kontroverse Positionen die man aus dem Inhalt ableiten koennte
10. target_audience: Fuer wen ist das Thema besonders relevant? (2-3 Zielgruppen)

WICHTIG — Format der Listen: key_points, tags, content_angles, hashtags,
controversial_takes und target_audience sind Arrays aus EINFACHEN STRINGS,
niemals aus Objekten.
  Richtig: "key_points": ["Erste Kernaussage", "Zweite Kernaussage"]
  Falsch:  "key_points": [{"point": "Erste Kernaussage"}]

Antworte NUR als JSON. Kein Markdown, keine Erklaerung."""

# Source-Type-spezifische Kontext-Hinweise für bessere Analyse
SOURCE_TYPE_CONTEXT = {
    "youtube": "Dies ist ein Video-Transkript. Der Ton ist umgangssprachlich, mit Wiederholungen und Füllwörtern. Fokussiere auf die Kernaussagen hinter dem gesprochenen Text.",
    "rss": "Dies ist ein Blog-Artikel oder News-Beitrag. Der Text ist bereits redigiert und strukturiert. Analysiere Argumente, Daten und Handlungsempfehlungen.",
    "podcast": "Dies ist ein Podcast-Transkript. Der Ton ist conversational mit mehreren Sprechern. Identifiziere die Hauptthesen und einprägsame Zitate.",
    "article": "Dies ist ein Fachartikel. Fokussiere auf fachliche Aussagen, Statistiken und praktische Empfehlungen.",
}


async def analyze_transcript(
    transcript_text: str,
    source_type: str = "youtube",
    title: str = "",
    routing_override: dict | None = None,
) -> dict | None:
    """Analyze content using Gemini Flash and return structured analysis.

    HINWEIS: Keine Truncation mehr — Gemini Flash 2.0 hat 1M Token Kontext.
    Ein typisches Transkript hat 7K-27K Tokens (2-4% des Limits).
    """
    try:
        # Kontext basierend auf Quelltyp
        type_hint = SOURCE_TYPE_CONTEXT.get(source_type, "")
        title_hint = f"\nTitel: {title}" if title else ""

        prompt = f"""Analysiere folgenden Inhalt (Quelltyp: {source_type}):
{type_hint}{title_hint}

--- INHALT ---
{transcript_text}
--- ENDE ---"""

        result = await llm_service.complete_json(
            prompt=prompt,
            system=ANALYSIS_SYSTEM_PROMPT,
            model="gemini-flash",
            purpose="analysis",
            routing_override=routing_override,
        )

        # Validate and fill missing keys
        expected_keys = {"summary", "key_points", "tags", "trend_score", "content_angles"}
        if not expected_keys.issubset(set(result.keys())):
            missing = expected_keys - set(result.keys())
            logger.warning(f"Analysis missing keys: {missing}")
            for key in missing:
                if key == "trend_score":
                    result[key] = 5
                elif key == "summary":
                    result[key] = "Analyse unvollstaendig"
                elif key in ("topic_pitch", "topic_title"):
                    result[key] = ""
                else:
                    result[key] = []

        # Listenfelder auf reine String-Listen normalisieren.
        #
        # ⛔ Die Pruefung oben sichert nur die ANWESENHEIT der Keys, nie den Typ
        # ihrer ELEMENTE. Der Prompt verlangt "als Array" — eine Liste von
        # Objekten (`[{"point": "..."}]`) erfuellt das und ist damit eine
        # zulaessige Antwort. Verbraucher wie `content_generator` setzen aber
        # Strings voraus und rufen `", ".join(...)` darauf auf.
        #
        # Ohne diese Zeilen wandert die unpassende Form als `source_items.
        # analysis` (JSONB) in die DB und toetet JEDEN spaeteren Lauf mit
        # `TypeError: sequence item 0: expected str instance, dict found` —
        # im Live-Log von Louis' Container 1722-mal in 7 Tagen, immer identisch.
        # Ein Retry half nie, weil die unbrauchbare Analyse persistent war.
        # Repariert wird deshalb der Vertrag, nicht das Modell.
        from services.analysis_normalize import normalize_text_list

        for _feld in (
            "key_points",
            "content_angles",
            "tags",
            "hashtags",
            "controversial_takes",
            "target_audience",
        ):
            if _feld in result:
                result[_feld] = normalize_text_list(result[_feld], feld=_feld)

        # Ensure all optional fields exist
        if "hashtags" not in result:
            result["hashtags"] = [f"#{t}" for t in result.get("tags", [])[:5]]
        if "topic_pitch" not in result:
            result["topic_pitch"] = result.get("summary", "")[:200]
        if "topic_title" not in result:
            result["topic_title"] = ""
        if "controversial_takes" not in result:
            result["controversial_takes"] = []
        if "target_audience" not in result:
            result["target_audience"] = []

        # Metadaten für späteres Lernen
        result["_meta"] = {
            "source_type": source_type,
            "input_length": len(transcript_text),
            "analyzed_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Analysis complete ({source_type}): {len(result.get('key_points', []))} key points, "
            f"trend_score={result.get('trend_score')}, input={len(transcript_text)} chars"
        )
        return result

    except BudgetExceededError:
        raise  # Propagate to caller for circuit breaker handling
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return None
