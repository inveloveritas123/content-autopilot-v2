# ADR-0004: Embedding-Versionierung mit Canary-Rollout

## Status

Akzeptiert (2026-05-04)

## Kontext

Embedding-Modelle verbessern sich regelmaessig (Vertex AI, OpenAI etc.). Ein Modell-Wechsel ohne Versionierung bedeutet: Alte Embeddings (Modell A) und neue Embeddings (Modell B) liegen in derselben Tabelle, aber ihr Vektorraum ist inkompatibel. Cosine-Similarity-Queries zwischen alten und neuen Vektoren liefern sinnlose Ergebnisse (Issue #150).

Ohne Rollback-Moeglichkeit ist jeder Modell-Wechsel ein Big-Bang-Risiko: Wenn das neue Modell schlechtere Recall@20-Werte liefert als das alte, gibt es keinen sicheren Weg zurueck — ausser manuellem Restore aus einem Backup.

## Entscheidung

Jede Embedding-Tabelle (`memory_chunks`, `content_pieces`) erhaelt eine `embedding_model_id VARCHAR(64)`-Spalte, die das Modell identifiziert das diesen Vektor erzeugt hat (Beispiel: `vertex-text-embedding-005`).

Canary-Rollout-Mechanismus (`embedding_canary`-Flag in der Konfiguration):

1. Neues Modell wird als Canary konfiguriert mit 10%-Traffic-Anteil
2. Fuer 10% der neu eingehenden Items wird das Canary-Modell verwendet, fuer 90% das Produktionsmodell
3. `run_embedding_drift_monitor` (woechentlich) vergleicht Recall@20 zwischen beiden Modellen
4. Wenn Canary-Recall >= Produktions-Recall: Promotion auf 100% via Config-Aenderung + Mass-Re-Embed-Job
5. Wenn Canary-Recall < Produktions-Recall: Canary-Flag deaktivieren, keine alten Daten beschaedigt

Default-Produktionsmodell: `vertex-text-embedding-005` (768-dim, EU-Region, KEIN `text-embedding-004` — gibt 404 in EU-Projekten).

## Konsequenzen

**Positiv:**
- Sicherer Modell-Wechsel mit automatischem Qualitaets-Gate
- Rollback ohne Restore: Canary einfach deaktivieren
- Audit-Trail: jeder Vektor hat seinen Erzeuger gespeichert

**Negativ:**
- +1 VARCHAR-Spalte pro Embedding-Tabelle (marginal)
- Mass-Re-Embed-Job bei Promotion: bei 100.000 Chunks ca. 2-3h Laufzeit und API-Kosten
- `embedding_model_id` muss in allen INSERT-Pfaden mitgefuehrt werden — Vergessen = stille Inkonsistenz

**Neutral:**
- Drift-Monitor laeuft bereits woechentlich (Celery Beat) — kein neuer Infrastruktur-Aufwand

## Alternativen die verworfen wurden

**Big-Bang-Re-Embed ohne Versionierung:** Alle Chunks auf einmal mit neuem Modell neu berechnen, alte Vektoren ueberschreiben. Kein Rollback wenn neues Modell schlechter ist. Bei einem 100k-Chunk-Tenant bedeutet "rollback" = Backup-Restore + stundenlanger Re-Embed mit altem Modell. Nicht akzeptabel.

**Separate Tabelle pro Modell-Version:** Jede Modell-Version bekommt eigene Tabelle (`memory_chunks_v1`, `memory_chunks_v2`). Stark normalisiert aber operativ komplex: JOIN-Logik muss beide Tabellen kennen, Migrationen werden aufwaendiger, Admin-Tooling verdoppelt. `embedding_model_id` in derselben Tabelle ist einfacher und ausreichend.
