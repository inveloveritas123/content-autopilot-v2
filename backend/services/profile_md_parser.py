"""MD-Onboarding-Parser (Phase 8.x, Issue #148, Welle C).

Erwartet Eric/Chris-Onboarding-MD mit Sektionen wie:

```markdown
# Onboarding — <Firma>
## Firma
- Name: ZKG GmbH
- Branche: Coaching
- Gegründet: 2018
- Mitarbeitende: 5
- Region: Berlin
- Website: https://zukunftsbund.de
## Ansprechpartner
- Name: Robert Hargesheimer
- Rolle: Geschäftsführer
- Email: robert@example.com
## USP
Wir verbinden Soft-Skills mit MINT-Karrieren.
## Zielgruppe
Solo-Berater 30–55 Jahre.
## Werte
Authentizität, Pragmatismus, Tiefe.
```

Heuristik:
- Sektionen via H2-Header, Felder via "- Label: Wert"-Bullet-Listen
- Multi-Line-Blöcke (USP/Zielgruppe/Werte) werden als ganze Absätze übernommen
"""
from __future__ import annotations

import re
from typing import Optional


SECTION_FIELD_MAP = {
    "firma": {
        "name": "company_name", "firma": "company_name", "firmenname": "company_name",
        "branche": "industry", "industry": "industry",
        "gegründet": "founded_year", "gegruendet": "founded_year", "founded": "founded_year",
        "mitarbeitende": "headcount", "mitarbeiter": "headcount", "headcount": "headcount",
        "region": "region", "standort": "region",
        "website": "website", "webseite": "website",
        "größe": "company_size", "groesse": "company_size", "size": "company_size",
        "rechtsform": "legal_form", "legal form": "legal_form",
    },
    "ansprechpartner": {
        "name": "contact_person_name", "ansprechpartner": "contact_person_name",
        "rolle": "contact_role", "position": "contact_role", "role": "contact_role",
        "email": "contact_email", "e-mail": "contact_email", "mail": "contact_email",
    },
    "kontakt": {
        "name": "contact_person_name",
        "rolle": "contact_role", "position": "contact_role",
        "email": "contact_email", "e-mail": "contact_email",
    },
}

BLOCK_FIELDS = {
    "usp": "usp", "alleinstellung": "usp", "unique selling": "usp",
    "zielgruppe": "target_audience", "target audience": "target_audience", "kunden": "target_audience",
    "werte": "values_short", "values": "values_short", "werteversprechen": "values_short",
}


def _norm(s: str) -> str:
    return s.strip().lower()


def parse_onboarding_md(md: str) -> list[dict]:
    """Parst eine MD-Datei und liefert eine Liste von Field-Vorschlägen.

    Returns: [{"field_name": "company_name", "value": "ZKG", "confidence": 0.9}]
    """
    if not md or len(md) < 10:
        return []

    suggestions: list[dict] = []
    lines = md.splitlines()
    current_section: Optional[str] = None
    current_block_field: Optional[str] = None
    block_buffer: list[str] = []

    def flush_block():
        nonlocal block_buffer, current_block_field
        if current_block_field and block_buffer:
            text_val = "\n".join(block_buffer).strip()
            if text_val and len(text_val) >= 5:
                suggestions.append({
                    "field_name": current_block_field,
                    "value": text_val[:2000],
                    "confidence": 0.9,
                })
        block_buffer = []
        current_block_field = None

    for line in lines:
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h2:
            flush_block()
            section_label = _norm(h2.group(1))
            current_section = None
            for sec_key in SECTION_FIELD_MAP.keys():
                if sec_key in section_label:
                    current_section = sec_key
                    break
            for block_key, field in BLOCK_FIELDS.items():
                if block_key in section_label:
                    current_block_field = field
                    break
            continue

        h1 = re.match(r"^#\s+(.+?)\s*$", line)
        if h1:
            flush_block()
            current_section = None
            continue

        if current_block_field and line.strip() and not line.startswith("#"):
            block_buffer.append(line.strip())
            continue

        bullet = re.match(r"^\s*[-*]\s+([^:]+?)\s*[:=]\s*(.+?)\s*$", line)
        if bullet and current_section:
            label = _norm(bullet.group(1))
            value = bullet.group(2).strip()
            field_map = SECTION_FIELD_MAP.get(current_section, {})
            field_name = None
            for label_key, fname in field_map.items():
                if label_key == label or label.startswith(label_key):
                    field_name = fname
                    break
            if not field_name:
                continue

            cast_value = value
            if field_name in ("founded_year", "headcount"):
                m = re.search(r"\d{1,4}", value)
                if not m:
                    continue
                cast_value = m.group(0)

            suggestions.append({
                "field_name": field_name,
                "value": cast_value,
                "confidence": 0.9,
            })

    flush_block()

    seen: dict[str, dict] = {}
    for s in suggestions:
        if s["field_name"] not in seen:
            seen[s["field_name"]] = s
    return list(seen.values())
