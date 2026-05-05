# Runbook: throttle_events-Tabelle purgen

## Wann ausfuehren

Die `throttle_events`-Tabelle speichert jeden geblockt LLM-Call. Bei normalem Betrieb (~100 Blocks/Tag) waechst sie auf ca. 3.000 Rows/Monat. Ab **10.000 Rows** oder wenn Queries auf `throttle_events` langsam werden (> 100ms), diesen Runbook ausfuehren.

Pruefung ob noetig:
```sql
SELECT COUNT(*) FROM throttle_events;
```

---

## Schritte

### 1. Aktuelle Row-Anzahl pruefen

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec postgres \
  psql -U cap -d cap_v2 -c "SELECT COUNT(*) FROM throttle_events;"
```

### 2. Rows aelter als 90 Tage loeschen

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec postgres \
  psql -U cap -d cap_v2 -c \
  "DELETE FROM throttle_events WHERE created_at < NOW() - INTERVAL '90 days';"
```

Erwartete Ausgabe: `DELETE <N>` — Anzahl entfernter Rows.

### 3. Optional: VACUUM ANALYZE

Bei grossen Loeschmengen (> 5.000 Rows) empfehlenswert:

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec postgres \
  psql -U cap -d cap_v2 -c "VACUUM ANALYZE throttle_events;"
```

---

## Verify

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec postgres \
  psql -U cap -d cap_v2 -c "SELECT COUNT(*) FROM throttle_events;"
```

Erwartet: < 10.000 Rows.

---

## Automatisierung (optional)

Dieser Purge kann als Celery-Beat-Task eingerichtet werden (z.B. monatlich). Bis dahin: manuell bei Bedarf.

Alternativ Cron auf dem Host:

```bash
# crontab -e
0 3 1 * * docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec -T postgres \
  psql -U cap -d cap_v2 -c "DELETE FROM throttle_events WHERE created_at < NOW() - INTERVAL '90 days';" \
  >> /var/log/cap-v2-throttle-purge.log 2>&1
```

---

## Eskalation

Wenn nach dem Purge Queries immer noch langsam sind: Index auf `created_at` pruefen.

```sql
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'throttle_events';
```

Falls kein Index auf `created_at`:

```sql
CREATE INDEX CONCURRENTLY idx_throttle_events_created_at ON throttle_events (created_at);
```
