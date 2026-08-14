"""
llm_json — robuster JSON-Parser fuer LLM-Outputs.

Strategien (in Reihenfolge):
1. Direkter json.loads-Versuch (Output ist reines JSON)
2. ```json- oder ```-Fenced-Block extrahieren und parsen
3. Brace-Matching: erstes vollstaendiges {...}-Objekt im Text finden
   (beachtet Strings und Escape-Sequenzen korrekt)
4. ValueError mit 200-Zeichen-Preview wenn alle Strategien scheitern

Verwendung:
    from services.llm_json import parse_json_from_text
    result = parse_json_from_text(raw_llm_response)
"""

import json

# strict=False erlaubt rohe Steuerzeichen (v.a. unescapte \n) innerhalb von
# JSON-Strings. Modelle rutschen bei mehrabsätzigem Text (z.B. LinkedIn-Posts
# im "post"-Feld) gelegentlich in echte Zeilenumbrüche statt \n-Escapes —
# das ist technisch ungültiges JSON, das strict-Mode sonst hart ablehnt,
# obwohl der Output inhaltlich vollständig und eindeutig ist (#62).
_JSON_LOADS_KWARGS = {"strict": False}


def parse_json_from_text(raw: str) -> dict:
    """Extrahiert ein JSON-Objekt aus einem LLM-Output-String.

    Versucht der Reihe nach:
    1. Direktes json.loads
    2. Extraktion aus ```json...``` oder ```...``` Fence
    3. Brace-Matching: erstes balanciertes {}-Objekt im Text
    4. ValueError wenn alles scheitert (mit 200-Zeichen-Preview)

    Args:
        raw: Rohtext aus dem LLM-Response.

    Returns:
        Geparstes dict.

    Raises:
        ValueError: Wenn kein parsebares JSON gefunden wird.
    """
    raw = raw.strip()

    # Strategie 1: direkter Parse
    try:
        return json.loads(raw, **_JSON_LOADS_KWARGS)
    except json.JSONDecodeError:
        pass

    # Strategie 2: Fenced code block (```json ... ``` oder ``` ... ```)
    for fence in ("```json", "```"):
        if fence in raw:
            start = raw.index(fence) + len(fence)
            end = raw.find("```", start)
            if end != -1:
                candidate = raw[start:end].strip()
                try:
                    return json.loads(candidate, **_JSON_LOADS_KWARGS)
                except json.JSONDecodeError:
                    pass

    # Strategie 3: Brace-Matching — erstes balanciertes {}-Objekt
    extracted = _extract_first_json_object(raw)
    if extracted is not None:
        try:
            return json.loads(extracted, **_JSON_LOADS_KWARGS)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Konnte kein JSON aus LLM-Output extrahieren. Anfang: {raw[:200]!r}")


def _extract_first_json_object(text: str) -> str | None:
    """Findet das erste vollstaendige, balancierte {}-Objekt im Text.

    Beachtet Strings (mit Escape-Sequenzen) damit {/} in Strings nicht
    als Klammer-Delimiter gezaehlt werden.

    Args:
        text: Eingabe-String.

    Returns:
        Der Substring vom ersten '{' bis zum passenden '}', oder None wenn
        kein vollstaendiges Objekt gefunden wurde.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    i = start

    while i < len(text):
        ch = text[i]

        if in_string:
            if ch == "\\" and i + 1 < len(text):
                # Escape-Sequenz: naechstes Zeichen ueberspringen
                i += 2
                continue
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        i += 1

    return None
