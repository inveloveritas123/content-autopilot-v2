"""
PromptLoader — Laedt Markdown-Prompts aus Nextcloud mit In-Memory-Cache und TTL.

Cache-Logik:
- Innerhalb TTL: stat()-Check gegen mtime, Refresh nur bei aenderung
- Ausserhalb TTL oder kein Cache: Vollstaendiges Laden
- Bei Storage-Fehler: direkte Exception, kein Stale-Fallback

Extraktion (Ansatz B — Loader tolerant, Dateien unangetastet):
- system_prompt  = Text zwischen ^## System-Prompt und ^## User-Prompt (oder Dateiende).
                   Zwischenliegende ## / ### Abschnitte BLEIBEN Teil des Blocks.
- user_prompt    = Text zwischen ^## User-Prompt und naechstem ^## (oder Dateiende).
                   Falls kein exakter ^## User-Prompt vorhanden: leerer String.
- Fence-Bereinigung: fuehrende ```lang und abschliessende ``` werden entfernt;
                     unbalancierte Einzelfences an Blockanfang/-ende ebenfalls.
                     Interne, balancierte Fences bleiben unveraendert.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from services.brand_voice_storage import BrandVoiceStorageAdapter, StorageError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt-Pfade
# ---------------------------------------------------------------------------

# Relative Pfade unter der content-truth-Wurzel (werden vom Storage-Adapter aufgeloest).
# NC-Pfad-Logik ist deprecated — der LocalFsAdapter haengt base_dir vorne an.
PROMPT_PATHS: dict[str, str] = {
    "P01": "prompts/P01-kundenkontext-extraktion.md",
    "P03": "prompts/P03-voice-analyse.md",
    "P04": "prompts/P04-kundenavatar-vertiefung.md",
    "P07": "prompts/P07-themen-research.md",
    "P08": "prompts/P08-fragen-konversation.md",
    "P09": "prompts/P09-content-ideen.md",
    "P10": "prompts/P10-content-kern-aufbau.md",
    "P12": "prompts/P12-post-generierung.md",
    "P12b": "prompts/P12b-post-optimierung.md",
    "P12c": "prompts/P12c-carousel-generator.md",
    "P13": "prompts/P13-hook-varianten.md",
    "P15": "prompts/P15-eigene-idee.md",
    "P16": "prompts/P16-post-ueberarbeitung.md",
    # P17 reaktiviert (Issue #41/#20): Heading-Fix #22 gelandet (## System-Prompt Z.35,
    # ## User-Prompt Z.241) → Loader liefert nicht-leeren System-Prompt. Ohne diese
    # Registrierung war der Beobachter komplett tot (KeyError). Tier S2 (pipeline_llm).
    "P17": "prompts/P17-kundenkontext-update.md",
    "fragenkatalog": "rules/fragenkatalog.md",
    "hookmaster": "rules/hookmaster.md",
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class LoadedPrompt:
    content: str  # vollstaendiger Markdown-Inhalt
    system_prompt: str  # extrahiert aus ## System-Prompt Block
    user_prompt_template: str  # extrahiert aus ## User-Prompt Block
    sha: str  # SHA-256 von content (hex)
    loaded_at: datetime  # timezone-aware UTC
    source_path: str  # Pfad in NC


# ---------------------------------------------------------------------------
# Hilfsfunktion: Fence-Bereinigung
# ---------------------------------------------------------------------------


def _strip_outer_fence(block: str) -> str:
    """Entfernt den aeusseren Code-Fence eines Markdown-Blocks.

    Faelle:
    1. Block beginnt mit ``` (oeffnender Fence) UND enthaelt eine abschliessende
       ```-Zeile (allein auf der Zeile): Inhalt zwischen beiden Fences wird
       zurueckgegeben. Moeglicher Inhalt NACH dem schliessenden Fence
       (z.B. '---'-Trennzeilen) wird verworfen — er gehoert zum Markdown-
       Rahmen, nicht zum Prompt-Inhalt.
    2. Block beginnt mit ``` aber hat keinen Abschluss: fuehrendes ``` entfernen.
    3. Block beginnt nicht mit ```: unveraendert zurueckgeben.

    Interne, balancierte Fences (z.B. Code-Beispiele im System-Prompt) bleiben
    vollstaendig erhalten, da nur der aeussere Wrapper entfernt wird.
    """
    stripped = block.strip()
    if not stripped.startswith("```"):
        return stripped

    # Finde die erste Zeile (oeffnender Fence)
    first_nl = stripped.find("\n")
    if first_nl < 0:
        # Nur ein ```, kein Inhalt
        return ""

    after_open = stripped[first_nl + 1 :]

    # Suche nach abschliessendem ``` (allein auf einer Zeile).
    # Zwei Formen:
    #   (a) Innerhalb des Texts: nach einem Zeilenumbruch: \n```...
    #   (b) Direkt am Anfang von after_open (z.B. bei "```\n```")
    close_m = re.search(r"(?:^|\n)[ \t]*```[ \t]*(?:\n|$)", after_open)
    if close_m:
        # Alles vor dem schliessenden Fence-Marker ist der Prompt-Inhalt
        return after_open[: close_m.start()].strip()

    # Kein schliessender Fence — gesamten Rest nach oeffnendem Fence zurueckgeben
    return after_open.strip()


# ---------------------------------------------------------------------------
# Hilfsfunktion: Markdown-Sektion extrahieren (robuste Version)
# ---------------------------------------------------------------------------


def _extract_section(content: str, section: str) -> str:
    """Extrahiert den Inhalt einer Markdown-Sektion robust.

    Ansatz B: Fuer 'System-Prompt' wird der gesamte Text bis zum naechsten
    ^## User-Prompt extrahiert — zwischenliegende ##/### Abschnitte bleiben
    Teil des Blocks (sie gehoeren zum System-Prompt-Inhalt der Datei).

    Fuer 'User-Prompt' wird nur der Text bis zur naechsten ^## Ueberschrift
    extrahiert.

    Fence-Bereinigung: aeusserer Code-Fence wird entfernt.
    Interne Fences bleiben unveraendert.

    Rueckwaertskompatibel fuer beliebige section-Namen: falls weder
    'System-Prompt' noch 'User-Prompt' uebergeben wird, faellt die Funktion
    auf das alte Verhalten zurueck (naechstes ^## oder Dateiende).
    """
    if section == "System-Prompt":
        return _extract_system_prompt(content)
    if section == "User-Prompt":
        return _extract_user_prompt(content)

    # Generischer Fallback fuer andere Sektionsnamen (altes Verhalten)
    pattern = rf"^##\s+{re.escape(section)}\s*\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not m:
        return ""
    block = m.group(1).strip()
    fence_m = re.match(r"^```\w*\n(.*?)```\s*$", block, re.DOTALL)
    return fence_m.group(1).strip() if fence_m else block


def _extract_system_prompt(content: str) -> str:
    """Extrahiert den System-Prompt: alles von ^## System-Prompt bis ^## User-Prompt.

    Falls kein ^## User-Prompt existiert: bis Dateiende.
    Zwischenliegende ##/### Abschnitte BLEIBEN Teil des System-Prompts.
    """
    sys_m = re.search(r"^## System-Prompt\b", content, re.MULTILINE)
    if sys_m is None:
        return ""

    # Suche nach ^## User-Prompt (beliebiger Suffix erlaubt: "User-Prompt: MODE OPENER" etc.)
    user_m = re.search(r"^## User-Prompt\b", content[sys_m.end() :], re.MULTILINE)

    if user_m is not None:
        end_pos = sys_m.end() + user_m.start()
        block = content[sys_m.end() : end_pos].strip()
    else:
        block = content[sys_m.end() :].strip()

    return _strip_outer_fence(block)


def _extract_user_prompt(content: str) -> str:
    """Extrahiert den User-Prompt: alles von ^## User-Prompt bis naechstes ^##.

    Akzeptiert dieselben Ueberschriften wie `_extract_system_prompt` — also auch
    '## User-Prompt: MODE RESPONSE'.

    ⚠️ Diese Toleranz ist der Fix eines stillen Totalausfalls (Befund 04.08.2026):
    `_extract_system_prompt` suchte die Endmarke mit `^## User-Prompt\\b` und traf
    '## User-Prompt: MODE OPENER'; diese Funktion verlangte `^## User-Prompt[ \\t]*$`,
    exakt und ohne Zusatz — kein Treffer, leerer User-Prompt. Dieselbe Datei, zwei
    Regexe mit verschiedener Strenge. Produktiv lief deshalb monatelang ein
    789-Byte-Stummel statt des entworfenen 18-KB-Prompts.

    Bei mehreren '## User-Prompt…'-Ueberschriften greift die ERSTE. Der Code ruft
    genau EIN Template auf und uebergibt den Modus als Platzhalter — eine Datei mit
    mehreren Modus-Abschnitten bekaeme also nur den ersten. Das ist Absicht: die
    Prompt-Datei muss dem Vertrag des Codes folgen, nicht umgekehrt.

    Falls kein ^## User-Prompt existiert: leerer String.
    """
    user_m = re.search(r"^## User-Prompt\b", content, re.MULTILINE)
    if user_m is None:
        return ""

    # Ab dem Zeilenende der Ueberschrift — sonst landete ': MODE RESPONSE' im Text.
    zeilenende = content.find("\n", user_m.end())
    rest = content[zeilenende + 1 :] if zeilenende != -1 else ""
    next_h = re.search(r"^## ", rest, re.MULTILINE)
    if next_h:
        block = rest[: next_h.start()].strip()
    else:
        block = rest.strip()

    return _strip_outer_fence(block)


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
        now = datetime.now(UTC)

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
                f"Unbekannter Prompt: {prompt_name!r}. " f"Bekannte Prompts: {list(PROMPT_PATHS)}"
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
        loaded_at = datetime.now(UTC)

        # Warnung bei leeren oder strukturell auffaelligen Prompts
        if not system_prompt:
            logger.warning(
                "prompt_loader: %r — system_prompt ist LEER (kein ## System-Prompt gefunden in %r)",
                prompt_name,
                path,
            )
        elif system_prompt.startswith("```") or system_prompt.endswith("```"):
            logger.warning(
                "prompt_loader: %r — system_prompt hat unbalancierte Fences (erste 80 Zeichen: %r)",
                prompt_name,
                system_prompt[:80],
            )

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
    # Nutzt get_default_storage_adapter() — defaultmaessig LocalFsStorageAdapter.
    # get_default_nc_adapter bleibt importierbar fuer Rueckwaertskompatibilitaet (deprecated).
    from services.brand_voice_storage import get_default_storage_adapter

    return PromptLoader(storage_adapter=get_default_storage_adapter())
