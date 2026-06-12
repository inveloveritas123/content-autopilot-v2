"""
LocalFsStorageAdapter — liest und schreibt Dateien direkt aus dem lokalen Filesystem.
Dient als Default-Ersatz fuer den Nextcloud-WebDAV-Adapter.
"""

import contextlib
import os
import tempfile
from datetime import UTC, datetime

from services.brand_voice_storage import StorageEntry, StorageError, StorageStat


class LocalFsStorageAdapter:
    """Liest/schreibt Dateien relativ zu einem konfigurierbaren Basisverzeichnis."""

    def __init__(self, base_dir: str) -> None:
        # Absoluten Pfad normalisieren, damit Path-Traversal-Pruefung zuverlaessig funktioniert
        self._base_dir = os.path.abspath(base_dir)
        # realpath der Wurzel fuer die Symlink-Escape-Pruefung (einmalig aufgeloest)
        self._base_real = os.path.realpath(self._base_dir)

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _resolve(self, path: str) -> str:
        """Gibt den absoluten Dateisystempfad fuer einen logischen Pfad zurueck.

        Fuehrendes '/' wird abgeschnitten, damit path relativ unter base_dir haengt.
        Path-Traversal (z.B. '../../etc/passwd') wird mit StorageError geblockt.
        """
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(self._base_dir, rel))
        # 1) Lexikalische Pruefung: blockt '../'-Traversal
        if not full.startswith(self._base_dir + os.sep) and full != self._base_dir:
            raise StorageError(
                f"Path-Traversal-Versuch blockiert: {path!r}",
                path,
            )
        # 2) realpath-Pruefung: blockt Symlinks innerhalb base_dir, die nach aussen zeigen
        real = os.path.realpath(full)
        if not real.startswith(self._base_real + os.sep) and real != self._base_real:
            raise StorageError(
                f"Symlink-Escape blockiert: {path!r}",
                path,
            )
        return full

    # ------------------------------------------------------------------
    # Oeffentliche API (BrandVoiceStorageAdapter-Protocol)
    # ------------------------------------------------------------------

    def read(self, path: str) -> bytes:
        """Liest den Dateiinhalt als Bytes."""
        full = self._resolve(path)
        try:
            with open(full, "rb") as fh:
                return fh.read()
        except OSError as exc:
            raise StorageError(f"Lesen fehlgeschlagen: {exc}", path) from exc

    def write(self, path: str, content: bytes) -> None:
        """Schreibt Bytes atomar (temp-Datei + os.replace); legt Parent-Verzeichnisse an."""
        full = self._resolve(path)
        parent = os.path.dirname(full)
        os.makedirs(parent, exist_ok=True)
        # Atomares Schreiben: erst in temp, dann umbenennen
        try:
            fd, tmp_path = tempfile.mkstemp(dir=parent, prefix=".tmp_")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(content)
                os.replace(tmp_path, full)
            except Exception:
                # Aufräumen bei Fehler
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise
        except OSError as exc:
            raise StorageError(f"Schreiben fehlgeschlagen: {exc}", path) from exc

    def exists(self, path: str) -> bool:
        """Prueft ob die Datei/das Verzeichnis existiert."""
        try:
            full = self._resolve(path)
        except StorageError:
            return False
        return os.path.exists(full)

    def stat(self, path: str) -> StorageStat:
        """Gibt Metadaten (mtime, size, etag) fuer eine Datei zurueck."""
        full = self._resolve(path)
        try:
            st = os.stat(full)
        except OSError as exc:
            raise StorageError(f"stat() fehlgeschlagen: {exc}", path) from exc
        mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC)
        size = st.st_size
        # ETag aus mtime in Nanosekunden + Groesse — stabil auch bei zwei Writes/Sekunde
        etag = f"{st.st_mtime_ns}-{size}"
        return StorageStat(mtime=mtime, size=size, etag=etag)

    def delete(self, path: str) -> None:
        """Loescht eine Datei atomar (os.unlink) mit Traversal-Schutz.

        Wird von LayeredStorageAdapter.delete_overlay() genutzt.
        Wirft StorageError wenn die Datei nicht existiert oder nicht geloescht
        werden kann.
        """
        full = self._resolve(path)
        try:
            os.unlink(full)
        except OSError as exc:
            raise StorageError(f"Loeschen fehlgeschlagen: {exc}", path) from exc

    def list(self, path: str) -> list[StorageEntry]:
        """Listet den Inhalt eines Verzeichnisses sortiert auf."""
        full = self._resolve(path)
        try:
            names = sorted(os.listdir(full))
        except OSError as exc:
            raise StorageError(f"Verzeichnis lesen fehlgeschlagen: {exc}", path) from exc
        entries: list[StorageEntry] = []
        for name in names:
            child_full = os.path.join(full, name)
            # Pfad relativ zu base_dir, mit fuehrendem '/' als kanonische Form
            rel = os.path.relpath(child_full, self._base_dir)
            entry_path = "/" + rel.replace(os.sep, "/")
            entries.append(
                StorageEntry(
                    name=name,
                    path=entry_path,
                    is_directory=os.path.isdir(child_full),
                )
            )
        return entries
