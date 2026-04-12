# Architektur-Entscheidung: Content Autopilot Workflow

> Stand: 12. April 2026 | Entscheidung: **Option C — MCP-First Hybrid**

---

## Das Problem

Wir brauchen einen Workflow der:
1. YouTube-Videos automatisch transkribiert und analysiert
2. Gezielte Fragen an den Unternehmer stellt
3. Aus dessen Antworten authentische LinkedIn-Posts erstellt
4. Skaliert auf mehrere Kunden
5. Kosteneffizient bleibt

---

## Drei Architektur-Optionen

### Option A: Full API Pipeline

```
┌──────────────────────────────────────────────────────┐
│                  FULL API PIPELINE                     │
│                                                        │
│  User ──→ Web-UI ──→ FastAPI ──→ LLM APIs ──→ DB     │
│                         ↑                              │
│                    Celery Worker                       │
│                    (alles automatisch)                  │
│                                                        │
│  ✗ Kein echter Dialog — nur Formular-Antworten        │
│  ✗ Jeder LLM-Call kostet API-Tokens                   │
│  ✗ Iteration = neue API-Calls = mehr Kosten           │
│  ✓ Komplett self-contained                            │
│  ✓ Kein Claude-Abo noetig                             │
└──────────────────────────────────────────────────────┘
```

**Kosten bei 40 Videos/Monat:** ~$12 API + Hosting
**Problem:** Der "Dialog" ist ein Webformular. Keine echte Konversation.

### Option B: Reines Cowork/CLI

```
┌──────────────────────────────────────────────────────┐
│              REINES COWORK / CLI                       │
│                                                        │
│  Unternehmer ──→ Claude Desktop/Cowork                │
│                     ↓                                  │
│              "Analysiere dieses Video"                 │
│              "Stell mir Fragen dazu"                   │
│              "Schreib einen Post daraus"               │
│                     ↓                                  │
│              Alles in der Konversation                  │
│                                                        │
│  ✓ Natuerlicher Dialog                                │
│  ✓ Im Abo enthalten (keine API-Kosten)               │
│  ✗ Kein Gedaechtnis zwischen Sessions                 │
│  ✗ Keine automatische Video-Erkennung                 │
│  ✗ Kein Dashboard / Uebersicht                        │
│  ✗ Skaliert schlecht auf mehrere Kunden               │
└──────────────────────────────────────────────────────┘
```

**Kosten:** $20/Monat Claude Pro Abo (das der Unternehmer eh hat)
**Problem:** Kein Langzeitgedaechtnis, keine Automatisierung.

### ★ Option C: MCP-First Hybrid (EMPFOHLEN)

```
┌─────────────────────────────────────────────────────────────────┐
│                  MCP-FIRST HYBRID ARCHITEKTUR                    │
│                                                                   │
│  ┌─────────────┐         ┌──────────────────────────────┐       │
│  │  BACKEND    │         │  CLAUDE DESKTOP / COWORK      │       │
│  │  (Server)   │         │  (beim Unternehmer)           │       │
│  │             │   MCP   │                                │       │
│  │  ┌────────┐ │◄───────►│  "Hey, 3 neue Videos wurden  │       │
│  │  │Celery  │ │         │   analysiert. Soll ich dir    │       │
│  │  │Beat    │ │         │   die Ideen zeigen?"          │       │
│  │  │        │ │         │                                │       │
│  │  │ Auto:  │ │         │  Unternehmer: "Ja, die erste  │       │
│  │  │ - YT   │ │         │   klingt gut. Frag mich dazu."│       │
│  │  │   Mon. │ │         │                                │       │
│  │  │ - Tran.│ │         │  Claude: "Wie hast du das in  │       │
│  │  │ - Anal.│ │         │   deinem Unternehmen erlebt?" │       │
│  │  │ - Ideen│ │         │                                │       │
│  │  └────────┘ │         │  Unternehmer: "Also bei uns..."│       │
│  │             │         │                                │       │
│  │  ┌────────┐ │         │  Claude: *generiert Post*      │       │
│  │  │  DB    │ │         │  "Hier sind 2 Varianten..."   │       │
│  │  │ (PG)   │ │         │                                │       │
│  │  └────────┘ │         │  → Push zu Nextcloud           │       │
│  │             │         │  → Status-Update in DB         │       │
│  │  ┌────────┐ │         └──────────────────────────────┘       │
│  │  │  NC    │ │                                                 │
│  │  │ Sync   │ │         ┌──────────────────────────────┐       │
│  │  └────────┘ │         │  WEB-DASHBOARD (React)        │       │
│  │             │◄───────►│  - Uebersicht aller Videos    │       │
│  └─────────────┘   API   │  - Ideen-Queue                │       │
│                          │  - Content-Kalender            │       │
│                          │  - Post-Freigabe               │       │
│                          └──────────────────────────────┘       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Was wo passiert:**

| Schritt | Wo | Warum dort | Kosten |
|---------|-----|------------|--------|
| YT-Monitoring | Backend (Celery Beat) | Automatisch, kein Mensch noetig | ~0 (RSS) |
| Transkription | Backend (yt-transcript-api) | Automatisch, kein LLM noetig | ~0 |
| Analyse | Backend (Gemini Flash) | Batch-Job, guenstig | ~$0.26/Mo |
| Ideen-Generierung | Backend (Gemini Flash) | Batch, vorbereitet fuer Dialog | ~$0.15/Mo |
| **Dialog mit Unternehmer** | **Cowork/Claude Desktop** | **Natuerliches Gespraech** | **Im Abo** |
| **Post-Generierung** | **Cowork/Claude Desktop** | **Iteration im Dialog** | **Im Abo** |
| **Brand-Voice-Learning** | **Cowork/Claude Desktop** | **Lernt aus jedem Gespraech** | **Im Abo** |
| Freigabe & Planung | Web-Dashboard | Uebersicht, Team-Zugriff | ~0 |
| NC-Sync | Backend | Automatisch | ~0 |

---

## Warum Option C gewinnt

### 1. Der Dialog ist ECHT

Option A: "Bitte beantworte diese 3 Fragen in einem Formular."
Option C: "Hey Robert, aus dem Video ueber Finanzplanung hab ich eine spannende Idee:
           Was wuerdest du Unternehmern raten, die gerade ihre erste Bilanz lesen?
           Erzaehl mal aus deiner Erfahrung."

Der Unternehmer redet mit Claude wie mit einem Kollegen. Claude kennt seinen Stil,
seine Branche, seine bisherigen Posts. Das ist kein Formular — das ist ein Arbeitsgespraech.

### 2. Iteration kostet nichts extra

Im API-Modus: "Post gefaellt mir nicht" → neuer API-Call → neue Kosten
Im Cowork-Modus: "Mach den Hook schaerfer" → sofort neue Version → im Abo

### 3. Brand Voice lernt natuerlich

Im API-Modus: Voice-Analyse als separater Service, extra Prompts, extra Kosten
Im Cowork-Modus: Claude hoert dem Unternehmer in jedem Gespraech zu und
                  lernt seine Sprache organisch.

### 4. Die teuren Teile sind im Abo

```
API-Kosten (Backend):              ~$0.50/Monat
  └─ Gemini Flash fuer Batch-Analyse
  └─ Transkription (kostenlos)
  └─ RSS-Monitoring (kostenlos)

Cowork/Claude Pro Abo:              $20/Monat
  └─ Dialog mit Unternehmer          ✓ enthalten
  └─ Post-Generierung (iterativ)     ✓ enthalten
  └─ Brand-Voice-Learning            ✓ enthalten
  └─ Review & Feinschliff            ✓ enthalten

TOTAL:                              ~$20.50/Monat
```

Zum Vergleich: Postiv kostet $99/Seat/Monat fuer weniger Funktionalitaet.

### 5. MCP macht alles verbindbar

```
Claude Desktop / Cowork
  ├── MCP: Content-Autopilot-API
  │    ├── get_pending_ideas()      → Welche Ideen warten?
  │    ├── get_idea_details(id)     → Idee + Kontext laden
  │    ├── save_answers(id, [...])  → Antworten speichern
  │    ├── save_post(id, text)      → Post in DB speichern
  │    └── update_status(id, s)     → Workflow-Status setzen
  │
  ├── MCP: Nextcloud
  │    ├── Fertige Posts hochladen
  │    ├── Redaktionsplan als Datei
  │    └── Brand-Voice-Profil lesen/schreiben
  │
  └── MCP: Gitea (optional)
       └── Aenderungen versionieren
```

---

## Skalierung auf mehrere Kunden

```
Kunde A (Handwerker):  Claude Pro → MCP → Backend (Tenant A)
Kunde B (Berater):     Claude Pro → MCP → Backend (Tenant B)
Kunde C (Agentur):     Claude Pro → MCP → Backend (Tenant C)
                                            │
                                     ┌──────┴──────┐
                                     │   1 Server   │
                                     │   1 DB       │
                                     │   Multi-     │
                                     │   Tenant     │
                                     └─────────────┘
```

Jeder Kunde:
- Zahlt sein eigenes Claude-Abo ($20/Mo)
- Hat seinen eigenen MCP-Zugang (API-Key = Tenant-Key)
- Backend-Kosten pro Kunde: ~$0.50/Mo (Gemini Flash Batch)
- Wir verkaufen: Plattform-Zugang + Einrichtung + Support

---

## Der Workflow in der Praxis

### Automatisch (Backend, laeuft 24/7):
```
1. Celery Beat checkt alle 15min auf neue Videos
2. Neues Video gefunden → Transkription starten
3. Transkript fertig → Analyse mit Gemini Flash
4. Analyse fertig → 5-8 Content-Ideen generieren
5. Ideen bereit → Status "pending_dialog"
6. [Optional: Notification an Unternehmer per E-Mail/Webhook]
```

### Interaktiv (Cowork, wenn der Unternehmer Zeit hat):
```
Unternehmer oeffnet Claude Desktop / Cowork

Claude: "Guten Morgen! Seit deinem letzten Besuch wurden 3 Videos
         analysiert. Ich habe 12 Content-Ideen vorbereitet.
         Die Top 3 nach Relevanz:

         1. 🔥 'Warum 80% der KMU ihre Liquiditaet falsch planen'
            (Kontroverse, Score 9.2)
         2. 💡 '5 Anzeichen dass dein Steuerberater nicht mitdenkt'
            (How-To, Score 8.7)
         3. 📊 'Steuerlast 2026: Was sich fuer Handwerker aendert'
            (Trend, Score 8.1)

         Worauf hast du Lust?"

Unternehmer: "Die erste! Das ist genau mein Ding."

Claude: "Cool. Dazu haette ich 2 kurze Fragen:
         1. Was ist der haeufigste Fehler den du bei Kunden siehst
            wenn es um Liquiditaetsplanung geht?
         2. Hast du ein konkretes Beispiel wo das fast schiefgegangen
            waere — natuerlich anonymisiert?"

Unternehmer: "Oh ja, letzte Woche erst. Ein Kunde hat..."

Claude: "Perfekt. Hier sind 2 Post-Varianten:

         [Variante 1 — Story-Hook]
         ...

         [Variante 2 — Provokanter Hook]
         ...

         Welche gefaellt dir besser? Oder soll ich was anpassen?"

Unternehmer: "Variante 2, aber der Schluss ist mir zu weich."

Claude: "Hier die ueberarbeitete Version: ..."

Unternehmer: "Perfekt! Poste das."

Claude: *speichert in DB + Nextcloud, Status: approved*
```

---

## Technische Umsetzung

### Was wir HABEN (bereits im Repo):
- [x] FastAPI Backend mit Multi-Tenant
- [x] Celery Worker + Beat
- [x] PostgreSQL + Redis
- [x] LLM Service (Gemini + Claude + LiteLLM)
- [x] Transkription + Analyse
- [x] Content Generator (Quick Mode)
- [x] React Frontend + Nginx
- [x] Docker Compose
- [x] ContentIdea + EntrepreneurAnswer Models (NEU)
- [x] Content Ideation Service (NEU)
- [x] Brand Voice Service (NEU)
- [x] Dialog-Mode Content Generator (NEU)
- [x] Ideas API Endpoints (NEU)

### Was wir BRAUCHEN:
- [ ] MCP-Server fuer Content-Autopilot-API
- [ ] Cowork Skill: Content-Dialog-Workflow
- [ ] Alembic Migration fuer neue Tabellen
- [ ] Celery Task: Automatische Ideation nach Analyse
- [ ] Notification-System (neue Ideen bereit)
- [ ] Frontend: Ideen-Queue + Dialog-View
- [ ] Brand-Voice-Profil im Tenant-Model

### Prioritaet:
1. **Sofort:** MCP-Server + Cowork Skill (der Dialog-Kern)
2. **Diese Woche:** Alembic Migration + Celery Ideation Task
3. **Naechste Woche:** Frontend Ideen-Queue
4. **Sprint 2:** Notification-System + Brand-Voice-Onboarding

---

## Entscheidung

**Wir bauen Option C: MCP-First Hybrid.**

Gruende:
- Der Dialog ist das Kernprodukt — und er ist am besten in Cowork/Claude Desktop
- API-Kosten bleiben minimal (~$0.50/Mo pro Kunde)
- Jeder Kunde zahlt sein eigenes Claude-Abo
- Backend bleibt schlank: nur Batch-Jobs + API + DB
- Skaliert auf beliebig viele Kunden mit einem Server
