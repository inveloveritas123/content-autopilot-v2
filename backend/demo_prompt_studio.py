"""Schlanker Demo-Server NUR fuer das Prompt-Studio (lokales Anschauen/Testen).

Mountet den ECHTEN api/prompt_studio-Router gegen das echte content-truth/ + ein
Temp-Overlay, ohne den vollen v2-Stack (DB/Celery/Telegram/LLM).
Schwere Importe (services.llm/nextcloud) + Auth (dependencies.get_tenant) werden
gestubbt. NICHT fuer Produktion — reines Demo-Harness.

Start:  PYTHONPATH=. CONTENT_TRUTH_BASE_PATH=<repo>/content-truth \
        CONTENT_TRUTH_OVERLAY_PATH=/tmp/cap-overlay \
        python demo_prompt_studio.py
"""
import os
import sys
import types

# --- Schwere/abhaengige Module stubben, BEVOR der Router importiert wird ---------

# dependencies.get_tenant: Fake-Tenant statt DB-Lookup
_dep = types.ModuleType("dependencies")


class _FakeTenant:
    id = "demo-tenant"
    name = "Demo CAP"


async def _get_tenant():  # FastAPI-Dependency ohne Header/DB
    return _FakeTenant()


_dep.get_tenant = _get_tenant
sys.modules["dependencies"] = _dep

# services.llm / services.nextcloud: leere Stubs (services/__init__ importiert sie)
_llm = types.ModuleType("services.llm")
_llm.llm_service = None
_llm.set_llm_tenant = lambda *a, **k: None
_llm.BudgetExceededError = type("BudgetExceededError", (Exception,), {})
sys.modules["services.llm"] = _llm

_nc = types.ModuleType("services.nextcloud")
_nc.nextcloud_client = None
sys.modules["services.nextcloud"] = _nc

# --- Env-Defaults fuer localfs + Overlay -----------------------------------------
os.environ.setdefault("PROMPT_STORAGE_BACKEND", "localfs")
_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("CONTENT_TRUTH_BASE_PATH", os.path.join(_repo, "content-truth"))
os.environ.setdefault("CONTENT_TRUTH_OVERLAY_PATH", "/tmp/cap-overlay")
os.makedirs(os.environ["CONTENT_TRUTH_OVERLAY_PATH"], exist_ok=True)

# --- App bauen --------------------------------------------------------------------
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api.prompt_studio import router as prompt_studio_router  # noqa: E402

app = FastAPI(title="Prompt-Studio DEMO")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(prompt_studio_router, prefix="/api", tags=["PromptStudio"])


@app.get("/api/tenant-init")
async def tenant_init():
    """Stub, damit das Frontend beim Laden nicht blockiert."""
    return {"ok": True, "tenant": {"id": "demo-tenant", "name": "Demo CAP"}}


@app.get("/api/health")
async def health():
    return {"status": "ok", "demo": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
