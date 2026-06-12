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
    "wortschatz",  # kanonischer Container (signalwoerter/verbotene_woerter/…)
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
    "zielkunde",  # kanonisch (Zielkunden-Kontext)
    "sprache",  # kanonisch (Lieblings-/Vermeidungswörter, du/sie)
    "vertrauen",  # kanonisch (Belege/Erfolgsgeschichten)
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
    "wortschatz",  # kanonischer Container
    "persoenlichkeits_stance",
    "vermeidungsprofil",
    # Transitions-Toleranz
    "verbotene_woerter",
    "intensitaetsmarker",
]

AVATAR_KEYS_FOR_P12B = ["sprache_der_zielgruppe", "content_trigger"]

# ── Kunden-Werte (P12-Injektion, Issue #43) ────────────────────────────────
# Top-Level-Keys aus tenant_customer_values.payload, die in den P12-Kontext
# dürfen. quellen/status werden je Werte-Eintrag vom prune_values()-Schritt
# gestrippt (Token-Hygiene); _meta wird durch prune() generell entfernt.
VALUES_KEYS_FOR_P12 = [
    "werte",          # Pflichtfeld: Liste mit wert/beschreibung/belege/gewicht
    "ueberzeugungen",  # Optional: tiefere Überzeugungsebene
    "tabus",           # Optional: Absolut-Verbote / rote Linien
]


def prune(payload, keys):
    """Top-Level-Whitelist: behält nur die gelisteten Keys, die vorhanden sind."""
    payload = payload or {}
    return {k: payload[k] for k in keys if k in payload}


def prune_values(payload: dict) -> dict:
    """Reduziert einen Werte-Payload auf die P12-relevanten Felder.

    1. Top-Level-Whitelist (VALUES_KEYS_FOR_P12) — entfernt _meta u. a.
    2. Filtert werte[] auf status == 'aktiv' (vorgeschlagene/verworfene nicht
       ins Prompt — Token-Hygiene + Qualitäts-Gate).
    3. Strippt je Werte-Eintrag die Felder quellen und status (Provenance-Daten
       braucht das LLM nicht; nur wert/beschreibung/belege/gewicht bleiben).
    4. Leerer oder fehlender Payload → {} (Fail-open garantiert).
    """
    pruned = prune(payload, VALUES_KEYS_FOR_P12)
    if not pruned:
        return {}

    raw_werte = pruned.get("werte")
    if isinstance(raw_werte, list):
        active_werte = []
        for entry in raw_werte:
            if not isinstance(entry, dict):
                continue
            if entry.get("status", "aktiv") != "aktiv":
                # vorgeschlagen/verworfen → nicht ins Prompt
                continue
            # Nur LLM-relevante Felder behalten
            stripped = {
                k: entry[k]
                for k in ("wert", "beschreibung", "belege", "gewicht")
                if k in entry
            }
            active_werte.append(stripped)
        pruned["werte"] = active_werte

    return pruned
