"""
prompt_health_core.py — Wiederverwendbare Health-Check-Logik fuer Prompt-Dateien.

Wird genutzt von:
- api/prompt_studio.py   — validate/save-Endpunkte
- scripts/prompt_health.py — CLI-Skript (umgestellt auf dieses Modul)

Keine schweren Abhaengigkeiten: stdlib only + services.prompt_loader
fuer _extract_section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Prompts die einen User-Prompt ERWARTEN (d.h. issues wenn leer)
# ---------------------------------------------------------------------------

_EXPECTS_USER_PROMPT = {
    "P01",
    "P03",
    "P04",
    "P09",
    "P12",
    "P12b",
    "P12c",
    "P13",
    "P15",
    "P16",
}

# Prompts fuer die kein System-Prompt erwartet wird
_NO_SYSTEM_EXPECTED = {"fragenkatalog", "hookmaster"}

# ---------------------------------------------------------------------------
# Ergebnis-Datenklasse
# ---------------------------------------------------------------------------


@dataclass
class PromptHealthResult:
    """Ergebnis eines Health-Checks fuer eine Prompt-Datei."""

    status: Literal["ok", "weird"]
    system_chars: int
    user_chars: int
    fences_balanced: bool
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fence-Balance-Pruefung
# ---------------------------------------------------------------------------


def _fences_balanced(text: str) -> bool:
    """Prueft ob alle ``` Code-Fences im Text balanciert sind.

    Einfache Heuristik: gerade Anzahl von ```-Zeilen = balanciert.
    """
    fence_lines = [line for line in text.splitlines() if line.strip().startswith("```")]
    return len(fence_lines) % 2 == 0


# ---------------------------------------------------------------------------
# Haupt-Prueffunktion
# ---------------------------------------------------------------------------


def check_prompt_content(
    content: str,
    *,
    prompt_key: str | None = None,
) -> PromptHealthResult:
    """Prueft den Inhalt einer Prompt/Rule-Datei (.md) auf Gesundheit.

    Argumente:
        content:    vollstaendiger Dateiinhalt (UTF-8 String)
        prompt_key: optionaler Schluessel (z.B. 'P12') fuer key-spezifische
                    Pruefregeln (_EXPECTS_USER_PROMPT, _NO_SYSTEM_EXPECTED).
                    None = alle Standard-Pruefungen greifen.

    Rueckgabe:
        PromptHealthResult mit status='ok' oder 'weird', Zeichenzahlen und
        Issue-Code-Liste.
    """
    # Sektionen extrahieren (lokaler Import um Zirkular-Importe zu vermeiden)
    from services.prompt_loader import _extract_section

    system_prompt = _extract_section(content, "System-Prompt")
    user_prompt = _extract_section(content, "User-Prompt")

    fences_ok = True
    issues: list[str] = []

    # Fence-Balance fuer System-Prompt pruefen
    if system_prompt:
        if system_prompt.startswith("```") or system_prompt.endswith("```"):
            fences_ok = False
            issues.append("OUTER_FENCE_VERBLIEBEN")
        elif not _fences_balanced(system_prompt):
            fences_ok = False
            issues.append("INTERNE_FENCES_UNBALANCIERT")

    # Leerer System-Prompt (ausser bei Prompts ohne System-Prompt-Sektion)
    if not system_prompt and prompt_key not in _NO_SYSTEM_EXPECTED:
        issues.append("SYSTEM_PROMPT_LEER")

    # Leerer User-Prompt bei Prompts die einen erwarten
    if not user_prompt and prompt_key in _EXPECTS_USER_PROMPT:
        issues.append("USER_PROMPT_LEER")

    status: Literal["ok", "weird"] = "weird" if issues else "ok"

    return PromptHealthResult(
        status=status,
        system_chars=len(system_prompt),
        user_chars=len(user_prompt),
        fences_balanced=fences_ok,
        issues=issues,
    )
