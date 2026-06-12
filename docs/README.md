# 📚 Content Autopilot v2 — Dokumentations-Index

> **Willkommen im Dokumentations-Verzeichnis!** Dieser Index wächst über mehrere Sessions und dokumentiert Vision, Architektur, Pläne und Betrieb des Projekts.
>
> **Einstiegspfad als Neuer:** Start mit **Vision & Projektplan** → **Figma-SOLL-IST** → **DEPLOY.md** → **Entscheidungen lesen** → Code.

---

## 🎯 Strategisch / Einstieg

| Datei | Beschreibung | Datum |
|-------|-------------|-------|
| [VISION-UND-PROJEKTPLAN.md](VISION-UND-PROJEKTPLAN.md) | Gesamtvision: MCP-First Hybrid-Workflow für LinkedIn-Content. Louis = Source of Truth, v2 ist die Basis. Telegram-first im Beta. | 2026-06-12 |
| [FIGMA-SOLL-IST-2026-06-12.md](FIGMA-SOLL-IST-2026-06-12.md) | Detaillierte Status-Tabelle gegen Figma-Board: 5 Bahnen (Onboarding, Quellen, Analyse, Content, Feedback), jeder Status neu verifiziert am Code. | 2026-06-12 |
| [MCP_IST_DAS_PRODUKT.md](MCP_IST_DAS_PRODUKT.md) | Kernphilosophie: Der MCP-Server ist das Produkt, nicht die App/Dashboard. Jeder AI-Client wird zum Content-Assistenten. | 2026-06 |

---

## 📋 Status / Abgleiche (chronologisch, neueste zuerst)

| Datei | Beschreibung | Datum | Status |
|-------|-------------|-------|--------|
| [HANDOFF-SESSION-2026-06-12.md](HANDOFF-SESSION-2026-06-12.md) | Session-Übergabe: Louis' Übergabe = Source of Truth in `content-truth/` verankert. Prompt-/Rule-/Schema-Dateien versioniert, deployt, über Prompt-Studio bearbeitbar. | 2026-06-12 | Aktuell |
| [SOLL-IST-2026-06-12-wiring.md](SOLL-IST-2026-06-12-wiring.md) | Fokus: Louis-Eric-Logik produktiv verdrahten + Modell-Hoheit im Dashboard. Setup-Pipeline P01–P04 heute produktiv machen. | 2026-06-12 | Aktuell |
| [SOLL-IST-TELEGRAM-READINESS.md](SOLL-IST-TELEGRAM-READINESS.md) | Frage: Kann der Wochenloop jetzt getestet werden? Antwort: Teilweise (Anbinden + Inbound + Opener: ja; echter Loop: nein). 3 präzise blockierende Issues (#15, #16/#17, #19). | 2026-06-12 | Teilweise gelöst |
| [IST-SOLL-2026-06-12.md](IST-SOLL-2026-06-12.md) | Ehrenhafte Übergabe-Inventur gegen Vision: Was ist real implementiert, was fehlt. Branch `feat/files-as-source-of-truth`, 44 uncommittete Dateien. | 2026-06-12 | Archiv |

---

## 🛠 Pläne

| Datei | Beschreibung | Priorität |
|-------|-------------|-----------|
| [plans/P2-deploy-und-autodeploy.md](plans/P2-deploy-und-autodeploy.md) | Konzept: `content-truth/` als Bind-Mount deployen, Auto-Deploy via GitHub Actions Setup-Pipeline. | Hoch |
| [plans/P3-prompt-studio.md](plans/P3-prompt-studio.md) | Spec: Dashboard-UI zum Durchsehen, Bearbeiten, Validieren von Prompts/Rules/Schemas ohne Container-Rebuild. | Hoch |
| [plans/P4-schema-realignment.md](plans/P4-schema-realignment.md) | Planung: Figma-Schema mit v2-Code in Einklang bringen (Feedback-Loop, Tenant-Model, Daten-Normalisierung). | Mittel |
| [plans/P5-anthropic-provider.md](plans/P5-anthropic-provider.md) | Setup-Pipeline auf Anthropic S6 (`claude-sonnet-4-6`) über Requesty/LiteLLM-Router. Robert hat S6 explizit freigegeben. | Hoch |

---

## 🏛 Architektur-Entscheidungen

**Übersicht:** Louis' Phase-1-Übergabe (Mai 2026) definierte Prinzipien. Unter `decisions/louis-phase1/`:

| ADR | Titel | Gültig? |
|-----|-------|---------|
| [0001](decisions/louis-phase1/0001-schema-first-stack-last.md) | Schema First, Stack Last | ✓ |
| [0002](decisions/louis-phase1/0002-tenant-wrapper-pflicht.md) | Tenant-Wrapper (\_meta) ist Pflicht | ✓ |
| [0003](decisions/louis-phase1/0003-sonnet-als-default.md) | Sonnet als LLM-Default | ✓ (→ S6 via P5) |
| [0004](decisions/louis-phase1/0004-typescript-direkt-statt-n8n.md) | TypeScript direkt, nicht N8N | ✓ |
| [0005](decisions/louis-phase1/0005-iststand-vs-zielbild-markierung.md) | IstStand vs. ZielBild markieren | ✓ |
| [0006](decisions/louis-phase1/0006-kuratiertes-voice-profile.md) | Kuratiertes Voice-Profil (12 Dimensionen) | ✓ |
| [0007](decisions/louis-phase1/0007-runner-builds-2026-05-26.md) | Runner-Builds für E2E/Deployment | ✓ |
| [0008](decisions/louis-phase1/0008-qualitaet-vor-kosten-und-per-prompt-modell.md) | Qualität > Kosten, Modell pro Prompt | ✓ |

Siehe auch: [decisions/louis-phase1/README.md](decisions/louis-phase1/README.md)

---

## 🚀 Betrieb

| Datei | Beschreibung |
|-------|-------------|
| [DEPLOY.md](DEPLOY.md) | Deploy-Dokumentation: manuell auf Server B (`152.53.142.163:10022`) + automatisch via GitHub Actions. Docker-Compose-Struktur, Health-Checks, Logs. |
| [SETUP.md](SETUP.md) | Voraussetzungen (Docker, PostgreSQL, Nextcloud, LLM-Keys) + Initialisierung. |
| [SERVER-E2E-BOOTSTRAP.md](SERVER-E2E-BOOTSTRAP.md) | Server-Setup für E2E-Tests mit Browser-Use. |
| [RESTORE.md](RESTORE.md) | Wiederherstellungs-Verfahren nach Problemen. |

**Runbooks** (unter `runbooks/`):
- [RUNBOOK-e2e-tests.md](runbooks/RUNBOOK-e2e-tests.md) — Playwright Smoke + Browser-Use Explore
- [RUNBOOK-drift-monitor-manuell.md](runbooks/RUNBOOK-drift-monitor-manuell.md) — Manueller Drift-Monitor
- [RUNBOOK-recovery-after-bad-migration.md](runbooks/RUNBOOK-recovery-after-bad-migration.md) — Recovery nach fehlgeschlagener Migration
- [RUNBOOK-throttle-events-purge.md](runbooks/RUNBOOK-throttle-events-purge.md) — Throttle-Events löschen
- [RUNBOOK-yt-cookies-rotieren.md](runbooks/RUNBOOK-yt-cookies-rotieren.md) — YouTube-Cookies rotieren

---

## 🔧 Technische Referenzen

| Datei | Beschreibung |
|-------|-------------|
| [DATABASE.md](DATABASE.md) | PostgreSQL-Schema: 31 Tabellen in 8 Funktionsbereichen, Migrations via Alembic. |
| [ARCHITEKTUR_ENTSCHEIDUNG.md](ARCHITEKTUR_ENTSCHEIDUNG.md) | Workflow-Architektur: YouTube → Transkript → Analyse → Content → Feedback. Option C: MCP-First Hybrid. |
| [MIGRATION_NOTES.md](MIGRATION_NOTES.md) | Breaking Changes & Rollback-Strategie (Migration 024, 026, 027). |
| [DEPLOYMENT-Github.md](DEPLOYMENT-Github.md) | GitHub Actions + Deployment-Integration. |
| [KONZEPT_v2.md](KONZEPT_v2.md) | MCP-First Gesamtkonzept v2.0: Erics Leitsatz „System das arbeitet, nicht denkt". |

---

## 📊 Audits & Berichte

### Meta-Audit (2026-05-04)
Tiefen-Code-Audit gegen echte Source: 9 Bereiche (A–I), 4 Explorer-Subagents.

| Bereich | Datei | Fokus |
|---------|-------|-------|
| **A** | [meta-audit-2026-05-04/A_modularity.md](meta-audit-2026-05-04/A_modularity.md) | Modularität: Component-Tree, Imports, Dependency-Graph |
| **B** | [meta-audit-2026-05-04/B_youtube.md](meta-audit-2026-05-04/B_youtube.md) | YouTube-Integration: Cookies, Transkript-Engine |
| **C** | [meta-audit-2026-05-04/C_security.md](meta-audit-2026-05-04/C_security.md) | Security: Auth, Secrets, Injection-Prevention |
| **D** | [meta-audit-2026-05-04/D_documentation.md](meta-audit-2026-05-04/D_documentation.md) | Dokumentation: Codedocs, API-Specs, README-Qualität |
| **E** | [meta-audit-2026-05-04/E_portability.md](meta-audit-2026-05-04/E_portability.md) | Portabilität: Docker, Env-Deps, Hardcoding |
| **F** | [meta-audit-2026-05-04/F_dsgvo.md](meta-audit-2026-05-04/F_dsgvo.md) | DSGVO: Datenlöschung, Consent, Logging |
| **G** | [meta-audit-2026-05-04/G_usability.md](meta-audit-2026-05-04/G_usability.md) | Usability: UX-Patterns, Error-States, Mobile |
| **H** | [meta-audit-2026-05-04/H_sota_scale.md](meta-audit-2026-05-04/H_sota_scale.md) | SOTA & Skalierung: Concurrency, Caching, Performance |
| **I** | [meta-audit-2026-05-04/I_techdebt.md](meta-audit-2026-05-04/I_techdebt.md) | Tech-Debt: Deferred Refactorings, Gotchas |
| **Synthese** | [meta-audit-2026-05-04/SUMMARY.md](meta-audit-2026-05-04/SUMMARY.md) | Zusammenfassung über alle Bereiche |

### Sprint 3 — UX-Audit (2026-05-05)
Audit von 38 JSX-Komponenten, 23k LoC, 14 Routes.

| Bereich | Datei | Fokus |
|---------|-------|-------|
| **A1** | [sprint3-ux-audit/A1_komponenten_inventur.md](sprint3-ux-audit/A1_komponenten_inventur.md) | Komponenten-Inventar: Tree, API, State |
| **A2** | [sprint3-ux-audit/A2_user_journey.md](sprint3-ux-audit/A2_user_journey.md) | User-Journey: Onboarding bis Content-Loop |
| **A3** | [sprint3-ux-audit/A3_konsistenz_check.md](sprint3-ux-audit/A3_konsistenz_check.md) | Konsistenz: Naming, Styling, Patterns |
| **A4** | [sprint3-ux-audit/A4_mobile_audit.md](sprint3-ux-audit/A4_mobile_audit.md) | Mobile: Responsive, Touch, Breakpoints |
| **Synthese** | [sprint3-ux-audit/SUMMARY-UX.md](sprint3-ux-audit/SUMMARY-UX.md) | Zusammenfassung über alle UX-Aspekte |

---

## 🏗 Legacy / Archiv

| Datei | Status | Grund |
|-------|--------|-------|
| [adr/ADR-*.md](adr/) | Veraltet | Ersetzt durch `decisions/louis-phase1/` (bessere Strukturierung) |

---

## 📞 Kontakt & Koordination

**Knecht-Architektur:** Zwei Claude-Instanzen (Haiku, Sonnet) auf dem Server, gesteuert via GitHub Labels. Siehe CLAUDE.md (im Repo-Root) für Details zu Knecht-Haiku, Knecht-Sonnet und Cowork-QA.

---

**Letzter Update:** 2026-06-12 · **Index enthält:** 51 Dateien aus 7 Kategorien
