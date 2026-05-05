# Runbook: YouTube-Cookies rotieren

## Wann ausfuehren

YouTube blockiert yt-dlp/youtube-transcript-api mit HTTP 403 ("Bot detected") wenn die Cookies abgelaufen oder gesperrt sind. Symptome:

- Activity-Fetcher loggt `403 Forbidden` fuer YouTube-Sources
- Source-Items werden nicht mehr aktualisiert (letzte `fetched_at` liegt > 2 Stunden zurueck obwohl neue Videos existieren)
- Test-Endpoint liefert Fehler (siehe Verify)

---

## Schritte

### 1. Neue cookies.txt exportieren

Im Google-Chrome/Chromium auf dem eigenen Rechner (eingeloggt als YouTube-Account):

1. Extension "Get cookies.txt LOCALLY" installieren (Chrome Web Store)
2. `youtube.com` oeffnen und eingeloggt sein
3. Extension anklicken → "Export" → Format: "Netscape HTTP Cookie File" → Speichern als `youtube_cookies.txt`

**Wichtig:** Der Account sollte aktiv und verifiziert sein. Wegwerf-Accounts werden schneller geblockt.

### 2. Cookie-Datei auf den Server uebertragen

```bash
# Von deinem lokalen Rechner aus
scp -P 10022 ~/Downloads/youtube_cookies.txt \
  meister@152.53.142.163:/opt/content-autopilot-v2/data/youtube_cookies.txt
```

### 3. Berechtigungen setzen

```bash
ssh -p 10022 meister@152.53.142.163 \
  "chown meister:meister /opt/content-autopilot-v2/data/youtube_cookies.txt && \
   chmod 600 /opt/content-autopilot-v2/data/youtube_cookies.txt"
```

### 4. Container-Restart (damit neue Datei gemounted wird)

```bash
ssh -p 10022 meister@152.53.142.163 \
  "cd /opt/content-autopilot-v2 && docker compose restart backend-v2 celery-worker"
```

---

## Verify

```bash
curl -H "X-API-Key: DEIN_API_KEY" \
  http://152.53.142.163:8601/api/activity/yt-test
```

Erwartet: `{"status": "ok", "message": "YouTube-Verbindung erfolgreich"}` oder aehnlich.

Falls der Endpoint nicht existiert, alternativ via Logs pruefen:

```bash
ssh -p 10022 meister@152.53.142.163 \
  "cd /opt/content-autopilot-v2 && docker compose logs --tail=50 celery-worker | grep -i youtube"
```

Erwartet: keine `403`-Fehler in den letzten 50 Zeilen nach einem manuellen Source-Fetch.

---

## Hinweise

- Cookie-Rotation alle 2-4 Wochen bei aktivem Betrieb empfohlen (YouTube sperrt Cookies nach Inaktivitaet oder Detect)
- Den Account der fuer die Cookies verwendet wird NICHT fuer andere Automatisierungen nutzen
- Cookies enthalten Session-Token — nicht in Git committen, nicht in Logs ausgeben

---

## Eskalation

Wenn Cookies sofort nach Rotation wieder geblockt werden:

1. Pruefe ob der Account eine CAPTCHA-Herausforderung hat (manuell auf youtube.com einloggen)
2. Warte 24h nach Account-Login bevor neue Cookies exportiert werden
3. Falls persistentes Blocking: anderen Google-Account verwenden
4. Als letzte Option: youtube-transcript-api ohne Cookies (nur fuer oeffenlich ungesperrte Videos mit Transkripten)
