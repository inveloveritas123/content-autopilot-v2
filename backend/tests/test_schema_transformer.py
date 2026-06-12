"""
test_schema_transformer.py — Unittests für services/schema_transformer.py

WICHTIG: Kein echtes DB-Zugriff, keine echten Kundendaten.
Alle Payloads sind synthetisch/fiktiv.

Ausführen:
    cd backend
    PYTHONPATH=. CONTENT_TRUTH_BASE_PATH=<repo>/content-truth \
        python -m pytest tests/test_schema_transformer.py -v

oder via unittest:
    cd backend
    PYTHONPATH=. CONTENT_TRUTH_BASE_PATH=<repo>/content-truth \
        python -m unittest tests.test_schema_transformer

Das Modul wird via importlib direkt geladen um den services/__init__.py-Import
(google.generativeai) zu umgehen.
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Modul direkt laden — umgeht services/__init__.py (google.generativeai)
# ---------------------------------------------------------------------------

def _load_transformer_module():
    """Lädt schema_transformer.py direkt via importlib ohne Package-__init__."""
    module_path = Path(__file__).parent.parent / "services" / "schema_transformer.py"
    if not module_path.exists():
        raise FileNotFoundError(f"schema_transformer.py nicht gefunden: {module_path}")

    spec = importlib.util.spec_from_file_location("schema_transformer", str(module_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    st = _load_transformer_module()
except Exception as e:
    raise ImportError(f"schema_transformer konnte nicht geladen werden: {e}") from e

# Funktionen alias
load_canonical_schema = st.load_canonical_schema
validate_canonical = st.validate_canonical
to_canonical = st.to_canonical
from_canonical = st.from_canonical


# ---------------------------------------------------------------------------
# Synthetische Test-Payloads
# ---------------------------------------------------------------------------

# Ein minimaler v2-P01-Payload (entspricht dem, was p01_task.py in die DB schreibt)
V2_P01_MINIMAL = {
    "unternehmensgeschichte": "Gegründet 2015 aus der Frustration über mangelnde Transparenz im Coaching.",
    "kernbotschaft": "Wirksames Leadership beginnt innen, nicht außen.",
    "zielgruppe": {
        "beschreibung": "Führungskräfte in KMUs, 35-55 Jahre alt",
        "probleme": ["Burnout-Risiko", "Schwierige Personalentscheidungen"],
    },
    "expertise": {
        "erfahrung_jahre": 12,
        "kunden_anzahl": "200+",
        "erfolgsgeschichte": "Begleitung von 50+ Transformationsprojekten",
    },
    "werte": ["Authentizität", "Wirksamkeit", "Klarheit"],
    "wunschzustand": None,
    "innenwelt": None,
}

# Kanonisch valider P01 — entspricht content-truth/schemas/p01.schema.json
CANONICAL_P01_VALID = {
    "_meta": {
        "agentur_id": "zb",
        "kunde_id": "test-kunde",
        "prompt_version": "p01-v1.0",
        "model": "anthropic/claude-sonnet-4-6",
        "generated_at": "2026-06-12T10:00:00Z",
    },
    "person": {
        "gruendungsgeschichte": "Gegründet 2015 aus der Frustration über mangelnde Transparenz.",
        "wendepunkt": None,
        "fehler_und_learnings": [],
    },
    "zielkunde": {
        "beschreibung": "Führungskräfte in KMUs, 35-55 Jahre",
        "wunschzustand": None,
        "innenwelt": None,
    },
    "angebot": {
        "elevator_pitch": "Wirksames Leadership beginnt innen.",
        "kernleistung": None,
        "transformation": None,
    },
    "positionierung": {
        "differenzierung": None,
        "werte_schwerpunkt": "Authentizität, Wirksamkeit, Klarheit",
        "usp_in_eigenen_worten": None,
    },
    "markt": {},
    "vertrauen": {
        "erfahrung_jahre": 12,
        "kunden_anzahl": "200+",
    },
    "sprache": {},
    "content_reservoir": {},
}

# Ein minimaler v2-P03-Payload
V2_P03_MINIMAL = {
    "tonalitaet": {
        "charakterisierung": "Direkt, klar, mit Tiefe",
        "spektrum": "Von sachlich bis emotional",
    },
    "kernthemen": ["Leadership", "Resilienz", "Selbstführung"],
    "stilprinzipien": {
        "laenge": "Kurze bis mittlere Sätze",
        "typische_satzanfaenge": ["Ich glaube,", "Was mir auffällt:", "Ehrlich gesagt:"],
        "verbindungen": "Parataxe, wenig Nebensätze",
        "beispiele": ["Das System funktioniert. Bis es das nicht mehr tut."],
    },
    "wortschatz": {
        "signalwoerter": ["Leadership", "Klarheit", "Tiefe"],
        "fuellwoerter": ["einfach", "ganz"],
        "verbotene_woerter": ["synergieren", "Mehrwert"],
    },
    "schreibrhythmus": {
        "laenge": "Variierend — kurze Punch-Sätze + längere Reflexionen",
    },
    "vermeidungsregeln": [
        "Keine Corporate-Floskeln",
        "Kein Selbstlob ohne Kontext",
    ],
}

# Kanonisch valider P03-Payload
CANONICAL_P03_VALID = {
    "_meta": {
        "agentur_id": "zb",
        "kunde_id": "test-kunde",
        "prompt_version": "p03-v1.4",
        "model": "anthropic/claude-sonnet-4-6",
        "generated_at": "2026-06-12T10:00:00Z",
    },
    "grundton": {
        "charakterisierung": "Direkt, klar, mit Tiefe",
        "spektrum": "Von sachlich bis emotional",
        "linkedin_kalibrierung": "Professionell, aber persönlich",
    },
    "satzarchitektur": {
        "laenge": "Kurze bis mittlere Sätze",
        "typische_satzanfaenge": ["Ich glaube,", "Was mir auffällt:", "Ehrlich gesagt:"],
        "verbindungen": "Parataxe",
        "beispiele": ["Das System funktioniert. Bis es das nicht mehr tut."],
    },
    "wortschatz": {
        "signalwoerter": ["Leadership", "Klarheit", "Tiefe"],
        "fuellwoerter": ["einfach", "ganz"],
        "verbotene_woerter": ["synergieren", "Mehrwert"],
    },
    "erzaehlmuster": {
        "story_einstieg": "Konkrete Situation",
        "argumentation": "These → Beleg → Schluss",
        "perspektive": "Erste Person singular",
    },
    "emotionaler_ausdruck": {
        "spektrum": "Zurückhaltend bis offen",
        "humor_typ": "Trocken, selten",
    },
    "persoenlichkeits_stance": {
        "archetyp": "Der Weise",
        "stance_in_aktion": ["Hinterfragt Annahmen", "Bleibt ruhig unter Druck"],
    },
    "emotionaler_subtext": {
        "subtext": "Vertrauen in Prozesse trotz Unsicherheit",
    },
    "ueberzeugungsstil": {
        "primaer": "Logos — Argumente und Evidenz",
    },
    "zielgruppen_sprachfilter": {
        "leser_profil": "Erfahrene Führungskräfte",
        "sprachbarrieren": ["Zu technisch", "Zu akademisch"],
    },
    "vermeidungsprofil": {
        "nie_sagen": ["synergieren", "Mehrwert"],
    },
    "referenz_saetze": {
        "original": [
            "Das System funktioniert — bis es das nicht mehr tut.",
            "Echte Veränderung beginnt im Stillen.",
            "Führung ist kein Titel, sondern eine Entscheidung.",
            "Was du nicht aussprichst, steuert dich trotzdem.",
            "Perfektion ist ein Alibi für Untätigkeit.",
        ],
        "adaptiert": [
            "Leadership ist eine innere Haltung.",
            "Stille ist keine Schwäche.",
            "Klarheit kommt nach dem Chaos.",
        ],
    },
}

# Ein minimaler v2-P04-Payload
V2_P04_MINIMAL = {
    "hauptperson": {
        "rolle_und_alltag": "Geschäftsführerin, 42, führt ein 30-köpfiges Team",
        "selbstbild": "Will stark wirken, fühlt sich manchmal überfordert",
    },
    "kernschmerzen": [
        "Keine Zeit für strategisches Denken",
        "Fühlt sich allein mit Entscheidungen",
        "Team versteht ihre Vision nicht",
    ],
    "transformation": {
        "wunschzustand": "Führt gelassen und klar, ohne Dauerdruck",
        "wunschidentitaet": "Inspirierendes Vorbild für ihr Team",
    },
    "einwaende": [
        "Coaching ist für Schwache",
        "Ich habe keine Zeit dafür",
        "Das kenne ich alles schon",
        "Das hat bei mir sowieso keinen Effekt",
    ],
    "kaufmotive": [
        "Konkrete Verhaltensänderungen in 90 Tagen",
        "Vertraulicher Rahmen ohne Firmenhierarchie",
        "Nachweisbare Ergebnisse",
    ],
    "sprachmuster": {
        "redewendungen": ["Am Ende des Tages", "Das ist nicht mein Problem"],
        "ansprache": "Du (direkt und auf Augenhöhe)",
    },
}

# META-Dict für DB-Spalten-Simulation
META_DICT = {
    "tenant_id": "uuid-1234-5678",
    "tenant_name": "Test Kunde GmbH",
    "model_id": "anthropic/claude-sonnet-4-6",
    "prompt_version_hash": "abc123def456",
    "created_at": "2026-06-12T10:00:00Z",
    "row_id": "row-abc123",
}


# ---------------------------------------------------------------------------
# Test-Klassen
# ---------------------------------------------------------------------------

class TestLoadCanonicalSchema(unittest.TestCase):
    """Testet load_canonical_schema() — Schema-Laden aus content-truth/schemas/."""

    def test_load_p01(self):
        """P01-Schema lädt ohne Fehler."""
        schema = load_canonical_schema("p01")
        self.assertIsInstance(schema, dict)
        self.assertIn("$schema", schema)
        self.assertIn("properties", schema)

    def test_load_p03(self):
        """P03-Schema lädt ohne Fehler."""
        schema = load_canonical_schema("p03")
        self.assertIsInstance(schema, dict)
        self.assertIn("required", schema)

    def test_load_p04(self):
        """P04-Schema lädt ohne Fehler."""
        schema = load_canonical_schema("p04")
        self.assertIsInstance(schema, dict)

    def test_case_insensitive(self):
        """Schlüssel sind case-insensitive."""
        schema_lower = load_canonical_schema("p01")
        schema_upper = load_canonical_schema("P01")
        self.assertEqual(schema_lower["title"], schema_upper["title"])

    def test_unknown_key_raises(self):
        """Unbekannter prompt_key → KeyError."""
        with self.assertRaises(KeyError):
            load_canonical_schema("p99")

    def test_p01_required_fields(self):
        """P01-Schema enthält erwartete Pflichtfelder."""
        schema = load_canonical_schema("p01")
        required = schema.get("required", [])
        self.assertIn("_meta", required)
        self.assertIn("person", required)
        self.assertIn("zielkunde", required)
        self.assertIn("angebot", required)

    def test_p03_required_fields(self):
        """P03-Schema enthält erwartete Pflichtfelder."""
        schema = load_canonical_schema("p03")
        required = schema.get("required", [])
        self.assertIn("_meta", required)
        self.assertIn("grundton", required)
        self.assertIn("wortschatz", required)
        self.assertIn("referenz_saetze", required)

    def test_schema_caching(self):
        """Zweiter Aufruf liefert dasselbe Objekt (Cache)."""
        s1 = load_canonical_schema("p01")
        s2 = load_canonical_schema("p01")
        self.assertIs(s1, s2, "Schema-Cache sollte dieselbe Objekt-Referenz zurückliefern")


class TestValidateCanonical(unittest.TestCase):
    """Testet validate_canonical() — Validierung gegen kanonische Schemas."""

    def test_valid_p01_payload(self):
        """Ein valider kanonischer P01-Payload → keine Fehler."""
        errors = validate_canonical("p01", CANONICAL_P01_VALID)
        self.assertEqual(
            errors, [],
            f"Erwartete keine Fehler, aber erhalten: {errors}"
        )

    def test_valid_p03_payload(self):
        """Ein valider kanonischer P03-Payload → keine Fehler."""
        errors = validate_canonical("p03", CANONICAL_P03_VALID)
        self.assertEqual(
            errors, [],
            f"Erwartete keine Fehler, aber erhalten: {errors}"
        )

    def test_invalid_missing_meta(self):
        """Payload ohne _meta → Fehler in Liste."""
        bad = {k: v for k, v in CANONICAL_P01_VALID.items() if k != "_meta"}
        errors = validate_canonical("p01", bad)
        self.assertTrue(
            len(errors) > 0,
            "Payload ohne _meta sollte Validierungsfehler erzeugen"
        )
        # Mindestens einer der Fehler sollte _meta erwähnen
        self.assertTrue(
            any("_meta" in e for e in errors),
            f"Kein _meta-Fehler in: {errors}"
        )

    def test_invalid_wrong_prompt_version_pattern(self):
        """_meta.prompt_version mit falschem Muster → Fehler."""
        bad = json.loads(json.dumps(CANONICAL_P01_VALID))
        bad["_meta"]["prompt_version"] = "FALSCHES-FORMAT"
        errors = validate_canonical("p01", bad)
        self.assertTrue(
            len(errors) > 0,
            "Falsches prompt_version-Muster sollte Fehler erzeugen"
        )

    def test_invalid_agentur_id_pattern(self):
        """agentur_id mit Großbuchstaben → Fehler (Pattern: ^[a-z0-9-]+$)."""
        bad = json.loads(json.dumps(CANONICAL_P01_VALID))
        bad["_meta"]["agentur_id"] = "ZB-GROSS"
        errors = validate_canonical("p01", bad)
        self.assertTrue(
            len(errors) > 0,
            "agentur_id mit Großbuchstaben sollte Fehler erzeugen"
        )

    def test_empty_dict_fails(self):
        """Leeres Dict ist kein valider P01-Payload."""
        errors = validate_canonical("p01", {})
        self.assertTrue(len(errors) > 0)

    def test_returns_list_never_none(self):
        """validate_canonical gibt immer eine Liste zurück, nie None."""
        result = validate_canonical("p01", CANONICAL_P01_VALID)
        self.assertIsInstance(result, list)

    def test_p03_valid_referenz_saetze(self):
        """P03 referenz_saetze.original mit minItems:5 wird geprüft."""
        bad = json.loads(json.dumps(CANONICAL_P03_VALID))
        # Nur 2 Original-Sätze → minItems:5 verletzt
        bad["referenz_saetze"]["original"] = ["Satz 1", "Satz 2"]
        errors = validate_canonical("p03", bad)
        self.assertTrue(
            len(errors) > 0,
            "referenz_saetze.original mit <5 Items sollte Fehler erzeugen"
        )


class TestToCanonicalP01(unittest.TestCase):
    """Testet to_canonical() für P01."""

    def setUp(self):
        self.result = to_canonical("p01", V2_P01_MINIMAL, META_DICT)

    def test_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_meta_present(self):
        """_meta wird rehydriert."""
        self.assertIn("_meta", self.result)

    def test_meta_agentur_id(self):
        """_meta.agentur_id Default ist 'zb'."""
        self.assertEqual(self.result["_meta"]["agentur_id"], "zb")

    def test_meta_kunde_id_slugged(self):
        """_meta.kunde_id wird aus tenant_name slugged."""
        self.assertEqual(self.result["_meta"]["kunde_id"], "test-kunde-gmbh")

    def test_meta_model(self):
        """_meta.model kommt aus meta['model_id']."""
        self.assertEqual(
            self.result["_meta"]["model"],
            "anthropic/claude-sonnet-4-6"
        )

    def test_meta_generation_id(self):
        """_meta.generation_id wird aus row_id erzeugt."""
        self.assertEqual(self.result["_meta"]["generation_id"], "gen_row-abc123")

    def test_unternehmensgeschichte_mapped(self):
        """v2.unternehmensgeschichte → person.gruendungsgeschichte."""
        self.assertEqual(
            self.result["person"]["gruendungsgeschichte"],
            V2_P01_MINIMAL["unternehmensgeschichte"],
        )

    def test_kernbotschaft_mapped(self):
        """v2.kernbotschaft → angebot.elevator_pitch."""
        self.assertEqual(
            self.result["angebot"]["elevator_pitch"],
            V2_P01_MINIMAL["kernbotschaft"],
        )

    def test_werte_joined(self):
        """v2.werte (array) → positionierung.werte_schwerpunkt (string)."""
        schwerpunkt = self.result["positionierung"]["werte_schwerpunkt"]
        self.assertIsInstance(schwerpunkt, str)
        self.assertIn("Authentizität", schwerpunkt)

    def test_wunschzustand_always_null(self):
        """zielkunde.wunschzustand ist immer null (P01-Vertrag)."""
        self.assertIsNone(self.result["zielkunde"]["wunschzustand"])

    def test_innenwelt_always_null(self):
        """zielkunde.innenwelt ist immer null (P01-Vertrag)."""
        self.assertIsNone(self.result["zielkunde"]["innenwelt"])

    def test_luecken_set(self):
        """Lossy-Mappings erzeugen Lücken in _meta.luecken."""
        luecken = self.result["_meta"].get("luecken", [])
        self.assertTrue(
            len(luecken) > 0,
            "Lossy-Mappings sollten Lücken erzeugen"
        )

    def test_required_canonical_keys_present(self):
        """Alle kanonisch erforderlichen Top-Level-Keys sind vorhanden."""
        for key in ["person", "zielkunde", "angebot", "positionierung",
                    "markt", "vertrauen", "sprache", "content_reservoir"]:
            self.assertIn(key, self.result, f"Fehlendes kanonisches Feld: {key}")

    def test_zielgruppe_beschreibung_mapped(self):
        """v2.zielgruppe.beschreibung → zielkunde.beschreibung."""
        self.assertEqual(
            self.result["zielkunde"].get("beschreibung"),
            "Führungskräfte in KMUs, 35-55 Jahre alt",
        )

    def test_expertise_mapped_to_vertrauen(self):
        """v2.expertise.erfahrung_jahre → vertrauen.erfahrung_jahre."""
        self.assertEqual(
            self.result["vertrauen"].get("erfahrung_jahre"),
            12,
        )


class TestToCanonicalP03(unittest.TestCase):
    """Testet to_canonical() für P03."""

    def setUp(self):
        self.result = to_canonical("p03", V2_P03_MINIMAL, META_DICT)

    def test_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_meta_present(self):
        self.assertIn("_meta", self.result)

    def test_grundton_charakterisierung(self):
        """v2.tonalitaet.charakterisierung → grundton.charakterisierung."""
        self.assertEqual(
            self.result["grundton"]["charakterisierung"],
            "Direkt, klar, mit Tiefe",
        )

    def test_wortschatz_signalwoerter(self):
        """v2.wortschatz.signalwoerter → kanonisch.wortschatz.signalwoerter."""
        self.assertEqual(
            self.result["wortschatz"]["signalwoerter"],
            ["Leadership", "Klarheit", "Tiefe"],
        )

    def test_wortschatz_verbotene_woerter(self):
        """v2.wortschatz.verbotene_woerter → kanonisch.wortschatz.verbotene_woerter."""
        self.assertIn("synergieren", self.result["wortschatz"]["verbotene_woerter"])

    def test_vermeidungsregeln_mapped(self):
        """v2.vermeidungsregeln → vermeidungsprofil.nie_sagen."""
        nie_sagen = self.result["vermeidungsprofil"]["nie_sagen"]
        self.assertIsInstance(nie_sagen, list)
        self.assertTrue(len(nie_sagen) > 0)

    def test_kernthemen_in_luecken(self):
        """v2.kernthemen erzeugt Lücken-Eintrag (kein kanonisches Ziel)."""
        luecken = self.result["_meta"].get("luecken", [])
        self.assertTrue(
            any("kernthemen" in l for l in luecken),
            f"kernthemen sollte als Lücke markiert sein. Lücken: {luecken}"
        )

    def test_referenz_saetze_empty_from_v2(self):
        """referenz_saetze sind aus v2-Payload nicht füllbar (leer, aber Lücke gesetzt)."""
        ref = self.result.get("referenz_saetze", {})
        self.assertIsInstance(ref.get("original"), list)
        self.assertEqual(len(ref["original"]), 0)
        luecken = self.result["_meta"].get("luecken", [])
        self.assertTrue(
            any("referenz_saetze" in l for l in luecken),
            "referenz_saetze sollte als Lücke markiert sein"
        )

    def test_satzarchitektur_laenge_from_stilprinzipien(self):
        """satzarchitektur.laenge wird aus stilprinzipien befüllt."""
        self.assertEqual(
            self.result["satzarchitektur"]["laenge"],
            "Kurze bis mittlere Sätze",
        )

    def test_satzarchitektur_typische_satzanfaenge(self):
        """typische_satzanfaenge werden aus stilprinzipien übernommen."""
        anfaenge = self.result["satzarchitektur"].get("typische_satzanfaenge", [])
        self.assertIn("Ich glaube,", anfaenge)


class TestToCanonicalP04(unittest.TestCase):
    """Testet to_canonical() für P04."""

    def setUp(self):
        self.result = to_canonical("p04", V2_P04_MINIMAL, META_DICT)

    def test_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_meta_present(self):
        self.assertIn("_meta", self.result)

    def test_identitaet_rolle_mapped(self):
        """v2.hauptperson.rolle_und_alltag → identitaet.rolle_und_alltag."""
        self.assertEqual(
            self.result["identitaet"]["rolle_und_alltag"],
            "Geschäftsführerin, 42, führt ein 30-köpfiges Team",
        )

    def test_innenwelt_innerer_monolog(self):
        """v2.kernschmerzen → innenwelt.innerer_monolog."""
        monolog = self.result["innenwelt"].get("innerer_monolog", [])
        self.assertIsInstance(monolog, list)
        self.assertIn("Keine Zeit für strategisches Denken", monolog)

    def test_wunschbild_wunschzustand(self):
        """v2.transformation.wunschzustand → wunschbild.wunschzustand."""
        self.assertEqual(
            self.result["wunschbild"]["wunschzustand"],
            "Führt gelassen und klar, ohne Dauerdruck",
        )

    def test_blockaden_glaubenssaetze(self):
        """v2.einwaende → blockaden.glaubenssaetze (erste Hälfte)."""
        glaubenssaetze = self.result["blockaden"].get("glaubenssaetze", [])
        self.assertIsInstance(glaubenssaetze, list)
        self.assertTrue(len(glaubenssaetze) > 0)

    def test_ausloesemoment_trigger_events(self):
        """v2.kaufmotive → ausloesemoment.trigger_events."""
        trigger = self.result["ausloesemoment"].get("trigger_events", [])
        self.assertIn("Konkrete Verhaltensänderungen in 90 Tagen", trigger)

    def test_sprache_redewendungen(self):
        """v2.sprachmuster.redewendungen → sprache_der_zielgruppe.redewendungen."""
        red = self.result["sprache_der_zielgruppe"].get("redewendungen", [])
        self.assertIn("Am Ende des Tages", red)

    def test_content_trigger_empty_with_luecke(self):
        """content_trigger ist leer + Lücke gesetzt (kein v2-Quellfeld)."""
        ct = self.result.get("content_trigger", {})
        self.assertEqual(ct.get("scroll_stopper"), [])
        self.assertEqual(ct.get("resonanz_saetze"), [])
        luecken = self.result["_meta"].get("luecken", [])
        self.assertTrue(
            any("content_trigger" in l for l in luecken),
            "content_trigger sollte als Lücke markiert sein"
        )

    def test_alltagsszenen_empty_with_luecke(self):
        """alltagsszenen ist leer + Lücke gesetzt."""
        as_ = self.result.get("alltagsszenen", {})
        self.assertEqual(as_.get("szenen"), [])
        luecken = self.result["_meta"].get("luecken", [])
        self.assertTrue(
            any("alltagsszenen" in l for l in luecken),
            "alltagsszenen sollte als Lücke markiert sein"
        )


class TestFromCanonical(unittest.TestCase):
    """Testet from_canonical() — Rück-Übersetzung kanonisch → v2."""

    def test_p01_from_canonical_returns_dict(self):
        result = from_canonical("p01", CANONICAL_P01_VALID)
        self.assertIsInstance(result, dict)

    def test_p01_no_meta_in_result(self):
        """_meta darf nicht im from_canonical-Ergebnis sein (gehört in DB-Spalten)."""
        result = from_canonical("p01", CANONICAL_P01_VALID)
        self.assertNotIn("_meta", result)

    def test_p01_elevator_pitch_back(self):
        """angebot.elevator_pitch → kernbotschaft."""
        result = from_canonical("p01", CANONICAL_P01_VALID)
        self.assertEqual(
            result.get("kernbotschaft"),
            CANONICAL_P01_VALID["angebot"]["elevator_pitch"]
        )

    def test_p01_gruendungsgeschichte_back(self):
        """person.gruendungsgeschichte → unternehmensgeschichte."""
        result = from_canonical("p01", CANONICAL_P01_VALID)
        self.assertEqual(
            result.get("unternehmensgeschichte"),
            CANONICAL_P01_VALID["person"]["gruendungsgeschichte"]
        )

    def test_p01_werte_schwerpunkt_split_back(self):
        """positionierung.werte_schwerpunkt (string) → werte (array)."""
        result = from_canonical("p01", CANONICAL_P01_VALID)
        werte = result.get("werte")
        self.assertIsInstance(werte, list)
        self.assertIn("Authentizität", werte)

    def test_p01_wunschzustand_null(self):
        """wunschzustand ist nach from_canonical immer None."""
        result = from_canonical("p01", CANONICAL_P01_VALID)
        self.assertIsNone(result.get("wunschzustand"))

    def test_p03_from_canonical_returns_dict(self):
        result = from_canonical("p03", CANONICAL_P03_VALID)
        self.assertIsInstance(result, dict)

    def test_p03_grundton_to_tonalitaet(self):
        """grundton.charakterisierung → tonalitaet.charakterisierung."""
        result = from_canonical("p03", CANONICAL_P03_VALID)
        ton = result.get("tonalitaet", {})
        self.assertEqual(
            ton.get("charakterisierung"),
            CANONICAL_P03_VALID["grundton"]["charakterisierung"],
        )

    def test_p03_vermeidungsprofil_to_vermeidungsregeln(self):
        """vermeidungsprofil.nie_sagen → vermeidungsregeln."""
        result = from_canonical("p03", CANONICAL_P03_VALID)
        rules = result.get("vermeidungsregeln", [])
        self.assertIn("synergieren", rules)

    def test_p03_kernthemen_always_empty(self):
        """kernthemen ist bei from_canonical immer [] (kein kanonisches Quellfeld)."""
        result = from_canonical("p03", CANONICAL_P03_VALID)
        self.assertEqual(result.get("kernthemen"), [])

    def test_p04_from_canonical_returns_dict(self):
        result = from_canonical("p04", {
            "_meta": {"agentur_id": "zb", "kunde_id": "x", "prompt_version": "p04-v1.0",
                      "model": "m", "generated_at": "2026-01-01T00:00:00Z"},
            "identitaet": {"rolle_und_alltag": "Manager", "selbstbild": "Stark"},
            "innenwelt": {"innerer_monolog": ["A", "B", "C"], "unausgesprochene_angst": "Versagen"},
            "wunschbild": {"wunschzustand": "Ruhig", "wunschidentitaet": "Inspirierend"},
            "content_trigger": {"scroll_stopper": ["S1"], "resonanz_saetze": ["R1", "R2", "R3", "R4", "R5"], "abstoss_trigger": ["A1", "A2"]},
            "sprache_der_zielgruppe": {"redewendungen": ["Am Ende"], "ansprache": "Du"},
            "alltagsszenen": {"szenen": ["S1", "S2", "S3", "S4", "S5"], "wiederkehrende_muster": ["M1", "M2", "M3"]},
            "blockaden": {"glaubenssaetze": ["G1", "G2", "G3"], "denkfehler": ["D1", "D2"]},
            "ausloesemoment": {"trigger_events": ["T1", "T2", "T3"], "emotional_tipping_point": "Krise"},
        })
        self.assertIsInstance(result, dict)
        self.assertNotIn("_meta", result)

    def test_unknown_prompt_key_raises(self):
        """Unbekannter prompt_key → KeyError."""
        with self.assertRaises(KeyError):
            from_canonical("p99", {})


class TestRoundTrip(unittest.TestCase):
    """Round-Trip-Tests: v2 → canonical → v2.

    Round-trips sind für die meisten Felder NICHT verlustfrei (lossy),
    daher wird hier geprüft, dass die Kernfelder erhalten bleiben und
    die Richtung to_canonical → from_canonical keine Daten halluziniert.
    """

    def test_p01_roundtrip_kernbotschaft(self):
        """kernbotschaft übersteht den Round-Trip verlustfrei."""
        canonical = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        v2_back = from_canonical("p01", canonical)
        self.assertEqual(
            v2_back.get("kernbotschaft"),
            V2_P01_MINIMAL["kernbotschaft"],
            "kernbotschaft sollte Round-Trip verlustfrei sein"
        )

    def test_p01_roundtrip_unternehmensgeschichte(self):
        """unternehmensgeschichte übersteht den Round-Trip verlustfrei."""
        canonical = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        v2_back = from_canonical("p01", canonical)
        self.assertEqual(
            v2_back.get("unternehmensgeschichte"),
            V2_P01_MINIMAL["unternehmensgeschichte"],
        )

    def test_p01_roundtrip_werte_lossy(self):
        """werte (array → string → array) ist lossy aber Inhalt erhalten."""
        canonical = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        v2_back = from_canonical("p01", canonical)
        werte_original = set(V2_P01_MINIMAL.get("werte") or [])
        werte_back = set(v2_back.get("werte") or [])
        # Inhalt sollte trotz Typ-Konversion erhalten sein
        self.assertEqual(
            werte_original, werte_back,
            "werte-Inhalt sollte Round-Trip überstehen (auch wenn lossy)"
        )

    def test_p03_roundtrip_wortschatz_signalwoerter(self):
        """wortschatz.signalwoerter übersteht den Round-Trip."""
        canonical = to_canonical("p03", V2_P03_MINIMAL, META_DICT)
        v2_back = from_canonical("p03", canonical)
        self.assertEqual(
            v2_back.get("wortschatz", {}).get("signalwoerter"),
            V2_P03_MINIMAL["wortschatz"]["signalwoerter"],
        )

    def test_p03_roundtrip_vermeidungsregeln(self):
        """vermeidungsregeln überstehen den Round-Trip."""
        canonical = to_canonical("p03", V2_P03_MINIMAL, META_DICT)
        v2_back = from_canonical("p03", canonical)
        self.assertEqual(
            v2_back.get("vermeidungsregeln"),
            V2_P03_MINIMAL["vermeidungsregeln"],
        )

    def test_p04_roundtrip_transformation(self):
        """transformation.wunschzustand übersteht den Round-Trip."""
        canonical = to_canonical("p04", V2_P04_MINIMAL, META_DICT)
        v2_back = from_canonical("p04", canonical)
        self.assertEqual(
            v2_back.get("transformation", {}).get("wunschzustand"),
            V2_P04_MINIMAL["transformation"]["wunschzustand"],
        )

    def test_p04_roundtrip_kaufmotive(self):
        """kaufmotive überstehen den Round-Trip (via ausloesemoment.trigger_events)."""
        canonical = to_canonical("p04", V2_P04_MINIMAL, META_DICT)
        v2_back = from_canonical("p04", canonical)
        self.assertEqual(
            v2_back.get("kaufmotive"),
            V2_P04_MINIMAL["kaufmotive"],
        )


class TestLueckenMarkierung(unittest.TestCase):
    """Testet dass Lücken (nicht befüllbare Pflichtfelder) korrekt markiert werden."""

    def test_p01_has_luecken(self):
        """P01-Transformation von v2 setzt immer Lücken."""
        result = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(len(luecken) > 0, "P01 v2→canonical sollte Lücken markieren")

    def test_p03_has_luecken(self):
        """P03-Transformation von v2 setzt immer Lücken."""
        result = to_canonical("p03", V2_P03_MINIMAL, META_DICT)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(len(luecken) > 0, "P03 v2→canonical sollte Lücken markieren")

    def test_p04_has_luecken(self):
        """P04-Transformation von v2 setzt immer Lücken."""
        result = to_canonical("p04", V2_P04_MINIMAL, META_DICT)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(len(luecken) > 0, "P04 v2→canonical sollte Lücken markieren")

    def test_p03_referenz_saetze_luecke(self):
        """referenz_saetze kann aus v2 nicht befüllt werden → Lücke."""
        result = to_canonical("p03", V2_P03_MINIMAL, META_DICT)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(
            any("referenz_saetze" in l for l in luecken),
            f"referenz_saetze-Lücke erwartet. Lücken: {luecken}"
        )

    def test_p04_alltagsszenen_luecke(self):
        """alltagsszenen kann aus v2 nicht befüllt werden → Lücke."""
        result = to_canonical("p04", V2_P04_MINIMAL, META_DICT)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(
            any("alltagsszenen" in l for l in luecken),
        )

    def test_p01_person_felder_luecke(self):
        """person.name/rolle/... haben keinen v2-Quell → Lücke."""
        result = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(
            any("person.name" in l or "person." in l for l in luecken),
            f"person-Felder-Lücke erwartet. Lücken: {luecken}"
        )

    def test_luecken_are_strings(self):
        """Jedes Lücken-Element ist ein String."""
        for pk, payload in [
            ("p01", V2_P01_MINIMAL),
            ("p03", V2_P03_MINIMAL),
            ("p04", V2_P04_MINIMAL),
        ]:
            result = to_canonical(pk, payload, META_DICT)
            for l in result["_meta"].get("luecken", []):
                self.assertIsInstance(l, str, f"Lücke in {pk} sollte String sein: {l!r}")


class TestMetaRehydrierung(unittest.TestCase):
    """Testet die _meta-Rehydrierung aus verschiedenen DB-Spalten-Kombinationen."""

    def test_tenant_slug_prio(self):
        """tenant_slug hat Priorität vor tenant_name."""
        meta = {**META_DICT, "tenant_slug": "direkter-slug"}
        result = to_canonical("p01", V2_P01_MINIMAL, meta)
        self.assertEqual(result["_meta"]["kunde_id"], "direkter-slug")

    def test_tenant_name_fallback(self):
        """Ohne tenant_slug wird tenant_name slugged."""
        meta = {k: v for k, v in META_DICT.items() if k != "tenant_slug"}
        result = to_canonical("p01", V2_P01_MINIMAL, meta)
        self.assertEqual(result["_meta"]["kunde_id"], "test-kunde-gmbh")

    def test_tenant_id_last_fallback(self):
        """Ohne tenant_slug und tenant_name wird tenant_id slugged."""
        meta = {"tenant_id": "UUID-1234", "model_id": "model-x", "created_at": "2026-01-01T00:00:00Z"}
        result = to_canonical("p01", V2_P01_MINIMAL, meta)
        # UUID-1234 → uuid-1234 (Großbuchstaben → klein)
        self.assertIn("uuid", result["_meta"]["kunde_id"])

    def test_prompt_version_legacy_from_hash(self):
        """Unbekannter Hash → 'p01-legacy'."""
        result = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        self.assertEqual(result["_meta"]["prompt_version"], "p01-legacy")

    def test_prompt_version_passthrough_semantic(self):
        """Semantische Version wie 'p01-v1.0' wird direkt übernommen."""
        meta = {**META_DICT, "prompt_version": "p01-v1.0"}
        result = to_canonical("p01", V2_P01_MINIMAL, meta)
        self.assertEqual(result["_meta"]["prompt_version"], "p01-v1.0")

    def test_generated_at_from_created_at(self):
        """created_at → _meta.generated_at."""
        result = to_canonical("p01", V2_P01_MINIMAL, META_DICT)
        self.assertEqual(result["_meta"]["generated_at"], "2026-06-12T10:00:00Z")


class TestEdgeCases(unittest.TestCase):
    """Edge Cases: leere Payloads, None-Werte, unerwartete Typen."""

    def test_empty_v2_p01(self):
        """Leerer v2-Payload → kanonisches Dict mit Lücken, kein Absturz."""
        result = to_canonical("p01", {}, META_DICT)
        self.assertIsInstance(result, dict)
        self.assertIn("_meta", result)
        # Pflichtfelder vorhanden aber leer/None
        self.assertIn("person", result)
        self.assertIn("angebot", result)

    def test_empty_v2_p03(self):
        """Leerer v2-P03-Payload → kanonisches Dict, kein Absturz."""
        result = to_canonical("p03", {}, META_DICT)
        self.assertIsInstance(result, dict)
        self.assertIn("grundton", result)

    def test_empty_v2_p04(self):
        """Leerer v2-P04-Payload → kanonisches Dict, kein Absturz."""
        result = to_canonical("p04", {}, META_DICT)
        self.assertIsInstance(result, dict)
        self.assertIn("identitaet", result)

    def test_p01_string_zielgruppe(self):
        """v2.zielgruppe als String (nicht Objekt) → beschreibung gesetzt."""
        payload = {**V2_P01_MINIMAL, "zielgruppe": "KMU-Führungskräfte"}
        result = to_canonical("p01", payload, META_DICT)
        self.assertEqual(result["zielkunde"]["beschreibung"], "KMU-Führungskräfte")

    def test_p04_string_hauptperson(self):
        """v2.hauptperson als String → identitaet.rolle_und_alltag gesetzt."""
        payload = {**V2_P04_MINIMAL, "hauptperson": "Erfahrener Manager"}
        result = to_canonical("p04", payload, META_DICT)
        self.assertEqual(result["identitaet"]["rolle_und_alltag"], "Erfahrener Manager")

    def test_unknown_prompt_key_to_canonical(self):
        """Unbekannter prompt_key → KeyError."""
        with self.assertRaises(KeyError):
            to_canonical("p99", {}, META_DICT)

    def test_p03_none_wortschatz(self):
        """v2.wortschatz = None → wortschatz mit leeren Listen, kein Absturz."""
        payload = {**V2_P03_MINIMAL, "wortschatz": None}
        result = to_canonical("p03", payload, META_DICT)
        self.assertIsInstance(result["wortschatz"], dict)

    def test_p01_none_werte(self):
        """v2.werte = None → positionierung.werte_schwerpunkt = None."""
        payload = {**V2_P01_MINIMAL, "werte": None}
        result = to_canonical("p01", payload, META_DICT)
        self.assertIsNone(result["positionierung"]["werte_schwerpunkt"])

    def test_p04_empty_kernschmerzen(self):
        """v2.kernschmerzen leer → innenwelt mit leerem innerer_monolog, Lücke."""
        payload = {**V2_P04_MINIMAL, "kernschmerzen": []}
        result = to_canonical("p04", payload, META_DICT)
        monolog = result["innenwelt"].get("innerer_monolog", [])
        self.assertIsInstance(monolog, list)
        luecken = result["_meta"].get("luecken", [])
        self.assertTrue(any("innerer_monolog" in l for l in luecken))


if __name__ == "__main__":
    unittest.main(verbosity=2)
