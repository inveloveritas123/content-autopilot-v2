"""
Echter Struktur-/Regel-Scorer fuer den Quality-Gate (Issue #38, Chunk 1).

Ersetzt den len/10-Stub durch gewichtete Signalauswertung:
  - Laengen-Baender (zu kurz / ideal / zu lang)
  - Caps-Ratio (Spam-Erkennung)
  - Satzzeichen / Satzstruktur
  - CTA / Hook-Praesenz (Fragezeichen am Ende / Handlungsaufforderung)
  - Hashtag-Sanity (Spam-Erkennung)
  - Branchen-Disclaimer (recht: Rechtsberatung, finanzen: Anlageberatung)
  - PII-/Eigenname-Heuristik (E2-nah)

Semantische LLM-Schicht: Issue #38 Chunk 2 (separat, nicht hier).

Kontrakt (stabil halten):
  quality_gate_check(post_text: str, branche: str) -> {
      "passed": bool,
      "score": float (0..100),
      "violations": list[str],
      "threshold": float,
      "branche": str,
  }

Dep-Frei: Nur stdlib (re, math, pathlib) + pyyaml (vorhanden im venv).
Kein Import von sqlalchemy / services.llm / pipeline_llm / config / fastapi.
Py3.9-kompatibel (kein datetime.UTC, kein X | Y union syntax in isinstance).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config-Loader
# ---------------------------------------------------------------------------

# Pfad zu quality_standards/ relativ zu dieser Datei, robust gegen file-import
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "quality_standards"

# In-Code-Defaults — werden verwendet wenn YAML-Datei fehlt oder nicht parsbar
_INCODE_DEFAULTS: dict[str, Any] = {
    "_generic": {
        "threshold": 55.0,
        "length": {"min_chars": 200, "ideal_min": 350, "ideal_max": 2000, "max_chars": 3000},
        "caps": {"max_ratio": 0.30},
        "hashtags": {"max_count": 10},
        "cta": {"required": False},
        "disclaimer": {"required": False},
        "weights": {
            "length": 35,
            "structure": 25,
            "cta_hook": 15,
            "caps_ok": 15,
            "hashtag_ok": 10,
        },
    },
    "handwerk": {
        "threshold": 60.0,
        "length": {"min_chars": 200, "ideal_min": 350, "ideal_max": 2000, "max_chars": 3000},
        "caps": {"max_ratio": 0.30},
        "hashtags": {"max_count": 10},
        "cta": {"required": False},
        "disclaimer": {"required": False},
        "weights": {
            "length": 35,
            "structure": 25,
            "cta_hook": 15,
            "caps_ok": 15,
            "hashtag_ok": 10,
        },
    },
    "recht": {
        "threshold": 65.0,
        "length": {"min_chars": 200, "ideal_min": 400, "ideal_max": 2000, "max_chars": 3000},
        "caps": {"max_ratio": 0.30},
        "hashtags": {"max_count": 10},
        "cta": {"required": False},
        "disclaimer": {
            "required": True,
            "min_chars_for_disclaimer": 400,
            "phrases": [
                "keine rechtsberatung",
                "kein rechtsberatung",
                "stellt keine rechtsberatung",
                "keine juristische",
                "nur zur information",
                "individuelle beratung",
                "anwalt konsultieren",
                "fachanwalt",
                "rechtsanwalt hinzuziehen",
            ],
        },
        "weights": {
            "length": 30,
            "structure": 20,
            "cta_hook": 10,
            "caps_ok": 15,
            "hashtag_ok": 5,
            "disclaimer": 20,
        },
    },
    "finanzen": {
        "threshold": 70.0,
        "length": {"min_chars": 200, "ideal_min": 400, "ideal_max": 2000, "max_chars": 3000},
        "caps": {"max_ratio": 0.30},
        "hashtags": {"max_count": 10},
        "cta": {"required": False},
        "disclaimer": {
            "required": True,
            "min_chars_for_disclaimer": 400,
            "phrases": [
                "keine anlageberatung",
                "kein anlageberatung",
                "keine finanzberatung",
                "keine steuerberatung",
                "nicht als anlageberatung",
                "allgemeine finanzbildung",
                "individuelle beratung",
                "finanzberater",
                "honorarberater",
                "steuerberater hinzuziehen",
            ],
        },
        "weights": {
            "length": 30,
            "structure": 20,
            "cta_hook": 10,
            "caps_ok": 15,
            "hashtag_ok": 5,
            "disclaimer": 20,
        },
    },
}


def _load_branche_config(branche: str) -> dict[str, Any]:
    """Laedt Branchen-Config aus YAML. Faellt auf In-Code-Defaults zurueck.

    NIE crashen — der file-importierte Scorer muss immer funktionieren.
    """
    # Whitelist-Guard (Defense-in-Depth): nur bekannte Branchen dürfen einen
    # Dateipfad bilden — verhindert Path-Traversal über ein evtl. tenant-abgeleitetes
    # `branche`. Unbekannte Branche → _generic-Default, kein Dateizugriff.
    if branche not in _INCODE_DEFAULTS:
        return _INCODE_DEFAULTS["_generic"]

    default_cfg: dict[str, Any] = _INCODE_DEFAULTS[branche]
    yaml_path = _CONFIG_DIR / f"{branche}.yml"

    if not yaml_path.exists():
        return default_cfg

    try:
        import yaml

        with open(yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return default_cfg
        # Merge: YAML ueberschreibt Defaults, fehlende Keys bleiben Default
        merged: dict[str, Any] = {}
        for key, default_val in default_cfg.items():
            yaml_val = data.get(key)
            if yaml_val is None:
                merged[key] = default_val
            elif isinstance(default_val, dict) and isinstance(yaml_val, dict):
                sub: dict[str, Any] = {}
                for sub_key, sub_default in default_val.items():
                    sub[sub_key] = yaml_val.get(sub_key, sub_default)
                # Additive keys from yaml (e.g. phrases)
                for sub_key in yaml_val:
                    if sub_key not in sub:
                        sub[sub_key] = yaml_val[sub_key]
                merged[key] = sub
            else:
                merged[key] = yaml_val
        return merged
    except Exception:
        return default_cfg


# ---------------------------------------------------------------------------
# Signal extractors
# ---------------------------------------------------------------------------

# Regex: PII-Heuristik — einfache Namensmuster (Grossbuchstabe + Kleinbuchstaben)
# und Ortsmuster (z.B. "in Berlin", "bei Familie", "Herr/Frau X")
_PII_PATTERNS = [
    re.compile(r"\bFamilie\s+[A-Z][a-z]+\b"),  # "Familie Mueller"
    re.compile(r"\b(Herr|Frau|Dr\.|Prof\.)\s+[A-Z][a-z]+\b"),  # "Herr Schmidt"
    re.compile(r"\b[A-Z][a-z]+(?:strasse|straße|str\.|weg|gasse|platz)\b"),  # Strassennamen
]

# CTA-Signale: Fragezeichen am Ende eines Satzes / typische CTA-Phrasen
# Alle Alternativen in einer Gruppe mit einheitlichem (?i)-Flag am Anfang
_CTA_RE = re.compile(
    r"(?i)"
    r"(\?\s*$"
    r"|\?\s*\n"
    r"|was (?:denkt|findet|meint)"
    r"|wie (?:seht|macht|handhabt) ihr"
    r"|habt ihr(?:\s+schon)?"
    r"|welche[rns]?\s+\w+\s+habt"
    r"|wer (?:hat|setzt|nutzt)"
    r"|stimmt ihr zu"
    r"|eure meinung"
    r")",
    re.MULTILINE,
)

# Hook-Signale am Anfang (erste 150 Zeichen)
_HOOK_RE = re.compile(
    r"(?i)"
    r"^(warum|wie|was|wer|welche"
    r"|der (?:groesste|grosse|wichtigste|haeufi)"
    r"|\d+\s+(?:fehler|tipps?|gruende?|fragen?|schritte?)"
    r"|das konzept|die wahrheit|ein ehrlicher?"
    r")"
)


def _length_score(text: str, cfg_len: dict[str, Any]) -> tuple[float, list[str]]:
    """Score-Anteil fuer Laenge (0..1) + Violations."""
    n = len(text)
    violations: list[str] = []
    min_chars = cfg_len.get("min_chars", 200)
    ideal_min = cfg_len.get("ideal_min", 350)
    ideal_max = cfg_len.get("ideal_max", 2000)
    max_chars = cfg_len.get("max_chars", 3000)

    if n < min_chars:
        violations.append("too_short")
        # Score proportional zur Mindestlaenge, maximal 0.4
        score = min(0.4, n / min_chars * 0.4)
        return score, violations

    if n > max_chars:
        violations.append("too_long")
        score = 0.5
        return score, violations

    # Gaussfoermige Bewertung im Idealbereich
    if ideal_min <= n <= ideal_max:
        score = 1.0
    elif n < ideal_min:
        # Linearer Anstieg zwischen min_chars und ideal_min
        score = 0.6 + 0.4 * (n - min_chars) / max(1, ideal_min - min_chars)
    else:
        # Leichter Abfall ueber ideal_max
        overshoot = (n - ideal_max) / max(1, max_chars - ideal_max)
        score = 1.0 - 0.3 * overshoot

    return max(0.0, min(1.0, score)), violations


def _caps_score(text: str, max_ratio: float) -> tuple[float, list[str]]:
    """Score-Anteil fuer Caps-Ratio (0..1) + Violations."""
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return 0.5, []
    caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
    violations: list[str] = []
    if caps_ratio > max_ratio:
        violations.append("excessive_caps")
        # Je mehr Caps, desto schlechter
        score = max(0.0, 1.0 - (caps_ratio / max(0.001, max_ratio)) * 0.8)
        return score, violations
    # Penalize aber weniger stark wenn nah an max_ratio
    score = 1.0 - 0.2 * (caps_ratio / max(0.001, max_ratio))
    return max(0.0, min(1.0, score)), []


def _structure_score(text: str) -> tuple[float, list[str]]:
    """Score-Anteil fuer Satzstruktur (0..1) + Violations.

    Prueft:
    - Vorhandensein von Satzzeichen (.!?)
    - Absatzstruktur (Newlines)
    - Interpunktionsdichte
    """
    violations: list[str] = []

    # Keine Satzzeichen -> schwerer Fehler
    if not re.search(r"[.!?]", text):
        violations.append("no_sentence_terminators")
        return 0.1, violations

    # Satzzeichen-Dichte: Anzahl Satzzeichen / Wortzahl
    words = text.split()
    word_count = max(1, len(words))
    terminators = len(re.findall(r"[.!?]", text))
    sentence_density = terminators / word_count

    # Ideal: ca. 1 Satzzeichen pro 10-15 Woerter
    # Zu wenig: monotoner Text; zu viel: Fragmente
    if 0.03 <= sentence_density <= 0.15:
        density_score = 1.0
    elif sentence_density < 0.03:
        density_score = max(0.3, sentence_density / 0.03)
    else:
        density_score = max(0.5, 1.0 - (sentence_density - 0.15) * 2)

    # Absatzstruktur: Newlines deuten auf strukturierten Post hin
    newline_count = text.count("\n")
    if newline_count >= 3:
        structure_bonus = 1.0
    elif newline_count >= 1:
        structure_bonus = 0.7
    else:
        structure_bonus = 0.4

    score = 0.6 * density_score + 0.4 * structure_bonus
    return max(0.0, min(1.0, score)), violations


def _cta_hook_score(text: str) -> float:
    """Score-Anteil fuer CTA / Hook-Praesenz (0..1)."""
    score = 0.0
    # CTA: Fragezeichen oder Aufruf am Ende
    if _CTA_RE.search(text):
        score += 0.7
    # Hook am Anfang (erste 150 Zeichen)
    if _HOOK_RE.search(text[:150]):
        score += 0.3
    return min(1.0, score)


def _hashtag_score(text: str, max_count: int) -> tuple[float, list[str]]:
    """Score-Anteil fuer Hashtag-Sanity (0..1) + Violations."""
    hashtags = re.findall(r"#\w+", text)
    count = len(hashtags)
    violations: list[str] = []
    if count > max_count:
        violations.append("hashtag_spam")
        return 0.2, violations
    return 1.0, violations


def _disclaimer_score(text: str, disclaimer_cfg: dict[str, Any]) -> tuple[float, list[str]]:
    """Score-Anteil fuer Branchen-Disclaimer (0..1) + Violations."""
    required = disclaimer_cfg.get("required", False)
    if not required:
        return 1.0, []

    min_chars = disclaimer_cfg.get("min_chars_for_disclaimer", 400)
    if len(text) < min_chars:
        # Kurze Posts brauchen keinen Disclaimer
        return 1.0, []

    phrases = disclaimer_cfg.get("phrases", [])
    text_lower = text.lower()
    found = any(phrase in text_lower for phrase in phrases)

    if not found:
        branche_hint = ""
        if "rechts" in str(phrases) or "fachanwalt" in str(phrases):
            branche_hint = "missing_legal_disclaimer"
        elif "anlage" in str(phrases) or "finanzberater" in str(phrases):
            branche_hint = "missing_financial_disclaimer"
        else:
            branche_hint = "missing_disclaimer"
        return 0.0, [branche_hint]

    return 1.0, []


def _pii_heuristic_check(text: str) -> list[str]:
    """Heuristischer PII-/Eigenname-Check. Gibt Violations zurueck (E2-nah).

    Prueft auf Vollnamen (Familie X, Herr/Frau X) und Strassennamen.
    Ist heuristisch — kein Ersatz fuer echtes NER.
    """
    violations: list[str] = []
    for pattern in _PII_PATTERNS:
        if pattern.search(text):
            violations.append("potential_pii_reference")
            break
    return violations


# ---------------------------------------------------------------------------
# Haupt-Scorer
# ---------------------------------------------------------------------------

# Cache fuer geladene Configs (Lifetime des Python-Prozesses)
_config_cache: dict[str, dict[str, Any]] = {}


def clear_config_cache() -> None:
    """Test-Hilfsfunktion: Cache leeren fuer saubere Test-Isolation."""
    _config_cache.clear()


def _get_config(branche: str) -> dict[str, Any]:
    """Gibt geladene/gecachte Config zurueck."""
    if branche not in _config_cache:
        _config_cache[branche] = _load_branche_config(branche)
    return _config_cache[branche]


def _anti_ki_hits(text: str) -> list[str]:
    """Floskel-Treffer aus dem voice_gate — ohne den Em-Dash-Hinweis.

    ⛔ FAIL-OPEN, bewusst: Faellt der Detektor aus (Import-Fehler, kaputte
    Blocklist), darf das den Versandpfad nicht blockieren — dieselbe Doktrin,
    die session_post_task fuer das Gate insgesamt anwendet. Ein leerer Treffersatz
    bedeutet dann "nicht gemessen", und der Score bleibt unveraendert gut. Das ist
    die richtige Richtung: lieber ein ungeprueft durchgelassener Post als gar keiner.
    """
    try:
        from services.voice_gate import check_anti_ki_phrases
    except Exception:  # pragma: no cover — Importfehler nur bei kaputtem Deployment
        return []
    try:
        hits = check_anti_ki_phrases(text)
    except Exception:  # pragma: no cover
        return []
    # Der Em-Dash-Treffer ist im voice_gate selbst als schwaches Signal markiert.
    return [h for h in hits if not h.startswith("[Typografie-Hinweis]")]


def _anti_ki_score(hits: list[str]) -> tuple[float, list[str]]:
    """Treffer -> (Score 0..1, Violations).

    Stufung bewusst grob — der Detektor liefert exakte Phrasen, keine
    Wahrscheinlichkeiten: 0 Treffer = sauber, 1-2 = Abzug, ab 3 = Block.
    """
    n = len(hits)
    if n == 0:
        return 1.0, []
    if n >= 3:
        return 0.0, ["ki_phrasen_massiv"]
    # 1 Treffer -> 0.5, 2 -> 0.25
    return (0.5 if n == 1 else 0.25), ["ki_phrasen"]


def quality_gate_check(post_text: str, branche: str) -> dict[str, Any]:
    """Bewertet einen LinkedIn-Post gegen branchenspezifische Quality-Standards.

    Args:
        post_text: Der zu pruefende LinkedIn-Post.
        branche:   Branchenkenner (handwerk | recht | finanzen | _generic).

    Returns:
        {
            "passed": bool,
            "score": float,        # 0..100
            "violations": list[str],
            "threshold": float,
            "branche": str,
        }

    Struktur-/Regel-Scorer (Chunk 1). Semantische LLM-Schicht: Chunk 2 (#38).
    """
    cfg = _get_config(branche)
    threshold: float = float(cfg.get("threshold", 55.0))

    if not post_text or not post_text.strip():
        return {
            "passed": False,
            "score": 0.0,
            "violations": ["empty_post"],
            "threshold": threshold,
            "branche": branche,
        }

    violations: list[str] = []

    # -- Signal 1: Laenge --
    len_score, len_violations = _length_score(post_text, cfg.get("length", {}))
    violations.extend(len_violations)

    # -- Signal 2: Caps-Ratio --
    caps_max = cfg.get("caps", {}).get("max_ratio", 0.30)
    caps_score, caps_violations = _caps_score(post_text, caps_max)
    violations.extend(caps_violations)

    # -- Signal 3: Satzstruktur --
    struct_score, struct_violations = _structure_score(post_text)
    violations.extend(struct_violations)

    # -- Signal 4: CTA / Hook --
    cta_score = _cta_hook_score(post_text)

    # -- Signal 5: Hashtag-Sanity --
    hashtag_max = cfg.get("hashtags", {}).get("max_count", 10)
    hashtag_score, hashtag_violations = _hashtag_score(post_text, hashtag_max)
    violations.extend(hashtag_violations)

    # -- Signal 6: Disclaimer (branchen-spezifisch) --
    disclaimer_cfg = cfg.get("disclaimer", {})
    disc_score, disc_violations = _disclaimer_score(post_text, disclaimer_cfg)
    violations.extend(disc_violations)

    # -- Signal 7: PII-Heuristik (weicher Check, kein Score-Killer) --
    pii_violations = _pii_heuristic_check(post_text)
    violations.extend(pii_violations)

    # -- Signal 8: KI-Floskeln (2026-08-21) --
    # ⛔ WARUM DIESES SIGNAL NACHGEZOGEN WURDE: Der Scorer mass bis hier
    #   ausschliesslich FORM (Laenge, Caps, Absaetze, Hashtags). Gemessen an vier
    #   realistischen Handwerker-Posts bewertete er dadurch einen Text aus fuenf
    #   VERBOTENEN Formulierungen mit 95.0 — waehrend der konkrete Post mit echter
    #   Szene und Zahl nur 84.3 bekam. Vierzehn aneinandergereihte Verbotsfloskeln
    #   bestanden mit 68.4. NEIN sagte der Scorer nur bei too_short/excessive_caps.
    #
    #   Der Prompt P12 verbietet genau diese Formulierungen auf 544 Zeilen — nichts
    #   pruefte, ob das Modell sich daran gehalten hat. Und der Detektor dafuer war
    #   die ganze Zeit da: voice_gate.check_anti_ki_phrases. Er lief nur separat in
    #   session_post_task, ausdruecklich "additiv, blockt nie eigenstaendig", und
    #   floss in DIESEN Score nicht ein. Zwei fertige Teile, keine Naht.
    #
    #   ⛔ Der Em-Dash-Treffer ist im voice_gate selbst als "schwaches Signal"
    #   ausgewiesen und wird deshalb NICHT gewichtet — sonst bestraft das Gate
    #   einen legitimen Gedankenstrich wie eine Floskel.
    ki_hits = _anti_ki_hits(post_text)
    ki_score, ki_violations = _anti_ki_score(ki_hits)
    violations.extend(ki_violations)

    # -- Gewichtete Score-Berechnung --
    weights: dict[str, Any] = cfg.get("weights", {})
    w_length = float(weights.get("length", 35))
    w_structure = float(weights.get("structure", 25))
    w_cta = float(weights.get("cta_hook", 15))
    w_caps = float(weights.get("caps_ok", 15))
    w_hashtag = float(weights.get("hashtag_ok", 10))
    w_disclaimer = float(weights.get("disclaimer", 0))
    # Default 30: das Signal muss den Formteil ueberstimmen koennen. Bei den
    # gemessenen Faellen kippt es den Floskeltext (95.0) unter den konkreten
    # Post — ohne einen sauberen Text zu bestrafen (0 Treffer => voller Score).
    w_anti_ki = float(weights.get("anti_ki", 30))

    total_weight = (
        w_length + w_structure + w_cta + w_caps + w_hashtag + w_disclaimer + w_anti_ki
    )
    if total_weight <= 0:
        total_weight = 100.0

    raw_score = (
        w_length * len_score
        + w_structure * struct_score
        + w_cta * cta_score
        + w_caps * caps_score
        + w_hashtag * hashtag_score
        + w_disclaimer * disc_score
        + w_anti_ki * ki_score
    )

    # Normierung auf 0..100
    score = 100.0 * raw_score / total_weight

    # Hard-Penalty fuer Block-Violations:
    # too_short, excessive_caps, no_sentence_terminators, empty_post,
    # missing_legal_disclaimer, missing_financial_disclaimer
    # -> Score kann auch bei gutem Rest den Threshold nicht erreichen
    block_violations = {
        "too_short",
        "excessive_caps",
        "no_sentence_terminators",
        "empty_post",
        "missing_legal_disclaimer",
        "missing_financial_disclaimer",
        "missing_disclaimer",
        # Ab drei echten Floskeln ist der Post nicht "etwas schwach", sondern
        # maschinengeschrieben — das darf kein guter Formteil ausgleichen.
        "ki_phrasen_massiv",
    }
    has_block_violation = bool(set(violations) & block_violations)

    if has_block_violation:
        # Sicherstellen dass Score sicher UNTER dem Threshold liegt
        score = min(score, threshold - 1.0)

    score = max(0.0, min(100.0, score))
    passed = score > threshold and not has_block_violation

    return {
        "passed": passed,
        "score": round(score, 2),
        "violations": violations,
        "threshold": threshold,
        "branche": branche,
    }
