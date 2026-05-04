"""Unit-Tests für MD-Onboarding-Parser (Issue #148, Welle C)."""
from __future__ import annotations

from services.profile_md_parser import parse_onboarding_md


SAMPLE_MD = """# Onboarding — Acme Corp

## Firma
- Name: Acme GmbH
- Branche: Beratung
- Gegründet: 2015
- Mitarbeitende: 12
- Region: Hamburg
- Website: https://acme.example.com

## Ansprechpartner
- Name: Max Mustermann
- Rolle: CEO
- Email: max@acme.example.com

## USP
Wir verbinden klassische Beratung mit modernen KI-Tools.

## Zielgruppe
Mittelständische B2B-Unternehmen 50–500 MA.

## Werte
Transparenz, Tempo, Tiefe.
"""


def test_parser_extracts_all_basic_fields():
    out = parse_onboarding_md(SAMPLE_MD)
    fields = {s["field_name"] for s in out}
    assert "company_name" in fields
    assert "industry" in fields
    assert "founded_year" in fields
    assert "headcount" in fields
    assert "region" in fields
    assert "website" in fields
    assert "contact_person_name" in fields
    assert "contact_role" in fields
    assert "contact_email" in fields
    assert "usp" in fields
    assert "target_audience" in fields
    assert "values_short" in fields


def test_parser_company_name_value():
    out = parse_onboarding_md(SAMPLE_MD)
    cn = next(s for s in out if s["field_name"] == "company_name")
    assert cn["value"] == "Acme GmbH"
    assert cn["confidence"] >= 0.9


def test_parser_founded_year_extracts_int_string():
    out = parse_onboarding_md(SAMPLE_MD)
    fy = next(s for s in out if s["field_name"] == "founded_year")
    assert fy["value"] == "2015"


def test_parser_headcount_extracts_int_string():
    out = parse_onboarding_md(SAMPLE_MD)
    hc = next(s for s in out if s["field_name"] == "headcount")
    assert hc["value"] == "12"


def test_parser_handles_empty_input():
    assert parse_onboarding_md("") == []
    assert parse_onboarding_md("foo") == []


def test_parser_handles_garbage_input():
    md = "Random text without any sections."
    assert parse_onboarding_md(md) == []


def test_parser_dedupes_double_definitions():
    md = """# X
## Firma
- Name: Erste GmbH
- Name: Zweite GmbH
"""
    out = parse_onboarding_md(md)
    company_names = [s for s in out if s["field_name"] == "company_name"]
    assert len(company_names) == 1
    assert company_names[0]["value"] == "Erste GmbH"


def test_parser_block_field_usp():
    md = """# X
## USP
Erste Zeile USP.
Zweite Zeile USP.
"""
    out = parse_onboarding_md(md)
    usp = [s for s in out if s["field_name"] == "usp"]
    assert len(usp) == 1
    assert "Erste Zeile" in usp[0]["value"]
    assert "Zweite Zeile" in usp[0]["value"]


def test_parser_truncates_long_blocks():
    md = "# X\n## USP\n" + ("X" * 5000)
    out = parse_onboarding_md(md)
    usp = next(s for s in out if s["field_name"] == "usp")
    assert len(usp["value"]) <= 2000
