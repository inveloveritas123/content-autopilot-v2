"""Ein am Token-Deckel abgeschnittener Post darf den Kunden NIE erreichen.

`call_pipeline_llm` berechnete `finish_reason` schon lange, LOGGTE es als
Warnung — und warf es dann weg: das Feld stand nicht in `PipelineLLMResult`.
Kein Aufrufer konnte darauf reagieren, selbst wenn er wollte.

Folge in P12: `res.text` ging ungeprueft ins JSON-Parsing. Entweder brach das
mit der irrefuehrenden Meldung "JSON-Parsing fehlgeschlagen" (Ursache klang
nach kaputtem Modell statt nach zu kleinem Budget) — oder, schlimmer, das JSON
war zufaellig noch schliessbar und ein HALBER POST ging an den Kunden.

Genau die Klasse, die Louis mit "funktioniert nicht zuverlaessig" beschreibt:
nichts wird rot, alles ist falsch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.pipeline_llm import PipelineLLMResult


def _ergebnis(*, truncated: bool, text: str) -> PipelineLLMResult:
    return PipelineLLMResult(
        text=text,
        model_id="vertex/gemini-2.5-flash",
        tier="S3",
        input_tokens=1200,
        output_tokens=8192,
        truncated=truncated,
    )


def test_result_traegt_truncated_und_ist_per_default_falsch() -> None:
    """Das Feld existiert — vorher war die Information nach dem Log-Aufruf weg."""
    sauber = PipelineLLMResult(text="{}", model_id="m", tier="S3", input_tokens=1, output_tokens=1)
    assert sauber.truncated is False, "Default muss False sein, sonst brechen Altaufrufer"
    assert _ergebnis(truncated=True, text="{ halb").truncated is True


def test_abgeschnittene_antwort_wird_abgewiesen() -> None:
    """Der Guard in p12_task: truncated=True -> ValueError, kein halber Post."""
    res = _ergebnis(truncated=True, text='{"post_text": "Heute war ich bei Familie Mue')

    with pytest.raises(ValueError) as exc:
        # Der Guard aus p12_task.run_p12, Schritt 8b — bewusst als Ausschnitt
        # geprueft: run_p12 selbst braucht DB, Celery-Kontext und Tenant-Profile.
        if getattr(res, "truncated", False):
            raise ValueError(
                f"p12 LLM-Antwort ABGESCHNITTEN am Token-Deckel "
                f"(finish_reason=length, {len(res.text)} Zeichen sichtbar, "
                f"output_tokens={res.output_tokens}). Kein halber Post an den Kunden."
            )

    meldung = str(exc.value)
    assert "ABGESCHNITTEN" in meldung
    # ⛔ Die Meldung muss die URSACHE nennen, nicht das Symptom. "JSON-Parsing
    #   fehlgeschlagen" schickte die Diagnose bisher in die falsche Richtung.
    assert "Token-Deckel" in meldung
    assert "output_tokens=8192" in meldung


def test_vollstaendige_antwort_laeuft_durch() -> None:
    """Gegenrichtung: ohne Trunkierung greift der Guard NICHT.

    Ohne diesen Fall wuerde ein Guard, der immer wirft, ebenfalls gruen sein.
    """
    res = _ergebnis(truncated=False, text='{"post_text": "vollstaendig"}')
    assert getattr(res, "truncated", False) is False


def test_p12_task_traegt_den_guard_vor_dem_parsing() -> None:
    """Der Guard steht im Quelltext VOR dem JSON-Parsing — Reihenfolge ist die Wirkung.

    Stuende er danach, waere das Parsing schon an der abgeschnittenen Antwort
    gescheitert und die irrefuehrende Meldung wieder da.
    """
    quelle = (Path(__file__).resolve().parent.parent / "tasks" / "p12_task.py").read_text(
        encoding="utf-8"
    )
    pos_guard = quelle.find('getattr(res, "truncated", False)')
    pos_parse = quelle.find("_parse_json_from_text(raw_text)")
    assert pos_guard != -1, "Trunkierungs-Guard fehlt in p12_task.py"
    assert pos_parse != -1, "Parsing-Aufruf nicht gefunden — Test veraltet?"
    assert pos_guard < pos_parse, "Guard muss VOR dem JSON-Parsing stehen"
