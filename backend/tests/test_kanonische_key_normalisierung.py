"""
test_kanonische_key_normalisierung.py — Prompt-Überschriften als JSON-Keys.

Belegt am 06.08.2026 auf Prod: P04 lieferte für Louis (6cff9601) und Eric
(a34a02c9) die Abschnitts-ÜBERSCHRIFTEN des Prompts als Top-Level-Keys —
`IDENTITÄT`, `CONTENT_TRIGGER`, und einmal `SPRACHE DER ZIELGRUPPE` (Leerzeichen),
einmal `SPRACHE_DER_ZIELGRUPPE` (Unterstrich). P01 lieferte für Eric zusätzlich
die Gliederungsnummern mit: `1_PERSON`, `8_CONTENT-RESERVOIR`.

Die Inhalte darunter waren kanonisch und vollständig (15.747 bzw. 18.681 Zeichen).
Nur die Namen stimmten nicht. P12s `prune()` macht einen exakten Key-Match und
traf 0 von 3 Avatar-Keys — jeder Post entstand ohne einen Avatar-Datenpunkt.

`_meta.luecken` hatte den Bruch bei JEDER Erzeugung protokolliert (alle acht
Pflichtfelder auf Wurzelebene). `is_canonical()` prüfte nur `_meta.prompt_version`
und meldete "kanonisch" — das Etikett, nicht die Ware.

Dep-frei via importlib: die Suite stubbt sqlalchemy/celery/services, und ein Test
gegen den Stub misst nichts.
"""

import importlib.util
from pathlib import Path


def _load(relpfad: str, name: str):
    p = Path(__file__).parent.parent / relpfad
    spec = importlib.util.spec_from_file_location(name, str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


st = _load("services/schema_transformer.py", "schema_transformer_under_test")
cp = _load("services/canonical_profiles.py", "canonical_profiles_norm_test")


# ---------------------------------------------------------------------------
# Normalisierung — die Zuordnung erfindet nichts, sie trifft Schema-Namen
# ---------------------------------------------------------------------------


class TestNormalisiereTopLevelKeys:
    def test_versalien_mit_umlaut_wird_kanonisch(self):
        """IDENTITÄT → identitaet (Umlaut-Transliteration wie im Schema)."""
        doc, umbenennungen = st.normalisiere_top_level_keys("p04", {"IDENTITÄT": {"a": 1}})
        assert "identitaet" in doc
        assert "IDENTITÄT" not in doc
        assert ("IDENTITÄT", "identitaet") in umbenennungen

    def test_leerzeichen_variante_louis(self):
        """Louis' Row: 'SPRACHE DER ZIELGRUPPE' mit Leerzeichen."""
        doc, _ = st.normalisiere_top_level_keys("p04", {"SPRACHE DER ZIELGRUPPE": {"a": 1}})
        assert "sprache_der_zielgruppe" in doc

    def test_unterstrich_variante_eric(self):
        """Erics Row: 'SPRACHE_DER_ZIELGRUPPE' mit Unterstrich — gleiches Ziel."""
        doc, _ = st.normalisiere_top_level_keys("p04", {"SPRACHE_DER_ZIELGRUPPE": {"a": 1}})
        assert "sprache_der_zielgruppe" in doc

    def test_gliederungsnummer_wird_gestrippt(self):
        """P01 bei Eric: '1_PERSON' → person, '8_CONTENT-RESERVOIR' → content_reservoir."""
        doc, _ = st.normalisiere_top_level_keys(
            "p01", {"1_PERSON": {"a": 1}, "8_CONTENT-RESERVOIR": {"b": 2}}
        )
        assert "person" in doc
        assert "content_reservoir" in doc

    def test_inhalt_bleibt_unveraendert(self):
        """Verlustfrei: nur der Name wandert, der Wert bleibt identisch."""
        inhalt = {"selbstbild": ["macht alles selbst"], "tief": {"x": [1, 2, 3]}}
        doc, _ = st.normalisiere_top_level_keys("p04", {"IDENTITÄT": inhalt})
        assert doc["identitaet"] == inhalt

    def test_meta_bleibt_unangetastet(self):
        """_meta ist Server-Hoheit und nie ein Schema-Feld der Nutzlast."""
        meta = {"prompt_version": "p04-v1.0"}
        doc, umbenennungen = st.normalisiere_top_level_keys("p04", {"_meta": meta})
        assert doc["_meta"] == meta
        assert umbenennungen == []

    def test_unbekannter_key_bleibt_stehen(self):
        """Was auf keinen Schema-Namen zeigt, wird nicht geraten und nicht verworfen."""
        doc, umbenennungen = st.normalisiere_top_level_keys("p04", {"VÖLLIG_FREMD": {"a": 1}})
        assert doc["VÖLLIG_FREMD"] == {"a": 1}
        assert umbenennungen == []

    def test_kollision_laesst_beide_stehen(self):
        """Existiert der kanonische Name schon, wird er nicht überschrieben."""
        doc, umbenennungen = st.normalisiere_top_level_keys(
            "p04", {"identitaet": {"echt": 1}, "IDENTITÄT": {"duplikat": 2}}
        )
        assert doc["identitaet"] == {"echt": 1}
        assert doc["IDENTITÄT"] == {"duplikat": 2}
        assert umbenennungen == []

    def test_kanonischer_payload_bleibt_unveraendert(self):
        """Gesunde Rows (Test-Tenants) dürfen sich nicht bewegen."""
        vorher = {"identitaet": {"a": 1}, "content_trigger": {"b": 2}}
        doc, umbenennungen = st.normalisiere_top_level_keys("p04", dict(vorher))
        assert doc == vorher
        assert umbenennungen == []

    def test_unerreichbares_schema_wird_laut_gemeldet(self, caplog):
        """Ohne Schema kann nicht zugeordnet werden — das darf nicht lautlos passieren.

        Der Payload geht unverändert durch (fail-open, die Profilerzeugung darf
        nicht crashen), aber ein stiller No-Op wäre genau der Fehlertyp, den
        dieser Fix beseitigt: eine Schutzschicht, die bei Störung schweigt.
        """
        with caplog.at_level("ERROR"):
            doc, umbenennungen = st.normalisiere_top_level_keys("gibtsnicht", {"IDENTITÄT": {}})

        assert doc == {"IDENTITÄT": {}}
        assert umbenennungen == []
        assert any(r.levelname == "ERROR" for r in caplog.records), "kein ERROR protokolliert"


# ---------------------------------------------------------------------------
# Der Wächter — er soll die Ware prüfen, nicht das Etikett
# ---------------------------------------------------------------------------

#: Louis' echtes _meta aus tenant_audience_avatar 5484ea47 (Prod, 06.08.2026).
LOUIS_META_ECHT = {
    "prompt_version": "p04-v1.0",
    "generation_id": "gen_5484ea47-f20e-411e-918e-ec794f0bf39c",
    "luecken": [
        "schema: (root): 'identitaet' is a required property",
        "schema: (root): 'innenwelt' is a required property",
        "schema: (root): 'wunschbild' is a required property",
        "schema: (root): 'content_trigger' is a required property",
        "schema: (root): 'sprache_der_zielgruppe' is a required property",
        "schema: (root): 'alltagsszenen' is a required property",
        "schema: (root): 'blockaden' is a required property",
        "schema: (root): 'ausloesemoment' is a required property",
    ],
}


class TestIsCanonicalPrueftDenInhalt:
    def test_wurzel_pflichtfeld_luecke_ist_nicht_kanonisch(self):
        """Louis' Row trug 'p04-v1.0' UND acht gerissene Wurzelfelder."""
        assert cp.is_canonical({"_meta": LOUIS_META_ECHT}) is False

    def test_luecke_in_unterobjekt_bleibt_kanonisch(self):
        """Prod-Row 5e8afa43: sieben required-Lücken, aber keine auf Wurzelebene.

        Solche Rows sind inhaltlich unvollständig, aber strukturell kanonisch —
        sie dürfen durch den schärferen Wächter nicht abgewertet werden.
        """
        meta = {
            "prompt_version": "p01-v1.0",
            "luecken": ["schema: person.rolle: 'titel' is a required property"],
        }
        assert cp.is_canonical({"_meta": meta}) is True

    def test_freitext_luecke_bleibt_kanonisch(self):
        """Nicht-Schema-Lücken sind inhaltliche Notizen, kein Strukturbruch."""
        meta = {
            "prompt_version": "p04-v1.0",
            "luecken": ["Kein Transkript verfügbar, Ableitung aus P01"],
        }
        assert cp.is_canonical({"_meta": meta}) is True

    def test_leere_luecken_bleiben_kanonisch(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "p04-v1.0", "luecken": []}}) is True


# ---------------------------------------------------------------------------
# Die Kette: was der Erzeuger speichert, muss der Wächter durchlassen
# ---------------------------------------------------------------------------

#: Die acht Überschriften, die P04 für Louis als Top-Level-Keys geliefert hat.
LOUIS_KEYS_ECHT = [
    "IDENTITÄT",
    "INNENWELT",
    "WUNSCHBILD",
    "CONTENT_TRIGGER",
    "SPRACHE DER ZIELGRUPPE",
    "ALLTAGSSZENEN",
    "BLOCKADEN",
    "AUSLOESEMOMENT",
]

#: Dieselben acht Felder in kanonischer Schreibweise — der Zustand NACH der Reparatur.
LOUIS_KEYS_ECHT_KLEIN = [
    "identitaet",
    "innenwelt",
    "wunschbild",
    "content_trigger",
    "sprache_der_zielgruppe",
    "alltagsszenen",
    "blockaden",
    "ausloesemoment",
]


class TestSchemaLueckenAktualisieren:
    """Nach einer Reparatur muss die Lückenliste den AKTUELLEN Stand zeigen.

    Prod-Befund 06.08.2026: direkt nach der Migration hatten die reparierten Rows
    0 echte Wurzelfehler, trugen aber weiter ihre acht alten `luecken` —
    `is_canonical()` las die alte Liste und meldete sie dauerhaft als kaputt.

    Der zweite Befund kam im Trockenlauf: bloßes STREICHEN reicht nicht. Solange
    `person` als Top-Level-Key fehlte, kam jsonschema gar nicht dazu, das
    Unterobjekt zu prüfen. Erst die Reparatur legt die darunterliegenden Fehler
    frei — bei Erics Kundenkontext neun Stück. Wer nur streicht, hinterlässt eine
    leere Liste an einer Row mit neun echten Befunden.
    """

    def test_veraltete_schema_luecke_verschwindet(self):
        payload = {k: {} for k in LOUIS_KEYS_ECHT_KLEIN}
        payload["_meta"] = {
            "prompt_version": "p04-v1.0",
            "luecken": ["schema: (root): 'identitaet' is a required property"],
        }
        doc, entfernt, _ = st.aktualisiere_schema_luecken("p04", payload)

        veraltet = "schema: (root): 'identitaet' is a required property"
        assert veraltet not in doc["_meta"]["luecken"]
        assert entfernt == [veraltet]

    def test_noch_bestehende_schema_luecke_bleibt(self):
        """Was die Validierung weiterhin meldet, darf nicht weggeputzt werden."""
        payload = {
            "_meta": {
                "prompt_version": "p04-v1.0",
                "luecken": ["schema: (root): 'identitaet' is a required property"],
            }
        }
        doc, entfernt, _ = st.aktualisiere_schema_luecken("p04", payload)

        assert "schema: (root): 'identitaet' is a required property" in doc["_meta"]["luecken"]
        assert entfernt == []

    def test_neu_aufgedeckte_fehler_kommen_in_die_liste(self):
        """Erst die Reparatur macht Unterobjekt-Fehler sichtbar — sie müssen dokumentiert werden.

        `identitaet` ist ein String statt eines Objekts. Solange der Key noch
        `IDENTITÄT` hieß, meldete die Validierung nur das fehlende Pflichtfeld.
        """
        payload = {k: {} for k in LOUIS_KEYS_ECHT_KLEIN}
        payload["identitaet"] = "kein Objekt"
        payload["_meta"] = {"prompt_version": "p04-v1.0", "luecken": []}

        doc, _, neu = st.aktualisiere_schema_luecken("p04", payload)

        assert neu, "neu aufgedeckte Fehler fehlen"
        assert any("identitaet" in eintrag for eintrag in doc["_meta"]["luecken"])

    def test_freitext_luecke_bleibt_immer(self):
        """Inhaltliche Notizen sind keine Schema-Befunde und gehen die Validierung nichts an."""
        payload = {k: {} for k in LOUIS_KEYS_ECHT_KLEIN}
        payload["_meta"] = {
            "prompt_version": "p04-v1.0",
            "luecken": ["Kein Transkript verfügbar, Ableitung aus P01"],
        }
        doc, entfernt, _ = st.aktualisiere_schema_luecken("p04", payload)

        assert "Kein Transkript verfügbar, Ableitung aus P01" in doc["_meta"]["luecken"]
        assert entfernt == []

    def test_zweiter_lauf_aendert_nichts(self):
        """Idempotenz: steht die Liste auf dem aktuellen Stand, gibt es nichts zu tun.

        Wichtig, weil das Migrationsskript nur schreibt, wenn sich etwas ändert —
        sonst würde jeder Lauf alle Rows anfassen.
        """
        payload = {k: {} for k in LOUIS_KEYS_ECHT_KLEIN}
        payload["_meta"] = {"prompt_version": "p04-v1.0"}

        doc, _, _ = st.aktualisiere_schema_luecken("p04", payload)
        _, entfernt, neu = st.aktualisiere_schema_luecken("p04", doc)

        assert entfernt == []
        assert neu == []

    def test_reparierte_row_besteht_danach_den_waechter(self):
        """Die Kette: umbenannt → Lücken aktualisiert → is_canonical sagt wieder True."""
        payload = {k: {} for k in LOUIS_KEYS_ECHT}
        payload["_meta"] = {
            "prompt_version": "p04-v1.0",
            "luecken": list(LOUIS_META_ECHT["luecken"]),
        }

        doc, _ = st.normalisiere_top_level_keys("p04", payload)
        doc, entfernt, _ = st.aktualisiere_schema_luecken("p04", doc)

        assert len(entfernt) == 8
        assert cp.is_canonical(doc) is True


class TestFinalizeCanonicalNormalisiert:
    def test_versalien_erzeugen_keine_wurzel_luecke_mehr(self):
        """Ein Payload wie Louis' Row darf beim Speichern kein Wurzelfeld mehr reißen."""
        parsed = {k: {} for k in LOUIS_KEYS_ECHT}
        doc, errors = st.finalize_canonical("p04", parsed, meta={"prompt_version": "p04-v1.0"})

        assert "identitaet" in doc
        assert "IDENTITÄT" not in doc
        wurzel_luecken = [e for e in errors if e.startswith("(root)") and "required" in e]
        assert wurzel_luecken == []

    def test_gespeichertes_dokument_besteht_den_waechter(self):
        """Die Kette schließt sich: erzeugt → normalisiert → is_canonical sagt True."""
        parsed = {k: {} for k in LOUIS_KEYS_ECHT}
        doc, _ = st.finalize_canonical("p04", parsed, meta={"prompt_version": "p04-v1.0"})

        assert cp.is_canonical(doc) is True
