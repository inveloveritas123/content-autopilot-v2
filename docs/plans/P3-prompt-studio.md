# P3 — Prompt-Studio (Spec)

**Status:** Konzept, nicht implementiert
**Ziel:** Oberfläche im bestehenden Dashboard, mit der content-truth-Dateien
(Prompts, Rules, Schemas) durchgesehen, bearbeitet, validiert und gespeichert
werden können — „direkt austauschbar", ohne Container-Rebuild.
**Löst:** Issue #23 / die in `docs/DEPLOY.md` („Achtung: bekannte Spannung")
dokumentierte `:ro`-Mount-Blockade: `./content-truth` ist als read-only
Bind-Mount in die Container gehängt (`docker-compose.v2.yml`, Zeilen 60, 105,
147). Runtime-Writes schlagen mit `StorageError` fehl — gewollt, denn
content-truth ist git-verwaltet. Schreibzugriff erfolgt deshalb über ein
**beschreibbares Overlay** unter `/app/data/prompts-custom` (Host:
`./data/prompts-custom`, via `.gitignore` Zeile 7 `data/` bereits gitignored).

Leserichtung überall: **Overlay-first, Fallback auf Base (content-truth)**.
Der `:ro`-Mount bleibt unangetastet; `git pull` bleibt konfliktfrei.

---

## 1. Overlay-Storage-Design

### 1.1 Neue Datei: `backend/services/layered_storage.py`

Ein `LayeredStorageAdapter`, der zwei Adapter komponiert und das bestehende
`BrandVoiceStorageAdapter`-Protocol (`backend/services/brand_voice_storage.py`,
Zeile 55: `list/read/write/exists/stat`) vollständig erfüllt — dadurch ist er
ein Drop-in für `PromptLoader` und alle anderen Konsumenten.

```python
from typing import Literal, Optional
from services.brand_voice_storage import (
    BrandVoiceStorageAdapter, StorageEntry, StorageStat, StorageError,
)

Source = Literal["base", "overlay"]


class LayeredStorageAdapter:
    """Komponiert ein beschreibbares Overlay ueber einer read-only Base.

    Lese-Semantik: Overlay-first, Fallback Base.
    Schreib-Semantik: ausschliesslich Overlay (Base ist :ro gemountet).
    """

    def __init__(
        self,
        overlay: BrandVoiceStorageAdapter,   # LocalFsStorageAdapter(base_dir=overlay_path)
        base: BrandVoiceStorageAdapter,      # LocalFsStorageAdapter(base_dir=content_truth_path)
    ) -> None: ...

    # --- BrandVoiceStorageAdapter-Protocol ---
    def read(self, path: str) -> bytes: ...        # overlay.exists(path) → overlay.read, sonst base.read
    def stat(self, path: str) -> StorageStat: ...  # overlay-first, sonst base (wichtig fuer PromptLoader-mtime-Check)
    def exists(self, path: str) -> bool: ...       # overlay.exists OR base.exists
    def write(self, path: str, content: bytes) -> None: ...  # IMMER overlay.write (legt Verzeichnisse an, atomar via os.replace)
    def list(self, path: str) -> list[StorageEntry]: ...     # Union base+overlay, Namens-dedupliziert, sortiert

    # --- Zusatz-API (nur vom Prompt-Studio genutzt) ---
    def source_of(self, path: str) -> Optional[Source]: ...
        # "overlay" wenn Overlay-Datei existiert, "base" wenn nur Base, None wenn nirgends
    def list_with_source(self, path: str) -> list[tuple[StorageEntry, Source, StorageStat]]: ...
        # gemergte Liste; Source = "overlay" wenn Datei im Overlay liegt (shadowed Base), sonst "base";
        # StorageStat des effektiv gelesenen Layers
    def stat_base(self, path: str) -> Optional[StorageStat]: ...
        # Base-Metadaten auch wenn Overlay existiert (fuer "Base neuer als Overlay"-Hinweis)
    def delete_overlay(self, path: str) -> bool: ...
        # loescht NUR die Overlay-Datei (os.unlink); True wenn geloescht, False wenn nicht vorhanden.
        # Base wird nie angefasst. → Revert-to-Base.
```

Wiederverwendung: Overlay und Base sind beides `LocalFsStorageAdapter`
(`backend/services/local_fs_storage.py`) — Traversal-/Symlink-Schutz
(`_resolve`, Zeilen 25–46) und atomares Schreiben (Zeilen 61–81) gelten damit
automatisch in beiden Layern. `delete_overlay` nutzt overlay-intern dieselbe
`_resolve`-Prüfung (kleine Ergänzung: `LocalFsStorageAdapter.delete(path)`
als neue Methode, oder `delete_overlay` resolved über `overlay._resolve` —
Empfehlung: **`delete(path)` dem `LocalFsStorageAdapter` hinzufügen**, das ist
sauber testbar).

### 1.2 Config (`backend/config.py`)

```python
# Beschreibbares Overlay fuer Prompt-Studio-Edits (gitignored, ./data-Mount)
content_truth_overlay_path: str = "/app/data/prompts-custom"
```

Pydantic-Settings mappt das automatisch auf ENV `CONTENT_TRUTH_OVERLAY_PATH`.

### 1.3 Factory-Änderung (`backend/services/brand_voice_storage.py`)

`get_default_storage_adapter()` (Zeile 331) liefert im `localfs`-Fall künftig
den Layered-Adapter:

```python
def get_default_storage_adapter() -> BrandVoiceStorageAdapter:
    backend = getattr(settings, "prompt_storage_backend", "localfs")
    if backend == "localfs":
        from services.local_fs_storage import LocalFsStorageAdapter
        from services.layered_storage import LayeredStorageAdapter
        base_dir = getattr(settings, "content_truth_base_path", "/app/content-truth")
        overlay_dir = getattr(settings, "content_truth_overlay_path", "/app/data/prompts-custom")
        return LayeredStorageAdapter(
            overlay=LocalFsStorageAdapter(base_dir=overlay_dir),
            base=LocalFsStorageAdapter(base_dir=base_dir),
        )
    return get_default_nc_adapter()
```

Damit lesen **alle** bestehenden Konsumenten (PromptLoader in den
p01/p12/p12b/p12c/voice_drift-Tasks, `scripts/prompt_health.py` bleibt
unverändert auf Base) Overlay-first — genau die „direkt austauschbar"-Semantik.
Das Overlay-Verzeichnis muss beim Start nicht existieren: `exists()` liefert
dann `False`, `list()` fängt den `StorageError` des Overlay-Layers ab und
liefert nur Base; `write()` legt Verzeichnisse per `os.makedirs` an.

### 1.4 Zusammenspiel mit dem PromptLoader (Cache!)

`PromptLoader.load()` (`backend/services/prompt_loader.py`, Zeilen 215–250)
macht bei jedem Cache-Hit innerhalb der TTL einen `stat()`-Check gegen `mtime`.
Da `LayeredStorageAdapter.stat()` overlay-first ist, gilt nach einem Save:

- **Gleicher Prozess:** der nächste `load()` sieht die neuere Overlay-mtime
  und lädt frisch — selbst innerhalb der TTL. Zusätzlich ruft der
  Save-Endpunkt defensiv `loader.invalidate(prompt_key)` auf der
  Loader-Instanz des API-Prozesses auf (falls der Pfad einem
  `PROMPT_PATHS`-Key entspricht), damit auch ein evtl. künftiger
  Singleton-Loader sofort konsistent ist.
- **Celery-Worker (anderer Prozess):** die Tasks erzeugen pro Ausführung einen
  frischen Loader via `get_default_prompt_loader()` (z. B.
  `backend/tasks/p12_task.py:330`) — kein Stale-Cache-Problem, **sofern der
  Worker das Overlay sehen kann** → 1.5.
- **Revert:** nach `delete_overlay` zeigt `stat()` wieder die Base-mtime, die
  ÄLTER als `loaded_at` sein kann → der mtime-Check würde den Cache-Eintrag
  fälschlich für aktuell halten. Deshalb ruft auch der Revert-Endpunkt
  explizit `loader.invalidate(prompt_key)` bzw. `invalidate_all()` auf.

### 1.5 Compose-Änderungen (`docker-compose.v2.yml`)

Ist-Zustand der `./data`-Mounts:

| Service | `./content-truth:/app/content-truth:ro` | `./data:/app/data` |
|---|---|---|
| backend-v2 | ja (Z. 60) | **ja** (Z. 59) |
| celery-worker-v2 | ja (Z. 105) | **NEIN — ergänzen** |
| celery-beat-v2 | ja (Z. 147) | **NEIN — ergänzen** |

Änderungen:

1. `celery-worker-v2` und `celery-beat-v2`: `- ./data:/app/data` in `volumes`
   ergänzen. Ohne das würden die Worker (die die Prompts tatsächlich
   konsumieren!) Overlay-Edits nie sehen — der Hauptzweck wäre verfehlt.
2. In allen drei Services ENV ergänzen (Default reicht, aber explizit ist
   konsistent zum bestehenden Stil):
   `CONTENT_TRUTH_OVERLAY_PATH: ${CONTENT_TRUTH_OVERLAY_PATH:-/app/data/prompts-custom}`
3. Hinweis: `read_only: true` der Container ist kein Problem — Bind-Mounts
   bleiben beschreibbar, nur das Root-FS ist ro.
4. `docs/DEPLOY.md`-Abschnitt „content-truth" um das Overlay ergänzen
   (Spannung ist dort bereits dokumentiert und wird hiermit aufgelöst).

---

## 2. API-Vertrag

Neue Datei: `backend/api/prompt_studio.py`. Muster: `backend/api/brand_voice.py`
(APIRouter, pydantic-Request-Modelle, `HTTPException` mit `detail`).
**Auth:** wie alle bestehenden Endpunkte via `Depends(get_tenant)` aus
`backend/dependencies.py` (X-API-Key-Header, 401 bei ungültig, 503 bei
disabled Tenant). Kein eigener Admin-Mechanismus — es gibt im Projekt keinen;
Prompt-Studio ist damit für jeden gültigen Tenant-Key erreichbar (bewusste
Entscheidung, Single-Operator-Setup; siehe Risiken 6.7).

### 2.0 Sicherheit: Pfad-Whitelist

Doppelte Verteidigung:

```python
import re
_ALLOWED_PATH = re.compile(r"^(prompts|rules|schemas)/[A-Za-z0-9._\-]+\.(md|json)$")

def _check_path(file_path: str) -> str:
    if not _ALLOWED_PATH.fullmatch(file_path) or ".." in file_path:
        raise HTTPException(status_code=400, detail="Pfad nicht erlaubt")
    return file_path
```

- Nur genau eine Verzeichnisebene unter `prompts/`, `rules/`, `schemas/`;
  Dateiname-Charset ohne `/`, ohne `..`; Endung `.md` oder `.json`.
- Zweite Schicht: `LocalFsStorageAdapter._resolve` blockt Traversal/Symlinks
  ohnehin mit `StorageError`.
- **Kein Anlegen neuer Dateien in v1:** Save ist nur erlaubt, wenn die Datei
  in der Base existiert (`adapter.stat_base(path)` bzw. `base.exists`) —
  sonst 404. Das hält die Menge editierbarer Dateien exakt auf den
  git-verwalteten Bestand (14 Prompts, 2 Rules, 4 Schemas).
- Größenlimit: `len(content) > 512_000` → 413.

### 2.1 Pydantic-Shapes

```python
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel

Kind = Literal["prompt", "rule", "schema"]
Source = Literal["base", "overlay"]

class PromptHealth(BaseModel):
    status: Literal["ok", "weird"]
    system_chars: int
    user_chars: int
    fences_balanced: bool
    issues: list[str]            # z.B. ["SYSTEM_PROMPT_LEER", "OUTER_FENCE_VERBLIEBEN"]

class PromptFileInfo(BaseModel):
    path: str                    # "prompts/P12-post-generierung.md"
    name: str                    # "P12-post-generierung.md"
    kind: Kind                   # aus Top-Level-Verzeichnis abgeleitet
    prompt_key: Optional[str]    # Reverse-Lookup in PROMPT_PATHS ("P12"), None fuer Schemas
    source: Source               # effektiver Lese-Layer
    has_overlay: bool
    size: int
    mtime: datetime              # des effektiven Layers
    base_mtime: Optional[datetime]   # immer Base-mtime (fuer "Base neuer als Overlay"-Warnung)

class PromptFileListResponse(BaseModel):
    files: list[PromptFileInfo]
    overlay_path: str            # informativ: settings.content_truth_overlay_path

class PromptFileContentResponse(BaseModel):
    path: str
    kind: Kind
    prompt_key: Optional[str]
    source: Source
    has_overlay: bool
    content: str                 # raw UTF-8
    sha256: str                  # hex, fuer optimistisches Locking
    mtime: datetime
    base_mtime: Optional[datetime]
    system_prompt: Optional[str] # via _extract_section(content, "System-Prompt"); None bei .json
    user_prompt: Optional[str]   # via _extract_section(content, "User-Prompt"); None bei .json
    health: Optional[PromptHealth]   # nur fuer .md; None bei Schemas

class ValidateRequest(BaseModel):
    content: str

class ValidateResponse(BaseModel):
    valid: bool
    kind: Kind
    health: Optional[PromptHealth]   # .md: prompt_health-Checks
    schema_errors: list[str]         # .json: Fehler aus json.loads + Draft202012Validator.check_schema

class SaveRequest(BaseModel):
    content: str
    base_sha256: Optional[str] = None  # sha256 des Stands, den der Client geladen hat

class SaveResponse(BaseModel):
    path: str
    source: Literal["overlay"]
    sha256: str
    mtime: datetime
    validation: ValidateResponse     # Save validiert immer mit

class RevertResponse(BaseModel):
    path: str
    reverted: bool                   # False wenn kein Overlay existierte (idempotent, trotzdem 200)
    source: Literal["base"]
```

### 2.2 Endpunkte

Router: `router = APIRouter(prefix="/prompt-studio")`, eingehängt unter
`/api` → effektive Pfade:

| Methode | Pfad | Request | Response | Fehler |
|---|---|---|---|---|
| GET | `/api/prompt-studio/files` | – | `PromptFileListResponse` | 401 |
| GET | `/api/prompt-studio/files/{file_path:path}` | – | `PromptFileContentResponse` | 400 (Whitelist), 404 (nicht vorhanden), 401 |
| POST | `/api/prompt-studio/files/{file_path:path}/validate` | `ValidateRequest` | `ValidateResponse` (immer 200, auch bei `valid=false`) | 400, 401, 413 |
| PUT | `/api/prompt-studio/files/{file_path:path}` | `SaveRequest` | `SaveResponse` | 400, 401, 404 (nicht in Base), 409 (sha-Konflikt), 413, 422 (Schema-Datei mit invalidem JSON) |
| DELETE | `/api/prompt-studio/files/{file_path:path}/overlay` | – | `RevertResponse` | 400, 401 |

`{file_path:path}` (FastAPI-Path-Converter) erlaubt den Slash in
`prompts/P12-post-generierung.md`.

**GET /files** — Quelle: `LayeredStorageAdapter.list_with_source()` über die
drei Whitelist-Verzeichnisse `prompts/`, `rules/`, `schemas/`; nur Dateien,
die `_ALLOWED_PATH` matchen. `prompt_key` per Reverse-Map aus `PROMPT_PATHS`
(`backend/services/prompt_loader.py:36`). Overlay-Dateien ohne Base-Pendant
(sollte es nicht geben, da Save Base-Existenz fordert) werden mit
`source="overlay", base_mtime=None` trotzdem gelistet — Robustheit gegen
manuell abgelegte Dateien.

**GET /files/{path}** — `adapter.read(path)` (overlay-first), `sha256` über
die Bytes; für `.md` zusätzlich `_extract_section(content, "System-Prompt")`
/ `"User-Prompt"` (direkt aus `services.prompt_loader` importieren) und der
Health-Check (siehe 2.3).

**POST /validate** — validiert den **mitgeschickten** Content (nicht den
gespeicherten), damit die UI vor dem Save prüfen kann:
- `kind == "schema"` (`schemas/*.json`): `json.loads` → bei Fehler
  `valid=false`, `schema_errors=[...]`; dann
  `jsonschema.Draft202012Validator.check_schema(parsed)` (jsonschema>=4.0 ist
  bereits in `backend/requirements.txt:22`) → `SchemaError` nach
  `schema_errors`. Validierung gegen das JSON-Schema-Meta-Schema.
- `kind in ("prompt", "rule")` (`.md`): Prompt-Health-Checks (2.3);
  `valid = (status == "ok")`. Für `rules/*.md` und Prompts ohne erwartete
  Sektionen gelten die Ausnahmelisten aus `prompt_health.py`
  (`_NO_SYSTEM_EXPECTED`, `_EXPECTS_USER_PROMPT`).

**PUT /files/{path}** — Ablauf:
1. Whitelist + Größenlimit + Base-Existenz prüfen.
2. Optimistisches Locking: wenn `base_sha256` gesetzt und ≠ sha256 des
   aktuell effektiv gelesenen Stands → **409** `{"detail": "Konflikt: Datei wurde zwischenzeitlich geaendert"}`.
3. Validieren wie POST /validate. Schema-Dateien mit invalidem JSON /
   Meta-Schema-Fehler → **422** (harter Block; ein kaputtes Schema würde die
   Pipeline brechen). Prompt-`.md` mit `status="weird"` → **speichern
   erlaubt** (Warnung in Response; Operator darf bewusst experimentieren).
4. `adapter.write(path, content.encode("utf-8"))` → schreibt atomar ins
   Overlay.
5. Cache invalidieren: `get_default_prompt_loader()`-Instanz des
   API-Prozesses → `invalidate(prompt_key)` falls `prompt_key` bekannt
   (Worker-Prozesse brauchen das nicht, siehe 1.4).
6. **Audit-Log**: strukturierte Logzeile (bestehendes
   `logging_config`-JSON-Logging nutzt correlation/tenant-Kontext):
   `logger.info("prompt_studio: save", extra={"path": ..., "tenant_id": str(tenant.id), "sha_before": ..., "sha_after": ..., "size": ...})`.
   Bewusst kein neues DB-Modell in v1 (Freigabe-Schwelle „neue DB-Tabellen").

**DELETE /files/{path}/overlay** — `adapter.delete_overlay(path)`; danach
`invalidate(prompt_key)` bzw. `invalidate_all()` (wegen der
mtime-Rückwärts-Falle, siehe 1.4). Idempotent: 200 mit `reverted=false`,
wenn kein Overlay existierte.

### 2.3 Health-Check-Wiederverwendung (`prompt_health`)

`backend/scripts/prompt_health.py` enthält die Logik (`_fences_balanced`,
Issue-Codes `SYSTEM_PROMPT_LEER`, `USER_PROMPT_LEER`,
`OUTER_FENCE_VERBLIEBEN`, `INTERNE_FENCES_UNBALANCIERT`), ist aber ein
Standalone-Skript mit importlib-Hacks. **Refactoring:** die reinen Funktionen
in ein neues Modul `backend/services/prompt_health_core.py` extrahieren:

```python
def check_prompt_content(content: str, *, prompt_key: str | None = None) -> PromptHealthResult
# PromptHealthResult: status, system_chars, user_chars, fences_balanced, issues
```

`scripts/prompt_health.py` und `api/prompt_studio.py` konsumieren beide dieses
Modul (das Skript behält seine importlib-Ladung, lädt aber jetzt
`prompt_health_core.py` statt eigener Kopien). Keine Logik-Duplikation.

---

## 3. Router-Registrierung

`backend/main.py`, im bestehenden Block (Import bei den anderen, Registrierung
nach `eval_router`, Zeile 234):

```python
from api.prompt_studio import router as prompt_studio_router
app.include_router(prompt_studio_router, prefix="/api", tags=["PromptStudio"])
```

Kein weiterer Verdrahtungsaufwand: CORS erlaubt bereits PUT/DELETE +
X-API-Key (main.py Z. 124–131), CSRF-Middleware exempted
X-API-Key-Requests, nginx proxied `/api/` pauschal.

---

## 4. Frontend

Bewusst schlicht: **eine** Seite, Liste links, Textarea rechts. Muster:
`frontend/src/components/Memory.jsx` / `CompanyProfile.jsx` (einfache
Fetch-on-Mount-Seiten mit Card/Button/Badge), nicht das komplexe
`BrandVoice.jsx`.

### 4.1 Route + Navigation

- `frontend/src/App.jsx`: `import PromptStudio from './components/PromptStudio'`
  und `<Route path="/settings/prompt-studio" element={<PromptStudio />} />`
  (bei den anderen `/settings/*`-Routen).
- `frontend/src/components/Layout.jsx`: Nav-Item in der Settings-Gruppe:
  `{ to: '/settings/prompt-studio', label: 'Prompt-Studio', icon: FileCode }`
  (lucide-react `FileCode`).

### 4.2 API-Client (`frontend/src/api.js`)

Bestehender `request()`-Wrapper (X-API-Key aus localStorage). Neue Sektion:

```js
// Prompt-Studio
export const getPromptFiles = () => request('/prompt-studio/files')
export const getPromptFile = (path) => request(`/prompt-studio/files/${path}`)
export const validatePromptFile = (path, content) =>
  request(`/prompt-studio/files/${path}/validate`, { method: 'POST', body: { content } })
export const savePromptFile = (path, content, baseSha) =>
  request(`/prompt-studio/files/${path}`, { method: 'PUT', body: { content, base_sha256: baseSha } })
export const revertPromptFile = (path) =>
  request(`/prompt-studio/files/${path}/overlay`, { method: 'DELETE' })
```

(`path` enthält genau einen Slash und nur whitelisted Zeichen — kein
encodeURIComponent nötig; URL bleibt `/api/prompt-studio/files/prompts/P12-….md`.)

### 4.3 Komponente `frontend/src/components/PromptStudio.jsx`

Ein File, interne Unterkomponenten, UI-Bausteine aus `src/components/ui/`
(Card, Button, Badge, Toast via `useToast`):

- **FileList** (linke Spalte): Gruppen „Prompts / Rules / Schemas"
  (aus `kind`), pro Eintrag Name, `prompt_key`, **Quelle-Badge**
  (`Badge` amber „overlay" / grau „base"), Warn-Icon wenn
  `has_overlay && base_mtime > mtime`-Logik greift („Base neuer als Overlay").
- **Editor** (rechte Spalte): schlichte `<textarea>` (monospace,
  `font-mono text-sm`, volle Höhe), kein Code-Editor-Paket. Dirty-State
  (Inhalt ≠ geladener Stand) → Save-Button aktiv, Navigations-Hinweis.
- **Buttons**: „Validieren" (POST validate → Ergebnis-Panel: Health-Status,
  issues-Liste bzw. schema_errors), „Speichern" (PUT mit `base_sha256` des
  geladenen Stands; bei 409 Toast „Konflikt — neu laden"), „Auf Base
  zurücksetzen" (DELETE overlay, nur sichtbar wenn `has_overlay`; mit
  `window.confirm`).
- **Read-only-Vorschau** (collapsed, optional v1): extrahierter
  `system_prompt` / `user_prompt` aus der GET-Response, damit man sieht, was
  der Loader tatsächlich extrahiert.
- Toast-Feedback für Save/Revert/Fehler; kein Optimismus-State, nach
  Save/Revert wird die Datei + Liste neu geladen.

Nicht in v1: Diff-Ansicht Overlay↔Base, Syntax-Highlighting, neue Dateien
anlegen, Verlauf/Versionen.

---

## 5. Test-Strategie

### 5.1 Backend

**`backend/tests/test_layered_storage.py`** — reine Unit-Tests mit
`tmp_path` (zwei temp-Verzeichnisse base/overlay):
- read/stat/exists: overlay-first, Fallback Base, beides fehlt → StorageError.
- write landet nur im Overlay; Base-Datei bleibt byte-identisch.
- list: Merge + Dedupe; `list_with_source` markiert shadowed Dateien als
  overlay; fehlendes Overlay-Verzeichnis → nur Base, kein Fehler.
- delete_overlay: löscht nur Overlay; idempotent; Traversal (`../x`) blockt.
- PromptLoader-Integration: Loader über LayeredAdapter, Save ins Overlay →
  nächster `load()` liefert neuen Inhalt trotz TTL (mtime-Check); Revert +
  `invalidate` → wieder Base-Inhalt.

**`backend/tests/test_prompt_studio_api.py`** — FastAPI `TestClient` nach dem
Muster von `test_telegram_webhook.py` (Mini-App, nur dieser Router — kein
main.py-Lifespan/DB nötig):

```python
_app = FastAPI()
_app.include_router(prompt_studio_router, prefix="/api")
_app.dependency_overrides[get_tenant] = lambda: _FakeTenant()
client = TestClient(_app, raise_server_exceptions=False)
```

Fixture baut temporäres Base-Verzeichnis (Kopie von 2–3 echten
content-truth-Dateien + ein Mini-Schema) und leeres Overlay; `monkeypatch`
auf `settings.content_truth_base_path` / `content_truth_overlay_path` (bzw.
auf die Adapter-Factory des Routers — Empfehlung: Router holt den Adapter
über eine kleine `get_studio_adapter()`-Funktion, die im Test überschrieben
wird). Fälle:
- list: Quellen-Markierung base/overlay, base_mtime gesetzt.
- get: raw + system/user-Extrakt + health; 404 unbekannt; 400 Traversal
  (`prompts/../config.py`, `etc/passwd`, `prompts/x.txt`).
- validate: gesundes .md → ok; .md ohne System-Prompt → weird mit
  `SYSTEM_PROMPT_LEER`; Schema mit kaputtem JSON / `"type": 123` →
  schema_errors.
- save: schreibt Overlay (Datei physisch prüfen), Response-Validation,
  409 bei falschem base_sha256, 422 bei kaputtem Schema-JSON, 404 bei Datei
  ohne Base-Pendant, 413 bei Übergröße.
- revert: Overlay weg, get liefert wieder Base, `reverted=false` beim
  zweiten Mal.
- Auth: ohne Override/mit echtem `get_tenant` → 401 ohne X-API-Key
  (ein Smoke-Case genügt).

### 5.2 Frontend (minimal)

`frontend/src/components/__tests__/PromptStudio.helpers.test.jsx` (vitest,
bestehendes Muster `*.helpers.test.jsx`): nur die pure Helper —
Gruppierung nach `kind`, Badge-Label/Farbe aus `source`,
„Base neuer als Overlay"-Prädikat, Dirty-Detection. Kein DOM-/Fetch-Test,
keine Playwright-Erweiterung in v1.

---

## 6. Risiken & Gegenmaßnahmen

1. **Overlay vs. `git pull` (Shadowing):** Sobald ein Overlay existiert, sind
   Base-Updates (git pull / Deploy) für die Pipeline unsichtbar — das Overlay
   gewinnt dauerhaft. Gegenmaßnahmen: `base_mtime` in List/Get + UI-Warnung
   „Base ist neuer als dein Overlay", prominenter Revert-Button. Bewusst
   akzeptiert: kein Auto-Merge. Operativer Hinweis in DEPLOY.md: nach
   Prompt-Releases Overlays prüfen/reverten.
2. **Cache-Staleness:** mtime-basierter stat-Check des PromptLoaders deckt
   Save ab; **Revert ist die Falle** (Base-mtime älter als Cache-`loaded_at`)
   → explizites `invalidate` im Revert-Endpunkt ist Pflicht, nicht Kür.
   Celery-Worker sind durch Loader-pro-Task safe — aber **nur mit dem
   `./data`-Mount** (1.5); fehlt er, liest der Worker stumm weiter Base →
   Deploy-Check: `docker compose exec celery-worker-v2 ls /app/data`.
3. **Gleichzeitige Edits:** zwei Browser-Tabs/Nutzer → Lost Update. Gelöst
   pragmatisch via optimistischem Locking (`base_sha256` → 409). Kein
   Locking-Server, kein Merge — bei 409 lädt der Client neu. Atomarität auf
   Dateiebene garantiert `os.replace` im LocalFsStorageAdapter (kein
   Halb-Geschriebenes lesbar).
4. **Schema-Validierung der Schema-Dateien selbst:**
   `Draft202012Validator.check_schema` prüft nur Meta-Schema-Konformität,
   nicht Semantik (ein gültiges, aber inhaltlich falsches Schema lässt
   P01/P03/P04-Outputs durchfallen oder zu lasch durch). Mitigation: harter
   422-Block nur für syntaktische Fehler, Rest in Operator-Verantwortung;
   Revert als Escape-Hatch; Schemas sind klein und im Repo reviewbar.
5. **`read_only: true`-Container:** kein Risiko fürs Overlay (Bind-Mount
   bleibt beschreibbar), aber Tests/CI ohne Mount müssen den Overlay-Pfad
   überschreiben können → Config-Feld statt Hardcode.
6. **Prompt-Injection/„Validität" von Prompts:** ein gespeicherter Prompt geht
   ungefiltert in LLM-Calls. Kein HTML-Escaping (würde Prompts zerstören);
   Schutz ist die Auth-Schicht + Audit-Log + Größenlimit. UI rendert Content
   nur in `<textarea>`/`<pre>` (kein dangerouslySetInnerHTML).
7. **Auth-Breite:** jeder gültige Tenant-Key darf editieren, Prompts sind
   global (nicht tenant-scoped). Im aktuellen Single-/Zwei-Tenant-Betrieb
   akzeptiert; falls Multi-Tenant ernst wird: Admin-Flag am Tenant
   nachrüsten (out of scope v1, würde DB-Änderung bedeuten →
   `freigabe-robert`).
8. **Backup:** `data/` ist gitignored — Overlays sind nicht versioniert.
   Audit-Log enthält sha-Hashes, aber nicht den Inhalt. Akzeptiert für v1;
   wer einen Stand behalten will, committet ihn nach content-truth.

---

## 7. Implementierungs-Dateilisten (parallelisierbar)

**Backend-Agent (disjunkt):**
- NEU `backend/services/layered_storage.py`
- NEU `backend/services/prompt_health_core.py` (Extraktion aus Skript)
- NEU `backend/api/prompt_studio.py`
- NEU `backend/tests/test_layered_storage.py`
- NEU `backend/tests/test_prompt_studio_api.py`
- EDIT `backend/config.py` (`content_truth_overlay_path`)
- EDIT `backend/services/brand_voice_storage.py` (`get_default_storage_adapter`)
- EDIT `backend/services/local_fs_storage.py` (`delete()`-Methode)
- EDIT `backend/scripts/prompt_health.py` (auf `prompt_health_core` umstellen)
- EDIT `backend/main.py` (Router-Registrierung)
- EDIT `docker-compose.v2.yml` (`./data`-Mount worker/beat, ENV)
- EDIT `docs/DEPLOY.md` (Overlay-Abschnitt)

**Frontend-Agent (disjunkt):**
- NEU `frontend/src/components/PromptStudio.jsx`
- NEU `frontend/src/components/__tests__/PromptStudio.helpers.test.jsx`
- EDIT `frontend/src/api.js` (5 Funktionen)
- EDIT `frontend/src/App.jsx` (Route)
- EDIT `frontend/src/components/Layout.jsx` (Nav-Item)

Einzige Kopplung: der API-Vertrag in Abschnitt 2 — beide Agenten
implementieren strikt gegen diese Spec.
