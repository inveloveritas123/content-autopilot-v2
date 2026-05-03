# content-autopilot-v2 — Datenbank-Dokumentation

## Übersicht

PostgreSQL-Datenbank `content_autopilot_v2`, User `autopilot`.
31 Tabellen in 8 Funktionsbereichen. Schema-Migrations via Alembic.

## Tabellen-Übersicht

### Kern (Migration 001–006)
| Tabelle | Beschreibung |
|---|---|
| `tenants` | Multi-Tenant-Root: API-Key, Name, Kill-Switch, Branding |
| `sources` | Content-Quellen (RSS, YouTube, Web-Scraping) |
| `source_items` | Einzelne Artikel/Videos aus Sources |
| `content_pieces` | Generierte Inhalte (LinkedIn, Newsletter, Carousel) |
| `campaigns` | Kampagnen zur Gruppierung von Content |

### Content-Pipeline (Migration 003)
| Tabelle | Beschreibung |
|---|---|
| `content_ideas` | Ideen aus Quellen (vor Generierung) |
| `entrepreneur_answers` | Antworten des Unternehmers auf Fragen |
| `content_performances` | Performance-Tracking (Views, Likes) |
| `idea_selection_logs` | Log welche Ideen warum ausgewählt wurden |

### LLM + Generation (Migration 007–015)
| Tabelle | Beschreibung |
|---|---|
| `llm_providers` | LLM-Provider-Konfiguration + Cost-Tracking (USD Cents) |
| `scheduled_posts` | Geplante Posts mit Veröffentlichungszeit |
| `carousel_templates` | Karussell-Layout-Templates |
| `content_dna_profiles` | Content-DNA-Profile für Stil-Konsistenz |
| `scraped_posts` | Gescrapte Competitor-Posts |
| `projects` | Projekt-Gruppierung für Sources |
| `llm_call_logs` | LLM-Call-History mit Kosten |

### Analyse (Migration 016–017)
| Tabelle | Beschreibung |
|---|---|
| `dialogue_questions` | Fragen für Unternehmer-Dialog |
| `quality_metrics` | Content-Qualitäts-Bewertungen |

### Brand Voice (Migration 018) — Tenant-spezifisch
| Tabelle | Beschreibung |
|---|---|
| `tenant_customer_context` | Kundenprofil (Person, Unternehmen, Branche) |
| `tenant_voice_profile` | Tonalität, Stil, Kommunikationsregeln |
| `tenant_audience_avatar` | Zielgruppen-Definition |
| `wizard_session` | Brand-Voice-Wizard-Sessions |
| `voice_drift_observation` | Erkannte Stil-Abweichungen |
| `daily_cost_tracking` | Tägliches Kosten-Budget-Tracking |
| `setup_pipeline_runs` | Status der Brand-Voice-Setup-Pipeline |

### Telegram-Integration (Migration 019) — Optional
| Tabelle | Beschreibung |
|---|---|
| `tenant_telegram_link` | Verknüpfung Tenant ↔ Telegram-Chat |
| `telegram_message_log` | Eingehende Telegram-Nachrichten |
| `bot_session` | Bot-Session-State |

### Voice Feedback + Models (Migration 020–023)
| Tabelle | Beschreibung |
|---|---|
| `voice_feedback` | Feedback zu generierten Inhalten |
| `models_available` | Verfügbare LLM-Modelle + Konfiguration |
| `backtest_runs` | Backtest-Läufe für Modell-Vergleiche |

### Tenant Governance (Migration 024–031)
| Tabelle | Beschreibung |
|---|---|
| `tenant_review_queue` | Sensitive Content-Review-Warteschlange |
| `tenant_reservoir` | Ideen-Reservoir für Batch-Generierung |
| `tenant_branding` | Branding-Einstellungen (Logo, Farben) |
| `tenant_bot_config` | Bot-Konfiguration (Random-Smart-Modus) |

---

## Alembic-Workflow

### Aktuelle Version prüfen
```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic current
```

### Alle Migrationen anzeigen
```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic history --verbose
```

### Upgrade auf neueste Version
```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic upgrade head
```

### Einzelne Version upgraden
```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic upgrade 025
```

### Downgrade (eine Stufe zurück)
```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic downgrade -1
```

### Neue Migration anlegen
```bash
# Im Backend-Container oder lokal mit aktivierter venv:
alembic revision --autogenerate -m "add_feature_xyz"
# Dann: backend/alembic/versions/032_add_feature_xyz.py prüfen + bereinigen
```

---

## Setup auf neuem Host (Migration-Reihenfolge)

```bash
# 1. Leere DB anlegen
psql -U postgres -c "CREATE USER autopilot WITH PASSWORD 'your-password';"
psql -U postgres -c "CREATE DATABASE content_autopilot_v2 OWNER autopilot;"

# 2. Stack starten — Migrationen laufen automatisch beim Backend-Start
docker compose -f docker-compose.v2.yml up -d --build

# 3. Status prüfen (sollte auf "031_tenant_bot_config" enden)
docker compose -f docker-compose.v2.yml exec backend-v2 alembic current
```

Automatische Migrations-Reihenfolge: 001 → 002 → ... → 031

---

## Backup & Restore

### Backup erstellen
```bash
# Vollständiges Backup (Schema + Daten)
pg_dump -U autopilot -h localhost -Fc content_autopilot_v2 > backup_$(date +%Y%m%d_%H%M).dump

# Nur Schema (ohne Daten)
pg_dump -U autopilot -h localhost --schema-only -Fc content_autopilot_v2 > schema_$(date +%Y%m%d).dump

# Mit Verschlüsselung (empfohlen für Production)
pg_dump -U autopilot -h localhost -Fc content_autopilot_v2 | \
  openssl enc -aes-256-cbc -pbkdf2 -out backup_$(date +%Y%m%d_%H%M).dump.enc
```

### Restore
```bash
# Aus unverschlüsseltem Backup
pg_restore -U autopilot -h localhost -d content_autopilot_v2 --no-owner backup_20260503.dump

# Aus verschlüsseltem Backup
openssl enc -d -aes-256-cbc -pbkdf2 -in backup_20260503.dump.enc | \
  pg_restore -U autopilot -h localhost -d content_autopilot_v2 --no-owner
```

### Migration zwischen Hosts
```bash
# 1. Backup auf altem Host
pg_dump -U autopilot -Fc content_autopilot_v2 > migration_$(date +%Y%m%d).dump

# 2. Datei übertragen
scp migration_20260503.dump user@new-host:/tmp/

# 3. Auf neuem Host: leere DB anlegen + Restore
psql -U postgres -c "CREATE DATABASE content_autopilot_v2 OWNER autopilot;"
pg_restore -U autopilot -d content_autopilot_v2 --no-owner /tmp/migration_20260503.dump

# 4. Neue Migrationen ausführen (falls Code neuer als Backup)
docker compose -f docker-compose.v2.yml exec backend-v2 alembic upgrade head
```

---

## Tenant-spezifische vs. globale Daten

**Tenant-spezifisch** (an `tenant_id` gebunden — werden bei Tenant-Löschung mitgelöscht):
- `sources`, `source_items`, `content_pieces`, `content_ideas`
- Alle Brand-Voice-Tabellen (`tenant_customer_context`, `tenant_voice_profile`, `tenant_audience_avatar`)
- `tenant_telegram_link`, `tenant_review_queue`, `tenant_reservoir`, `tenant_branding`, `tenant_bot_config`
- `llm_providers`, `scheduled_posts`, `projects`

**Global** (tenantübergreifend):
- `models_available` — verfügbare LLM-Modelle (Admin-verwaltet)
- `backtest_runs` — Modell-Benchmarks

---
