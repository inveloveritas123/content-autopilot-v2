"""
test_canonical_wiring.py — Tests für den nativen kanonischen Schreibpfad.

Deckt build_canonical_meta() + finalize_canonical() in services/schema_transformer.py
ab — die Funktionen, mit denen P01/P03/P04 Louis-konforme Outputs absichern,
OHNE v2-Transformation (SOLL-IST-2026-06-12-wiring.md).

WICHTIG: Kein DB-Zugriff, keine echten Kundendaten. Alle Payloads synthetisch.

Ausführen:
    cd backend
    PYTHONPATH=. CONTENT_TRUTH_BASE_PATH=<repo>/content-truth \
        python -m pytest tests/test_canonical_wiring.py -v

Das Modul wird via importlib direkt geladen, um services/__init__.py
(google.generativeai) zu umgehen.
"""

import importlib.util
import unittest
from pathlib import Path


def _load_transformer_module():
    module_path = Path(__file__).parent.parent / "services" / "schema_transformer.py"
    spec = importlib.util.spec_from_file_location("schema_transformer_wiring", str(module_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


st = _load_transformer_module()
build_canonical_meta = st.build_canonical_meta
finalize_canonical = st.finalize_canonical
validate_canonical = st.validate_canonical
resolve_canonical_prompt_version = st.resolve_canonical_prompt_version


# ---------------------------------------------------------------------------
# Synthetische, vollständig Louis-konforme Beispiel-Outputs (ohne _meta —
# das setzt der Server). Decken die Pflicht-minItems der Schemas ab.
# ---------------------------------------------------------------------------


def _valid_p01() -> dict:
    return {
        "person": {"name": "Test Person", "rolle": "Coach"},
        "zielkunde": {
            "beschreibung": "Solo-Selbstständige",
            "wunschzustand": None,
            "innenwelt": None,
        },
        "angebot": {"elevator_pitch": "Ich helfe X bei Y"},
        "positionierung": {"werte_schwerpunkt": "Ehrlichkeit"},
        "markt": {"mitbewerber": "viele"},
        "vertrauen": {"erfolgsgeschichte": "10 Jahre"},
        "sprache": {"du_oder_sie": "du", "lieblingswörter": ["konkret"]},
        "content_reservoir": {"starke_meinungen": ["Weniger ist mehr"]},
    }


def _valid_p03() -> dict:
    return {
        "grundton": {
            "charakterisierung": "direkt",
            "spektrum": "warm",
            "linkedin_kalibrierung": "mittel",
        },
        "satzarchitektur": {
            "laenge": "kurz",
            "typische_satzanfaenge": ["Ich", "Wir", "Stell dir vor"],
            "verbindungen": "und, aber",
            "beispiele": ["Kurz und klar."],
        },
        "wortschatz": {
            "signalwoerter": ["konkret"],
            "fuellwoerter": ["halt"],
            "verbotene_woerter": ["Synergie"],
        },
        "erzaehlmuster": {
            "perspektive": "ich",
            "story_einstieg": "in medias res",
            "argumentation": "induktiv",
        },
        "emotionaler_ausdruck": {"spektrum": "breit", "humor_typ": "trocken"},
        "persoenlichkeits_stance": {"archetyp": "Mentor", "stance_in_aktion": ["ermutigt"]},
        "emotionaler_subtext": {"subtext": "Zuversicht"},
        "ueberzeugungsstil": {"primaer": "Story"},
        "zielgruppen_sprachfilter": {"leser_profil": "Gründer", "sprachbarrieren": ["Fachjargon"]},
        "vermeidungsprofil": {"nie_sagen": ["Buzzword"]},
        "referenz_saetze": {
            "original": ["s1", "s2", "s3", "s4", "s5"],
            "adaptiert": ["a1", "a2", "a3"],
        },
    }


def _valid_p04() -> dict:
    return {
        "identitaet": {"rolle_und_alltag": "Soloselbstständig", "selbstbild": "Macher"},
        "innenwelt": {"innerer_monolog": ["g1", "g2", "g3"], "unausgesprochene_angst": "Scheitern"},
        "wunschbild": {"wunschzustand": "frei", "wunschidentitaet": "Experte"},
        "content_trigger": {
            "scroll_stopper": ["x1", "x2", "x3"],
            "resonanz_saetze": ["r1", "r2", "r3", "r4", "r5"],
            "abstoss_trigger": ["t1", "t2"],
        },
        "sprache_der_zielgruppe": {"redewendungen": ["w1", "w2", "w3"], "ansprache": "du"},
        "alltagsszenen": {
            "szenen": ["s1", "s2", "s3", "s4", "s5"],
            "wiederkehrende_muster": ["m1", "m2", "m3"],
        },
        "blockaden": {"glaubenssaetze": ["b1", "b2", "b3"], "denkfehler": ["d1", "d2"]},
        "ausloesemoment": {
            "trigger_events": ["e1", "e2", "e3"],
            "emotional_tipping_point": "jetzt",
        },
    }


_META_BASE = {
    "tenant_id": "11111111-2222-3333-4444-555555555555",
    "model": "anthropic/claude-sonnet-4-6",
    "generated_at": "2026-06-12T10:00:00+00:00",
}


class TestBuildCanonicalMeta(unittest.TestCase):
    def test_authoritative_fields_present(self):
        meta = build_canonical_meta("p01", **_META_BASE)
        for key in ("agentur_id", "kunde_id", "prompt_version", "model", "generated_at"):
            self.assertIn(key, meta)
        self.assertEqual(meta["model"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(meta["generated_at"], "2026-06-12T10:00:00+00:00")

    def test_prompt_version_pattern(self):
        for key, expected in (("p01", "p01-v1.0"), ("p03", "p03-v1.0"), ("p04", "p04-v1.0")):
            meta = build_canonical_meta(key, **_META_BASE)
            self.assertEqual(meta["prompt_version"], expected)

    def test_kunde_id_from_tenant_name_slug(self):
        meta = build_canonical_meta("p01", tenant_name="Eric Spielhaus", **_META_BASE)
        self.assertEqual(meta["kunde_id"], "eric-spielhaus")

    def test_kunde_id_fallback_is_pattern_valid(self):
        # Ohne Name → Slug aus tenant_id (UUID), muss ^[a-z0-9-]+$ erfüllen
        meta = build_canonical_meta("p01", **_META_BASE)
        self.assertRegex(meta["kunde_id"], r"^[a-z0-9-]+$")

    def test_agentur_id_default_zb(self):
        meta = build_canonical_meta("p01", **_META_BASE)
        self.assertEqual(meta["agentur_id"], "zb")

    def test_llm_meta_extras_merged_but_authoritative_protected(self):
        llm_meta = {
            "agentur_id": "HACKED",  # autoritativ → muss ignoriert werden
            "prompt_version": "garbage",  # autoritativ → muss ignoriert werden
            "p04_aufgaben": ["leite X ab"],  # harmlos → übernehmen
            "transkript_qualitaet": "gut",  # harmlos → übernehmen
        }
        meta = build_canonical_meta("p01", llm_meta=llm_meta, **_META_BASE)
        self.assertEqual(meta["agentur_id"], "zb")
        self.assertEqual(meta["prompt_version"], "p01-v1.0")
        self.assertEqual(meta["p04_aufgaben"], ["leite X ab"])
        self.assertEqual(meta["transkript_qualitaet"], "gut")


class TestFinalizeCanonicalValid(unittest.TestCase):
    def test_valid_p01_passes(self):
        meta = build_canonical_meta("p01", **_META_BASE)
        doc, errors = finalize_canonical("p01", _valid_p01(), meta=meta)
        self.assertEqual(errors, [], msg=f"unerwartete Fehler: {errors}")
        self.assertIn("_meta", doc)
        self.assertEqual(validate_canonical("p01", doc), [])

    def test_valid_p03_passes(self):
        meta = build_canonical_meta("p03", **_META_BASE)
        doc, errors = finalize_canonical("p03", _valid_p03(), meta=meta)
        self.assertEqual(errors, [], msg=f"unerwartete Fehler: {errors}")

    def test_valid_p04_passes(self):
        meta = build_canonical_meta("p04", **_META_BASE)
        doc, errors = finalize_canonical("p04", _valid_p04(), meta=meta)
        self.assertEqual(errors, [], msg=f"unerwartete Fehler: {errors}")


class TestFinalizeCanonicalSoftFail(unittest.TestCase):
    def test_incomplete_p04_does_not_raise_and_records_luecken(self):
        # P04 mit zu wenigen Items → minItems verletzt → Lücken statt Hard-Fail
        broken = _valid_p04()
        broken["alltagsszenen"]["szenen"] = ["nur eine"]
        meta = build_canonical_meta("p04", **_META_BASE)
        doc, errors = finalize_canonical("p04", broken, meta=meta)
        self.assertTrue(errors, "Schema-Fehler erwartet")
        self.assertIn("luecken", doc["_meta"])
        self.assertTrue(any("szenen" in g for g in doc["_meta"]["luecken"]))

    def test_p01_additionalproperties_violation_recorded(self):
        # v2-Altfeld auf Top-Level → P01 hat additionalProperties:false → Lücke
        broken = _valid_p01()
        broken["wunschzustand"] = None  # v2-Bug, darf NICHT mehr vorkommen
        meta = build_canonical_meta("p01", **_META_BASE)
        doc, errors = finalize_canonical("p01", broken, meta=meta)
        self.assertTrue(errors)

    def test_empty_doc_soft_fails_with_meta(self):
        meta = build_canonical_meta("p03", **_META_BASE)
        doc, errors = finalize_canonical("p03", {}, meta=meta)
        self.assertTrue(errors)
        self.assertEqual(doc["_meta"]["agentur_id"], "zb")  # _meta trotzdem korrekt

    def test_luecken_are_deduped(self):
        meta = build_canonical_meta(
            "p04", luecken=["schema: alltagsszenen.szenen: x"], **_META_BASE
        )
        broken = _valid_p04()
        broken["alltagsszenen"]["szenen"] = []
        doc, errors = finalize_canonical("p04", broken, meta=meta)
        luecken = doc["_meta"]["luecken"]
        self.assertEqual(len(luecken), len(set(luecken)))


if __name__ == "__main__":
    unittest.main()
