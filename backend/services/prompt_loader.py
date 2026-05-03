"""
PromptLoader — Laedt Markdown-Prompts aus Nextcloud mit In-Memory-Cache und TTL.

Cache-Logik:
- Innerhalb TTL: stat()-Check gegen mtime, Refresh nur bei aenderung
- Ausserhalb TTL oder kein Cache: Vollstaendiges Laden
- Bei Storage-Fehler: direkte Exception, kein Stale-Fallback
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.brand_voice_storage import BrandVoiceStorageAdapter, StorageError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt-Pfade
# ---------------------------------------------------------------------------

def _prompt_base() -> str:
    from config import settings as _s
    return _s.prompt_nc_base_path


_PROMPT_BASE = _prompt_base()

PROMPT_PATHS: dict[str, str] = {
    "P01":          _PROMPT_BASE + "P01-kundenkontext-extraktion.md",
    "P03":          _PROMPT_BASE + "P03-voice-profile.md",
    "P04":          _PROMPT_BASE + "P04-audience-avatar.md",
    "P12":          _PROMPT_BASE + "P12-content-generator.md",
    "P12b":         _PROMPT_BASE + "P12b-content-generator-short.md",
    "P12c":         _PROMPT_BASE + "P12c-carousel-generator.md",
    "fragenkatalog": _PROMPT_BASE + "fragenkatalog.md",
    "hookmaster":   _PROMPT_BASE + "hookmaster.md",
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class LoadedPrompt:
    content: str                  # vollstaendiger Markdown-Inhalt
    system_prompt: str            # extrahiert aus ## System-Prompt Block
    user_prompt_template: str     # extrahiert aus ## User-Prompt Block
    sha: str                      # SHA-256 von content (hex)
    loaded_at: datetime           # timezone-aware UTC
    source_path: str              # Pfad in NC


# ---------------------------------------------------------------------------
# Hilfsfunktion: Markdown-Sektion extrahieren
# ---------------------------------------------------------------------------

def _extract_section(content: str, section: str) -> str:
    """Extrahiert den Inhalt einer Markdown-Sektion (## section ... ## next)."""
    pattern = rf"^##\s+{re.escape(section)}\s*\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not m:
        return ""
    block = m.group(1).strip()
    # Code-Zaun entfernen, falls vorhanden
    fence_m = re.match(r"^```\w*\n(.*?)```\s*$", block, re.DOTALL)
    return fence_m.group(1).strip() if fence_m else block


# ---------------------------------------------------------------------------
# PromptLoader
# ---------------------------------------------------------------------------

class PromptLoader:
    def __init__(
        self,
        storage_adapter: BrandVoiceStorageAdapter,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._adapter = storage_adapter
        self._ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: dict[str, LoadedPrompt] = {}

    # ------------------------------------------------------------------
    # Oeffentliche API
    # ------------------------------------------------------------------

    def load(self, prompt_name: str) -> LoadedPrompt:
        """Laedt den Prompt aus NC oder dem Cache.

        Cache-Hit-Bedingung:
        - Eintrag im Cache AND loaded_at + TTL > now()
        - UND stat().mtime <= loaded_at (Datei hat sich nicht geaendert)

        Bei Storage-Fehler: direkte Exception, kein Stale-Fallback.
        """
        path = self._resolve_path(prompt_name)
        now = datetime.now(timezone.utc)

        cached = self._cache.get(prompt_name)
        if cached is not None and (cached.loaded_at + self._ttl) > now:
            # TTL noch gueltig — stat-Check
            try:
                stat = self._adapter.stat(path)
                if stat.mtime <= cached.loaded_at:
                    logger.debug("prompt_loader: cache hit fuer %r", prompt_name)
                    return cached
                logger.debug(
                    "prompt_loader: mtime neuer als Cache (%s > %s), refresh fuer %r",
                    stat.mtime,
                    cached.loaded_at,
                    prompt_name,
                )
            except StorageError:
                # stat gescheitert → kein Stale-Fallback, stattdessen frischen Load versuchen
                # Falls danach auch read() scheitert, wird die Exception direkt re-raised
                logger.warning(
                    "prompt_loader: stat() fuer %r fehlgeschlagen, versuche trotzdem zu laden",
                    prompt_name,
                )

        # Vollstaendiges Laden aus NC
        return self._fetch_and_cache(prompt_name, path)

    def invalidate(self, prompt_name: str) -> None:
        """Entfernt einen einzelnen Eintrag aus dem Cache."""
        removed = self._cache.pop(prompt_name, None)
        if removed is not None:
            logger.debug("prompt_loader: cache invalidiert fuer %r", prompt_name)

    def invalidate_all(self) -> None:
        """Leert den gesamten Cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.debug("prompt_loader: %d Cache-Eintraege geleert", count)

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _resolve_path(self, prompt_name: str) -> str:
        """Liefert den NC-Pfad fuer einen bekannten Prompt-Namen."""
        path = PROMPT_PATHS.get(prompt_name)
        if path is None:
            raise KeyError(
                f"Unbekannter Prompt: {prompt_name!r}. "
                f"Bekannte Prompts: {list(PROMPT_PATHS)}"
            )
        return path

    def _fetch_and_cache(self, prompt_name: str, path: str) -> LoadedPrompt:
        """Laedt Datei aus NC, parst sie und speichert im Cache."""
        logger.debug("prompt_loader: lade %r von %r", prompt_name, path)

        raw: bytes = self._adapter.read(path)  # StorageError wird direkt re-raised
        content = raw.decode("utf-8")

        system_prompt = _extract_section(content, "System-Prompt")
        user_prompt_template = _extract_section(content, "User-Prompt")
        sha = hashlib.sha256(raw).hexdigest()
        loaded_at = datetime.now(timezone.utc)

        prompt = LoadedPrompt(
            content=content,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            sha=sha,
            loaded_at=loaded_at,
            source_path=path,
        )
        self._cache[prompt_name] = prompt
        logger.info(
            "prompt_loader: %r geladen, sha=%s, system_prompt=%d Zeichen, user_prompt=%d Zeichen",
            prompt_name,
            sha[:12],
            len(system_prompt),
            len(user_prompt_template),
        )
        return prompt


# ---------------------------------------------------------------------------
# Default-Instance Factory
# ---------------------------------------------------------------------------

def get_default_prompt_loader() -> PromptLoader:
    from services.brand_voice_storage import get_default_nc_adapter
    return PromptLoader(storage_adapter=get_default_nc_adapter())
