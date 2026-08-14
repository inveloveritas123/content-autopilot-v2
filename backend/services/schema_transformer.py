"""
schema_transformer.py — Transformer-Schicht zwischen v2-DB-Payload und kanonischem Schema.

Kontext (P4-schema-realignment.md, Stufe ii):
  Die v2-Datenbank speichert Payloads in Feldern, die NICHT mit Louis' kanonischen
  Schemas (content-truth/schemas/) übereinstimmen (Überlappung ~0 bei P01/P04,
  1 Feld bei P03). Diese Bibliothek übersetzt bidirektional — OHNE die Datenbank
  oder die Tasks zu verändern. Das Wiring in Tasks/API ist ein separater Schritt.

Architektur-Entscheid:
  - Deklarative Mapping-Tabellen (dicts) pro Prompt, keine if-Kaskaden.
  - Lossy-Mappings sind als solche markiert und erzeugen `_meta.luecken`.
  - Der Transformer halluziniert NIE fehlende Daten; stattdessen wird `None`
    oder ein Lücken-Eintrag gesetzt.
  - `_meta` wird aus DB-Spalten / meta-dict rehydriert, nie aus dem payload
    erfunden (ADR-0002-konform).

Verwendung:
  from services.schema_transformer import load_canonical_schema, to_canonical, from_canonical

Autoren-Übergabe:
  Alle OFFEN:-Kommentare im Modul sind kandidaten für GitHub-Issues (P4-Plan).

Stand: 2026-06-12
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Wandelt einen Anzeige-Namen in einen URL-sicheren Slug um (kebab-case).

    Übernommen aus services/brand_voice_storage.py — hier dupliziert um den
    Transformer unabhängig von dem services-Package zu halten (das google.generativeai
    beim Import zieht).
    """
    s = (name or "").lower().strip()
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        s = s.replace(src, dst)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64] or "default"


def _get_content_truth_schemas_dir() -> Path:
    """Gibt das Verzeichnis der kanonischen Schemas zurück.

    Reihenfolge:
      1. Umgebungsvariable CONTENT_TRUTH_BASE_PATH
      2. config.settings.content_truth_base_path (wenn config importierbar)
      3. Fallback: <repo-root>/content-truth (relativ zu dieser Datei)
    """
    env_path = os.environ.get("CONTENT_TRUTH_BASE_PATH", "").strip()
    if env_path:
        return Path(env_path) / "schemas"

    try:
        # Lazy-Import: config zieht keine google-Deps
        from config import settings  # type: ignore

        return Path(settings.content_truth_base_path) / "schemas"
    except Exception:
        pass

    # Fallback: relativ zu dieser Datei → backend/../content-truth/schemas
    return Path(__file__).parent.parent.parent / "content-truth" / "schemas"


# ---------------------------------------------------------------------------
# Schema-Laden
# ---------------------------------------------------------------------------

# Interner Schema-Cache (Prozess-Lifetime)
_SCHEMA_CACHE: dict[str, dict] = {}

# Mapping von prompt_key → Dateiname im schemas/-Verzeichnis
_SCHEMA_FILE_MAP: dict[str, str] = {
    "p01": "p01.schema.json",
    "p03": "p03.schema.json",
    "p04": "p04.schema.json",
    "voice_profile": "voice_profile.schema.json",
    "values": "values.schema.json",  # #43 — Werte-Entität (Chris-Abstimmung ausstehend)
}

# Semantische Default-Prompt-Version je Prompt (Pattern: ^p0X-vN.N$ oder ^values-vN.N$).
# Louis' Prompts pinnen das Pattern NICHT zuverlässig im Output, das LLM darf
# es also nicht bestimmen. Server-seitig setzen wir die Vertrags-Version hier.
# Override pro Prompt via Env CANONICAL_PROMPT_VERSION_P01 etc.
CANONICAL_PROMPT_VERSION: dict[str, str] = {
    "p01": "p01-v1.0",
    "p03": "p03-v1.0",
    "p04": "p04-v1.0",
    "values": "values-v1.0",  # #43 — Werte-Schema-Version (Namensraum: Schema, nicht Prompt)
}

# Autoritative _meta-Felder: vom Server bestimmt, NIE vom LLM überschrieben.
_AUTHORITATIVE_META_KEYS = frozenset(
    {"agentur_id", "kunde_id", "prompt_version", "model", "generated_at"}
)


def load_canonical_schema(prompt_key: str) -> dict:
    """Lädt das kanonische Louis-Schema für einen Prompt-Schlüssel.

    Das Schema wird aus dem Verzeichnis gelesen, das über
    CONTENT_TRUTH_BASE_PATH / config.settings.content_truth_base_path
    konfiguriert ist (Suffix /schemas/ wird automatisch angehängt).

    Args:
        prompt_key: Kleinbuchstaben-Schlüssel, z.B. 'p01', 'p03', 'p04'.

    Returns:
        Das Schema als dict (JSON-Objekt).

    Raises:
        KeyError: Wenn prompt_key unbekannt ist.
        FileNotFoundError: Wenn die Schema-Datei nicht existiert.
        json.JSONDecodeError: Bei ungültiger JSON-Datei.
    """
    key = prompt_key.lower()
    if key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[key]

    if key not in _SCHEMA_FILE_MAP:
        raise KeyError(
            f"Unbekannter prompt_key '{prompt_key}'. "
            f"Bekannte Schlüssel: {sorted(_SCHEMA_FILE_MAP)}"
        )

    schemas_dir = _get_content_truth_schemas_dir()
    schema_path = schemas_dir / _SCHEMA_FILE_MAP[key]

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Kanonisches Schema nicht gefunden: {schema_path}. "
            f"Ist CONTENT_TRUTH_BASE_PATH korrekt gesetzt?"
        )

    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)

    _SCHEMA_CACHE[key] = schema
    logger.debug("Kanonisches Schema geladen: %s", schema_path)
    return schema


# ---------------------------------------------------------------------------
# Validierung
# ---------------------------------------------------------------------------


def validate_canonical(prompt_key: str, payload: dict) -> list[str]:
    """Validiert einen Payload gegen das kanonische Louis-Schema (Draft 2020-12).

    Verwendet `jsonschema.validators.validator_for()` statt einem fixen Draft7Validator,
    damit Draft 2020-12-Keywords (z.B. `prefixItems`) korrekt ausgewertet werden.

    Args:
        prompt_key: Schlüssel wie 'p01', 'p03', 'p04'.
        payload:    Das zu validierende Dict (kanonisches Format inkl. _meta).

    Returns:
        Liste der Fehlermeldungen (leer = valide). Nie None.
    """
    import jsonschema
    import jsonschema.validators

    schema = load_canonical_schema(prompt_key)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)

    errors = []
    for error in validator.iter_errors(payload):
        # Pfad + Nachricht für klare Ausgabe
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {error.message}")

    return errors


# ---------------------------------------------------------------------------
# Top-Level-Keys: Prompt-Überschriften auf Schema-Namen zurückführen
# ---------------------------------------------------------------------------


def _vergleichsschluessel(name: str) -> str:
    """Reduziert einen Key auf die Form, in der er mit Schema-Namen vergleichbar ist.

    Klein, Umlaute transliteriert (wie die Schemas sie schreiben: identitaet),
    führende Gliederungsnummer entfernt, alle Trenner zu '_'.

        IDENTITÄT              → identitaet
        SPRACHE DER ZIELGRUPPE → sprache_der_zielgruppe
        SPRACHE_DER_ZIELGRUPPE → sprache_der_zielgruppe
        8_CONTENT-RESERVOIR    → content_reservoir
    """
    s = (name or "").strip().lower()
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        s = s.replace(src, dst)
    s = re.sub(r"^\d+[\s_.\-]+", "", s)  # Gliederungsnummer aus dem Prompt
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def normalisiere_top_level_keys(prompt_key: str, payload: dict) -> tuple[dict, list]:
    """Führt Top-Level-Keys auf die Namen des kanonischen Schemas zurück.

    Hintergrund (Prod-Befund 06.08.2026): Das LLM übernimmt gelegentlich die
    Abschnitts-Überschriften des Prompts als JSON-Keys — `IDENTITÄT` statt
    `identitaet`, `1_PERSON` statt `person`. Der Inhalt darunter ist kanonisch,
    nur der Name nicht. P12s `prune()` macht einen exakten Key-Match und verwirft
    solche Felder lautlos; Louis' und Erics Avatar kamen dadurch mit 0 von 3
    Feldern beim Post-Prompt an.

    Umbenannt wird ausschließlich auf einen Namen, den das Schema führt — die
    Zielmenge ist damit bekannt und die Zuordnung rät nicht. Unbekannte Keys
    bleiben unverändert stehen (nie verwerfen), und ein bereits belegter
    kanonischer Name wird nie überschrieben.

    Returns:
        (doc, umbenennungen): ``doc`` mit korrigierten Namen, ``umbenennungen``
        als Liste von (alt, neu) — leer, wenn nichts zu tun war.
    """
    if not isinstance(payload, dict):
        return {}, []

    try:
        schema = load_canonical_schema(prompt_key)
    except Exception as exc:
        # Fail-open: die Profilerzeugung darf daran nicht sterben. Aber NICHT
        # stumm — ohne Schema gibt es keine Zielmenge, die Normalisierung ist
        # dann wirkungslos, und ein lautloser No-Op ist genau der Fehlertyp,
        # gegen den diese Funktion gebaut wurde.
        logger.error(
            "normalisiere_top_level_keys(%s): Schema nicht ladbar (%s: %s) — "
            "Top-Level-Keys bleiben ungeprüft. CONTENT_TRUTH_BASE_PATH korrekt?",
            prompt_key,
            type(exc).__name__,
            exc,
        )
        return dict(payload), []

    nach_vergleichsform = {
        _vergleichsschluessel(name): name for name in (schema.get("properties") or {})
    }

    doc: dict = {}
    umbenennungen: list = []
    for key, wert in payload.items():
        ziel = nach_vergleichsform.get(_vergleichsschluessel(key))
        if ziel is None or ziel == key or ziel in payload:
            doc[key] = wert
            continue
        doc[ziel] = wert
        umbenennungen.append((key, ziel))

    return doc, umbenennungen


def aktualisiere_schema_luecken(prompt_key: str, payload: dict) -> tuple[dict, list, list]:
    """Setzt die Schema-Einträge in ``_meta.luecken`` auf den aktuellen Validierungsstand.

    Nötig nach einer Reparatur am Bestand: `normalisiere_top_level_keys()` behebt
    den Strukturbruch, aber die bei der Erzeugung protokollierten Lücken bleiben
    im ``_meta`` stehen. `is_canonical()` liest genau diese Liste — die reparierte
    Row gälte also weiterhin als kaputt, und der Wächter meldete bei jedem Lauf
    grundlos "Re-Run empfohlen". Ein Wächter, der ohne Anlass meckert, wird
    ignoriert; genau so wurde das Lücken-Signal ursprünglich wertlos.

    Bloßes STREICHEN reicht dabei nicht. Solange ein Pflichtfeld auf Wurzelebene
    fehlt, prüft jsonschema das zugehörige Unterobjekt gar nicht erst — erst die
    Reparatur legt die darunterliegenden Fehler frei (bei Erics Kundenkontext am
    06.08.2026: neun Stück). Wer nur streicht, hinterlässt eine leere Liste an
    einer Row mit neun echten Befunden und macht den Wächter blind statt ehrlich.
    Deshalb werden die Schema-Einträge ERSETZT, nicht gefiltert.

    Freitext-Notizen (ohne ``schema: ``-Präfix) bleiben unangetastet — sie sind
    inhaltliche Hinweise und gehen die Strukturprüfung nichts an.

    Returns:
        (doc, entfernt, neu): ``doc`` mit aktualisierter Lückenliste, dazu die
        weggefallenen und die neu hinzugekommenen Schema-Einträge.
    """
    if not isinstance(payload, dict):
        return {}, [], []

    meta = payload.get("_meta")
    if not isinstance(meta, dict):
        return payload, [], []

    try:
        aktuell = [f"schema: {e}" for e in validate_canonical(prompt_key, payload)]
    except Exception as exc:
        logger.error(
            "aktualisiere_schema_luecken(%s): Validierung nicht moeglich (%s: %s) — "
            "Lueckenliste bleibt unveraendert.",
            prompt_key,
            type(exc).__name__,
            exc,
        )
        return payload, [], []

    bisher = list(meta.get("luecken") or [])
    freitext = [x for x in bisher if not (isinstance(x, str) and x.startswith("schema: "))]
    schema_bisher = [x for x in bisher if isinstance(x, str) and x.startswith("schema: ")]

    entfernt = [x for x in schema_bisher if x not in aktuell]
    neu = [x for x in aktuell if x not in schema_bisher]
    if not entfernt and not neu:
        return payload, [], []

    doc = dict(payload)
    doc["_meta"] = {**meta, "luecken": freitext + aktuell}
    return doc, entfernt, neu


# ---------------------------------------------------------------------------
# Deklarative Mapping-Tabellen
# ---------------------------------------------------------------------------
# Jeder Eintrag ist ein Dict mit:
#   "v2_field":       Dotted-Path im v2-payload (z.B. "zielgruppe.beschreibung")
#   "canonical_path": Dotted-Path im kanonischen Output (z.B. "zielkunde.beschreibung")
#   "lossy":          True wenn die Übersetzung semantisch verlustbehaftet ist
#   "note":           Erläuterung für den nächsten Entwickler
#
# Einfache Felder ohne Unter-Struktur: v2_field ist ein String-Schlüssel auf
# oberster Ebene; canonical_path ist dotted.
#
# Wichtig: Felder die in v2 NICHT existieren, aber im kanonischen Schema Pflicht
# sind, werden als OFFEN-Kommentar markiert und vom Transformer mit None / leerem
# Array / leerer Liste befüllt — begleitet von einem _meta.luecken-Eintrag.

# ── P01: unternehmenskontext → kanonisch ────────────────────────────────────
#
# v2-Felder (aus backend/schemas/p01_output_schema.json + tatsächliche LLM-Outputs):
#   unternehmensgeschichte (str|null)
#   kernbotschaft          (str|null)
#   zielgruppe             (object|null) — freies Objekt, Sub-Felder variabel
#   expertise              (object|null) — freies Objekt
#   werte                  (array|null)
#   wunschzustand          (null, erzwungen)
#   innenwelt              (null, erzwungen)
#
# Kanonische Felder (content-truth/schemas/p01.schema.json):
#   person.gruendungsgeschichte, person.name, person.rolle, ...
#   angebot.elevator_pitch, angebot.kernleistung, ...
#   zielkunde.beschreibung, zielkunde.psychografie, ...
#   positionierung.werte_schwerpunkt, ...
#   vertrauen.* ...
#   sprache.* ...
#   content_reservoir.* ...

P01_V2_TO_CANONICAL: list[dict] = [
    {
        "v2_field": "unternehmensgeschichte",
        "canonical_path": "person.gruendungsgeschichte",
        "lossy": False,
        "note": (
            "v2 speichert Gründungsgeschichte + Wendepunkte als freien String. "
            "Louis trennt das in gruendungsgeschichte / wendepunkt. "
            "Hier direkte Übernahme; wendepunkt bleibt leer (Lücke)."
        ),
    },
    {
        "v2_field": "kernbotschaft",
        "canonical_path": "angebot.elevator_pitch",
        "lossy": False,
        "note": "Semantisch eng verwandt. Direkte Übernahme.",
    },
    # OFFEN: v2-'zielgruppe' ist ein freies Objekt; kanonisch hat 'zielkunde'
    # mit 10+ Sub-Feldern (beschreibung, psychografie, schmerzpunkte_*, ...).
    # Das Sub-Feld-Layout von v2.zielgruppe ist LLM-abhängig und nicht fixiert.
    # Strategie: Wenn 'zielgruppe' ein string ist → zielkunde.beschreibung.
    #            Wenn dict: Sub-Felder nach Best-Effort zuordnen (s. _map_zielgruppe_to_canonical).
    {
        "v2_field": "zielgruppe",
        "canonical_path": "zielkunde",
        "lossy": True,
        "note": (
            "LOSSY: v2.zielgruppe ist ein freies Objekt ohne feste Sub-Felder. "
            "Kanonisch hat zielkunde 10 Sub-Felder mit definierten Pfaden. "
            "Übersetzung via _map_zielgruppe_to_canonical() auf Best-Effort-Basis. "
            "psychografie, schmerzpunkte_*, fehlglauben etc. können NICHT "
            "zuverlässig befüllt werden → Lücken-Markierung."
        ),
    },
    # OFFEN: v2-'expertise' ist ein freies Objekt.
    # Kanonisch: vertrauen.erfahrung_jahre, vertrauen.kunden_anzahl,
    #            vertrauen.zertifikate, vertrauen.erfolgsgeschichte etc.
    # Sub-Felder in v2.expertise variieren (LLM-abhängig).
    {
        "v2_field": "expertise",
        "canonical_path": "vertrauen",
        "lossy": True,
        "note": (
            "LOSSY: v2.expertise ist freies Objekt. "
            "Kanonisch: vertrauen mit Sub-Feldern erfahrung_jahre, kunden_anzahl, "
            "zertifikate, auszeichnungen, erfolgsgeschichte, kundenzitate. "
            "Sub-Felder werden per Best-Effort-Matching befüllt; "
            "nicht zuordenbare Inhalte gehen verloren → Lücke."
        ),
    },
    # OFFEN: v2-'werte' ist ein Array of strings.
    # Kanonisch: positionierung.werte_schwerpunkt ist ein String (Freitext).
    # Übersetzung: Array → kommagetrennt / join. Verlustfrei bezüglich Inhalt,
    # aber Semantik ändert sich (Array → String).
    {
        "v2_field": "werte",
        "canonical_path": "positionierung.werte_schwerpunkt",
        "lossy": True,
        "note": (
            "LOSSY (Typ-Konversion): v2.werte ist array[string], "
            "kanonisch positionierung.werte_schwerpunkt ist string. "
            "Übersetzung via ', '.join(werte). Round-trip verlustbehaftet "
            "(Einzelwerte nicht rückgewinnbar)."
        ),
    },
    {
        "v2_field": "wunschzustand",
        "canonical_path": "zielkunde.wunschzustand",
        "lossy": False,
        "note": (
            "P01-Vertrag: wunschzustand ist IMMER null (wird von P04 abgeleitet). "
            "v2 erzwingt das bereits (p01_task.py Zeile 268). Direkte Übernahme."
        ),
    },
    {
        "v2_field": "innenwelt",
        "canonical_path": "zielkunde.innenwelt",
        "lossy": False,
        "note": (
            "P01-Vertrag: innenwelt ist IMMER null (wird von P04 abgeleitet). "
            "v2 erzwingt das bereits. Direkte Übernahme."
        ),
    },
]

# ── P03: voice-profile → kanonisch ──────────────────────────────────────────
#
# v2-Felder (backend/schemas/p03_output_schema.json):
#   tonalitaet     (object|null) — freies Objekt
#   kernthemen     (array|null)
#   stilprinzipien (object|null) — freies Objekt
#   wortschatz     (object|null) — freies Objekt; Sub-Felder variieren
#   schreibrhythmus (object|null)
#   vermeidungsregeln (array|null)
#
# Kanonische Felder (p03.schema.json) — stark aufgefächert:
#   grundton.{charakterisierung, spektrum, linkedin_kalibrierung}
#   satzarchitektur.{laenge, typische_satzanfaenge, verbindungen, beispiele}
#   wortschatz.{signalwoerter, fuellwoerter, verbotene_woerter, ...}
#   erzaehlmuster.{story_einstieg, argumentation, perspektive}
#   emotionaler_ausdruck.{spektrum, humor_typ}
#   persoenlichkeits_stance.{archetyp, stance_in_aktion}
#   emotionaler_subtext.{subtext}
#   ueberzeugungsstil.{primaer}
#   zielgruppen_sprachfilter.{leser_profil, sprachbarrieren}
#   vermeidungsprofil.{nie_sagen}
#   referenz_saetze.{original (minItems:5), adaptiert (minItems:3)}

P03_V2_TO_CANONICAL: list[dict] = [
    # OFFEN: v2.tonalitaet ist ein freies Objekt.
    # Kanonisch: grundton hat 3 Pflichtfelder (charakterisierung, spektrum,
    # linkedin_kalibrierung) und ist ein Vertragsobjekt mit minItems-Regeln.
    # Es gibt keine 1:1-Entsprechung — bestenfalls partiell.
    {
        "v2_field": "tonalitaet",
        "canonical_path": "grundton",
        "lossy": True,
        "note": (
            "LOSSY: v2.tonalitaet ist freies Objekt. "
            "Kanonisch grundton hat Pflichtfelder charakterisierung/spektrum/"
            "linkedin_kalibrierung. "
            "Mapping via _map_tonalitaet_to_grundton(). "
            "OFFEN: Pflichtfelder können aus Alt-Payload häufig NICHT "
            "verlässlich befüllt werden → Re-Run von P03 empfohlen."
        ),
    },
    # OFFEN: v2.kernthemen hat KEIN Ziel im kanonischen P03-Schema!
    # Louis' P03 ist bewusst ein Form-Profil (WIE), nicht ein Inhalts-Profil (WAS).
    # kernthemen (Content-Säulen) passen eher in P01.content_reservoir.wiederkehrende_themen.
    # → Im kanonischen P03-Output nicht enthalten; wird in _meta.luecken notiert.
    {
        "v2_field": "kernthemen",
        "canonical_path": None,
        "lossy": True,
        "note": (
            "KEIN KANONISCHES ZIEL: v2.kernthemen (Content-Säulen) existiert in "
            "p03.schema.json nicht — Louis trennt Form (P03) von Inhalt (P01). "
            "Kandidat: p01.content_reservoir.wiederkehrende_themen. "
            "Wird in _meta.luecken markiert, NICHT im kanonischen P03-Output übernommen."
        ),
    },
    # OFFEN: v2.stilprinzipien → kanonisch satzarchitektur + erzaehlmuster
    # Beide haben Pflichtfelder die aus einem freien Stilprinzipien-Objekt
    # nicht zuverlässig befüllt werden können.
    {
        "v2_field": "stilprinzipien",
        "canonical_path": "satzarchitektur",
        "lossy": True,
        "note": (
            "LOSSY: v2.stilprinzipien ist ein freies Objekt. "
            "Kanonisch: satzarchitektur (laenge, typische_satzanfaenge, verbindungen, "
            "beispiele) + erzaehlmuster (story_einstieg, argumentation, perspektive). "
            "Sub-Felder werden per Best-Effort befüllt; Arrays wie typische_satzanfaenge "
            "(minItems:3) können aus freien Texten meist NICHT atomisch extrahiert werden."
        ),
    },
    # P03.wortschatz: einziges Feld das in beiden Schemas vorkommt.
    # v2: freies Objekt — Sub-Felder variieren (LLM-Output abhängig).
    # Kanonisch: wortschatz.signalwoerter (Pflicht, minItems:1),
    #            wortschatz.fuellwoerter, wortschatz.verbotene_woerter (Pflicht).
    {
        "v2_field": "wortschatz",
        "canonical_path": "wortschatz",
        "lossy": True,
        "note": (
            "TEILWEISE LOSSY: Feld existiert in beiden Schemas. "
            "Sub-Struktur differiert: v2 hat variable Sub-Felder, "
            "kanonisch erfordert signalwoerter/fuellwoerter/verbotene_woerter. "
            "Mapping via _map_wortschatz_p03() — versucht bekannte Sub-Felder "
            "zu übernehmen; fehlende Pflichtfelder → Lücken-Markierung."
        ),
    },
    # OFFEN: v2.schreibrhythmus → kanonisch satzarchitektur.laenge (partiell)
    # schreibrhythmus enthält Satzlängen-Info, aber auch Rhythmus/Pause-Angaben
    # die im kanonischen Schema kein direktes Ziel haben.
    {
        "v2_field": "schreibrhythmus",
        "canonical_path": "satzarchitektur.laenge",
        "lossy": True,
        "note": (
            "LOSSY: v2.schreibrhythmus ist ein Objekt mit Satzlänge + Rhythmus. "
            "Kanonisch: nur satzarchitektur.laenge (String) ist das nächste Ziel. "
            "Rhythmus-Inhalte jenseits der Länge gehen verloren."
        ),
    },
    # v2.vermeidungsregeln (array) → kanonisch vermeidungsprofil.nie_sagen (array, minItems:1)
    {
        "v2_field": "vermeidungsregeln",
        "canonical_path": "vermeidungsprofil.nie_sagen",
        "lossy": False,
        "note": (
            "Direktes Mapping möglich. v2: array of strings/objects. "
            "Kanonisch: nie_sagen: array of (string|object with item/grund). "
            "Strings werden direkt übernommen; Objekte per Best-Effort."
        ),
    },
]

# ── P04: audience-avatar → kanonisch ────────────────────────────────────────
#
# v2-Felder (backend/schemas/p04_output_schema.json):
#   hauptperson    (object|null) — Beschreibung der Zielgruppe
#   kernschmerzen  (array|null)
#   transformation (object|null)
#   einwaende      (array|null)
#   kaufmotive     (array|null)
#   sprachmuster   (object|null)
#
# Kanonische Felder (p04.schema.json):
#   identitaet.{rolle_und_alltag, selbstbild}
#   innenwelt.{innerer_monolog (minItems:3), unausgesprochene_angst}
#   wunschbild.{wunschzustand, wunschidentitaet}
#   content_trigger.{scroll_stopper (minItems:3), resonanz_saetze (minItems:5), abstoss_trigger (minItems:2)}
#   sprache_der_zielgruppe.{redewendungen (minItems:3), ansprache}
#   alltagsszenen.{szenen (minItems:5), wiederkehrende_muster (minItems:3)}
#   blockaden.{glaubenssaetze (minItems:3), denkfehler (minItems:2)}
#   ausloesemoment.{trigger_events (minItems:3), emotional_tipping_point}

P04_V2_TO_CANONICAL: list[dict] = [
    # OFFEN: v2.hauptperson ist ein freies Objekt über die Zielgruppe.
    # Kanonisch: identitaet.rolle_und_alltag (Pflicht-String) + selbstbild (Pflicht-String).
    {
        "v2_field": "hauptperson",
        "canonical_path": "identitaet",
        "lossy": True,
        "note": (
            "LOSSY: v2.hauptperson ist freies Objekt. "
            "Kanonisch: identitaet mit Pflichtfeldern rolle_und_alltag/selbstbild. "
            "Falls hauptperson ein String ist → rolle_und_alltag. "
            "Falls Objekt: Sub-Felder per Best-Effort befüllen. "
            "fremdwahrnehmung fehlt in v2 → Lücke."
        ),
    },
    # v2.kernschmerzen (array) → kanonisch innenwelt + blockaden
    # innenwelt.innerer_monolog (minItems:3) könnte aus kernschmerzen befüllt werden,
    # aber unausgesprochene_angst (Pflicht-String) fehlt in v2.
    {
        "v2_field": "kernschmerzen",
        "canonical_path": "innenwelt",
        "lossy": True,
        "note": (
            "LOSSY: v2.kernschmerzen ist array. "
            "Kanonisch: innenwelt.innerer_monolog (array, minItems:3) + "
            "unausgesprochene_angst (String, Pflicht). "
            "Kernschmerzen → innerer_monolog per Best-Effort (wenn genug Einträge). "
            "unausgesprochene_angst: wird als erster Kernschmerz verwendet (verlustbehaftet). "
            "OFFEN: blockaden.glaubenssaetze + denkfehler haben keinen direkten "
            "v2-Quell-Kandidaten außer kernschmerzen → Lücken-Markierung."
        ),
    },
    # v2.transformation (object) → kanonisch wunschbild
    {
        "v2_field": "transformation",
        "canonical_path": "wunschbild",
        "lossy": True,
        "note": (
            "LOSSY: v2.transformation ist freies Objekt. "
            "Kanonisch: wunschbild.wunschzustand (String, Pflicht) + "
            "wunschidentitaet (String, Pflicht). "
            "Falls transformation ein String ist → wunschzustand. "
            "Falls Objekt: Sub-Felder per Best-Effort."
        ),
    },
    # v2.einwaende (array) → kanonisch blockaden.glaubenssaetze / denkfehler
    {
        "v2_field": "einwaende",
        "canonical_path": "blockaden",
        "lossy": True,
        "note": (
            "LOSSY: v2.einwaende ist array. "
            "Kanonisch: blockaden.glaubenssaetze (minItems:3) + denkfehler (minItems:2). "
            "Einwände → erste Hälfte als glaubenssaetze, zweite als denkfehler (heuristisch). "
            "OFFEN: Semantischer Unterschied Einwand vs. Glaubenssatz/Denkfehler ist "
            "nicht immer deckungsgleich → Review nötig."
        ),
    },
    # v2.kaufmotive (array) → kanonisch ausloesemoment + wunschbild
    {
        "v2_field": "kaufmotive",
        "canonical_path": "ausloesemoment",
        "lossy": True,
        "note": (
            "LOSSY: v2.kaufmotive ist array. "
            "Kanonisch: ausloesemoment.trigger_events (minItems:3) + "
            "emotional_tipping_point (String, Pflicht). "
            "Kaufmotive → trigger_events per Best-Effort. "
            "emotional_tipping_point: wird als erstes Kaufmotiv verwendet (verlustbehaftet). "
            "OFFEN: alltagsszenen hat keinen v2-Quell-Kandidaten → immer Lücke."
        ),
    },
    # v2.sprachmuster (object) → kanonisch sprache_der_zielgruppe
    {
        "v2_field": "sprachmuster",
        "canonical_path": "sprache_der_zielgruppe",
        "lossy": True,
        "note": (
            "LOSSY: v2.sprachmuster ist freies Objekt. "
            "Kanonisch: sprache_der_zielgruppe.redewendungen (array, minItems:3) + "
            "ansprache (String, Pflicht). "
            "Falls sprachmuster Sub-Felder hat: per Best-Effort. "
            "content_trigger hat KEINEN v2-Quell-Kandidaten → immer Lücke."
        ),
    },
]

# Lookup-Tabelle für to_canonical / from_canonical
_MAPPING_TABLES: dict[str, list[dict]] = {
    "p01": P01_V2_TO_CANONICAL,
    "p03": P03_V2_TO_CANONICAL,
    "p04": P04_V2_TO_CANONICAL,
}


# ---------------------------------------------------------------------------
# Interne Mapping-Hilfsfunktionen (Best-Effort, nie halluzinierend)
# ---------------------------------------------------------------------------


def _get_nested(obj: Any, dotted_path: str, default: Any = None) -> Any:
    """Gibt den Wert an einem Dotted-Path zurück oder default."""
    parts = dotted_path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return default
        if current is None:
            return default
    return current


def _set_nested(obj: dict, dotted_path: str, value: Any) -> None:
    """Setzt einen Wert an einem Dotted-Path; erstellt fehlende Zwischen-Dicts."""
    parts = dotted_path.split(".")
    current = obj
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _map_zielgruppe_to_canonical(zielgruppe: Any) -> dict:
    """Best-Effort: v2.zielgruppe → kanonisches zielkunde-Objekt.

    v2.zielgruppe kann ein String oder ein freies Objekt mit variablen
    Sub-Feldern sein. Kanonisch hat zielkunde 10 Sub-Felder.
    """
    if zielgruppe is None:
        return {"beschreibung": None, "wunschzustand": None, "innenwelt": None}

    if isinstance(zielgruppe, str):
        return {
            "beschreibung": zielgruppe,
            "psychografie": None,
            "wunschzustand": None,
            "innenwelt": None,
        }

    if isinstance(zielgruppe, dict):
        # Bekannte Sub-Feld-Muster aus LLM-Outputs
        return {
            "beschreibung": (
                zielgruppe.get("beschreibung")
                or zielgruppe.get("beschreibung_zielgruppe")
                or zielgruppe.get("zusammenfassung")
            ),
            "psychografie": zielgruppe.get("psychografie"),
            "schmerzpunkte_oberflaeche": (
                zielgruppe.get("schmerzpunkte_oberflaeche")
                or zielgruppe.get("schmerzpunkte")
                or zielgruppe.get("probleme")
            ),
            "schmerzpunkte_tiefe": zielgruppe.get("schmerzpunkte_tiefe"),
            "bisherige_loesungsversuche": zielgruppe.get("bisherige_loesungsversuche"),
            "haeufigste_frage": zielgruppe.get("haeufigste_frage"),
            "fehlglauben": zielgruppe.get("fehlglauben"),
            "filter_positiv": zielgruppe.get("filter_positiv"),
            "filter_negativ": zielgruppe.get("filter_negativ"),
            # P01-Vertrag: IMMER null
            "wunschzustand": None,
            "innenwelt": None,
        }

    return {"beschreibung": str(zielgruppe), "wunschzustand": None, "innenwelt": None}


def _map_expertise_to_vertrauen(expertise: Any) -> dict:
    """Best-Effort: v2.expertise → kanonisches vertrauen-Objekt."""
    if expertise is None:
        return {}
    if isinstance(expertise, str):
        return {"erfolgsgeschichte": expertise}
    if isinstance(expertise, dict):
        return {
            "erfahrung_jahre": expertise.get("erfahrung_jahre") or expertise.get("jahre"),
            "kunden_anzahl": expertise.get("kunden_anzahl") or expertise.get("kunden"),
            "zertifikate": expertise.get("zertifikate"),
            "auszeichnungen": expertise.get("auszeichnungen"),
            "erfolgsgeschichte": expertise.get("erfolgsgeschichte") or expertise.get("erfahrung"),
            "kundenzitate": expertise.get("kundenzitate") or expertise.get("testimonials"),
        }
    return {"erfolgsgeschichte": str(expertise)}


def _map_tonalitaet_to_grundton(tonalitaet: Any) -> dict:
    """Best-Effort: v2.tonalitaet → kanonisches grundton-Objekt.

    grundton ist ein Pflicht-Objekt mit charakterisierung/spektrum/linkedin_kalibrierung.
    Alle drei sind Strings. v2.tonalitaet ist ein freies Objekt.
    """
    if tonalitaet is None:
        return {}
    if isinstance(tonalitaet, str):
        return {"charakterisierung": tonalitaet, "spektrum": None, "linkedin_kalibrierung": None}
    if isinstance(tonalitaet, dict):
        return {
            "charakterisierung": (
                tonalitaet.get("charakterisierung")
                or tonalitaet.get("beschreibung")
                or tonalitaet.get("grundton")
                or tonalitaet.get("ton")
            ),
            "spektrum": tonalitaet.get("spektrum"),
            "linkedin_kalibrierung": (
                tonalitaet.get("linkedin_kalibrierung") or tonalitaet.get("kalibrierung")
            ),
        }
    return {"charakterisierung": str(tonalitaet)}


def _map_stilprinzipien_to_satzarchitektur(stilprinzipien: Any) -> dict:
    """Best-Effort: v2.stilprinzipien → kanonisches satzarchitektur-Objekt."""
    if stilprinzipien is None:
        return {}
    if isinstance(stilprinzipien, str):
        return {
            "laenge": stilprinzipien,
            "typische_satzanfaenge": [],
            "verbindungen": None,
            "beispiele": [],
        }
    if isinstance(stilprinzipien, dict):
        return {
            "laenge": (
                stilprinzipien.get("laenge")
                or stilprinzipien.get("satzlaenge")
                or stilprinzipien.get("satz_laenge")
            ),
            "typische_satzanfaenge": (
                stilprinzipien.get("typische_satzanfaenge")
                or stilprinzipien.get("satzanfaenge")
                or []
            ),
            "verbindungen": stilprinzipien.get("verbindungen"),
            "fragmente": stilprinzipien.get("fragmente"),
            "beispiele": stilprinzipien.get("beispiele") or [],
        }
    return {}


def _map_wortschatz_p03(wortschatz: Any) -> dict:
    """Best-Effort: v2.wortschatz → kanonisches wortschatz-Objekt für P03.

    Kanonisch: signalwoerter (Pflicht, array), fuellwoerter, verbotene_woerter (Pflicht).
    """
    if wortschatz is None:
        return {}
    if isinstance(wortschatz, dict):
        # Versuche bekannte Sub-Felder zu übernehmen
        return {
            "signalwoerter": (
                wortschatz.get("signalwoerter")
                or wortschatz.get("signal_woerter")
                or wortschatz.get("markenwörter")
                or []
            ),
            "fuellwoerter": (
                wortschatz.get("fuellwoerter") or wortschatz.get("fuell_woerter") or []
            ),
            "verbotene_woerter": (
                wortschatz.get("verbotene_woerter")
                or wortschatz.get("verbotene_wörter")
                or wortschatz.get("tabu")
                or []
            ),
            "fachsprache_level": wortschatz.get("fachsprache_level"),
            "fachsprache_beschreibung": wortschatz.get("fachsprache_beschreibung"),
            "anglizismen": wortschatz.get("anglizismen"),
            "intensitaetsmarker": wortschatz.get("intensitaetsmarker") or [],
        }
    return {}


def _map_schreibrhythmus_to_laenge(schreibrhythmus: Any) -> Any:
    """Best-Effort: v2.schreibrhythmus → kanonisches satzarchitektur.laenge (String)."""
    if schreibrhythmus is None:
        return None
    if isinstance(schreibrhythmus, str):
        return schreibrhythmus
    if isinstance(schreibrhythmus, dict):
        return (
            schreibrhythmus.get("laenge")
            or schreibrhythmus.get("satzlaenge")
            or schreibrhythmus.get("beschreibung")
        )
    return None


def _map_hauptperson_to_identitaet(hauptperson: Any) -> dict:
    """Best-Effort: v2.hauptperson → kanonisches identitaet-Objekt."""
    if hauptperson is None:
        return {}
    if isinstance(hauptperson, str):
        return {"rolle_und_alltag": hauptperson, "selbstbild": None}
    if isinstance(hauptperson, dict):
        return {
            "rolle_und_alltag": (
                hauptperson.get("rolle_und_alltag")
                or hauptperson.get("rolle")
                or hauptperson.get("beschreibung")
            ),
            "selbstbild": hauptperson.get("selbstbild"),
            "fremdwahrnehmung": hauptperson.get("fremdwahrnehmung"),
        }
    return {"rolle_und_alltag": str(hauptperson), "selbstbild": None}


def _map_kernschmerzen_to_innenwelt(kernschmerzen: Any) -> dict:
    """Best-Effort: v2.kernschmerzen → kanonisches innenwelt-Objekt."""
    if not kernschmerzen:
        return {}
    items = kernschmerzen if isinstance(kernschmerzen, list) else [str(kernschmerzen)]
    return {
        "innerer_monolog": items[: max(len(items), 3)],
        "unausgesprochene_angst": items[0] if items else None,
    }


def _map_transformation_to_wunschbild(transformation: Any) -> dict:
    """Best-Effort: v2.transformation → kanonisches wunschbild-Objekt."""
    if transformation is None:
        return {}
    if isinstance(transformation, str):
        return {"wunschzustand": transformation, "wunschidentitaet": None}
    if isinstance(transformation, dict):
        return {
            "wunschzustand": (
                transformation.get("wunschzustand")
                or transformation.get("zielzustand")
                or transformation.get("transformation")
            ),
            "wunschidentitaet": (
                transformation.get("wunschidentitaet") or transformation.get("neue_identitaet")
            ),
            "status_signal": transformation.get("status_signal"),
        }
    return {"wunschzustand": str(transformation), "wunschidentitaet": None}


def _map_einwaende_to_blockaden(einwaende: Any) -> dict:
    """Best-Effort: v2.einwaende → kanonisches blockaden-Objekt.

    Heuristik: erste Hälfte → glaubenssaetze, zweite → denkfehler.
    """
    if not einwaende:
        return {}
    items = einwaende if isinstance(einwaende, list) else [str(einwaende)]
    mid = max(len(items) // 2, 1)
    return {
        "glaubenssaetze": items[:mid] if items else [],
        "denkfehler": items[mid:] if len(items) > mid else [],
    }


def _map_kaufmotive_to_ausloesemoment(kaufmotive: Any) -> dict:
    """Best-Effort: v2.kaufmotive → kanonisches ausloesemoment-Objekt."""
    if not kaufmotive:
        return {}
    items = kaufmotive if isinstance(kaufmotive, list) else [str(kaufmotive)]
    return {
        "trigger_events": items,
        "emotional_tipping_point": items[0] if items else None,
    }


def _map_sprachmuster_to_sprache_der_zielgruppe(sprachmuster: Any) -> dict:
    """Best-Effort: v2.sprachmuster → kanonisches sprache_der_zielgruppe-Objekt."""
    if sprachmuster is None:
        return {}
    if isinstance(sprachmuster, str):
        return {"redewendungen": [], "ansprache": sprachmuster}
    if isinstance(sprachmuster, dict):
        return {
            "redewendungen": (
                sprachmuster.get("redewendungen") or sprachmuster.get("phrasen") or []
            ),
            "tabu_woerter": sprachmuster.get("tabu_woerter") or [],
            "ansprache": (sprachmuster.get("ansprache") or sprachmuster.get("du_sie")),
        }
    return {"redewendungen": [], "ansprache": None}


# ---------------------------------------------------------------------------
# _meta-Rehydrierung aus DB-Spalten
# ---------------------------------------------------------------------------


def _build_meta(prompt_key: str, meta: dict) -> dict:
    """Rehydriert das kanonische _meta-Objekt aus DB-Spalten / übergebenen Werten.

    Das _meta-Feld wird NIE im v2-payload gespeichert (ADR-0002). Stattdessen
    liegen die Informationen in DB-Spalten. Diese Funktion baut das kanonische
    _meta aus dem `meta`-Dict zusammen, das Aufrufer mit den DB-Spalten befüllen.

    Erwartete Schlüssel in `meta`:
      - tenant_id (str):           DB-Spalte; wird zu kunde_id slugged
      - tenant_name (str):         Optional — Klarnamen für slug-Generierung
      - tenant_slug (str):         Optional — direkter Slug (Prio vor tenant_name)
      - model_id (str):            DB-Spalte model_id → _meta.model
      - prompt_version_hash (str): DB-Spalte; wird zu prompt_version gemappt
                                   (falls kein semantisches 'p0X-v...' bekannt → 'legacy')
      - created_at (str):          ISO-8601 Timestamp → _meta.generated_at
      - row_id (str):              Optional → _meta.generation_id (als 'gen_<id>')
      - token_usage (dict):        Optional — aus llm_call_log-Join
      - luecken (list):            Vom Transformer gesetzte Lücken-Liste

    Fehlende Schlüssel werden als None / 'unknown' / [] gesetzt, NICHT halluziniert.
    """
    prompt_key_lower = prompt_key.lower()

    # kunde_id: Prio: tenant_slug → _slugify(tenant_name) → _slugify(tenant_id)
    tenant_slug = (meta.get("tenant_slug") or "").strip()
    if not tenant_slug:
        tenant_name = (meta.get("tenant_name") or "").strip()
        if tenant_name:
            tenant_slug = _slugify(tenant_name)
        else:
            tenant_slug = _slugify(str(meta.get("tenant_id") or "unknown"))

    # agentur_id: heute immer 'zb' (Zukunftsbund).
    # OFFEN (Stufe iv): Neue Spalte 'agentur_id' in tenants-Tabelle geplant
    # (050_canonical_meta_columns.py). Bis dahin Fallback auf 'zb'.
    agentur_id = (meta.get("agentur_id") or "zb").strip() or "zb"

    # prompt_version: semantische Version aus bekannten Hash-Mappings
    # OFFEN: Vollständige Hash→Version-Mapping-Tabelle in separatem ADR definieren.
    raw_version = meta.get("prompt_version") or meta.get("prompt_version_hash") or ""
    prompt_version = _resolve_prompt_version(prompt_key_lower, raw_version)

    # model: DB-Spalte model_id
    model = meta.get("model_id") or meta.get("model") or "unknown"

    # generated_at: DB-Spalte created_at
    generated_at = meta.get("created_at") or meta.get("generated_at") or ""

    # generation_id: aus row_id ableiten
    row_id = meta.get("row_id") or meta.get("id") or ""
    generation_id = f"gen_{row_id}" if row_id else ""

    result: dict = {
        "agentur_id": agentur_id,
        "kunde_id": tenant_slug,
        "prompt_version": prompt_version,
        "model": model,
        "generated_at": generated_at,
    }
    if generation_id:
        result["generation_id"] = generation_id

    token_usage = meta.get("token_usage")
    if token_usage and isinstance(token_usage, dict):
        result["token_usage"] = token_usage

    luecken = meta.get("luecken") or []
    if luecken:
        result["luecken"] = luecken

    return result


def _resolve_prompt_version(prompt_key: str, raw: str) -> str:
    """Versucht, einen Hash oder freien String in eine semantische Version umzuwandeln.

    Reihenfolge:
    1. Leer/None → '<key>-legacy'.
    2. Bereits semantische Version ('^p0[0-9]+-v...' oder '^values-v...') → direkt.
    3. Hash == SHA-256 des aktuellen Prompt-Files für prompt_key → '<key>-v1.0'.
       (fail-open: Datei nicht lesbar / unbekannter Schlüssel → weiter zu 4.)
    4. Unbekannter Hash → '<key>-legacy'.

    INVARIANTE: Rows mit altem/unbekanntem Hash bleiben 'legacy' (is_canonical=False).
    NICHT-implementiert: historische Hash→Version-Mappings (= Robert/DEFERIERT, Issue #26).
    """
    if not raw:
        return f"{prompt_key}-legacy"

    # Prüfe ob bereits eine semantische Version (beide Namensräume: p0X + values)
    if re.match(r"^(p0[0-9]+|values)-v[0-9]+\.[0-9]+$", raw):
        return raw

    # Aktuellen Prompt-SHA prüfen (lazy, gecacht, fail-open)
    current_sha = _get_current_prompt_sha(prompt_key)
    if current_sha and raw == current_sha:
        resolved = f"{prompt_key}-{_CURRENT_PROMPT_VERSION}"
        logger.debug(
            "prompt_version_hash '%s' für %s matcht aktuellen Prompt-SHA → %s",
            raw[:16],
            prompt_key,
            resolved,
        )
        return resolved

    logger.debug("prompt_version_hash '%s' für %s unbekannt → 'legacy'", raw[:16], prompt_key)
    return f"{prompt_key}-legacy"


# Aktuelle semantische Vertragsversion für neue Prompt-SHA-Matches.
# Zentral definiert — beim Bump des Prompts hier erhöhen UND content-truth commiten.
_CURRENT_PROMPT_VERSION: str = "v1.0"

# Prompt-Key → Relativer Pfad unter content-truth/ (spiegelt PROMPT_PATHS in prompt_loader).
# Nur die drei nativen Schreibpfad-Prompts (P01/P03/P04).
_PROMPT_RELATIVE_PATHS: dict[str, str] = {
    "p01": "prompts/P01-kundenkontext-extraktion.md",
    "p03": "prompts/P03-voice-analyse.md",
    "p04": "prompts/P04-kundenavatar-vertiefung.md",
}

# Prozess-Level-Cache: prompt_key → SHA-256-Hex (einmal berechnet, nie invalidiert).
# Akzeptierbar: Prompt-Files ändern sich nur bei Deployments.
_PROMPT_SHA_CACHE: dict[str, str] = {}


def _get_current_prompt_sha(prompt_key: str) -> str | None:
    """Gibt den SHA-256-Hex des aktuellen Prompt-Files zurück. Fail-open: None.

    Nutzt einen Prozess-Level-Cache (ein Lese-IO pro Prompt-Key pro Prozess-Start).
    Unbekannte prompt_keys oder nicht-lesbare Dateien → None (kein Absturz).
    """
    cached = _PROMPT_SHA_CACHE.get(prompt_key)
    if cached is not None:
        return cached

    rel_path = _PROMPT_RELATIVE_PATHS.get(prompt_key)
    if rel_path is None:
        return None

    # Basis-Verzeichnis: CONTENT_TRUTH_BASE_PATH oder Fallback analog _get_content_truth_schemas_dir
    base = _get_content_truth_base_dir()
    file_path = base / rel_path
    try:
        raw_bytes = file_path.read_bytes()
        sha = hashlib.sha256(raw_bytes).hexdigest()
        _PROMPT_SHA_CACHE[prompt_key] = sha
        logger.debug("_get_current_prompt_sha(%s): %s (aus %s)", prompt_key, sha[:16], file_path)
        return sha
    except OSError as exc:
        logger.debug(
            "_get_current_prompt_sha(%s): Datei nicht lesbar (%s) → fail-open",
            prompt_key,
            exc,
        )
        return None


def _get_content_truth_base_dir() -> Path:
    """Gibt das content-truth-Basisverzeichnis zurück (ohne '/schemas'-Suffix).

    Analog zu _get_content_truth_schemas_dir() — wiederverwendet dieselbe
    Env-Variable und Config-Quelle, gibt aber das Basisverzeichnis zurück.
    """
    env_path = os.environ.get("CONTENT_TRUTH_BASE_PATH", "").strip()
    if env_path:
        return Path(env_path)

    try:
        from config import settings  # type: ignore

        return Path(settings.content_truth_base_path)
    except Exception:
        pass

    # Fallback: relativ zu dieser Datei → backend/../content-truth
    return Path(__file__).parent.parent.parent / "content-truth"


# ---------------------------------------------------------------------------
# to_canonical: v2-DB-Row → kanonisches Louis-JSON
# ---------------------------------------------------------------------------


def to_canonical(prompt_key: str, v2_payload: dict, meta: dict) -> dict:
    """Übersetzt einen v2-DB-Payload in das kanonische Louis-Format.

    Args:
        prompt_key: 'p01', 'p03' oder 'p04'.
        v2_payload: Das raw payload-Dict aus der DB-Spalte (ohne _meta).
        meta:       Dict mit DB-Spalten-Werten für _meta-Rehydrierung.
                    Erwartete Schlüssel: siehe _build_meta().

    Returns:
        Kanonisches Dict (inkl. _meta). Lossy-Felder werden als Lücken
        in _meta.luecken markiert. Nie wird halluziniert.

    Raises:
        KeyError: Wenn prompt_key unbekannt ist.
    """
    key = prompt_key.lower()
    if key not in _MAPPING_TABLES:
        raise KeyError(
            f"Unbekannter prompt_key '{prompt_key}'. " f"Unterstützt: {sorted(_MAPPING_TABLES)}"
        )

    luecken: list[str] = []
    canonical: dict = {}

    if key == "p01":
        canonical = _to_canonical_p01(v2_payload, luecken)
    elif key == "p03":
        canonical = _to_canonical_p03(v2_payload, luecken)
    elif key == "p04":
        canonical = _to_canonical_p04(v2_payload, luecken)

    # _meta rehydrieren (Lücken werden in meta injiziert)
    meta_with_luecken = dict(meta)
    if luecken:
        existing = meta_with_luecken.get("luecken") or []
        meta_with_luecken["luecken"] = existing + luecken

    canonical["_meta"] = _build_meta(key, meta_with_luecken)
    return canonical


def _to_canonical_p01(v2: dict, luecken: list[str]) -> dict:
    """P01-spezifische to_canonical-Logik."""
    result: dict = {
        "person": {},
        "zielkunde": {},
        "angebot": {},
        "positionierung": {},
        "markt": {},
        "vertrauen": {},
        "sprache": {},
        "content_reservoir": {},
    }

    # unternehmensgeschichte → person.gruendungsgeschichte
    result["person"]["gruendungsgeschichte"] = v2.get("unternehmensgeschichte")

    # person.wendepunkt fehlt in v2 → Lücke
    if v2.get("unternehmensgeschichte"):
        luecken.append("person.wendepunkt: nicht aus v2.unternehmensgeschichte ableitbar")
    result["person"]["wendepunkt"] = None

    # kernbotschaft → angebot.elevator_pitch
    result["angebot"]["elevator_pitch"] = v2.get("kernbotschaft")

    # werte (array) → positionierung.werte_schwerpunkt (string)
    werte = v2.get("werte")
    if isinstance(werte, list) and werte:
        result["positionierung"]["werte_schwerpunkt"] = ", ".join(str(w) for w in werte if w)
    elif isinstance(werte, str):
        result["positionierung"]["werte_schwerpunkt"] = werte
    else:
        result["positionierung"]["werte_schwerpunkt"] = None

    # zielgruppe → zielkunde (lossy)
    zielgruppe = v2.get("zielgruppe")
    result["zielkunde"] = _map_zielgruppe_to_canonical(zielgruppe)
    if zielgruppe:
        luecken.append(
            "zielkunde: v2.zielgruppe ist ein freies Objekt; "
            "psychografie/schmerzpunkte_tiefe/fehlglauben konnten nicht vollständig befüllt werden"
        )

    # expertise → vertrauen (lossy)
    expertise = v2.get("expertise")
    result["vertrauen"] = _map_expertise_to_vertrauen(expertise)
    if expertise:
        luecken.append(
            "vertrauen: v2.expertise ist ein freies Objekt; "
            "Sub-Felder wurden per Best-Effort befüllt"
        )

    # v2 hat keine Felder für: person.name/rolle/unternehmen/branche/...
    luecken.append(
        "person.name/rolle/unternehmen/branche/tagesablauf/antrieb: "
        "keine v2-Quellfelder vorhanden → immer null"
    )

    # v2 hat keine Felder für: markt, sprache, content_reservoir
    luecken.append("markt/sprache/content_reservoir: keine v2-Quellfelder vorhanden → leer")

    # wunschzustand / innenwelt: P01-Vertrag → immer null
    result["zielkunde"]["wunschzustand"] = None
    result["zielkunde"]["innenwelt"] = None

    return result


def _to_canonical_p03(v2: dict, luecken: list[str]) -> dict:
    """P03-spezifische to_canonical-Logik."""
    result: dict = {
        "grundton": {},
        "satzarchitektur": {},
        "wortschatz": {},
        "erzaehlmuster": {},
        "emotionaler_ausdruck": {},
        "persoenlichkeits_stance": {},
        "emotionaler_subtext": {},
        "ueberzeugungsstil": {},
        "zielgruppen_sprachfilter": {},
        "vermeidungsprofil": {},
        "referenz_saetze": {},
    }

    # tonalitaet → grundton
    tonalitaet = v2.get("tonalitaet")
    mapped_grundton = _map_tonalitaet_to_grundton(tonalitaet)
    result["grundton"].update(mapped_grundton)
    if not mapped_grundton.get("charakterisierung"):
        luecken.append(
            "grundton.charakterisierung: aus v2.tonalitaet nicht befüllbar → Re-Run P03 empfohlen"
        )

    # stilprinzipien → satzarchitektur
    stilprinzipien = v2.get("stilprinzipien")
    mapped_satz = _map_stilprinzipien_to_satzarchitektur(stilprinzipien)
    result["satzarchitektur"].update(mapped_satz)

    # schreibrhythmus → satzarchitektur.laenge (nur wenn noch nicht gesetzt)
    schreibrhythmus = v2.get("schreibrhythmus")
    if schreibrhythmus and not result["satzarchitektur"].get("laenge"):
        result["satzarchitektur"]["laenge"] = _map_schreibrhythmus_to_laenge(schreibrhythmus)

    # satzarchitektur Pflicht-Arrays mit minItems:3
    if not result["satzarchitektur"].get("typische_satzanfaenge"):
        luecken.append(
            "satzarchitektur.typische_satzanfaenge (minItems:3): "
            "nicht aus v2 ableitbar → Re-Run P03 empfohlen"
        )
        result["satzarchitektur"]["typische_satzanfaenge"] = []

    if not result["satzarchitektur"].get("beispiele"):
        result["satzarchitektur"]["beispiele"] = []

    # wortschatz → wortschatz (partiell lossy)
    wortschatz = v2.get("wortschatz")
    mapped_wortschatz = _map_wortschatz_p03(wortschatz)
    result["wortschatz"].update(mapped_wortschatz)
    if not result["wortschatz"].get("signalwoerter"):
        luecken.append("wortschatz.signalwoerter (Pflicht): nicht aus v2.wortschatz befüllbar")
        result["wortschatz"]["signalwoerter"] = []
    if "verbotene_woerter" not in result["wortschatz"]:
        result["wortschatz"]["verbotene_woerter"] = []

    # kernthemen: kein kanonisches Ziel in P03 → nur Lücke notieren
    kernthemen = v2.get("kernthemen")
    if kernthemen:
        luecken.append(
            "v2.kernthemen hat KEIN kanonisches Ziel in p03.schema.json "
            "(Louis P03 = Form, nicht Inhalt). "
            "Kandidat: p01.content_reservoir.wiederkehrende_themen"
        )

    # Felder ohne v2-Quell-Kandidaten → immer Lücke
    for feld, hinweis in [
        ("erzaehlmuster", "story_einstieg/argumentation/perspektive"),
        ("emotionaler_ausdruck", "spektrum/humor_typ"),
        ("persoenlichkeits_stance", "archetyp/stance_in_aktion"),
        ("emotionaler_subtext", "subtext"),
        ("ueberzeugungsstil", "primaer"),
        ("zielgruppen_sprachfilter", "leser_profil/sprachbarrieren"),
        ("referenz_saetze", "original(minItems:5)/adaptiert(minItems:3)"),
    ]:
        luecken.append(f"{feld}.{hinweis}: kein v2-Quellfeld vorhanden → Re-Run P03 empfohlen")

    # Pflicht-Felder auf Minimalwerte setzen damit Struktur vorhanden
    result["erzaehlmuster"] = {"story_einstieg": None, "argumentation": None, "perspektive": None}
    result["emotionaler_ausdruck"] = {"spektrum": None, "humor_typ": None}
    result["persoenlichkeits_stance"] = {"archetyp": None, "stance_in_aktion": []}
    result["emotionaler_subtext"] = {"subtext": None}
    result["ueberzeugungsstil"] = {"primaer": None}
    result["zielgruppen_sprachfilter"] = {"leser_profil": None, "sprachbarrieren": []}
    result["referenz_saetze"] = {"original": [], "adaptiert": []}

    # vermeidungsregeln → vermeidungsprofil.nie_sagen
    vermeidungsregeln = v2.get("vermeidungsregeln")
    if vermeidungsregeln and isinstance(vermeidungsregeln, list):
        result["vermeidungsprofil"]["nie_sagen"] = vermeidungsregeln
    else:
        result["vermeidungsprofil"]["nie_sagen"] = []
        if not vermeidungsregeln:
            luecken.append(
                "vermeidungsprofil.nie_sagen (Pflicht, minItems:1): v2.vermeidungsregeln leer"
            )

    return result


def _to_canonical_p04(v2: dict, luecken: list[str]) -> dict:
    """P04-spezifische to_canonical-Logik."""
    result: dict = {
        "identitaet": {},
        "innenwelt": {},
        "wunschbild": {},
        "content_trigger": {},
        "sprache_der_zielgruppe": {},
        "alltagsszenen": {},
        "blockaden": {},
        "ausloesemoment": {},
    }

    # hauptperson → identitaet
    result["identitaet"] = _map_hauptperson_to_identitaet(v2.get("hauptperson"))
    if not result["identitaet"].get("rolle_und_alltag"):
        luecken.append("identitaet.rolle_und_alltag (Pflicht): nicht aus v2.hauptperson befüllbar")
    if not result["identitaet"].get("selbstbild"):
        luecken.append("identitaet.selbstbild (Pflicht): nicht aus v2 befüllbar")

    # kernschmerzen → innenwelt
    result["innenwelt"] = _map_kernschmerzen_to_innenwelt(v2.get("kernschmerzen"))
    kernschmerzen = v2.get("kernschmerzen") or []
    if len(kernschmerzen) < 3:
        luecken.append(
            f"innenwelt.innerer_monolog (minItems:3): nur {len(kernschmerzen)} "
            "Kernschmerzen in v2 → unter Mindestanzahl"
        )

    # transformation → wunschbild
    result["wunschbild"] = _map_transformation_to_wunschbild(v2.get("transformation"))
    if not result["wunschbild"].get("wunschzustand"):
        luecken.append("wunschbild.wunschzustand (Pflicht): nicht aus v2.transformation befüllbar")
    if not result["wunschbild"].get("wunschidentitaet"):
        luecken.append("wunschbild.wunschidentitaet (Pflicht): nicht aus v2 befüllbar")

    # einwaende → blockaden
    result["blockaden"] = _map_einwaende_to_blockaden(v2.get("einwaende"))
    einwaende = v2.get("einwaende") or []
    if len(einwaende) < 3:
        luecken.append(
            f"blockaden.glaubenssaetze (minItems:3): nur {len(einwaende)} "
            "Einwände in v2 → unter Mindestanzahl"
        )

    # kaufmotive → ausloesemoment
    result["ausloesemoment"] = _map_kaufmotive_to_ausloesemoment(v2.get("kaufmotive"))
    kaufmotive = v2.get("kaufmotive") or []
    if len(kaufmotive) < 3:
        luecken.append(
            f"ausloesemoment.trigger_events (minItems:3): nur {len(kaufmotive)} "
            "Kaufmotive in v2 → unter Mindestanzahl"
        )

    # sprachmuster → sprache_der_zielgruppe
    result["sprache_der_zielgruppe"] = _map_sprachmuster_to_sprache_der_zielgruppe(
        v2.get("sprachmuster")
    )

    # content_trigger: kein v2-Quellfeld vorhanden
    luecken.append(
        "content_trigger (scroll_stopper/resonanz_saetze/abstoss_trigger): "
        "kein v2-Quellfeld vorhanden → Re-Run P04 empfohlen"
    )
    result["content_trigger"] = {
        "scroll_stopper": [],
        "resonanz_saetze": [],
        "abstoss_trigger": [],
    }

    # alltagsszenen: kein v2-Quellfeld vorhanden
    luecken.append(
        "alltagsszenen (szenen minItems:5 / wiederkehrende_muster minItems:3): "
        "kein v2-Quellfeld vorhanden → Re-Run P04 empfohlen"
    )
    result["alltagsszenen"] = {
        "szenen": [],
        "wiederkehrende_muster": [],
    }

    return result


# ---------------------------------------------------------------------------
# from_canonical: kanonisches Louis-JSON → v2-DB-Payload
# ---------------------------------------------------------------------------


def from_canonical(prompt_key: str, canonical: dict) -> dict:
    """Übersetzt ein kanonisches Louis-Dokument zurück in ein v2-kompatibles Payload-Dict.

    Verwendungszweck: Wenn neue Tasks bereits kanonische Outputs erzeugen und
    diese in den bestehenden v2-DB-Spalten gespeichert werden sollen, ohne
    die Task-Struktur sofort vollständig umzubauen.

    HINWEIS: Die Rück-Übersetzung ist für P01/P04 noch LOSSY, da kanonische
    Felder keine 1:1-Entsprechung in v2 haben. _meta wird aus dem canonical
    extrahiert und als separates Rückgabe-Element genutzt (nicht im payload).

    Args:
        prompt_key: 'p01', 'p03' oder 'p04'.
        canonical:  Kanonisches Dict (inkl. _meta).

    Returns:
        v2-kompatibles payload-Dict (ohne _meta — das gehört in DB-Spalten).

    Raises:
        KeyError: Wenn prompt_key unbekannt ist.
    """
    key = prompt_key.lower()
    if key not in _MAPPING_TABLES:
        raise KeyError(
            f"Unbekannter prompt_key '{prompt_key}'. " f"Unterstützt: {sorted(_MAPPING_TABLES)}"
        )

    if key == "p01":
        return _from_canonical_p01(canonical)
    elif key == "p03":
        return _from_canonical_p03(canonical)
    elif key == "p04":
        return _from_canonical_p04(canonical)

    return {}


def _from_canonical_p01(canonical: dict) -> dict:
    """Kanonisch P01 → v2-Payload."""
    person = canonical.get("person") or {}
    angebot = canonical.get("angebot") or {}
    positionierung = canonical.get("positionierung") or {}
    zielkunde = canonical.get("zielkunde") or {}
    vertrauen = canonical.get("vertrauen") or {}

    return {
        # person.gruendungsgeschichte → unternehmensgeschichte
        "unternehmensgeschichte": person.get("gruendungsgeschichte"),
        # angebot.elevator_pitch → kernbotschaft
        "kernbotschaft": angebot.get("elevator_pitch"),
        # zielkunde → zielgruppe (lossy: Sub-Felder werden als dict übernommen)
        "zielgruppe": {
            k: v for k, v in zielkunde.items() if k not in ("wunschzustand", "innenwelt")
        }
        or None,
        # vertrauen → expertise (lossy)
        "expertise": vertrauen or None,
        # positionierung.werte_schwerpunkt (string) → werte (array of strings, lossy)
        "werte": (
            [w.strip() for w in positionierung["werte_schwerpunkt"].split(",")]
            if positionierung.get("werte_schwerpunkt")
            else []
        ),
        # P01-Vertrag
        "wunschzustand": None,
        "innenwelt": None,
    }


def _from_canonical_p03(canonical: dict) -> dict:
    """Kanonisch P03 → v2-Payload."""
    grundton = canonical.get("grundton") or {}
    wortschatz = canonical.get("wortschatz") or {}
    satzarchitektur = canonical.get("satzarchitektur") or {}
    erzaehlmuster = canonical.get("erzaehlmuster") or {}
    vermeidungsprofil = canonical.get("vermeidungsprofil") or {}

    # tonalitaet: aus grundton rekonstruieren
    tonalitaet = {
        "charakterisierung": grundton.get("charakterisierung"),
        "spektrum": grundton.get("spektrum"),
        "linkedin_kalibrierung": grundton.get("linkedin_kalibrierung"),
    }

    # stilprinzipien: aus satzarchitektur + erzaehlmuster
    stilprinzipien = {
        "laenge": satzarchitektur.get("laenge"),
        "typische_satzanfaenge": satzarchitektur.get("typische_satzanfaenge", []),
        "verbindungen": satzarchitektur.get("verbindungen"),
        "beispiele": satzarchitektur.get("beispiele", []),
        "story_einstieg": erzaehlmuster.get("story_einstieg"),
        "argumentation": erzaehlmuster.get("argumentation"),
    }

    # schreibrhythmus: aus satzarchitektur.laenge (umgekehrte lossy-Konversion)
    schreibrhythmus = {"laenge": satzarchitektur.get("laenge")}

    return {
        "tonalitaet": tonalitaet,
        # OFFEN: kernthemen hat kein kanonisches Pendant → immer leer
        "kernthemen": [],
        "stilprinzipien": stilprinzipien,
        "wortschatz": wortschatz,
        "schreibrhythmus": schreibrhythmus,
        "vermeidungsregeln": vermeidungsprofil.get("nie_sagen", []),
    }


def _from_canonical_p04(canonical: dict) -> dict:
    """Kanonisch P04 → v2-Payload."""
    identitaet = canonical.get("identitaet") or {}
    innenwelt = canonical.get("innenwelt") or {}
    wunschbild = canonical.get("wunschbild") or {}
    blockaden = canonical.get("blockaden") or {}
    ausloesemoment = canonical.get("ausloesemoment") or {}
    sprache = canonical.get("sprache_der_zielgruppe") or {}

    # hauptperson: aus identitaet
    hauptperson = {
        "rolle_und_alltag": identitaet.get("rolle_und_alltag"),
        "selbstbild": identitaet.get("selbstbild"),
        "fremdwahrnehmung": identitaet.get("fremdwahrnehmung"),
    }

    # kernschmerzen: aus innenwelt.innerer_monolog
    kernschmerzen = innenwelt.get("innerer_monolog") or []

    # transformation: aus wunschbild
    transformation = {
        "wunschzustand": wunschbild.get("wunschzustand"),
        "wunschidentitaet": wunschbild.get("wunschidentitaet"),
    }

    # einwaende: blockaden.glaubenssaetze + denkfehler zusammenführen
    einwaende = list(blockaden.get("glaubenssaetze") or []) + list(
        blockaden.get("denkfehler") or []
    )

    # kaufmotive: aus ausloesemoment.trigger_events
    kaufmotive = ausloesemoment.get("trigger_events") or []

    return {
        "hauptperson": hauptperson,
        "kernschmerzen": kernschmerzen,
        "transformation": transformation,
        "einwaende": einwaende,
        "kaufmotive": kaufmotive,
        "sprachmuster": {
            "redewendungen": sprache.get("redewendungen", []),
            "tabu_woerter": sprache.get("tabu_woerter", []),
            "ansprache": sprache.get("ansprache"),
        },
    }


# ---------------------------------------------------------------------------
# Nativer Schreibpfad: kanonisches _meta bauen + Output finalisieren
# ---------------------------------------------------------------------------
# Hintergrund (SOLL-IST-2026-06-12-wiring.md §2/§3):
#   Louis' Prompts erzeugen bereits nativ kanonische Outputs inkl. _meta.
#   Die Tasks (P01/P03/P04) müssen daher NICHT mehr v2↔kanonisch transformieren,
#   sondern nur (a) _meta server-seitig absichern (ADR-0002: _meta gehört dem
#   Server, nicht dem LLM) und (b) gegen das kanonische Schema validieren.
#   Diese beiden Funktionen kapseln genau das.


def resolve_canonical_prompt_version(prompt_key: str) -> str:
    """Liefert die semantische Vertrags-Version (`p0X-vN.N`) für einen Prompt.

    Reihenfolge: Env ``CANONICAL_PROMPT_VERSION_<P>`` → ``CANONICAL_PROMPT_VERSION``
    → Fallback ``<key>-v1.0``. Immer pattern-konform (``^p0X-vN.N$``).
    """
    key = prompt_key.lower()
    env_val = os.environ.get(f"CANONICAL_PROMPT_VERSION_{key.upper()}", "").strip()
    # Erweitert um 'values'-Präfix (Issue #43): values-v1.0 ist gültig neben p0X-vN.N.
    if env_val and re.match(r"^(p0[0-9]+|values)-v[0-9]+\.[0-9]+$", env_val):
        return env_val
    return CANONICAL_PROMPT_VERSION.get(key, f"{key}-v1.0")


def build_canonical_meta(
    prompt_key: str,
    *,
    tenant_id: str,
    model: str,
    generated_at: str,
    tenant_name: str | None = None,
    tenant_slug: str | None = None,
    agentur_id: str | None = None,
    prompt_version: str | None = None,
    row_id: str | None = None,
    token_usage: dict | None = None,
    luecken: list | None = None,
    llm_meta: dict | None = None,
) -> dict:
    """Baut das autoritative kanonische ``_meta`` für einen Pipeline-Output.

    Die Pflichtfelder (agentur_id/kunde_id/prompt_version/model/generated_at)
    bestimmt IMMER der Server. Harmlose Zusatzfelder, die das LLM in seinem
    ``_meta`` geliefert hat (z.B. ``p04_aufgaben``, ``hypothesen``,
    ``transkript_qualitaet``), werden übernommen — aber NIE dürfen sie ein
    autoritatives Feld überschreiben.

    Args:
        prompt_key:   'p01' | 'p03' | 'p04'.
        tenant_id:    Tenant-UUID (für kunde_id-Slug-Fallback).
        model:        Router-Modell-ID (z.B. 'anthropic/claude-sonnet-4-6').
        generated_at: ISO-8601-Zeitstempel.
        tenant_name:  Optional Klarname → schönerer kunde_id-Slug.
        tenant_slug:  Optional direkter Slug (höchste Prio für kunde_id).
        agentur_id:   Optional; Default 'zb' (s. #26 / Migration 050).
        prompt_version: Optional Override; sonst resolve_canonical_prompt_version().
        row_id:       Optional DB-Row-ID → generation_id 'gen_<id>'.
        token_usage:  Optional {input_tokens, output_tokens}.
        luecken:      Optional Liste dokumentierter Lücken.
        llm_meta:     Optional vom LLM geliefertes _meta (Zusatzfelder werden gemerged).

    Returns:
        Kanonisches _meta-Dict (alle Pflichtfelder gesetzt).
    """
    key = prompt_key.lower()
    pv = prompt_version or resolve_canonical_prompt_version(key)

    raw_inputs = {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "tenant_slug": tenant_slug,
        "agentur_id": agentur_id,
        "prompt_version": pv,
        "model_id": model,
        "created_at": generated_at,
        "row_id": row_id,
        "token_usage": token_usage,
        "luecken": luecken,
    }
    meta = _build_meta(key, {k: v for k, v in raw_inputs.items() if v is not None})

    # Harmlose LLM-_meta-Extras übernehmen (z.B. p04_aufgaben, hypothesen),
    # ohne autoritative Felder oder bereits gesetzte Schlüssel zu überschreiben.
    if isinstance(llm_meta, dict):
        for k, v in llm_meta.items():
            if k in _AUTHORITATIVE_META_KEYS:
                continue
            if k not in meta and v is not None:
                meta[k] = v

    return meta


def finalize_canonical(prompt_key: str, parsed: dict, *, meta: dict) -> tuple[dict, list]:
    """Hängt das autoritative ``_meta`` an, validiert kanonisch, dokumentiert Lücken.

    Wirft NIE bei Schema-Verstoß (DoD: dokumentierte ``_meta.luecken`` statt
    hartem Fehler/Halluzination). Schema-Fehler werden als ``schema: <pfad>: <msg>``
    in ``_meta.luecken`` festgehalten und das Best-Effort-Dokument zurückgegeben.

    Args:
        prompt_key: 'p01' | 'p03' | 'p04'.
        parsed:     Das vom LLM geparste Dokument (kanonische Louis-Struktur).
        meta:       Autoritatives _meta aus build_canonical_meta().

    Returns:
        (doc, errors): ``doc`` ist das kanonische Dokument inkl. finalem ``_meta``;
        ``errors`` ist die (ggf. leere) Liste der Schema-Validierungsfehler.
    """
    key = prompt_key.lower()
    doc: dict = dict(parsed) if isinstance(parsed, dict) else {}

    # Prompt-Überschriften als Keys (IDENTITÄT, 1_PERSON) zurückführen, BEVOR
    # validiert wird — sonst meldet die Validierung acht gerissene Pflichtfelder
    # für ein Dokument, dessen Inhalt vollständig ist.
    doc, umbenennungen = normalisiere_top_level_keys(key, doc)
    if umbenennungen:
        logger.warning(
            "finalize_canonical(%s): %d Top-Level-Key(s) aus Prompt-Überschriften "
            "auf Schema-Namen zurückgeführt: %s",
            key,
            len(umbenennungen),
            ", ".join(f"{alt}→{neu}" for alt, neu in umbenennungen),
        )

    final_meta = dict(meta)
    doc["_meta"] = final_meta

    errors = validate_canonical(key, doc)
    if errors:
        existing = list(final_meta.get("luecken") or [])
        gap_entries = [f"schema: {e}" for e in errors]
        # Dedup, Reihenfolge erhalten
        seen = set(existing)
        for g in gap_entries:
            if g not in seen:
                existing.append(g)
                seen.add(g)
        final_meta["luecken"] = existing
        doc["_meta"] = final_meta
        logger.warning(
            "finalize_canonical(%s): %d Schema-Lücke(n) dokumentiert (kein Hard-Fail)",
            key,
            len(errors),
        )

    return doc, errors
