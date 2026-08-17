"""daily_cost_tenant.cost_usd: numeric(10,4) -> numeric(14,8)

Revision ID: 067
Revises: 065
Create Date: 2026-08-17

⛔ Warum diese Migration nötig ist — der Kostendeckel versagte in die
FALSCHE Richtung:

`daily_cost_tenant.cost_usd` war `numeric(10,4)` und konnte damit nur bis
0,0001 USD auflösen. Ein typischer Pipeline-LLM-Call kostet aber rund
0,0000108 USD — eine Größenordnung darunter. Jeder Betrag unter 0,00005
wurde beim Speichern zu exakt `0`. Das ist kein Rundungsfehler, sondern
Totalverlust.

Gemessen gegen Postgres (nicht gerechnet), 2026-08-17:

    | Prüfung                  | numeric(10,4) | numeric(14,8) | Wahrheit   |
    |--------------------------|---------------|---------------|------------|
    | ein Betrag 0.0000108     | 0.0000    ❌  | 0.00001080 ✅ | 0.0000108  |
    | 1000 Beträge summiert    | 0.0000    ❌  | 0.01080000 ✅ | 0.0108     |

`services/llm.py` liest genau diese Tabelle für den Tages-Kostendeckel. Eine
zu niedrige Summe heißt: der Deckel greift ZU SPÄT statt zu früh — also
genau die Richtung, in der ein Kostendeckel nutzlos ist. Bei einem
Zielbudget von < 170 EUR/Monat (CLAUDE.md) ist das ein falsches
Sicherheitsgefühl statt eines Schutzes.

Betroffen sind die vielen kleinen Calls des Dauerbetriebs
(`layer1_extraction`, `p14_entry_service`, `sensitive_detector`,
`p08_service`). Der `call_count` zählte dabei korrekt hoch: das Dashboard
zeigte Aktivität bei 0,00 USD.

Abgrenzung, ebenfalls nachgemessen: `SELECT 0.0002 + 0.0000108` liefert in
Postgres korrekt `0.0002108`. Die RECHNUNG stimmt also; abgeschnitten wird
erst beim ABLEGEN. Der additive UPSERT in `services/pipeline_llm.py`
(`_erfasse_kosten`) ist damit korrekt gebaut — die Spalte war das Nadelöhr.

Risiko: gering. Reine Präzisionserweiterung, keine Datenumwandlung, kein
Backfill. Bestehende Werte bleiben gültig (`0.0002` -> `0.00020000`).

⛔ Bereits verlorene Beträge sind NICHT rekonstruierbar — sie wurden nie
gespeichert. Diese Migration wirkt ausschließlich nach vorn.

Warum (14,8) und nicht mehr: 8 Nachkommastellen fassen einen Einzel-Call
(1e-5 USD) mit drei Stellen Reserve. 14 Gesamtstellen lassen 999.999 USD
Tagessumme zu — bei einem Monatsbudget von 170 EUR nie erreichbar, aber
ohne die Enge von (10,4).

Befund-Slug: zubu-cost-usd-numeric-10-4-schneidet-kleinbetraege-ab (P1)

⛔ Zur Nummernlücke (066 fehlt, das ist Absicht):
Diese Migration hat drei Nummern durchlaufen, bevor 067 feststand.
`orko_migration_slot.sh` gab zunächst „54" zurück, obwohl `054_voice_profile_
source_voice_fallback.py` längst existierte — ein Oktal-Bug: `belegt_max`
lieferte korrekt `065`, aber `$(( 065 + 1 ))` liest die führende Null als
Oktalzahl (0o65 = 53) und ergibt 54. Eine Revision `054` hätte die Kette
gespalten; die Rückfrage statt des Ratens hat das verhindert. Der Hub hat den
Bug gefixt (`10#` erzwingt Dezimal) und dabei mit einer Testreservierung 066
belegt, weshalb diese Migration auf 067 steht. Eine übersprungene Nummer ist
harmlos — eine doppelt vergebene nicht.
"""

from alembic import op

revision = "067"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE daily_cost_tenant ALTER COLUMN cost_usd TYPE numeric(14,8)")


def downgrade():
    # ⛔ Verlustbehaftet und bewusst so: der Rückweg auf numeric(10,4) schneidet
    # alle Nachkommastellen ab der fünften wieder ab. Genau deshalb existiert
    # diese Migration. Ein Downgrade ist nur sinnvoll, um einen Deploy
    # zurückzurollen, BEVOR nennenswerte Beträge in der neuen Präzision
    # aufgelaufen sind.
    op.execute("ALTER TABLE daily_cost_tenant ALTER COLUMN cost_usd TYPE numeric(10,4)")
