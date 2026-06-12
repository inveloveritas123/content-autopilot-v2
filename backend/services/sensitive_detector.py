"""
Sensitive-Topic-Detector (Issue #83)

Zwei-Schicht-Architektur:
  Schicht A — Pattern-basiert (instant, kein LLM-Kosten)
  Schicht B — LLM-Klassifikator (Haiku, nur bei Schicht-A-Trigger)

KEYWORD-LISTEN SIND KONSTANTEN — Änderungen erfordern Code-Review.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

Category = Literal[
    "politics", "religion", "hate", "health_claims", "financial_advice", "legal_advice"
]

# ============================================================
# KEYWORD-LISTEN (Code-Review-Pflicht bei Änderungen)
# ============================================================

KEYWORDS: dict[str, list[str]] = {
    "politics": [
        # Parteien
        "AfD",
        "CDU",
        "CSU",
        "SPD",
        "Grüne",
        "FDP",
        "Linke",
        "BSW",
        "NPD",
        "Pegida",
        # Ämter & Institutionen
        "Bundeskanzler",
        "Bundestag",
        "Bundesrat",
        "Bundesregierung",
        "Bundesminister",
        "Landtag",
        "Stadtrat",
        "Bürgermeister",
        "Abgeordneter",
        "Abgeordnete",
        "die Regierung",
        "Regierung vertuscht",
        "Regierung lügt",
        # Wahlbegriffe
        "Bundestagswahl",
        "Landtagswahl",
        "Kommunalwahl",
        "Volksabstimmung",
        "Wähler",
        "Wahlkampf",
        "Stimmzettel",
        "Wahlrecht",
        "Demokratie",
        "Opposition",
        # Politische Konzepte
        "Koalition",
        "Regierungspartei",
        "Rechtsextrem",
        "Linksextrem",
        "Nationalismus",
        "Faschismus",
        "Kommunismus",
        "Sozialismus",
        "Neoliberalismus",
        # Internationale Politik
        "Nato",
        "EU-Parlament",
        "Sanktionen",
        "Militäreinsatz",
        "Kriegsverbrechen",
        "Putsch",
        "Diktator",
        "Oligarch",
        "geopolitisch",
        "Staatsfeind",
        # Weitere
        "politische Meinung",
        "Parteinahme",
        "Ideologie",
        "Systemkritik",
        "Staatsversagen",
        "politischer Skandal",
        "Korruptionsaffäre",
        "Lobbyismus",
        "Parteifinanzierung",
        "Wahlbetrug",
        "Deep State",
        "Verschwörung",
        "Umsturz",
    ],
    "religion": [
        # Christentum
        "Jesus",
        "Christus",
        "Bibel",
        "Gott sei Dank",
        "Halleluja",
        "Ostern religiös",
        "Weihnachten religiös",
        "Papst",
        "Priester",
        "Kirche",
        "evangelisch",
        "katholisch",
        "Protestantismus",
        "Kreuzigung",
        "Auferstehung",
        "Sünde",
        "Sünder",
        # Islam
        "Allah",
        "Mohammed",
        "Koran",
        "Moschee",
        "Imam",
        "Ramadan",
        "Dschihad",
        "Scharia",
        "Muslimbruderschaft",
        "Islamist",
        "Islamophobie",
        # Judentum
        "Torah",
        "Talmud",
        "Synagoge",
        "Rabbiner",
        "Antisemitismus",
        "antisemitisch",
        "Holocaust leugnen",
        "Juden",
        "Judentum",
        # Sonstige Religionen
        "Hindu",
        "Hinduismus",
        "Buddha",
        "Buddhismus",
        "Nirwana",
        "Scientology",
        "Sekte",
        "Kult",
        "Okkultismus",
        "Satanismus",
        "Zeugen Jehovas",
        "Mormonen",
        "Abtreibung religiös",
        # Religiöser Konflikt
        "Gotteslästerung",
        "Blasphemie",
        "Kreuzzug",
        "Glaubenskrieg",
        "religiöse Verfolgung",
        "Inquisition",
        "Fundamentalismus",
    ],
    "hate": [
        # Diskriminierung (umschrieben, keine direkte Wiedergabe von Slurs)
        "Rassismus",
        "rassistisch",
        "Diskriminierung",
        "Fremdenfeindlichkeit",
        "Ausländerhass",
        "Islamphobie",
        "Homophobie",
        "homophob",
        "Transphobie",
        "Antisemitismus",
        "antisemitisch",
        "Frauenfeindlichkeit",
        "misogyn",
        # Hate-Vokabular (direkte Flags)
        "Volksverräter",
        "Lügenpresse",
        "Überfremdung",
        "Umvolkung",
        "Rassenmischung",
        "Untermenschen",
        "entartet",
        "lebensunwertes Leben",
        "Kulturmarxismus",
        "Gleichschaltung politisch",
        # Gewaltandrohung
        "sollte eliminiert werden",
        "gehört ausgerottet",
        "Tod den",
        "Mörder an die",
        # Body-Shaming + Hate
        "Fette",
        "Behinderte als Schimpfwort",
        "Geistig Zurückgebliebene",
        # Sexismus
        "Schlampe",
        "Hure politisch",
        "gehört ans Herd",
        "Weiber sollen",
    ],
    "health_claims": [
        # Heilsversprechen
        "heilt Krebs",
        "heilend",
        "Wunderheilung",
        "Wundermittel",
        "100% geheilt",
        "vollständig geheilt",
        "kuriert",
        "Heilmittel gegen",
        # Medizinische Fehlinformationen
        "Impfschaden",
        "Impfung verursacht",
        "5G Krankheit",
        "Chemtrails krank",
        "Mikrowellen gesundheitsschädlich",
        "Fluorid giftig",
        "Homöopathie heilt",
        "bewiesen heilend",
        "klinisch bewiesen ohne Quelle",
        # Diagnosen ohne Kontext
        "Du hast Krebs",
        "Du leidest an",
        "Diagnose stellen ohne",
        "Symptome von HIV",
        "Sie sind krank weil",
        # Verbotene Gesundheitsbehauptungen (DSGVO/HWG)
        "lindert Beschwerden garantiert",
        "beseitigt Krankheiten",
        "schützt vor Viren garantiert",
        "stärkt Immunsystem klinisch",
        "anti-aging klinisch bewiesen",
        "verjüngt nachweislich",
        "Alzheimer verhindern durch",
        "Diabetes heilen durch",
        "Blutdruck senken garantiert",
        "Herzinfarkt verhindern mit",
        # Nahrungsergänzung
        "Supplements heilen",
        "Vitamine heilen Krebs",
        "CBD heilt",
    ],
    "financial_advice": [
        # Konkrete Anlageempfehlungen
        "Kaufen Sie jetzt",
        "kaufe sofort Aktien",
        "investiere in",
        "sichere Rendite",
        "garantierte Rendite",
        "risikofreie Anlage",
        "100% Gewinn",
        "kann nicht verlieren",
        "sicheres Investment",
        "Geheimtipp Aktie",
        # Spezifische Wertpapiere mit Empfehlung
        "Bitcoin kaufen jetzt",
        "Ethereum kaufen",
        "Krypto-Tipp",
        "Pump and Dump",
        "meine Aktienempfehlung",
        "Insiderwissen Börse",
        # Finanzversprechen
        "reich werden schnell",
        "passives Einkommen garantiert",
        "finanzielle Freiheit sofort",
        "in 30 Tagen Millionär",
        "Altersvorsorge optimal",
        "steuerfreies Einkommen legal",
        # Schuldentipps
        "umgehe Steuer legal",
        "Steuern vermeiden so",
        "Steuern vermeiden legal",
        "Schwarzgeld legal",
        "Kapitalflucht",
        # Versicherungen
        "unnötige Versicherung kündigen alle",
        "Versicherungsbetrug",
        "Schadensfall manipulieren",
    ],
    "legal_advice": [
        # Konkrete Rechtsberatung
        "Sie haben Anspruch auf",
        "Sie haben rechtlichen Anspruch",
        "klagen Sie ohne Anwalt",
        "rechtlich durchsetzen ohne Anwalt",
        "klagen Sie jetzt",
        "Klage einreichen einfach",
        "Anwalt unnötig",
        "Gericht gewinnen so",
        "Richter beeinflussen",
        # Vertragsrecht
        "Vertrag brechen legal",
        "Kündigung anfechten so",
        "Mietrecht: kündigen ohne Grund",
        "Arbeitsrecht umgehen",
        # Strafrecht
        "illegal aber legal wenn",
        "Straftat verjährt automatisch",
        "Polizei muss nicht",
        "Hausdurchsuchung ablehnen so",
        "Strafanzeige erstatten gegen alle",
        "einstweilige Verfügung",
        # Marken/IP
        "Marke anmelden ohne Anwalt garantiert",
        "Copyright umgehen legal",
        "Patent stehlen legal",
        "geistiges Eigentum übertragen so",
        # Datenschutz
        "DSGVO umgehen",
        "Datenschutz ignorieren legal",
        "Nutzer ohne Einwilligung tracken",
    ],
}

# Kategorien mit hartem Default (auch bei niedrigem Confidence eskalieren)
HARD_ESCALATION_CATEGORIES = {"health_claims", "financial_advice", "legal_advice"}
HARD_ESCALATION_CONFIDENCE_THRESHOLD = 0.3  # tiefer als normal (0.6)
NORMAL_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class FlaggedPhrase:
    phrase: str
    category: str


@dataclass
class SensitiveResult:
    is_sensitive: bool
    categories: list[str] = field(default_factory=list)
    confidence: float = 0.0
    flagged_phrases: list[FlaggedPhrase] = field(default_factory=list)
    detection_layer: str = "pattern"  # 'pattern' or 'llm'
    severity: str = "low"  # low/medium/high


def _pattern_check(text: str) -> tuple[list[str], list[FlaggedPhrase], float]:
    """Schicht A: Keyword-Matching (case-insensitive, Wortgrenzen)."""
    text_lower = text.lower()
    found_categories: set[str] = set()
    found_phrases: list[FlaggedPhrase] = []

    for category, keywords in KEYWORDS.items():
        for kw in keywords:
            kw_lower = kw.lower()
            # For single words: use word boundary matching
            # For multi-word phrases: use substring matching (phrases are specific enough)
            if " " in kw_lower:
                matched = kw_lower in text_lower
            else:
                # \b doesn't work well with German umlauts in re, use manual approach:
                # check that character before and after the match is not word-like
                idx = text_lower.find(kw_lower)
                matched = False
                while idx != -1:
                    start_ok = idx == 0 or not text_lower[idx - 1].isalpha()
                    end_idx = idx + len(kw_lower)
                    end_ok = end_idx >= len(text_lower) or not text_lower[end_idx].isalpha()
                    if start_ok and end_ok:
                        matched = True
                        break
                    idx = text_lower.find(kw_lower, idx + 1)

            if matched:
                found_categories.add(category)
                found_phrases.append(FlaggedPhrase(phrase=kw, category=category))

    if not found_categories:
        return [], [], 0.0

    match_count = len(found_phrases)
    confidence = min(0.5 + match_count * 0.1, 0.95)
    return list(found_categories), found_phrases, confidence


def _llm_check(text: str) -> tuple[list[str], list[FlaggedPhrase], float]:
    """Schicht B: LLM-Klassifikator via Router (nur bei Schicht-A-Trigger)."""
    from services.pipeline_llm import call_pipeline_llm

    system_prompt = (
        "Du bist ein Content-Moderator. Klassifiziere den Post auf sensible Themen. "
        "Antworte NUR mit einem JSON-Objekt, KEIN anderer Text."
    )
    user_prompt = f"""Analysiere den folgenden LinkedIn-Post auf sensible Themen.

Mögliche Kategorien: politics, religion, hate, health_claims, financial_advice, legal_advice

Format:
{{
  "is_sensitive": true/false,
  "categories": ["kategorie1"],
  "confidence": 0.0-1.0,
  "flagged_phrases": [{{"phrase": "...", "category": "..."}}]
}}

Post:
{text[:2000]}"""

    try:
        result = call_pipeline_llm(
            prompt_key="SENSITIVE_DETECT",
            system_prompt=system_prompt,
            user_content=user_prompt,
            tenant_id="",
        )
        raw = result.text.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        phrases = [
            FlaggedPhrase(p["phrase"], p["category"]) for p in data.get("flagged_phrases", [])
        ]
        return data.get("categories", []), phrases, float(data.get("confidence", 0.5))
    except Exception as e:
        logger.warning(f"[SensitiveDetector] LLM check failed: {e}")
        return [], [], 0.0


def _compute_severity(categories: list[str], confidence: float) -> str:
    if any(c in HARD_ESCALATION_CATEGORIES for c in categories):
        return "high"
    if confidence >= 0.8 or len(categories) >= 2:
        return "medium"
    return "low"


def detect_sensitive_topics(post_text: str, use_llm: bool = True) -> SensitiveResult:
    """
    Haupteinstiegspunkt. Gibt SensitiveResult zurück.

    Logik:
    1. Schicht A (Pattern) — immer
    2. Wenn Schicht A triggert: Schicht B (LLM) für höhere Präzision
    3. Ergebnis kombinieren: is_sensitive wenn Confidence über Schwellwert
    """
    categories_a, phrases_a, confidence_a = _pattern_check(post_text)

    if not categories_a:
        return SensitiveResult(is_sensitive=False, detection_layer="pattern")

    detection_layer = "pattern"
    categories = categories_a
    phrases = phrases_a
    confidence = confidence_a

    if use_llm:
        try:
            categories_b, phrases_b, confidence_b = _llm_check(post_text)
            if categories_b:
                # Merge: LLM overrides confidence, union of categories
                categories = list(set(categories_a) | set(categories_b))
                # De-duplicate phrases by phrase text
                seen = {p.phrase for p in phrases_a}
                phrases = phrases_a + [p for p in phrases_b if p.phrase not in seen]
                confidence = max(confidence_a, confidence_b)
                detection_layer = "llm"
            else:
                # LLM found nothing — lower confidence
                confidence = confidence_a * 0.7
        except Exception as e:
            logger.warning(f"[SensitiveDetector] LLM layer error: {e}")

    # Determine if we actually flag it
    hard_hit = any(c in HARD_ESCALATION_CATEGORIES for c in categories)
    threshold = HARD_ESCALATION_CONFIDENCE_THRESHOLD if hard_hit else NORMAL_CONFIDENCE_THRESHOLD
    is_sensitive = confidence >= threshold

    severity = _compute_severity(categories, confidence) if is_sensitive else "low"

    return SensitiveResult(
        is_sensitive=is_sensitive,
        categories=categories,
        confidence=round(confidence, 2),
        flagged_phrases=phrases,
        detection_layer=detection_layer,
        severity=severity,
    )
