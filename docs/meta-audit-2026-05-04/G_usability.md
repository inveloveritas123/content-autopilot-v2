# Usability + Scope Audit — content-autopilot-v2 (2026-05-04)

## Befund

### Frontend-Seiten
**50 JSX/TSX-Dateien gefunden**  
- Layout: `frontend/src/components/Layout.jsx` mit 12 Haupt-Navigations-Items (sidebar)
- Routes in `Layout.jsx:29-53` zeigen: Dashboard, Pipeline, Quellen, Ideen, Posts, Dialogue, Posten, Kalender, Analytics, Feedback, Einstellungen, LLM Analytics
- Admin-Section: `/admin/models/backtest` (Models-Backtest)
- Brand Voice Section: 4 Sub-Routes (`/brand-voice`, `/brand-voice/insights`, `/brand-voice/review-queue`, `/memory`)

### Mobile-Responsiveness
**50 Responsive-Patterns gefunden** (`@media`, `sm:`, `md:`, `lg:`)  
- Tailwind-Framework verwendet (Utility-First)
- Min-Height: `44px` auf allen Buttons (WCAG Touch-Target Größe)
- Beispiel: `Layout.jsx:164` — `min-h-[44px]` für Accessibility

### ❌ Approve-Flow
**0 Treffer:** Keine `services/approve_*.py` oder `components/Approve*.jsx`  
- Code sieht ReviewQueue-Komponente (`ReviewQueue.jsx`) vor, aber kein dedizierter Approve-Service
- User decideReviewQueueItem() wird aufgerufen, aber keine separate Approve-Logik

### ✅ Telegram-Bot-Code
**3 Dateien gefunden:**
- `backend/api/telegram.py:1-50` — Webhook-Receiver mit Rate-Limiting pro IP (`_bad_attempts` Dict)
- `backend/tasks/telegram_task.py` — Async Task-Handler
- `backend/tests/test_telegram_webhook.py` — Test-Suite
- Alembic-Migration: `backend/alembic/versions/019_telegram_tables.py`

### Sidebar-Items (Layout)
**14 verlinkte Routes:**
1. `/` Dashboard
2. `/pipeline` Pipeline
3. `/sources` Quellen
4. `/ideas` Ideen
5. `/posts` Posts
6. `/dialogue` Dialogue
7. `/publish` Posten
8. `/calendar` Kalender
9. `/analytics` Analytics
10. `/feedback` Feedback
11. `/settings` Einstellungen
12. `/settings/analytics` LLM Analytics
13. `/brand-voice` Brand Voice
14. `/admin/models/backtest` Modelle

---

## Top-3-Empfehlungen

1. **Approve-Workflow** → Expliziter Service (`backend/services/approve_service.py`) mit Audit-Trail für Content-Genehmigungen (wer, wann, was geändert)
2. **Telegram-Status-Dashboard** → Integrations-Tab mit Webhook-Status, letzter erfolgreicher Call, Queue-Länge
3. **Mobile-Testfrage** → Sind alle 50 JSX-Seiten mobile-getestet oder nur kritische 5-10? (Dashboard, Quellen, Posts)
