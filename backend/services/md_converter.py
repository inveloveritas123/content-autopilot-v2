"""
MD→JSON Konverter fuer Content-Autopilot v2 (Issue #57).

Konvertiert ein Markdown-Voice-Dokument in ein P03-Voice-Profil-JSON.
Nutzt Claude Haiku (sync Anthropic SDK) mit Cost-Cap-Pruefung.
"""

import asyncio
import json
import logging
import os
import re

import jsonschema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# ANTHROPIC_MODEL_ID entfernt (Issue #46): LLM-Call läuft über EU-Router-Seam
# Tier MD_CONVERTER → S2 (mistral/mistral-small-latest) in pipeline_llm.py
_MD_CONVERTER_PROMPT_KEY = "MD_CONVERTER"

INJECTION_PATTERNS = [
    r"(?i)(ignore (previous|above|prior)|forget (the|your)|new instruction)",
    r"(?i)(you are now|system prompt|act as|pretend you)",
    r"(?i)(jailbreak|dan mode|developer mode)",
]

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _extract_section(content: str, section: str) -> str:
    """Extrahiert den Inhalt einer Markdown-Sektion.

    Delegiert an die zentrale robuste Implementierung in prompt_loader.py.
    Identisches Verhalten: System-Prompt umfasst alle zwischenliegenden ##-Abschnitte.
    """
    from services.prompt_loader import _extract_section as _pl_extract

    return _pl_extract(content, section)


# ---------------------------------------------------------------------------
# Oeffentliche Service-Funktion
# ---------------------------------------------------------------------------


def convert_md_to_p03_json(
    md_content: str,
    tenant_id: str,
    storage_adapter=None,  # Optional, fuer PromptLoader — falls None: direkte Prompt-Datei
) -> dict:
    """Konvertiert Markdown-Voice-Dokument zu P03-JSON.

    Returns: validated P03-JSON dict.
    Raises: ValueError bei Injection-Verdacht, jsonschema.ValidationError bei Schema-Verletzung.
    """

    # ------------------------------------------------------------------
    # 1. Injection-Check
    # ------------------------------------------------------------------
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, md_content):
            logger.warning("Possible prompt injection in MD upload: pattern=%s", pattern)
            raise ValueError("Moeglicher Injection-Versuch im hochgeladenen Dokument erkannt.")

    # ------------------------------------------------------------------
    # 2. Prompt laden
    # ------------------------------------------------------------------
    if storage_adapter is not None:
        # Via PromptLoader aus Nextcloud
        from services.prompt_loader import PromptLoader

        loader = PromptLoader(storage_adapter=storage_adapter)
        loaded = loader.load("P03")
        system_prompt = loaded.system_prompt
        user_template = loaded.user_prompt_template
    else:
        # Direkt aus lokaler Prompt-Datei
        prompt_file = os.path.join(os.path.dirname(__file__), "../prompts/md_to_p03_converter.md")
        with open(prompt_file, encoding="utf-8") as f:
            raw = f.read()
        system_prompt = _extract_section(raw, "System-Prompt")
        user_template = _extract_section(raw, "User-Prompt")

    # {md_content}-Platzhalter direkt ersetzen (kein format() um Injection zu vermeiden)
    user_prompt = user_template.replace("{md_content}", md_content)

    # ------------------------------------------------------------------
    # 3. Cost-Cap prüfen (async via asyncio.run)
    # ------------------------------------------------------------------
    async def _check_cost() -> None:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        from config import settings as s
        from services.cost_cap import CostCapMiddleware, estimate_anthropic_cost

        engine = create_async_engine(s.database_url)
        SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with SessionLocal() as sess:
            mw = CostCapMiddleware(sess)
            # Schätzung mit Haiku-Preis als konservativem Fallback (S2-Tier ist günstiger)
            est = estimate_anthropic_cost(
                "claude-haiku-4-5",
                len(md_content) // 4,  # grobe Token-Schaetzung
                1000,  # Output-Budget
            )
            await mw.check_and_record(tenant_id, est)

    try:
        asyncio.run(_check_cost())
    except RuntimeError as _loop_err:
        if "event loop is already running" in str(_loop_err):
            # FastAPI-Kontext: Event Loop läuft bereits — Cost-Check muss vom Caller
            # via await aufgerufen werden. Hier nur warnen, nicht blockieren.
            logger.warning(
                "md_converter: asyncio.run() nicht möglich (laufende Event Loop) — "
                "Cost-Cap wurde NICHT geprüft. Caller sollte convert_md_to_p03_json "
                "als async aufrufen oder nest_asyncio einsetzen."
            )
        else:
            raise

    # ------------------------------------------------------------------
    # 4. LLM-Call über EU-Router-Seam (Issue #46: kein direkter Anthropic-Call)
    #    Tier MD_CONVERTER → S2 (mistral/mistral-small-latest)
    # ------------------------------------------------------------------
    from services.pipeline_llm import call_pipeline_llm

    llm_result = call_pipeline_llm(
        prompt_key=_MD_CONVERTER_PROMPT_KEY,
        system_prompt=system_prompt,
        user_content=user_prompt,
        tenant_id=tenant_id,
    )
    raw_text = llm_result.text.strip()

    # ------------------------------------------------------------------
    # 5. JSON-Parsing
    # ------------------------------------------------------------------
    raw_clean = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    output_json = json.loads(raw_clean)

    # ------------------------------------------------------------------
    # 6. Schema-Validierung
    # ------------------------------------------------------------------
    schema_file = os.path.join(os.path.dirname(__file__), "../schemas/p03_output_schema.json")
    if os.path.exists(schema_file):
        with open(schema_file, encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(output_json, schema)
    else:
        logger.warning(
            "md_converter: Schema-Datei nicht gefunden (%s) — Validierung übersprungen. "
            "Stellen Sie sicher, dass p03_output_schema.json deployed ist.",
            schema_file,
        )

    # ------------------------------------------------------------------
    # 7. Return
    # ------------------------------------------------------------------
    logger.info(
        "md_converter: P03-JSON erfolgreich erstellt fuer tenant=%s, Felder=%d",
        tenant_id,
        len(output_json),
    )
    return output_json
