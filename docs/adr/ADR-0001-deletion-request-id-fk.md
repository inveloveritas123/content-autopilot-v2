# ADR-0001: deletion_request_id FK statt time-window matching

## Status

Akzeptiert (2026-05-04)

## Kontext

Bei parallelen DSGVO-Loeschantraegen (Art. 17) trat eine Race-Condition auf: Die urspruengliche Implementierung identifizierte betroffene Zeilen per `deleted_at BETWEEN (request_time - 2s) AND (request_time + 2s)`. Kamen zwei Delete-Requests innerhalb von 2 Sekunden herein, konnten ihre Loeschvorgaenge sich gegenseitig beeinflussen — ein Recovery-Versuch fuer Antrag A haette faelschlicherweise Rows von Antrag B reaktiviert (Issues #149, #157).

Das Time-Window-Matching ist ausserdem nicht auditierbar: Es gibt keinen deterministischen Nachweis, welche Zeilen zu welchem Antrag gehoeren — ein Problem fuer Art. 5 Abs. 2 DSGVO (Rechenschaftspflicht).

## Entscheidung

Alle Soft-Delete-Tabellen erhalten eine explizite UUID-Fremdschluessel-Spalte `deletion_request_id` (NOT NULL wenn geloescht, NULL fuer aktive Zeilen). Die Cascade-Logik in `api/data_deletion.py` traegt beim Loeschen die UUID des zugehoerigen `deletion_requests`-Eintrags in alle betroffenen Zeilen ein. Recovery-Operationen filtern ausschliesslich auf diese UUID.

Betroffene Tabellen: `memory_chunks`, `content_pieces`, `content_ideas`, `source_items`, `llm_call_logs`, `telegram_message_log`.

Migrationsschritte: Migration 047 fuegt die Spalte hinzu, ein Backfill-Skript (`scripts/backfill_deletion_fk.py`) befuellt historische Eintraege anhand der naechsten verfuegbaren `deletion_request_id` oder setzt `NULL` wo keine Zuordnung moeglich ist.

## Konsequenzen

**Positiv:**
- Garantierte Recovery-Isolation: Antrag A kann nie Antrag-B-Rows reaktivieren
- Lueckenloser Audit-Trail per UUID — Rechenschaftspflicht nach Art. 5 Abs. 2 erfullt
- Deterministische DB-Queries statt fehleranfaelliger Zeitfenster-Logik

**Negativ:**
- Migration 047 + Backfill noetig; Backfill kann bei grossen Tenant-Datenmengen mehrere Minuten dauern
- Eine zusaetzliche Nullable-Spalte pro betroffener Tabelle erhoehr den Speicherbedarf marginal

**Neutral:**
- Delete-Pfad unveraendert performant (UUID-Index auf `deletion_request_id`)

## Alternativen die verworfen wurden

**Pg-Advisory-Lock pro Delete-Request:** Ein PostgreSQL Advisory Lock haette die Race-Condition verhindert, aber bei Bulk-Recovery (viele Antraege gleichzeitig) zu hoher Lock-Contention gefuehrt. Ausserdem loest ein Advisory Lock das Audit-Problem nicht — die Zeilen blieben ohne explizite FK nicht deterministisch einer Request-UUID zugeordnet.
