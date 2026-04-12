# Design-Entscheidungen

## 2026-04-01: LiteLLM Free Tier als Test-Proxy
- Für API-Tests wird LiteLLM Free Tier unterstützt
- llm.py bekommt optionalen LITELLM_BASE_URL Parameter
- Wenn gesetzt, werden alle LLM-Calls über LiteLLM geroutet

## 2026-04-01: Celery mit sync DB-Zugriff
- Celery Tasks nutzen synchrones SQLAlchemy (nicht async)
- Grund: Celery Worker sind sync, asyncpg in sync context = Probleme
- Separate sync DATABASE_URL (postgresql:// statt postgresql+asyncpg://)

## 2026-04-01: Frontend ohne echtes shadcn/ui CLI
- shadcn/ui Komponenten werden manuell als Tailwind-basierte Komponenten erstellt
- Grund: shadcn CLI braucht TypeScript + Next.js Setup, wir nutzen Vite + JSX
- Gleiche Optik, simpler Setup
