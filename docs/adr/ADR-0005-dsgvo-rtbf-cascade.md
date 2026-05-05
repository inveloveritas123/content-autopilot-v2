# ADR-0005: RtbF DSGVO Art. 17 Cascade-Modell

## Status

Akzeptiert (2026-05-04)

## Kontext

DSGVO Art. 17 ("Recht auf Vergessenwerden") verlangt, dass auf Anfrage eines Nutzers ALLE personenbezogenen Daten geloescht werden. Gleichzeitig verlangt DSGVO Art. 5 Abs. 2 (Rechenschaftspflicht), dass der Verantwortliche nachweisen kann, dass Loeschungen tatsaechlich durchgefuehrt wurden — und diesen Nachweis 10 Jahre aufbewahrt (Issues #148, #149).

Das erzeugt einen Zielkonflikt:
- Art. 17: Alle Daten loeschen
- Art. 5 Abs. 2: Nachweis der Loeschung 10 Jahre aufbewahren

Ausserdem: Personenbezogene Daten koennen in mehreren Tabellen liegen (Memory-Chunks mit Voice-Transkripten, Content-Pieces mit persoenlichen Angaben, LLM-Call-Logs mit Prompt-Texten) und in Nextcloud-Files ausserhalb der Datenbank.

## Entscheidung

Das Cascade-Modell trennt Audit-Log und Nutzerdaten strikt:

**`deletion_requests`-Tabelle als 10-Jahres-Audit-Log:**
- Kein Fremdschluessel zu `tenants` (intentional — Tenant koennte selbst geloescht sein, Log muss bleiben)
- Spalten: `id UUID`, `tenant_id UUID`, `requested_by`, `requested_at`, `completed_at`, `status`, `notes`
- Retention: 10 Jahre, keine automatische Bereinigung

**Cascade auf 6 Tabellen via `deletion_request_id`-FK:**
- `memory_chunks` — Voice-Transkripte, Embeddings
- `content_pieces` — Generierte Inhalte mit Personenbezug
- `content_ideas` — Ideenentwuerfe
- `source_items` — Quell-Items (YouTube-Transkripte etc.)
- `llm_call_logs` — Prompt + Response Texte
- `telegram_message_log` — Telegram-Konversationen

Jede Soft-Delete-Zeile traegt die `deletion_request_id` (siehe ADR-0001). Der Delete-Service setzt alle betroffenen Zeilen auf Soft-Deleted + tragt die UUID ein. Ein Celery-Task (`deletion_purge`, taeglich 02:00) loescht Hard die Rows nach Ablauf der konfigurierten Retention (Default: sofort nach Antrag, konfigurierbar auf bis zu 30 Tage fuer Widerrufs-Window).

**Nextcloud-Files:** Werden separat via NC-Adapter geloescht (`/content-autopilot/v2/Kunde/{slug}/`-Verzeichnis). Kein DB-FK — NC ist ausserhalb der DB-Transaktion. Fehler werden in `deletion_requests.notes` dokumentiert und manuell nachbearbeitet.

## Konsequenzen

**Positiv:**
- DSGVO Art. 17 erfuellt: Alle personenbezogenen Daten werden cascadiert geloescht
- DSGVO Art. 5 Abs. 2 erfuellt: 10-Jahres-Audit-Log der Loeschantraege bleibt erhalten
- Bewusster und dokumentierter Trade-off (dieser ADR ist der Nachweis)
- Recovery-Isolation durch `deletion_request_id`-FK (ADR-0001)

**Negativ:**
- NC-File-Loeschung ist nicht atomar mit DB-Cascade — bei NC-Ausfall koennen Files zurueckbleiben
- `deletion_requests`-Tabelle hat bewusst keinen FK zu `tenants` — referentielle Integritaet muss in der Applikationsschicht sichergestellt werden
- Hard-Delete via `deletion_purge` ist irreversibel — Backup vor Purge empfohlen

**Neutral:**
- Soft-Delete-Mechanismus war bereits vorhanden, wird jetzt mit FK verknuepft
- `deletion_request_id`-Backfill fuer historische Daten (Migration 047)

## Alternativen die verworfen wurden

**Hard-Delete ohne Audit-Log:** Einfachste Implementierung — alle Rows direkt loeschen, keine `deletion_requests`-Tabelle. Verstosst gegen DSGVO Art. 5 Abs. 2 (Rechenschaftspflicht). Ohne Nachweis der Loeschung kein Art.-17-Nachweis gegenueber Aufsichtsbehoerden. Nicht akzeptabel.

**Pseudonymisierung statt Loeschung:** Personenbezogene Felder werden ueberschrieben (`name → GELOESCHT`, `text → [REDACTED]`). Art. 17 erlaubt Pseudonymisierung als Alternative in bestimmten Faellen (z.B. wenn Daten fuer Forschung weiter benoetigt werden). Fuer Content-Autopilot gibt es keinen legitimen Weiterverarbeitungs-Grund nach Kuendigungsanfrage — echter Hard-Delete ist rechtssicherer.

**Kaskade via ON DELETE CASCADE in PostgreSQL:** FK-Cascade automatisch auf DB-Ebene. Verliert die Kontrolle ueber Reihenfolge und Logging — kein `deletion_request_id` wuerde gesetzt, kein Audit-Event wuerden gefeuert. Applikations-seitige Cascade ist hier beabsichtigt.
