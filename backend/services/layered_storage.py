"""
LayeredStorageAdapter — Komponiert ein beschreibbares Overlay ueber einer read-only Base.

Lese-Semantik: Overlay-first, Fallback auf Base.
Schreib-Semantik: ausschliesslich Overlay (Base ist :ro gemountet).

Verwendet von:
- api/prompt_studio.py  — Prompt-Studio-Endpunkte
- services/brand_voice_storage.py  — get_default_storage_adapter (localfs-Pfad)

Alle Traversal- und Symlink-Schutz-Massnahmen greifen automatisch, da
Overlay und Base beides LocalFsStorageAdapter-Instanzen sind.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from services.brand_voice_storage import (
    BrandVoiceStorageAdapter,
    StorageEntry,
    StorageStat,
    StorageError,
)

logger = logging.getLogger(__name__)

# Quelle einer Datei: effektiver Lese-Layer
Source = Literal["base", "overlay"]


class LayeredStorageAdapter:
    """Komponiert ein beschreibbares Overlay ueber einer read-only Base.

    Das Overlay-Verzeichnis muss beim Start nicht existieren:
    - exists()  liefert False fuer Overlay-Anfragen → faellt auf Base zurueck
    - list()    faengt StorageError des Overlay-Layers ab → liefert nur Base
    - write()   legt Verzeichnisse via os.makedirs an (im LocalFsStorageAdapter)

    Protokoll-Konformitaet: implementiert BrandVoiceStorageAdapter vollstaendig,
    kann als Drop-in fuer PromptLoader und alle anderen Konsumenten eingesetzt
    werden.
    """

    def __init__(
        self,
        overlay: BrandVoiceStorageAdapter,  # LocalFsStorageAdapter(base_dir=overlay_path)
        base: BrandVoiceStorageAdapter,     # LocalFsStorageAdapter(base_dir=content_truth_path)
    ) -> None:
        self._overlay = overlay
        self._base = base

    # ------------------------------------------------------------------
    # BrandVoiceStorageAdapter-Protocol
    # ------------------------------------------------------------------

    def read(self, path: str) -> bytes:
        """Liest overlay-first; faellt auf Base zurueck wenn Overlay fehlt."""
        if self._overlay_exists_safe(path):
            return self._overlay.read(path)
        return self._base.read(path)

    def stat(self, path: str) -> StorageStat:
        """Gibt Metadaten overlay-first zurueck.

        Wichtig fuer PromptLoader-mtime-Check: nach einem Save zeigt stat()
        die Overlay-mtime, die neuer als loaded_at ist → Cache-Refresh.
        """
        if self._overlay_exists_safe(path):
            return self._overlay.stat(path)
        return self._base.stat(path)

    def exists(self, path: str) -> bool:
        """True wenn Datei in Overlay ODER Base existiert."""
        return self._overlay_exists_safe(path) or self._base.exists(path)

    def write(self, path: str, content: bytes) -> None:
        """Schreibt IMMER ins Overlay (Base ist :ro).

        LocalFsStorageAdapter.write() legt Parent-Verzeichnisse automatisch
        an — auch wenn das Overlay-Verzeichnis bisher nicht existiert.
        """
        self._overlay.write(path, content)

    def list(self, path: str) -> list[StorageEntry]:
        """Gibt die gemergte, deduplizierte, sortierte Dateiliste zurueck.

        Namens-Duplikate (Overlay shadowed Base) werden einmalig aufgenommen;
        Overlay-Eintraege gewinnen bei Konflikten.
        """
        entries_map: dict[str, StorageEntry] = {}

        # Base-Eintraege zuerst einlesen
        try:
            for entry in self._base.list(path):
                entries_map[entry.name] = entry
        except StorageError:
            pass

        # Overlay-Eintraege ueberschreiben Base-Duplikate
        try:
            for entry in self._overlay.list(path):
                entries_map[entry.name] = entry
        except StorageError:
            # Overlay-Verzeichnis existiert noch nicht → kein Fehler
            pass

        return sorted(entries_map.values(), key=lambda e: e.name)

    # ------------------------------------------------------------------
    # Zusatz-API — nur vom Prompt-Studio genutzt
    # ------------------------------------------------------------------

    def source_of(self, path: str) -> Optional[Source]:
        """Gibt 'overlay' wenn Overlay-Datei existiert, 'base' wenn nur Base,
        None wenn nirgends vorhanden."""
        if self._overlay_exists_safe(path):
            return "overlay"
        if self._base.exists(path):
            return "base"
        return None

    def list_with_source(
        self, path: str
    ) -> list[tuple[StorageEntry, Source, StorageStat]]:
        """Gemergte Liste mit Quell-Layer und effektivem Stat.

        Source = 'overlay' wenn Datei im Overlay liegt (shadowed Base),
                 'base' wenn nur in der Base.
        StorageStat des effektiv gelesenen Layers (overlay-first).
        """
        # Alle Dateinamen aus Base und Overlay sammeln
        names_base: dict[str, StorageEntry] = {}
        names_overlay: dict[str, StorageEntry] = {}

        try:
            for entry in self._base.list(path):
                if not entry.is_directory:
                    names_base[entry.name] = entry
        except StorageError:
            pass

        try:
            for entry in self._overlay.list(path):
                if not entry.is_directory:
                    names_overlay[entry.name] = entry
        except StorageError:
            pass

        # Mergen: Overlay-Eintraege gewinnen
        all_names = dict(names_base)
        all_names.update(names_overlay)

        result: list[tuple[StorageEntry, Source, StorageStat]] = []
        for name, entry in sorted(all_names.items()):
            if name in names_overlay:
                source: Source = "overlay"
                try:
                    stat = self._overlay.stat(entry.path.lstrip("/"))
                except StorageError:
                    stat = self._base.stat(entry.path.lstrip("/"))
            else:
                source = "base"
                try:
                    stat = self._base.stat(entry.path.lstrip("/"))
                except StorageError:
                    continue
            result.append((entry, source, stat))

        return result

    def stat_base(self, path: str) -> Optional[StorageStat]:
        """Base-Metadaten, auch wenn ein Overlay existiert.

        Wird vom Prompt-Studio verwendet um 'Base neuer als Overlay'-Warnungen
        zu erzeugen.
        """
        try:
            return self._base.stat(path)
        except StorageError:
            return None

    def delete_overlay(self, path: str) -> bool:
        """Loescht NUR die Overlay-Datei (os.unlink via LocalFsStorageAdapter.delete).

        Gibt True zurueck wenn geloescht, False wenn kein Overlay existierte.
        Base wird nie angefasst. → Revert-to-Base-Operation.

        Traversal-Schutz: _resolve() im LocalFsStorageAdapter blockt '../'-Versuche.
        """
        if not self._overlay_exists_safe(path):
            return False
        self._overlay.delete(path)
        return True

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _overlay_exists_safe(self, path: str) -> bool:
        """Prueft Overlay-Existenz; gibt False zurueck wenn Verzeichnis fehlt."""
        try:
            return self._overlay.exists(path)
        except StorageError:
            return False
