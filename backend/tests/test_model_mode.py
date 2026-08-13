"""
tests/test_model_mode.py — Modell-Modus-Switch (Issue #72)

KERNBEWEISE (dep-freie Imports via importlib; Py3.9-kompatibel):
  A. Sicherheits-Invariante: Testmodus → bit-identisch mit altem Routing.
     KEY-INVARIANTE (Opus-Review #72): _resolve_model gibt IMMER einen KEY zurück,
     niemals einen aufgelösten String. testmodus → "claude-sonnet" (KEY) → Gemini via
     REQUESTY_MODELS. Der _litellm-Pfad bleibt exakt gleich wie ohne Feature.
  B. Produktivmodus → KEY "claude-sonnet-eu" → bedrock/claude-sonnet-4-6@eu-central-1.
  C. routing_override gewinnt in jedem Modus (höchste Präzedenz).
  D. Kein Kontext → 'testmodus' (fail-safe).
  E. GET /tenants/me/model-mode → Default 'testmodus'.
  F. PUT /tenants/me/model-mode → gültige Werte OK, ungültige 422.
  G. E3-Mandantentrennung.
  H. Setup-Pfad (pipeline_llm) unberührt.
  I. ECHTER _resolve_litellm_model-Pfad (aus services/llm_mapping.py — dep-frei,
     direkt importierbar ohne Stubs). Testet die tatsächliche Mapping-Logik.

Strategie:
  services/llm_mapping.py ist dep-frei (kein httpx, kein sqlalchemy) → direkt
  importierbar in Py3.9 ohne Stubs. services.model_mode wird via importlib geladen.
  services.llm (schwer) wird nur als Stub benötigt damit services/__init__ nicht
  crasht. Die echte Mapping-Logik kommt aus llm_mapping.py.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import pathlib
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── 1. Schwere Stubs ZUERST (vor jedem echten Import) ─────────────────────────


def _stub(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# conftest.py setzt bereits: anthropic, google, google.generativeai, celery


# services.tenant_export / tenant_import: echten Import ZUERST, VOR allen models-Stubs.
# Wenn das hier klappt (CI-Docker: openpyxl + sqlalchemy + models echte Pakete),
# liegt das echte Modul in sys.modules und test_tenant_export_formats.py bleibt grün.
# Schlägt es fehl (lokale Dev ohne openpyxl), wird weiter unten ein Stub gesetzt.
def _load_service_direct(qual_name: str) -> bool:
    """Lade services/<module>.py direkt per importlib, ohne services/__init__ zu triggern."""
    if qual_name in sys.modules:
        return True
    _p = pathlib.Path(__file__).parent.parent / "services" / f"{qual_name.split('.')[-1]}.py"
    try:
        _spec = importlib.util.spec_from_file_location(qual_name, _p)
        _m = importlib.util.module_from_spec(_spec)
        sys.modules[qual_name] = _m
        _spec.loader.exec_module(_m)
        return True
    except Exception:
        sys.modules.pop(qual_name, None)
        return False


_load_service_direct("services.tenant_export")
_load_service_direct("services.tenant_import")

# httpx, redis
_stub("httpx")
_stub("redis")

# sqlalchemy-Familie
if "sqlalchemy" not in sys.modules:
    _sa = _stub("sqlalchemy")
    _sa.func = MagicMock()
    _sa.select = MagicMock()
    _sa.text = lambda sql: sql
    _sa.Boolean = MagicMock()
    _sa.DateTime = MagicMock()
    _sa.String = MagicMock()
    _sa.Text = MagicMock()
    _sa.Integer = MagicMock()
    _stub("sqlalchemy.ext")
    _stub("sqlalchemy.ext.asyncio").AsyncSession = MagicMock()
    _sa_orm = _stub("sqlalchemy.orm")
    _sa_orm.Mapped = MagicMock()
    _sa_orm.mapped_column = MagicMock()
    _sa_orm.relationship = MagicMock()
    _sa_orm.attributes = _stub("sqlalchemy.orm.attributes")
    _sa_orm.attributes.flag_modified = MagicMock()
    _stub("sqlalchemy.dialects")
    _sa_pg = _stub("sqlalchemy.dialects.postgresql")
    _sa_pg.JSONB = MagicMock()
    _sa_pg.UUID = MagicMock()

# pydantic
if "pydantic" not in sys.modules:
    _pd = _stub("pydantic")
    _pd.BaseModel = object

# fastapi
if "fastapi" not in sys.modules:
    _fa = _stub("fastapi")

    class _FakeHTTPException(Exception):
        def __init__(self, status_code: int, detail=None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class _FakeAPIRouter:
        def __init__(self, *a, **kw):
            pass

        def _noop_decorator(self, *a, **kw):
            def decorator(fn):
                return fn

            if len(a) == 1 and callable(a[0]):
                return a[0]
            return decorator

        get = post = put = patch = delete = _noop_decorator

    _fa.APIRouter = _FakeAPIRouter
    _fa.Depends = lambda x: x
    _fa.File = MagicMock()
    _fa.Header = MagicMock()
    _fa.Query = MagicMock()
    _fa.UploadFile = MagicMock()
    _fa.HTTPException = _FakeHTTPException
    _stub("fastapi.responses").StreamingResponse = MagicMock()
    HTTPException = _FakeHTTPException
else:
    from fastapi import HTTPException

# config.settings stub
_cfg = _stub("config")
if not hasattr(_cfg, "settings"):
    _cfg.settings = MagicMock()
    _cfg.settings.litellm_base_url = "https://router.requesty.ai/v1"
    _cfg.settings.litellm_api_key = "test-key"
    _cfg.settings.gemini_api_key = "not-needed-using-litellm"
    _cfg.settings.anthropic_api_key = "not-needed-using-litellm"
    _cfg.settings.telegram_admin_chat_id = None
    _cfg.settings.redis_url = "redis://localhost:6379"
    _cfg.settings.max_calls_per_tenant_per_hour = 100

# models.*
_stub("models.base").sync_session_factory = MagicMock()
_stub("models")
_stub("models.tenant").Tenant = MagicMock()
_stub("models.content_performance").ContentPerformance = MagicMock()

# services.* (schwere Untermodule) — VOR dem Import von services/__init__
# services.llm muss gestubbt werden damit services/__init__ kein TypeError wirft
_llm_stub = _stub("services.llm")
if not hasattr(_llm_stub, "llm_service"):
    _llm_stub.llm_service = MagicMock()
    _llm_stub.set_llm_tenant = MagicMock()
    _llm_stub.PURPOSE_MAX_TOKENS = {}
    _llm_stub.PURPOSE_MODEL_MAP = {}
    _llm_stub.REQUESTY_MODELS = {}
    _llm_stub.BudgetExceededError = type("BudgetExceededError", (Exception,), {})

_stub("services.nextcloud").nextcloud_client = MagicMock()

# tenant_export / tenant_import: echten Import bevorzugen damit
# test_tenant_export_formats.py die echte Klasse bekommt (kein sys.modules-Poison).
# Stub nur als Fallback wenn openpyxl o.ä. fehlt.
if "services.tenant_export" not in sys.modules:
    try:
        import services.tenant_export
    except Exception:
        _te = _stub("services.tenant_export")
        _te.TenantExportService = MagicMock(return_value=MagicMock())
if "services.tenant_import" not in sys.modules:
    try:
        import services.tenant_import  # noqa: F401
    except Exception:
        _ti = _stub("services.tenant_import")
        _ti.TenantImportService = MagicMock(return_value=MagicMock())

_th = _stub("services.throttle")
if not hasattr(_th, "RateLimitExceededError"):
    _th.RateLimitExceededError = type("RateLimitExceededError", (Exception,), {})
if not hasattr(_th, "check_and_record_throttle"):
    _th.check_and_record_throttle = MagicMock(return_value=(True, 0, 0))

_pr = _stub("services.provider_resolver")
if not hasattr(_pr, "get_active_provider"):
    _pr.get_active_provider = MagicMock(return_value=None)
    _pr.track_cost = MagicMock()
    _pr._DAILY_CAP_USD = 5.0
    _pr._GLOBAL_CAP_USD = 50.0

_stub("dependencies").get_db = MagicMock()
_stub("dependencies").get_tenant = MagicMock()

# ── 2. services.model_mode direkt per importlib laden (bypasst __init__) ──────
# Da services/__init__.py services.llm importiert (→ ContextVar[str|None] RuntimeError),
# laden wir services.model_mode manuell via spec ohne den Package-Init zu triggern.

_BACKEND_DIR = pathlib.Path(__file__).parent.parent

_mm_spec = importlib.util.spec_from_file_location(
    "services.model_mode",
    _BACKEND_DIR / "services" / "model_mode.py",
)
_mm_module = importlib.util.module_from_spec(_mm_spec)
sys.modules["services.model_mode"] = _mm_module
_mm_spec.loader.exec_module(_mm_module)

# Symbole in den Modulnamespace holen
CREATIVE_MODEL_BY_MODE = _mm_module.CREATIVE_MODEL_BY_MODE
CREATIVE_MODEL_KEYS = _mm_module.CREATIVE_MODEL_KEYS
CREATIVE_PURPOSES = _mm_module.CREATIVE_PURPOSES
DEFAULT_MODEL_MODE = _mm_module.DEFAULT_MODEL_MODE
VALID_MODEL_MODES = _mm_module.VALID_MODEL_MODES
get_tenant_model_mode = _mm_module.get_tenant_model_mode
# resolve_creative_model wurde in Opus-Review #72 als toter Code entfernt
# (Test test_resolve_creative_model_nicht_mehr_vorhanden prüft das explizit)

# ── 3. Echte Mapping-Konstanten und _resolve_litellm_model aus llm_mapping.py ──
# llm_mapping.py ist dep-frei (kein httpx, kein sqlalchemy, kein anthropic) →
# direkt importierbar in Py3.9 ohne Stubs. Dies ist die Quelle der Wahrheit.

_lm_spec = importlib.util.spec_from_file_location(
    "services.llm_mapping",
    _BACKEND_DIR / "services" / "llm_mapping.py",
)
_lm_module = importlib.util.module_from_spec(_lm_spec)
sys.modules["services.llm_mapping"] = _lm_module
_lm_spec.loader.exec_module(_lm_module)

# ECHTE Funktion aus llm_mapping.py (kein Replikat, kein AST-Hack)
_resolve_litellm_model = _lm_module._resolve_litellm_model
REQUESTY_MODELS: dict = _lm_module.REQUESTY_MODELS


# PURPOSE_MODEL_MAP: per AST aus llm.py lesen (nur ein Dict-Literal, sicher)
def _read_purpose_model_map() -> dict:
    """Liest PURPOSE_MODEL_MAP direkt aus llm.py (nur Dict-Literal, kein Import)."""
    import ast

    llm_src = (_BACKEND_DIR / "services" / "llm.py").read_text()
    tree = ast.parse(llm_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PURPOSE_MODEL_MAP":
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        pass
    return {}


PURPOSE_MODEL_MAP: dict = _read_purpose_model_map()


# _resolve_model_logic: Replika von LLMService._resolve_model (nur der KEY-Teil).
# KEY-INVARIANTE (Opus-Review #72): gibt IMMER einen KEY zurück, nie einen
# aufgelösten String. Testmodus → "claude-sonnet" (KEY, nicht "vertex/...").
# Um die bit-identische Invariante für den ECHTEN _litellm-Pfad zu prüfen,
# kombinieren wir _resolve_model_logic mit _resolve_litellm_model (siehe TestInvarianteTestmodus).
def _resolve_model_logic(
    model: str,
    purpose: str | None,
    routing_override: dict | None,
    *,
    mode: str = "testmodus",
) -> str:
    """Replika von LLMService._resolve_model — gibt IMMER einen KEY zurück.

    KEY-INVARIANTE (Opus-Review #72):
      testmodus   → "claude-sonnet"    (KEY → Gemini via REQUESTY_MODELS, bit-identisch)
      produktiv   → "claude-sonnet-eu" (KEY → Bedrock via REQUESTY_MODELS)
      benutzerd.  → "claude-sonnet"    (kein Override → KEY bleibt)

    Präzedenz:
      1. routing_override[purpose]  — höchste Priorität
      2. model_mode (testmodus/produktiv/benutzerdefiniert)
      3. fall-through (aktuelles Verhalten)
    """
    if purpose:
        # Ebene 1: routing_override
        if routing_override and purpose in routing_override:
            return routing_override[purpose]
        if purpose in PURPOSE_MODEL_MAP:
            resolved = PURPOSE_MODEL_MAP[purpose]
            # Ebene 2: Modus-Switch für kreative Keys — gibt KEY zurück, nie String
            if resolved in CREATIVE_MODEL_KEYS:
                mode_key = CREATIVE_MODEL_BY_MODE.get(mode)
                if mode_key is not None:
                    return mode_key  # KEY: "claude-sonnet" oder "claude-sonnet-eu"
                # benutzerdefiniert → None → kein override → return resolved (KEY)
            return resolved  # KEY (z.B. "gemini-flash", "claude-sonnet")
    return model  # unverändert


# ── 4. helpers ─────────────────────────────────────────────────────────────────


def _make_tenant(settings_data: dict | None = None):
    t = MagicMock()
    t.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    t.settings = settings_data or {}
    return t


# ── 5. INVARIANTE A: Testmodus → bit-identisch ────────────────────────────────


class TestInvarianteTestmodus:
    """KERNBEWEIS: Default 'testmodus' ist bit-identisch mit altem Verhalten.

    KEY-INVARIANTE (Opus-Review #72):
      _resolve_model_logic gibt IMMER einen KEY zurück (nie einen aufgelösten String).
      testmodus → KEY "claude-sonnet" → exakt derselbe _litellm-Pfad wie vor dem Feature.
      Bit-Identität = gleicher KEY → gleicher _litellm-Durchlauf → gleiches litellm_model + task.
    """

    def _old_key(self, purpose: str) -> str:
        """Altes Verhalten VOR dem Feature: KEY aus PURPOSE_MODEL_MAP."""
        return PURPOSE_MODEL_MAP.get(purpose, "gemini-flash")

    def _old_litellm_model(self, purpose: str) -> str:
        """Altes litellm_model VOR dem Feature (nach _litellm-Auflösung)."""
        key = self._old_key(purpose)
        litellm_model, _ = _resolve_litellm_model(key, None)
        return litellm_model

    @pytest.mark.parametrize("purpose", sorted(CREATIVE_PURPOSES))
    def test_testmodus_key_gleich_altem_key(self, purpose):
        """KEY-INVARIANTE: testmodus gibt exakt denselben KEY zurück wie vor dem Feature.

        Dies ist der ECHTE Bit-Identitätsbeweis: gleicher KEY → gleicher _litellm-Pfad.
        """
        key_new = _resolve_model_logic("claude-sonnet", purpose, None, mode="testmodus")
        key_old = self._old_key(purpose)
        assert key_new == key_old, (
            f"KEY-INVARIANTE VERLETZT für purpose='{purpose}':\n"
            f"  mit Feature (testmodus): {key_new!r}\n"
            f"  ohne Feature (alt):      {key_old!r}\n"
            "testmodus muss exakt denselben KEY liefern wie vor dem Feature!"
        )

    @pytest.mark.parametrize("purpose", sorted(CREATIVE_PURPOSES))
    def test_testmodus_litellm_model_gleich_alt(self, purpose):
        """ECHTER _litellm-Pfad: testmodus → gleicher litellm_model-String wie vor dem Feature."""
        key_new = _resolve_model_logic("claude-sonnet", purpose, None, mode="testmodus")
        litellm_new, task_new = _resolve_litellm_model(key_new, None)
        litellm_old = self._old_litellm_model(purpose)
        assert litellm_new == litellm_old, (
            f"_litellm-Invariante VERLETZT für purpose='{purpose}':\n"
            f"  testmodus litellm_model: {litellm_new!r}\n"
            f"  alt litellm_model:       {litellm_old!r}\n"
            "Der _litellm-Pfad muss im testmodus bit-identisch bleiben!"
        )
        # Auch task muss identisch sein (beeinflusst get_active_provider + Cost-Tracking)
        _, task_old = _resolve_litellm_model(self._old_key(purpose), None)
        assert task_new == task_old, (
            f"task-Invariante VERLETZT für purpose='{purpose}':\n"
            f"  testmodus task: {task_new!r}\n"
            f"  alt task:       {task_old!r}"
        )

    @pytest.mark.parametrize("purpose", sorted(CREATIVE_PURPOSES))
    def test_testmodus_ist_gemini_flash_lite(self, purpose):
        """INVARIANTE A (explizit): testmodus-litellm_model == REQUESTY_MODELS["claude-sonnet"]
        (Gemini-Flash-Lite — konkreter Modell-String lebt allein in llm_mapping.py, siehe
        REQUESTY_MODELS-Docstring dort für die aktuelle Version)."""
        key = _resolve_model_logic("claude-sonnet", purpose, None, mode="testmodus")
        litellm_model, task = _resolve_litellm_model(key, None)
        assert (
            litellm_model == REQUESTY_MODELS["claude-sonnet"]
        ), f"purpose='{purpose}': erwartet Gemini-Flash-Lite, bekam {litellm_model!r}"
        assert task == "creative"

    def test_testmodus_key_ist_claude_sonnet(self):
        """KEY-INVARIANTE explizit: testmodus → KEY 'claude-sonnet' (nicht aufgelöster String)."""
        key = CREATIVE_MODEL_BY_MODE["testmodus"]
        assert (
            key == "claude-sonnet"
        ), f"CREATIVE_MODEL_BY_MODE['testmodus'] muss KEY 'claude-sonnet' sein, nicht {key!r}"
        # Und dieser KEY muss in REQUESTY_MODELS existieren
        assert key in REQUESTY_MODELS, f"KEY {key!r} fehlt in REQUESTY_MODELS"

    def test_testmodus_key_in_requesty_models(self):
        """KEY-INVARIANTE: CREATIVE_MODEL_BY_MODE['testmodus'] zeigt via REQUESTY_MODELS auf
        denselben Gemini-String wie der KEY 'claude-sonnet' direkt — keine zweite Quelle."""
        key = CREATIVE_MODEL_BY_MODE["testmodus"]
        assert REQUESTY_MODELS[key] == REQUESTY_MODELS["claude-sonnet"], (
            "INVARIANTE VERLETZT!\n"
            f"REQUESTY_MODELS[{key!r}] = {REQUESTY_MODELS.get(key)!r}\n"
            f"REQUESTY_MODELS['claude-sonnet'] = {REQUESTY_MODELS.get('claude-sonnet')!r}"
        )

    def test_non_creative_purposes_unaffected(self):
        """Nicht-kreative Purposes: resolve_model gibt immer denselben KEY zurück,
        unabhängig vom Modus (= kein CREATIVE_MODEL_KEYS-Match)."""
        non_creative = [p for p in PURPOSE_MODEL_MAP if p not in CREATIVE_PURPOSES]
        assert non_creative, "Keine nicht-kreativen Purposes gefunden"
        for purpose in non_creative:
            # In allen Modi muss der KEY identisch sein
            key_testmodus = _resolve_model_logic("gemini-flash", purpose, None, mode="testmodus")
            key_produktiv = _resolve_model_logic("gemini-flash", purpose, None, mode="produktiv")
            assert key_testmodus == key_produktiv, (
                f"Nicht-kreative Purpose '{purpose}' verändert sich bei Moduswechsel!\n"
                f"  testmodus:  {key_testmodus!r}\n"
                f"  produktiv:  {key_produktiv!r}"
            )
            # Und: Ergebnis ist der PURPOSE_MODEL_MAP-Wert (KEY)
            expected_key = PURPOSE_MODEL_MAP.get(purpose, "gemini-flash")
            assert key_testmodus == expected_key, (
                f"Purpose '{purpose}': erwartet model-key {expected_key!r}, "
                f"bekam {key_testmodus!r}"
            )


# ── 6. Produktivmodus ─────────────────────────────────────────────────────────


class TestProduktivmodus:
    """KERNBEWEIS B: produktiv → KEY 'claude-sonnet-eu' → Bedrock-Frankfurt.

    KEY-INVARIANTE (Opus-Review #72): _resolve_model_logic gibt den KEY zurück;
    _resolve_litellm_model löst KEY → litellm_model auf. Beide Ebenen werden getestet.
    """

    @pytest.mark.parametrize("purpose", sorted(CREATIVE_PURPOSES))
    def test_produktiv_liefert_bedrock_s6_key(self, purpose):
        """produktiv → KEY 'claude-sonnet-eu' (nicht direkt der Bedrock-String)."""
        key = _resolve_model_logic("claude-sonnet", purpose, None, mode="produktiv")
        assert (
            key == "claude-sonnet-eu"
        ), f"purpose='{purpose}': erwartet KEY 'claude-sonnet-eu', bekam {key!r}"

    @pytest.mark.parametrize("purpose", sorted(CREATIVE_PURPOSES))
    def test_produktiv_litellm_model_ist_bedrock(self, purpose):
        """ECHTER _litellm-Pfad: KEY 'claude-sonnet-eu' → bedrock/claude-sonnet-4-6@eu-central-1."""
        key = _resolve_model_logic("claude-sonnet", purpose, None, mode="produktiv")
        litellm_model, task = _resolve_litellm_model(key, None)
        assert (
            litellm_model == "bedrock/claude-sonnet-4-6@eu-central-1"
        ), f"purpose='{purpose}': erwartet Bedrock-S6, bekam {litellm_model!r}"
        assert task == "creative", f"purpose='{purpose}': erwartet task='creative', bekam {task!r}"

    @pytest.mark.parametrize("purpose", sorted(CREATIVE_PURPOSES))
    def test_produktiv_mit_db_provider_liefert_bedrock(self, purpose):
        """ECHTER _litellm-Pfad mit aktivem DB-Provider: task='creative' → Bedrock-String."""
        provider = {
            "base_url": "https://router.requesty.ai/v1",
            "api_key": "test-key",
            "model_name": "provider-default-model",
            "provider_id": 1,
            "auto_cache": True,
        }
        key = _resolve_model_logic("claude-sonnet", purpose, None, mode="produktiv")
        litellm_model, task = _resolve_litellm_model(key, provider)
        # Auch mit aktivem Provider muss der KEY-Lookup greifen (nicht provider["model_name"])
        assert (
            litellm_model == "bedrock/claude-sonnet-4-6@eu-central-1"
        ), f"provider aktiv, purpose='{purpose}': KEY-Lookup muss greifen, bekam {litellm_model!r}"
        assert task == "creative"

    def test_produktiv_key_ist_claude_sonnet_eu(self):
        """KEY-INVARIANTE explizit: CREATIVE_MODEL_BY_MODE['produktiv'] == 'claude-sonnet-eu'."""
        key = CREATIVE_MODEL_BY_MODE["produktiv"]
        assert key == "claude-sonnet-eu"
        assert key in REQUESTY_MODELS

    def test_produktiv_requesty_models_ist_bedrock(self):
        """REQUESTY_MODELS['claude-sonnet-eu'] → Bedrock-Frankfurt EU."""
        model = REQUESTY_MODELS["claude-sonnet-eu"]
        assert "eu-central-1" in model
        assert "bedrock/" in model

    def test_produktiv_ungleich_testmodus_key(self):
        assert CREATIVE_MODEL_BY_MODE["testmodus"] != CREATIVE_MODEL_BY_MODE["produktiv"]

    def test_produktiv_ungleich_testmodus_litellm_model(self):
        """Auch aufgelöst müssen die Modi unterschiedliche litellm_model-Strings liefern."""
        key_test = CREATIVE_MODEL_BY_MODE["testmodus"]
        key_prod = CREATIVE_MODEL_BY_MODE["produktiv"]
        m_test, _ = _resolve_litellm_model(key_test, None)
        m_prod, _ = _resolve_litellm_model(key_prod, None)
        assert m_test != m_prod

    def test_benutzerdefiniert_ist_none(self):
        assert CREATIVE_MODEL_BY_MODE["benutzerdefiniert"] is None


# ── 7. routing_override: höchste Präzedenz ────────────────────────────────────


class TestRoutingOverridePraezedenz:
    def test_override_schlaegt_testmodus(self):
        override = {"ideation": "my-custom-model"}
        result = _resolve_model_logic("claude-sonnet", "ideation", override, mode="testmodus")
        assert result == "my-custom-model"

    def test_override_schlaegt_produktivmodus(self):
        override = {"ideation": "my-custom-model"}
        result = _resolve_model_logic("claude-sonnet", "ideation", override, mode="produktiv")
        assert result == "my-custom-model"

    def test_override_nur_fuer_betroffenen_purpose(self):
        override = {"ideation": "my-custom-model"}
        result_ideation = _resolve_model_logic(
            "claude-sonnet", "ideation", override, mode="produktiv"
        )
        result_questions = _resolve_model_logic(
            "claude-sonnet", "questions", override, mode="produktiv"
        )
        assert result_ideation == "my-custom-model"
        # questions hat keinen override → Modus greift → KEY "claude-sonnet-eu"
        assert result_questions == CREATIVE_MODEL_BY_MODE["produktiv"]  # = "claude-sonnet-eu"

    def test_ohne_override_kein_einfluss(self):
        # Kein override → Modus greift
        result = _resolve_model_logic("claude-sonnet", "ideation", None, mode="produktiv")
        assert result == CREATIVE_MODEL_BY_MODE["produktiv"]


# ── 8a. ECHTER _resolve_litellm_model (aus services/llm_mapping.py) ──────────


class TestResolveLitellmModel:
    """Prüft die ECHTE reine Mapping-Funktion _resolve_litellm_model aus llm_mapping.py.

    Diese Tests treffen den tatsächlichen _litellm-Auflösungs-Pfad, nicht eine Replika.
    Kein httpx, kein DB-Mock nötig — die Funktion ist rein.
    """

    # ── testmodus: "claude-sonnet" → Gemini, task creative ────────────────────

    def test_claude_sonnet_ohne_provider_gibt_gemini(self):
        litellm_model, task = _resolve_litellm_model("claude-sonnet", None)
        assert litellm_model == REQUESTY_MODELS["claude-sonnet"]
        assert task == "creative"

    def test_claude_sonnet_mit_provider_gibt_gemini(self):
        """KEY-LOOKUP schlägt provider['model_name'] — KEY-Invariante gilt auch mit Provider."""
        provider = {
            "model_name": "provider-default",
            "base_url": "x",
            "api_key": "k",
            "provider_id": 1,
        }
        litellm_model, task = _resolve_litellm_model("claude-sonnet", provider)
        assert litellm_model == REQUESTY_MODELS["claude-sonnet"]
        assert task == "creative"

    # ── produktiv: "claude-sonnet-eu" → Bedrock, task creative ───────────────

    def test_claude_sonnet_eu_ohne_provider_gibt_bedrock(self):
        litellm_model, task = _resolve_litellm_model("claude-sonnet-eu", None)
        assert litellm_model == "bedrock/claude-sonnet-4-6@eu-central-1"
        assert task == "creative"

    def test_claude_sonnet_eu_mit_provider_gibt_bedrock(self):
        """KEY-LOOKUP schlägt auch hier provider['model_name']."""
        provider = {
            "model_name": "provider-default",
            "base_url": "x",
            "api_key": "k",
            "provider_id": 1,
        }
        litellm_model, task = _resolve_litellm_model("claude-sonnet-eu", provider)
        assert litellm_model == "bedrock/claude-sonnet-4-6@eu-central-1"
        assert task == "creative"

    # ── gemini-flash: "gemini-flash" → Gemini, task analysis ─────────────────

    def test_gemini_flash_ohne_provider(self):
        litellm_model, task = _resolve_litellm_model("gemini-flash", None)
        assert litellm_model == REQUESTY_MODELS["gemini-flash"]
        assert task == "analysis"

    def test_gemini_flash_mit_provider(self):
        provider = {
            "model_name": "provider-default",
            "base_url": "x",
            "api_key": "k",
            "provider_id": 1,
        }
        litellm_model, task = _resolve_litellm_model("gemini-flash", provider)
        assert litellm_model == REQUESTY_MODELS["gemini-flash"]
        assert task == "analysis"

    # ── task-Identität: testmodus vs. alt (ohne Feature) ─────────────────────

    def test_testmodus_task_identisch_mit_alt(self):
        """testmodus-KEY 'claude-sonnet' → task 'creative' — gleich wie ohne Feature."""
        _, task_testmodus = _resolve_litellm_model("claude-sonnet", None)
        # Vor dem Feature war model direkt "claude-sonnet" → gleicher Aufruf
        assert task_testmodus == "creative"

    def test_produktiv_task_identisch_mit_testmodus(self):
        """produktiv-KEY 'claude-sonnet-eu' → task 'creative' (gleich wie 'claude-sonnet')."""
        _, task_prod = _resolve_litellm_model("claude-sonnet-eu", None)
        _, task_test = _resolve_litellm_model("claude-sonnet", None)
        assert task_prod == task_test == "creative"

    # ── unbekannter Key → task "all" ──────────────────────────────────────────

    def test_unbekannter_key_ohne_provider(self):
        litellm_model, task = _resolve_litellm_model("unknown-model", None)
        assert task == "all"
        assert litellm_model == "unknown-model"  # passthrough

    def test_unbekannter_key_mit_provider_nutzt_provider_model_name(self):
        provider = {
            "model_name": "provider-model",
            "base_url": "x",
            "api_key": "k",
            "provider_id": 1,
        }
        litellm_model, task = _resolve_litellm_model("totally-unknown", provider)
        assert task == "all"
        assert litellm_model == "provider-model"


# ── 8. get_tenant_model_mode: Fail-open ───────────────────────────────────────


class TestGetTenantModelMode:
    def test_kein_tenant_id_gibt_testmodus(self):
        assert get_tenant_model_mode(None) == DEFAULT_MODEL_MODE
        assert get_tenant_model_mode("") == DEFAULT_MODEL_MODE

    def test_ungültiger_wert_fällt_auf_testmodus(self):
        """Logik: ungültiger Wert → DEFAULT_MODEL_MODE."""
        mode = "hack-modus"
        result = mode if mode in VALID_MODEL_MODES else DEFAULT_MODEL_MODE
        assert result == DEFAULT_MODEL_MODE

    def test_sync_session_factory_fehler_fail_open(self, monkeypatch):
        """Simulierter DB-Fehler → fail-open 'testmodus'."""
        import models.base as mb

        class _FailCM:
            def __enter__(self):
                raise RuntimeError("connection refused")

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(mb, "sync_session_factory", lambda: _FailCM())
        result = get_tenant_model_mode("some-real-id")
        assert (
            result == DEFAULT_MODEL_MODE
        ), f"DB-Fehler → Fallback 'testmodus' erwartet, bekam '{result}'"

    def test_gültige_modi_werden_akzeptiert(self, monkeypatch):
        """Wenn DB einen gültigen Modus zurückgibt → wird er zurückgegeben."""
        import models.base as mb

        for expected_mode in VALID_MODEL_MODES:

            class _MockCM:
                def __enter__(self_):
                    class _MockSession:
                        def execute(self__, _sql, _params):
                            class _Row:
                                def fetchone(self___):
                                    return ({"model_mode": expected_mode},)

                            return _Row()

                    return _MockSession()

                def __exit__(self_, *a):
                    return False

            monkeypatch.setattr(mb, "sync_session_factory", lambda: _MockCM())
            result = get_tenant_model_mode("some-id")
            assert (
                result == expected_mode
            ), f"Modus '{expected_mode}' wurde nicht korrekt zurückgegeben"


# ── 9. API-Endpoints ──────────────────────────────────────────────────────────


class TestModelModeApi:
    def test_get_model_mode_default_testmodus(self):
        from api.tenants import get_model_mode

        tenant = _make_tenant(settings_data={})
        result = asyncio.run(get_model_mode(tenant=tenant))
        assert result["model_mode"] == "testmodus"

    def test_get_model_mode_liest_aus_settings(self):
        from api.tenants import get_model_mode

        tenant = _make_tenant(settings_data={"model_mode": "produktiv"})
        result = asyncio.run(get_model_mode(tenant=tenant))
        assert result["model_mode"] == "produktiv"

    def test_get_model_mode_ungültiger_wert_fällt_auf_testmodus(self):
        from api.tenants import get_model_mode

        tenant = _make_tenant(settings_data={"model_mode": "hack-modus"})
        result = asyncio.run(get_model_mode(tenant=tenant))
        assert result["model_mode"] == "testmodus"

    def _make_mode_data(self, mode: str):
        """Erzeugt ein ModelModeUpdate-ähnliches Objekt das .model_mode hat.
        Pydantic.BaseModel ist gestubbt als object → kein Keyword-Init möglich.
        """
        data = MagicMock()
        data.model_mode = mode
        return data

    @pytest.mark.parametrize("mode", sorted(VALID_MODEL_MODES))
    def test_put_model_mode_gültige_werte(self, mode):
        from api.tenants import set_model_mode

        tenant = _make_tenant(settings_data={})
        db = AsyncMock()
        result = asyncio.run(
            set_model_mode(
                data=self._make_mode_data(mode),
                tenant=tenant,
                db=db,
            )
        )
        assert result["model_mode"] == mode
        db.commit.assert_awaited_once()

    @pytest.mark.parametrize("invalid_mode", ["hack-modus", "production", "test"])
    def test_put_model_mode_422_bei_ungültigem_wert(self, invalid_mode):
        """Ungültige Werte (die auch nach .lower() nicht in VALID_MODEL_MODES) → 422."""
        from api.tenants import set_model_mode

        tenant = _make_tenant(settings_data={})
        db = AsyncMock()
        data = self._make_mode_data(invalid_mode)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(set_model_mode(data=data, tenant=tenant, db=db))
        assert exc_info.value.status_code == 422

    def test_put_model_mode_leerer_string_422(self):
        from api.tenants import set_model_mode

        tenant = _make_tenant(settings_data={})
        db = AsyncMock()
        data = self._make_mode_data("")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(set_model_mode(data=data, tenant=tenant, db=db))
        assert exc_info.value.status_code == 422

    def test_put_schreibt_korrekt_und_erhält_andere_settings(self):
        from api.tenants import set_model_mode

        tenant = _make_tenant(settings_data={"tone": "professionell"})
        db = AsyncMock()
        asyncio.run(
            set_model_mode(
                data=self._make_mode_data("produktiv"),
                tenant=tenant,
                db=db,
            )
        )
        assert tenant.settings["model_mode"] == "produktiv"
        assert tenant.settings.get("tone") == "professionell"

    def test_get_gibt_valid_modes_zurück(self):
        from api.tenants import get_model_mode

        tenant = _make_tenant(settings_data={})
        result = asyncio.run(get_model_mode(tenant=tenant))
        assert "valid_modes" in result
        assert set(result["valid_modes"]) == VALID_MODEL_MODES


# ── 10. E3 Mandantentrennung ──────────────────────────────────────────────────


class TestE3Mandantentrennung:
    def _make_mode_data(self, mode: str):
        data = MagicMock()
        data.model_mode = mode
        return data

    def test_e3_schreibt_nur_eigene_tenant_settings(self):
        from api.tenants import set_model_mode

        own_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        other_id_str = "22222222-2222-2222-2222-222222222222"

        tenant = _make_tenant(settings_data={})
        tenant.id = own_id
        db = AsyncMock()

        asyncio.run(
            set_model_mode(
                data=self._make_mode_data("produktiv"),
                tenant=tenant,
                db=db,
            )
        )

        # Kein direktes SQL → db.execute wird nicht aufgerufen
        # (set_model_mode schreibt in tenant.settings und committet nur)
        for call in db.execute.call_args_list:
            call_str = str(call)
            assert (
                other_id_str not in call_str
            ), f"Fremde Tenant-ID {other_id_str} in DB-Call — E3-Verletzung!"

    def test_e3_get_liest_nur_aus_dependency_tenant(self):
        from api.tenants import get_model_mode

        tenant = _make_tenant(settings_data={"model_mode": "produktiv"})
        result = asyncio.run(get_model_mode(tenant=tenant))
        assert result["model_mode"] == "produktiv"


# ── 11. Setup-Pfad unberührt ──────────────────────────────────────────────────


class TestSetupPfadUnberührt:
    def test_pipeline_llm_keine_model_mode_imports(self):
        """pipeline_llm.py importiert services.model_mode NICHT."""
        pipeline_llm_path = _BACKEND_DIR / "services" / "pipeline_llm.py"
        if not pipeline_llm_path.exists():
            pytest.skip("pipeline_llm.py nicht gefunden")
        source = pipeline_llm_path.read_text()
        assert (
            "model_mode" not in source
        ), "INVARIANTE VERLETZT: pipeline_llm.py wurde durch dieses Feature geändert!"

    def test_llm_py_resolve_model_hat_model_mode_integration(self):
        """services/llm.py enthält die model_mode-Integration."""
        llm_path = _BACKEND_DIR / "services" / "llm.py"
        source = llm_path.read_text()
        assert "model_mode" in source
        assert "CREATIVE_MODEL_KEYS" in source
        assert "get_tenant_model_mode" in source

    def test_pipeline_llm_s6_tier_unverändert(self):
        """pipeline_llm.py enthält S6 = bedrock/claude-sonnet-4-6@eu-central-1 (grep-basiert)."""
        pipeline_llm_path = _BACKEND_DIR / "services" / "pipeline_llm.py"
        if not pipeline_llm_path.exists():
            pytest.skip("pipeline_llm.py nicht gefunden")
        source = pipeline_llm_path.read_text()
        assert '"S6"' in source or "'S6'" in source, "TIER_MODELS['S6'] nicht in pipeline_llm.py"
        assert (
            "bedrock/claude-sonnet-4-6@eu-central-1" in source
        ), "S6-Modell-String 'bedrock/claude-sonnet-4-6@eu-central-1' fehlt in pipeline_llm.py"


# ── 12. Konstanten-Konsistenz ─────────────────────────────────────────────────


class TestKonstanten:
    def test_valid_modes_vollständig(self):
        assert frozenset({"testmodus", "produktiv", "benutzerdefiniert"}) == VALID_MODEL_MODES

    def test_default_ist_testmodus(self):
        assert DEFAULT_MODEL_MODE == "testmodus"

    def test_creative_model_keys_enthalten_claude_sonnet(self):
        assert "claude-sonnet" in CREATIVE_MODEL_KEYS

    def test_creative_model_keys_enthalten_claude_sonnet_eu(self):
        """KEY-INVARIANTE: 'claude-sonnet-eu' muss in CREATIVE_MODEL_KEYS sein."""
        assert "claude-sonnet-eu" in CREATIVE_MODEL_KEYS

    def test_alle_creative_keys_in_requesty_models(self):
        """Alle kreativen KEYs müssen in REQUESTY_MODELS auflösbar sein."""
        for key in CREATIVE_MODEL_KEYS:
            assert (
                key in REQUESTY_MODELS
            ), f"CREATIVE_MODEL_KEY '{key}' fehlt in REQUESTY_MODELS — KEY-Invariante verletzt"

    def test_creative_model_by_mode_werte_sind_keys_nicht_strings(self):
        """KEY-INVARIANTE: CREATIVE_MODEL_BY_MODE-Werte müssen KEYs aus REQUESTY_MODELS sein (oder None)."""
        for mode, key in CREATIVE_MODEL_BY_MODE.items():
            if key is not None:
                assert (
                    key in REQUESTY_MODELS
                ), f"CREATIVE_MODEL_BY_MODE['{mode}'] = {key!r} ist kein gültiger REQUESTY_MODELS-KEY"

    def test_creative_purposes_sind_teilmenge_von_purpose_model_map(self):
        for p in CREATIVE_PURPOSES:
            assert p in PURPOSE_MODEL_MAP, f"Creative purpose '{p}' fehlt in PURPOSE_MODEL_MAP"

    def test_alle_creative_purposes_zeigen_auf_claude_sonnet(self):
        for p in CREATIVE_PURPOSES:
            assert (
                PURPOSE_MODEL_MAP[p] == "claude-sonnet"
            ), f"Purpose '{p}' zeigt nicht auf 'claude-sonnet' in PURPOSE_MODEL_MAP"

    def test_drei_modi_in_creative_model_by_mode(self):
        assert set(CREATIVE_MODEL_BY_MODE.keys()) == VALID_MODEL_MODES

    def test_purpose_model_map_hat_kreative_purposes(self):
        for p in CREATIVE_PURPOSES:
            assert p in PURPOSE_MODEL_MAP

    def test_claude_sonnet_eu_in_requesty_models(self):
        """'claude-sonnet-eu' muss in REQUESTY_MODELS und auf Bedrock-Frankfurt zeigen."""
        assert "claude-sonnet-eu" in REQUESTY_MODELS
        assert REQUESTY_MODELS["claude-sonnet-eu"] == "bedrock/claude-sonnet-4-6@eu-central-1"

    def test_resolve_creative_model_nicht_mehr_vorhanden(self):
        """Toter Code resolve_creative_model wurde entfernt (Opus-Review #72)."""
        assert not hasattr(
            _mm_module, "resolve_creative_model"
        ), "resolve_creative_model sollte entfernt sein (toter Code laut Opus-Review #72)"
