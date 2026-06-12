"""
test_golden_eric.py — Offline-Golden-E2E mit Louis' echten Eric-Beispiel-Outputs.

Beweist, dass REALE Louis-P01/P03/P04-Outputs den exakten Task-Schreibpfad
(finalize_canonical → kanonische Validierung) sauber durchlaufen und dass das
P12-Pruning den wortschatz-Block erhält — ohne DB/LLM.

PII-Hinweis (WERKBANK): Die Eric-Daten werden NICHT ins Repo committed. Der Test
liest sie aus dem untracked Louis-Paket (Pfad via GOLDEN_ERIC_DIR oder Default)
und SKIPPT, wenn die Daten fehlen (z.B. in CI). Kein Kundendatensatz im Git.

    cd backend
    PYTHONPATH=. CONTENT_TRUTH_BASE_PATH=<repo>/content-truth \
        python -m pytest tests/test_golden_eric.py -v
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

_DEFAULT_ERIC = (
    Path(__file__).resolve().parents[3]
    / "Import"
    / "Linkedin-Content-Autopilot"
    / "data"
    / "kunden"
    / "eric-spielhaus-2026-05-15"
)
ERIC_DIR = Path(os.environ.get("GOLDEN_ERIC_DIR", str(_DEFAULT_ERIC)))

pytestmark = pytest.mark.skipif(
    not (ERIC_DIR / "p01.json").exists(),
    reason=f"Eric-Golden-Daten nicht vorhanden ({ERIC_DIR}) — übersprungen (kein PII im Repo).",
)


def _load_mod(name, relpath):
    p = Path(__file__).parent.parent / relpath
    spec = importlib.util.spec_from_file_location(name, str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


st = _load_mod("st_golden", "services/schema_transformer.py")
pp = _load_mod("pp_golden", "services/../tasks/p12_pruning.py")

_META = {
    "tenant_id": "eric-golden-tenant",
    "model": "anthropic/claude-sonnet-4-6",
    "generated_at": "2026-06-12T10:00:00+00:00",
    "tenant_name": "Eric Spielhaus",
}


def _load(key):
    return json.loads((ERIC_DIR / f"{key}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", ["p01", "p03", "p04"])
def test_real_eric_output_passes_finalize_canonical(key):
    raw = _load(key)
    meta = st.build_canonical_meta(key, llm_meta=raw.get("_meta"), **_META)
    doc, errors = st.finalize_canonical(key, raw, meta=meta)
    assert errors == [], f"{key}: echte Louis-Daten erzeugen Schema-Lücken: {errors[:5]}"
    # _meta server-seitig korrekt gesetzt
    assert doc["_meta"]["agentur_id"] == "zb"
    assert doc["_meta"]["kunde_id"] == "eric-spielhaus"
    assert doc["_meta"]["prompt_version"] == f"{key}-v1.0"


def test_p12_pruning_keeps_eric_wortschatz():
    voice = _load("p03")
    pruned = pp.prune(voice, pp.VOICE_KEYS_FOR_P12)
    assert "wortschatz" in pruned, "Wortschatz-Block ging beim P12-Pruning verloren"
    # Eric hat echte Signalwörter — die müssen P12 erreichen
    assert pruned["wortschatz"].get("signalwoerter"), "Eric-Signalwörter fehlen im P12-Kontext"
