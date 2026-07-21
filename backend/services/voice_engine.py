"""Voice-Engine: Few-Shot-Exzerpt-Steuerung für authentische Stimme (W4, 2026-07-21).

Doktrin (llm_foo/content-creation, adversarial verifiziert + persona-forge in Praxis):
Eine ATTRIBUT-Beschreibung („Ton: direkt, Sätze: kurz") steuert ein LLM NICHT
zuverlässig — echte VERBATIM-Textbeispiele der Person schlagen sie in LLM-as-Judge
70–85 %. Deshalb ist der Kern der Stimm-Steuerung ein Many-Shot aus (Reverse-Prompt,
verbatim Exzerpt)-Paaren, die als synthetische User/Assistant-Konversationshistorie
vor den eigentlichen Auftrag gesetzt werden. Die Attribut-Beschreibung bleibt nur als
Orientierung im System-Prompt.

Diese Engine baut aus dem gespeicherten Voice-Profil (tenant_voice_profile) die
Few-Shot-Messages. Quelle der Exzerpte:
- voice_profile["referenz_saetze"]: 8–10 wortwörtliche Sätze, die die Stimme maximal
  repräsentieren (P03 extrahiert sie bereits).
- optional voice_profile["example_texts"] / ["fewshot"]: ganze Beispiel-Posts.

Reverse-Prompt: Zu jedem Exzerpt wird ein synthetischer „Welcher Auftrag hätte zu
diesem Text geführt?"-Prompt erzeugt (generisch, ohne zusätzlichen LLM-Call — ein
knapper Themen-Platzhalter genügt als Konversationsanker).
"""

from __future__ import annotations

# Wie viele Exzerpte maximal in die Few-Shot-Historie (Token-Budget vs. Signal).
_MAX_FEWSHOT = 6


def _extract_excerpts(voice_profile: dict) -> list[str]:
    """Zieht verbatim Exzerpte aus dem Voice-Profil (robust gegen Schema-Varianten)."""
    excerpts: list[str] = []

    # 1) referenz_saetze — das P03-Feld mit den prägnantesten Sätzen.
    ref = voice_profile.get("referenz_saetze")
    if isinstance(ref, list):
        excerpts.extend(str(s).strip() for s in ref if str(s).strip())
    elif isinstance(ref, dict):
        # manche Profile schachteln unter {"saetze": [...]}
        inner = ref.get("saetze") or ref.get("beispiele")
        if isinstance(inner, list):
            excerpts.extend(str(s).strip() for s in inner if str(s).strip())

    # 2) example_texts / fewshot — ganze Beispiel-Posts (stärkstes Signal).
    for key in ("example_texts", "fewshot", "beispiel_posts"):
        val = voice_profile.get(key)
        if isinstance(val, list):
            excerpts.extend(str(s).strip() for s in val if str(s).strip())

    # Dedupe unter Erhalt der Reihenfolge, längste zuerst (mehr Kontext = stärker).
    seen: set[str] = set()
    unique = []
    for e in sorted(excerpts, key=len, reverse=True):
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique[:_MAX_FEWSHOT]


def _reverse_prompt_for(excerpt: str) -> str:
    """Synthetischer Auftrag, der zu diesem Exzerpt geführt haben könnte.

    Generisch gehalten (kein extra LLM-Call): Der Zweck ist nur, das verbatim
    Exzerpt als Assistant-Antwort in eine plausible Konversation einzubetten, damit
    das Modell den Stil als „so antworte ICH" internalisiert (Many-Shot-Prinzip).
    """
    return (
        "Schreibe einen kurzen LinkedIn-Beitrag in deiner authentischen Stimme "
        "zu einem Thema aus deinem Fachgebiet."
    )


def build_voice_fewshot(voice_profile: dict) -> list[dict]:
    """Baut die Few-Shot-Message-Liste (user/assistant-Paare) für call_pipeline_llm.

    Gibt [] zurück, wenn keine verwertbaren Exzerpte vorliegen — dann läuft P12 wie
    bisher (nur Attribut-Profil), ohne Crash. Die Exzerpte STEUERN die Stimme.
    """
    excerpts = _extract_excerpts(voice_profile)
    messages: list[dict] = []
    for excerpt in excerpts:
        messages.append({"role": "user", "content": _reverse_prompt_for(excerpt)})
        messages.append({"role": "assistant", "content": excerpt})
    return messages


def has_voice_excerpts(voice_profile: dict) -> bool:
    """True, wenn genug verbatim Exzerpte für eine sinnvolle Few-Shot-Steuerung da sind."""
    return len(_extract_excerpts(voice_profile)) >= 2
