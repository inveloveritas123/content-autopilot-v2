# Runbook: Embedding-Drift-Monitor manuell ausfuehren

## Wann ausfuehren

Der Drift-Monitor laeuft automatisch jeden Montag um 03:00 Uhr (Celery Beat). Diesen Runbook nutzen wenn:

- Robert sofort Drift-Daten sehen will (nicht bis Montag warten)
- Ein Embedding-Modell-Wechsel vorbereitet wird und Recall@20-Baseline benoetigt wird
- Ungewoehnlich viele Throttle-Events mit `scope='embedding_drift'` auftauchen und manuell nachgeprueft werden soll

---

## Schritte

### 1. Task manuell triggern

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec backend-v2 \
  celery -A tasks call tasks.drift_monitor_task.run_embedding_drift_monitor
```

Erwartete Ausgabe: eine Task-ID (UUID). Der Task laeuft asynchron im Celery-Worker.

### 2. Task-Status verfolgen (optional)

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml logs -f celery-worker \
  | grep -i "drift"
```

Typische Laufzeit: 30-120 Sekunden je nach Datenmenge.

### 3. Ergebnis pruefen

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec postgres \
  psql -U cap -d cap_v2 -c \
  "SELECT scope, created_at, details FROM throttle_events \
   WHERE scope = 'embedding_drift' \
   ORDER BY created_at DESC LIMIT 5;"
```

Erwartet: maximal 1 neuer Eintrag pro Tenant pro Modell.

---

## Ergebnisse interpretieren

| Feld `details` | Bedeutung |
|----------------|-----------|
| `recall_at_20 >= 0.8` | Kein Drift — Modell liefert gute Ergebnisse |
| `recall_at_20 < 0.8` | Drift erkannt — Pruefung ob Canary-Modell besser abschneidet |
| `canary_recall > prod_recall` | Canary bereit zur Promotion — Robert informieren |

---

## Verify

```bash
docker compose -f /opt/content-autopilot-v2/docker-compose.yml exec postgres \
  psql -U cap -d cap_v2 -c \
  "SELECT COUNT(*) FROM throttle_events WHERE scope = 'embedding_drift' \
   AND created_at > NOW() - INTERVAL '10 minutes';"
```

Erwartet: >= 1 (neuer Eintrag vom manuellen Run).

---

## Eskalation

Wenn `recall_at_20 < 0.6` (starker Drift):

1. Canary-Modell pruefen: ist ein neues Modell als Canary konfiguriert?
2. Falls nicht: `embedding_canary`-Konfiguration in der Admin-UI setzen
3. Robert und ggf. Cowork informieren vor Promotion
4. Siehe [ADR-0004](../adr/ADR-0004-embedding-versionierung-canary.md) fuer Canary-Rollout-Prozess
