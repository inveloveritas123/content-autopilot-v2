"""
tasks/p12_pruning.py — Prune-Whitelists für P12/P12b auf Louis-KANONISCHE Profile.

Bugfix (Fable-Kontroll-Review 2026-06-12): Die alten Whitelists listeten
`signalwoerter`/`fuellwoerter`/`verbotene_woerter`/`intensitaetsmarker` als
TOP-LEVEL-Keys. Kanonisch (content-truth/schemas/p03) liegen sie aber
verschachtelt unter `wortschatz` — der Block fiel beim Prunen still weg
(= Herzstück der Stimm-Imitation). Fix: `wortschatz` als Container aufnehmen.
Flache Alt-Keys bleiben tolerant in der Liste (schaden nicht, greifen nur bei
etwaigen Transitions-Rows).

Dep-frei (keine sqlalchemy/celery/google-Imports) → via importlib testbar.
"""

# ── P12 (Post-Generierung) ──────────────────────────────────────────────────
VOICE_KEYS_FOR_P12 = [
    "grundton",
    "satzarchitektur",
    "wortschatz",            # kanonischer Container (signalwoerter/verbotene_woerter/…)
    "erzaehlmuster",
    "emotionaler_ausdruck",
    "persoenlichkeits_stance",
    "emotionaler_subtext",
    "ueberzeugungsstil",
    "zielgruppen_sprachfilter",
    "vermeidungsprofil",
    "referenz_saetze",
    # Transitions-Toleranz: flache Alt-Keys (i.d.R. absent bei kanonischen Rows)
    "signalwoerter",
    "fuellwoerter",
    "verbotene_woerter",
    "intensitaetsmarker",
]

CONTEXT_KEYS_FOR_P12 = [
    "person",
    "angebot",
    "positionierung",
    "zielkunde",             # kanonisch (Zielkunden-Kontext)
    "sprache",               # kanonisch (Lieblings-/Vermeidungswörter, du/sie)
    "vertrauen",             # kanonisch (Belege/Erfolgsgeschichten)
    # Alt-v2-Toleranz (absent bei kanonischen Rows)
    "kernbotschaft",
    "expertise",
]

AVATAR_KEYS_FOR_P12 = [
    "identitaet",
    "content_trigger",
    "sprache_der_zielgruppe",
]

# ── P12b (Post-Optimierung) ─────────────────────────────────────────────────
VOICE_KEYS_FOR_P12B = [
    "grundton",
    "satzarchitektur",
    "wortschatz",            # kanonischer Container
    "persoenlichkeits_stance",
    "vermeidungsprofil",
    # Transitions-Toleranz
    "verbotene_woerter",
    "intensitaetsmarker",
]

AVATAR_KEYS_FOR_P12B = ["sprache_der_zielgruppe", "content_trigger"]


def prune(payload, keys):
    """Top-Level-Whitelist: behält nur die gelisteten Keys, die vorhanden sind."""
    payload = payload or {}
    return {k: payload[k] for k in keys if k in payload}
