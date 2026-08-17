# AUDITED-2026-08-15 (zubu-louis-immer-eine-antwort): Tiefen-Audit, Datei vollstaendig gelesen.
"""KI-Kennzeichnung — EU-AI-Act Art. 50 Transparenz (W6, 2026-07-21).

Art. 50 verlangt, dass KI-generierte Inhalte als solche erkennbar sind. Für den
Content-Autopilot gilt:
- JEDER generierte Post ist KI-generiert (content_pieces.ai_generated=True).
- Das Publishing ist MANUELL (der Kunde kopiert den Post und postet selbst) — der
  Mensch ist damit der autorisierende Veröffentlicher. Art. 50 erlaubt in diesem
  Fall, dass kein Zwangs-Label im veröffentlichten Post steht, SOFERN der Kunde
  informiert ist, dass der Entwurf KI-generiert ist.
- Deshalb: der Entwurf, den der Kunde im Chat bekommt, trägt einen dezenten,
  abtrennbaren KI-Hinweis (den der Kunde vor dem Posten entfernt oder stehen lässt).
  Der DB-Nachweis (ai_generated + human_reviewed) bleibt unabhängig davon bestehen.

Der Hinweis ist KURZ und klar als Meta-Zeile erkennbar (nicht Teil des Post-Texts),
per Trennlinie abgesetzt, damit der Kunde ihn leicht wegkopieren kann.
"""

from __future__ import annotations

# Dezenter, abtrennbarer Hinweis unter dem Entwurf (nicht im Post-Text selbst).
_AI_NOTICE = (
    "\n\n— — —\n"
    "ℹ️ Dieser Entwurf wurde KI-gestützt in deiner Stimme erstellt. "
    "Prüfe ihn vor dem Posten; die Hinweiszeile kannst du entfernen."
)


def append_ai_notice(draft_text: str) -> str:
    """Hängt den KI-Transparenz-Hinweis abtrennbar unter den Entwurf.

    Idempotent: fügt den Hinweis nicht doppelt an.
    """
    if not draft_text:
        return draft_text
    if "KI-gestützt in deiner Stimme erstellt" in draft_text:
        return draft_text
    return draft_text + _AI_NOTICE
