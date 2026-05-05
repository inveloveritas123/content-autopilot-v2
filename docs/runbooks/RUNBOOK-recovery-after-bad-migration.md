# Runbook: Recovery nach fehlgeschlagener Migration

## Wann ausfuehren

Eine Alembic-Migration ist durchgelaufen aber:
- Backend-Container crasht beim Start mit `alembic.exc.ProgrammingError` oder `column does not exist`
- `/api/health` liefert 503 oder antwortet nicht
- Celery-Worker startet nicht (Schema-Fehler in Task-Initialisierung)

---

## Vor dem Recovery: Situation beurteilen

```bash
# Backend-Logs ansehen
cd /opt/content-autopilot-v2
docker compose logs --tail=50 backend-v2

# Alembic-Zustand pruefen
docker compose exec backend-v2 alembic current 2>/dev/null || echo "Backend nicht erreichbar"

# Alternativ direkt via psql
docker compose exec postgres psql -U cap -d cap_v2 \
  -c "SELECT version_num FROM alembic_version;"
```

---

## Schritte

### Schritt 1: Backend stoppen

```bash
cd /opt/content-autopilot-v2
docker compose stop backend-v2 celery-worker
```

### Schritt 2: Migration zurueckrollen

```bash
# -1 = eine Migrationsstufe zurueck
scripts/safe_alembic.sh "downgrade -1"
```

Erwartete Ausgabe: `Downgrade from <hash_neu> to <hash_alt>... done`

**Wichtig:** Laut Constraint #10 ist `alembic downgrade` hier explizit erlaubt (Notfall-Rollback). In normalen Faellen `safe_alembic.sh` verwenden. Das direkte `alembic downgrade` im Container umgehen — immer vom Host aus via `safe_alembic.sh`.

### Schritt 3: Backup wiederherstellen (falls Downgrade nicht reicht)

Wenn `downgrade -1` den Fehler nicht behebt (z.B. Data-Migration hatte Side-Effects):

```bash
# Verfuegbare Snapshots anzeigen
ls -lt /opt/backup/cap-v2-pre-migration-*.sql.gz | head -5

# Neuesten Snapshot identifizieren (Timestamp vor der fehlgeschlagenen Migration)
SNAPSHOT=/opt/backup/cap-v2-pre-migration-YYYYMMDD-HHMMSS.sql.gz  # ANPASSEN

# DB leeren und Snapshot einspielen
docker compose exec -T postgres psql -U cap -d postgres -c "DROP DATABASE cap_v2;"
docker compose exec -T postgres psql -U cap -d postgres -c "CREATE DATABASE cap_v2 OWNER cap;"
gunzip < "$SNAPSHOT" | docker compose exec -T postgres psql -U cap -d cap_v2

# Alembic-Zustand auf Snapshot-Revision setzen
docker compose exec backend-v2 alembic stamp <revision_vor_fehlgeschlagener_migration>
```

Die korrekte Revision findest du mit:
```bash
git log --oneline backend/alembic/versions/ | head -10
```

### Schritt 4: Backend neu starten

```bash
cd /opt/content-autopilot-v2
docker compose up -d backend-v2 celery-worker
```

### Schritt 5: Migration-Code korrigieren

Die fehlerhafte Migration-Datei unter `backend/alembic/versions/` identifizieren und den Bug beheben. Dann neu ausfuehren:

```bash
scripts/safe_alembic.sh "upgrade head"
```

---

## Verify

```bash
# Health-Check
curl http://localhost:8601/api/health
# Erwartet: {"status": "ok", ...}

# Alembic-Stand
docker compose exec backend-v2 alembic current
# Erwartet: <hash> (head)

# Celery-Worker laeuft
docker compose logs --tail=20 celery-worker | grep -i "ready\|celery@"
```

---

## Eskalation

Wenn nach Restore `alembic stamp` einen unbekannten Revision-Hash erwartet:

1. `alembic history` ausfuehren und den letzten bekannten Stand identifizieren
2. `alembic stamp <hash>` mit dem korrekten Hash
3. Falls unklar: Robert informieren und manuell in `alembic_version`-Tabelle schauen

```sql
SELECT * FROM alembic_version;
```

---

## Praevention

- Immer `scripts/safe_alembic.sh` verwenden (macht automatisch Pre-Snapshot)
- Neue Migrations lokal testen bevor auf Produktion
- Migration-Code-Review: Destruktive Operationen (DROP COLUMN, DROP TABLE) benoetigen explizite Bestaetigung
- Siehe [CLAUDE-PHASE2-CONSTRAINTS.md](../../CLAUDE-PHASE2-CONSTRAINTS.md) Constraint #10/#11
