# Content Autopilot v2 — Restore-Anleitung

Copy-paste Befehle fuer alle Restore-Szenarien.

---

## Voraussetzungen

```bash
# Pruefen ob pg_dump / pg_restore verfuegbar ist
which pg_dump pg_restore psql

# DB-Verbindung testen (Passwort aus .env -> DB_PASSWORD)
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2 -c "SELECT 1;"
```

---

## 1. Restore aus Pre-Migration-Snapshot

Wird automatisch von `scripts/safe_alembic.sh` vor jeder Migration angelegt.
Ablage: `/opt/backup/cap-v2-pre-migration-YYYYMMDD-HHMMSS.sql.gz`

```bash
# 1a. Snapshots auflisten
ls -lh /opt/backup/cap-v2-pre-migration-*.sql.gz

# 1b. Alle offenen DB-Verbindungen killen (Pflicht vor Drop)
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='content_autopilot_v2' AND pid <> pg_backend_pid();"

# 1c. Stack stoppen (keine neuen Verbindungen)
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml down

# 1d. Datenbank leeren und neu anlegen
PGPASSWORD="<PG_SUPERUSER_PASSWORD>" psql -h localhost -U postgres -c \
  "DROP DATABASE IF EXISTS content_autopilot_v2;"
PGPASSWORD="<PG_SUPERUSER_PASSWORD>" psql -h localhost -U postgres -c \
  "CREATE DATABASE content_autopilot_v2 OWNER autopilot;"

# 1e. Snapshot einspielen
SNAPSHOT="/opt/backup/cap-v2-pre-migration-YYYYMMDD-HHMMSS.sql.gz"
gunzip -c "$SNAPSHOT" | PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2

# 1f. Alembic-State pruefen (zeigt Revision die im Dump war)
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml up -d backend-v2
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 alembic current

# 1g. Stack vollstaendig starten
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml up -d
```

---

## 2. Restore aus Daily Backup

Ablage: `/opt/backup/cap-v2-daily-YYYYMMDD.sql.gz` (oder `.sql.gz.gpg`)

```bash
# 2a. Backup auswaehlen
ls -lh /opt/backup/cap-v2-daily-*.sql.gz 2>/dev/null
ls -lh /opt/backup/cap-v2-daily-*.sql.gz.gpg 2>/dev/null

# 2b. Verbindungen killen + Stack stoppen (wie 1b/1c oben)
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='content_autopilot_v2' AND pid <> pg_backend_pid();"
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml down

# 2c. Datenbank leeren
PGPASSWORD="<PG_SUPERUSER_PASSWORD>" psql -h localhost -U postgres -c \
  "DROP DATABASE IF EXISTS content_autopilot_v2;"
PGPASSWORD="<PG_SUPERUSER_PASSWORD>" psql -h localhost -U postgres -c \
  "CREATE DATABASE content_autopilot_v2 OWNER autopilot;"

# 2d. Backup einspielen (unverschluesselt)
BACKUP="/opt/backup/cap-v2-daily-YYYYMMDD.sql.gz"
gunzip -c "$BACKUP" | PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2

# 2e. Stack starten
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml up -d
```

---

## 3. GPG-verschluesseltes Backup entschluesseln

Wenn `BACKUP_GPG_PASSPHRASE` in `.env` gesetzt war, sind Daily Backups
als `.sql.gz.gpg` abgelegt.

```bash
# Variante A: entschluesseln + restore in einem Schritt
BACKUP="/opt/backup/cap-v2-daily-YYYYMMDD.sql.gz.gpg"
gpg --batch --yes --passphrase "<BACKUP_GPG_PASSPHRASE>" \
    --decrypt "$BACKUP" \
  | gunzip \
  | PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2

# Variante B: erst entschluesseln, dann restore
gpg --batch --yes --passphrase "<BACKUP_GPG_PASSPHRASE>" \
    --output /tmp/cap-v2-restore.sql.gz \
    --decrypt "$BACKUP"
gunzip -c /tmp/cap-v2-restore.sql.gz | \
  PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2
rm /tmp/cap-v2-restore.sql.gz
```

---

## 4. Migration-State manuell setzen (alembic stamp)

Verwenden wenn die DB den richtigen Stand hat, die alembic_version-Tabelle
aber nicht uebereinstimmt (z.B. nach manuellem Eingriff).

```bash
# Aktuelle Revision anzeigen
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 alembic current

# Alle Revisionen anzeigen
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 alembic history --verbose

# State auf bestimmte Revision setzen (KEIN Schema-Aenderung — nur Tabelleneintrag!)
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 \
  alembic stamp 025_name_der_migration

# State auf "head" setzen (neueste bekannte Revision markieren)
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 \
  alembic stamp head

# Danach: fehlende Migrationen anwenden
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 \
  alembic upgrade head
```

---

## 5. Troubleshooting

### Problem: "database is being accessed by other users"

```bash
# Alle Verbindungen zur DB anzeigen
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U postgres -c \
  "SELECT pid, usename, application_name, state FROM pg_stat_activity WHERE datname='content_autopilot_v2';"

# Alle Verbindungen ausser der eigenen killen
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='content_autopilot_v2' AND pid <> pg_backend_pid();"
```

### Problem: "role autopilot does not exist" nach Drop+Create

```bash
# User neu anlegen
PGPASSWORD="<PG_SUPERUSER_PASSWORD>" psql -h localhost -U postgres -c \
  "CREATE USER autopilot WITH PASSWORD '<DB_PASSWORD>';"
PGPASSWORD="<PG_SUPERUSER_PASSWORD>" psql -h localhost -U postgres -c \
  "GRANT ALL PRIVILEGES ON DATABASE content_autopilot_v2 TO autopilot;"
```

### Problem: "pg_restore: error: input file appears to be a text format dump"

Das Backup wurde mit plaintext `psql`-Format erstellt (via `gunzip | psql`).
Nicht mit `pg_restore` einspielen — `psql` verwenden:

```bash
gunzip -c backup.sql.gz | PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2
```

### Problem: Alembic meldet "Can't locate revision" nach Restore

```bash
# alembic_version Tabelle pruefen
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -U autopilot -d content_autopilot_v2 \
  -c "SELECT * FROM alembic_version;"

# Revision manuell korrigieren (siehe Abschnitt 4)
docker compose -f /opt/content-autopilot-v2/docker-compose.v2.yml exec -T backend-v2 \
  alembic stamp <korrekte_revision>
```

### Problem: pg_dump laeuft durch, Datei ist aber 0 Byte / sehr klein

```bash
# Direkt testen (Ausgabe auf stdout)
PGPASSWORD="<DB_PASSWORD>" pg_dump -h localhost -U autopilot content_autopilot_v2 | head -20

# Verbindungsparameter pruefen
PGPASSWORD="<DB_PASSWORD>" psql -h localhost -p 5432 -U autopilot -d content_autopilot_v2 -c "\dt"
```

---

## Hinweise

- Snapshots liegen in `/opt/backup/` — kein externes Backup-Target bisher konfiguriert.
- Pre-Migration-Snapshots werden 30 Tage aufbewahrt, Daily Backups ebenfalls.
- Bei produktivem Einsatz: zusaetzlich `rsync` oder S3-Upload einrichten.
- `BACKUP_GPG_PASSPHRASE` aus `.env` sicher aufbewahren — ohne Passphrase kein Restore!
