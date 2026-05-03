# Migration Notes — Breaking Changes

## Übersicht Breaking Changes

| Migration | Typ | Auswirkung | Rollback möglich? |
|---|---|---|---|
| 024 | Daten-Migration | ZFB→ZKG Tenant-Rename + Test-Daten gelöscht | Nein (Datenverlust) |
| 026 | Schema-Änderung | Kill-Switch Spalten (neue Governance) | Ja |
| 027 | Schema-Änderung | `approval_method` Pflichtfeld in content_pieces | Ja (NULL erlaubt) |

---

## Migration 024 — ZFB→ZKG Tenant-Migration (BREAKING)

**Was passiert:**
- Tenant-Slug `zfb` wird zu `zkg` umbenannt
- API-Key `***REMOVED-TENANT-KEY***` bleibt als Secondary-Key bis 2026-08-01 gültig
- Test-Daten aus altem ZFB-Kontext werden gelöscht

**Wann relevant:** Upgrade von Systemen die vor 2026-04 installiert wurden.

**Vor Migration testen:**
```bash
# Backup machen!
pg_dump -U autopilot -Fc content_autopilot_v2 > pre_024_backup.dump

# Dry-run: Was würde gelöscht?
psql -U autopilot -d content_autopilot_v2 -c "
  SELECT COUNT(*) as affected_rows, 'tenants' as table_name
  FROM tenants WHERE api_key LIKE 'cap-tenant-zfb%';"
```

**Rollback (falls Migration 024 schiefläuft):**
```bash
docker compose -f docker-compose.v2.yml exec backend-v2 alembic downgrade 023
# Dann: Backup von pre_024_backup.dump einspielen
pg_restore -U autopilot -d content_autopilot_v2 --no-owner --data-only pre_024_backup.dump
```

---

## Neue Migration hinzufügen — Checkliste

1. **Backup** vor jeder Schema-Änderung in Production
2. Migration mit `--autogenerate` erstellen und **manuell prüfen**
3. Breaking Changes in `docs/MIGRATION_NOTES.md` dokumentieren
4. Migration auf Staging testen bevor Production
5. Downgrade-Pfad testen: `alembic downgrade -1` muss funktionieren

```bash
# Standard-Workflow neue Migration
alembic revision --autogenerate -m "032_beschreibung"
# → Datei prüfen: op.add_column / op.drop_column korrekt?
# → Downgrade-Funktion vollständig?
alembic upgrade head    # lokal testen
alembic downgrade -1    # rollback testen
alembic upgrade head    # wieder hoch
```

---

## Rollback-Strategie

**Faustregel:** Backup VOR jeder Migration. Besonders vor:
- `drop_column` / `drop_table` Operationen
- Daten-Transformationen (UPDATE in Migrations)
- `ALTER COLUMN ... NOT NULL` Constraints

**Automatisches Backup** (empfohlen, siehe Issue #105):
Wird als Pre-Migration-Hook implementiert — vor jedem `alembic upgrade` läuft `pg_dump`.
