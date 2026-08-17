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


# ---------------------------------------------------------------------------
# Art. 50 Abs. 1 — Kennzeichnung der INTERAKTION (nicht des Inhalts)
# ---------------------------------------------------------------------------
#
# ⛔ Das oben ist Art. 50 Abs. 4 (KI-erzeugter INHALT). Abs. 1 ist ein ANDERER
# Tatbestand: Systeme, die für die direkte Interaktion mit natürlichen Personen
# bestimmt sind, müssen so gestaltet sein, dass die Person INFORMIERT WIRD, dass
# sie mit einem KI-System interagiert — sofern das nicht aus dem Kontext
# offensichtlich ist.
#
# Für den Chat ist es NICHT offensichtlich: Der Bot formuliert seine Rückfragen
# bereits heute per LLM (`p08_service` → `call_pipeline_llm`, ebenso
# `p14_entry_service`). Aus Nutzersicht ist das ein Gesprächspartner, der
# Rückfragen stellt — genau die Situation, die Abs. 1 adressiert.
#
# Der Zeitpunkt ist "vor oder bei der ersten Interaktion". Deshalb steht der
# Hinweis an den beiden Stellen, die ein Nutzer garantiert sieht: im
# Willkommenstext (/start) und in der Hilfe (/help, jederzeit abrufbar).
#
# Bewusst NICHT unter jede einzelne Bot-Nachricht: Abs. 1 verlangt Information,
# keine Dauerbeschallung. Ein Hinweis unter jeder Zeile würde gelesen werden wie
# ein Cookie-Banner — also gar nicht — und wäre damit schlechtere Transparenz
# bei mehr Text.

CHAT_AI_HINWEIS = (
    "🤖 Du schreibst mit einem KI-Assistenten. Meine Rückfragen und Vorschläge "
    "sind KI-generiert — deine Inhalte und die Freigabe bleiben bei dir."
)


def chat_ai_hinweis_block() -> str:
    """Der Interaktionshinweis als abgesetzter Block für Chat-Texte.

    Eigene Funktion statt roher Konstante an fünf Stellen: der Wortlaut einer
    Rechtspflicht gehört an EINEN Ort. Ändert sich die Formulierung (oder die
    Rechtslage), ist hier die einzige Stelle.
    """
    return f"\n\n─────────────────────────\n{CHAT_AI_HINWEIS}"


def hat_chat_ai_hinweis(text: str) -> bool:
    """True, wenn der Text den Interaktionshinweis bereits trägt.

    Für Tests und für Aufrufer, die Texte zusammensetzen — verhindert, dass der
    Hinweis doppelt erscheint.
    """
    return bool(text) and "Du schreibst mit einem KI-Assistenten" in text
