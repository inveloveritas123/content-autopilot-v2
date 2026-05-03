import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import unquote

import httpx

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StorageEntry:
    name: str
    path: str
    is_directory: bool


@dataclass
class StorageStat:
    mtime: datetime
    size: int
    etag: str


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class StorageError(Exception):
    def __init__(self, message: str, path: str) -> None:
        super().__init__(message)
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"StorageError({self.message!r}, path={self.path!r})"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class BrandVoiceStorageAdapter(Protocol):
    def list(self, path: str) -> list[StorageEntry]: ...
    def read(self, path: str) -> bytes: ...
    def write(self, path: str, content: bytes) -> None: ...
    def exists(self, path: str) -> bool: ...
    def stat(self, path: str) -> StorageStat: ...


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _get_brand_voice_base() -> str:
    from config import settings as _s
    return _s.brand_voice_nc_base_path


def tenant_voice_path(slug: str, sub: str = "") -> str:
    base = _get_brand_voice_base().rstrip("/") + f"/{slug}/"
    return base + sub if sub else base


# ---------------------------------------------------------------------------
# NextcloudWebDAVAdapter
# ---------------------------------------------------------------------------

_PROPFIND_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:">
    <d:prop>
        <d:displayname/>
        <d:getcontentlength/>
        <d:getlastmodified/>
        <d:getetag/>
        <d:resourcetype/>
    </d:prop>
</d:propfind>"""

_NS = {"d": "DAV:"}


class NextcloudWebDAVAdapter:
    def __init__(self, base_url: str, user: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._user = user
        self._token = token
        self._dav_base = f"{self._base_url}/remote.php/dav/files/{self._user}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth(self) -> tuple[str, str]:
        return (self._user, self._token)

    def _url(self, path: str) -> str:
        """Build absolute WebDAV URL for the given logical path."""
        # Ensure path starts with /
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._dav_base}{path}"

    def _client(self, timeout: float = 30.0) -> httpx.Client:
        return httpx.Client(timeout=timeout)

    def _raise_for_status(self, resp: httpx.Response, path: str) -> None:
        """Re-raise HTTP errors as StorageError."""
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise StorageError(
                f"HTTP {exc.response.status_code} for {exc.request.url}",
                path,
            ) from exc

    def _parse_entries(self, xml_text: str, request_path: str) -> list[StorageEntry]:
        """Parse PROPFIND Depth=1 response into StorageEntry list (root excluded)."""
        root = ET.fromstring(xml_text)
        dav_base_path = f"/remote.php/dav/files/{self._user}"
        req_clean = request_path.rstrip("/")

        entries: list[StorageEntry] = []
        for response in root.findall(".//d:response", _NS):
            href_el = response.find("d:href", _NS)
            href = href_el.text if href_el is not None else ""

            clean_path = unquote(href.replace(dav_base_path, "")).rstrip("/")

            # Skip the requested folder itself
            if clean_path == req_clean or clean_path == "":
                continue

            displayname_el = response.find(".//d:displayname", _NS)
            name = (
                displayname_el.text
                if displayname_el is not None and displayname_el.text
                else clean_path.split("/")[-1]
            )
            is_dir = response.find(".//d:resourcetype/d:collection", _NS) is not None

            entries.append(StorageEntry(name=name, path=clean_path, is_directory=is_dir))

        return entries

    def _mkcol_parents(self, path: str) -> None:
        """Ensure all parent directories exist (MKCOL, ignore 405 = already exists)."""
        # Strip filename → only directory parts
        parts = path.rstrip("/").split("/")
        # Remove filename (last non-empty segment if path is a file path)
        dir_parts = parts[:-1]

        current = ""
        for part in dir_parts:
            if not part:
                continue
            current += f"/{part}"
            url = self._url(current)
            with self._client(timeout=15) as client:
                resp = client.request("MKCOL", url, auth=self._auth())
                # 201 = created, 405 = already exists — both are fine
                if resp.status_code not in (201, 405, 301, 302):
                    logger.warning(
                        "MKCOL %s returned %s — parent folder creation may have failed",
                        current,
                        resp.status_code,
                    )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list(self, path: str) -> list[StorageEntry]:
        """PROPFIND Depth=1 — returns child entries, excludes the folder itself."""
        url = self._url(path)
        with self._client() as client:
            resp = client.request(
                "PROPFIND",
                url,
                content=_PROPFIND_BODY,
                headers={"Depth": "1", "Content-Type": "application/xml"},
                auth=self._auth(),
            )
        if resp.status_code not in (207, 200):
            self._raise_for_status(resp, path)

        return self._parse_entries(resp.text, path)

    def read(self, path: str) -> bytes:
        """GET — returns raw bytes of the file."""
        url = self._url(path)
        with self._client(timeout=60) as client:
            resp = client.get(url, auth=self._auth())
        if resp.status_code != 200:
            self._raise_for_status(resp, path)
        return resp.content

    def write(self, path: str, content: bytes) -> None:
        """PUT — uploads bytes; creates parent folders via MKCOL if needed."""
        url = self._url(path)
        with self._client(timeout=60) as client:
            resp = client.put(
                url,
                content=content,
                headers={"Content-Type": "application/octet-stream"},
                auth=self._auth(),
            )

        if resp.status_code == 404:
            # Parent folder missing — create it and retry
            self._mkcol_parents(path)
            with self._client(timeout=60) as client:
                resp = client.put(
                    url,
                    content=content,
                    headers={"Content-Type": "application/octet-stream"},
                    auth=self._auth(),
                )

        if resp.status_code not in (200, 201, 204):
            self._raise_for_status(resp, path)

    def exists(self, path: str) -> bool:
        """HEAD — True if the resource exists (200), False otherwise."""
        url = self._url(path)
        try:
            with self._client(timeout=10) as client:
                resp = client.request("HEAD", url, auth=self._auth())
            return resp.status_code == 200
        except httpx.TimeoutException as exc:
            raise StorageError(f"Timeout checking existence of {path!r}", path) from exc
        except httpx.HTTPError:
            return False

    def stat(self, path: str) -> StorageStat:
        """PROPFIND Depth=0 — returns mtime, size, etag for a single resource."""
        url = self._url(path)
        with self._client() as client:
            resp = client.request(
                "PROPFIND",
                url,
                content=_PROPFIND_BODY,
                headers={"Depth": "0", "Content-Type": "application/xml"},
                auth=self._auth(),
            )
        if resp.status_code not in (207, 200):
            self._raise_for_status(resp, path)

        root = ET.fromstring(resp.text)

        # Pick first (and only) response element
        response_el = root.find(".//d:response", _NS)
        if response_el is None:
            return StorageStat(
                mtime=datetime(1970, 1, 1, tzinfo=timezone.utc),
                size=0,
                etag="",
            )

        # mtime
        mtime_el = response_el.find(".//d:getlastmodified", _NS)
        if mtime_el is not None and mtime_el.text:
            try:
                mtime = parsedate_to_datetime(mtime_el.text)
            except Exception:
                mtime = datetime(1970, 1, 1, tzinfo=timezone.utc)
        else:
            mtime = datetime(1970, 1, 1, tzinfo=timezone.utc)

        # size
        size_el = response_el.find(".//d:getcontentlength", _NS)
        try:
            size = int(size_el.text) if size_el is not None and size_el.text else 0
        except (ValueError, TypeError):
            size = 0

        # etag
        etag_el = response_el.find(".//d:getetag", _NS)
        etag = etag_el.text.strip('"') if etag_el is not None and etag_el.text else ""

        return StorageStat(mtime=mtime, size=size, etag=etag)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_ADAPTER_REGISTRY: dict[str, type] = {
    "nc": NextcloudWebDAVAdapter,
}


def get_adapter(adapter_name: str, config: dict) -> BrandVoiceStorageAdapter:
    cls = _ADAPTER_REGISTRY.get(adapter_name)
    if cls is None:
        raise ValueError(
            f"Unknown storage adapter: {adapter_name!r}. Available: {list(_ADAPTER_REGISTRY)}"
        )
    return cls(**config)


# ---------------------------------------------------------------------------
# Default instance
# ---------------------------------------------------------------------------

def get_default_nc_adapter() -> NextcloudWebDAVAdapter:
    return NextcloudWebDAVAdapter(
        base_url=os.getenv("NC_BASE_URL", settings.nextcloud_url),
        user=os.getenv("NC_SERVICE_USER", settings.nextcloud_user),
        token=os.getenv("NC_SERVICE_TOKEN", settings.nextcloud_password),
    )


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------

import re as _re_slug


def _slugify(name: str) -> str:
    """Convert a display name to a URL-safe directory slug."""
    s = (name or "").lower().strip()
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        s = s.replace(src, dst)
    s = _re_slug.sub(r"[^\w\s-]", "", s)
    s = _re_slug.sub(r"[\s_]+", "-", s)
    s = _re_slug.sub(r"-+", "-", s).strip("-")
    return s[:64] or "default"


# ---------------------------------------------------------------------------
# NC Back-Sync (App → NC)
# ---------------------------------------------------------------------------

_PILLAR_TABLES = {
    "voice_profile": "tenant_voice_profile",
    "customer_context": "tenant_customer_context",
    "audience_avatar": "tenant_audience_avatar",
}


def sync_brand_voice_to_nc(
    tenant_id: str,
    project_id: str | None = None,
) -> dict:
    """Sync active brand voice profiles back to Nextcloud.

    Path scheme: {nc_base}/{tenant_slug}/{project_slug}/{pillar}.json

    Returns {"synced": [...], "skipped": [...], "errors": [...]}.
    Never raises — all errors are collected and returned.
    """
    import json as _json
    from sqlalchemy import text as _text
    from models.base import sync_session_factory

    synced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    try:
        with sync_session_factory() as session:
            # Resolve tenant name → slug
            tenant_row = session.execute(
                _text("SELECT name FROM tenants WHERE id = :t"),
                {"t": str(tenant_id)},
            ).fetchone()
            if not tenant_row:
                return {
                    "synced": [],
                    "skipped": [],
                    "errors": [f"Tenant {tenant_id} not found"],
                }
            tenant_slug = _slugify(tenant_row[0])

            # Resolve project slug
            if project_id is not None:
                proj_row = session.execute(
                    _text("SELECT slug FROM projects WHERE id = :p"),
                    {"p": str(project_id)},
                ).fetchone()
                project_slug = proj_row[0] if proj_row and proj_row[0] else _slugify(str(project_id))
            else:
                project_slug = "default"

            nc_base = _get_brand_voice_base().rstrip("/")
            nc_dir = f"{nc_base}/{tenant_slug}/{project_slug}"

            # Fetch and write each pillar
            for pillar, tbl in _PILLAR_TABLES.items():
                try:
                    if project_id is None:
                        row = session.execute(
                            _text(
                                f"SELECT payload FROM {tbl} "
                                "WHERE tenant_id=:t AND project_id IS NULL AND is_active=true "
                                "ORDER BY version DESC LIMIT 1"
                            ),
                            {"t": str(tenant_id)},
                        ).fetchone()
                    else:
                        row = session.execute(
                            _text(
                                f"SELECT payload FROM {tbl} "
                                "WHERE tenant_id=:t AND project_id=:pid AND is_active=true "
                                "ORDER BY version DESC LIMIT 1"
                            ),
                            {"t": str(tenant_id), "pid": str(project_id)},
                        ).fetchone()

                    if not row or not row[0]:
                        skipped.append(pillar)
                        continue

                    payload = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
                    nc_path = f"{nc_dir}/{pillar}.json"
                    content = _json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

                    adapter = get_default_nc_adapter()
                    adapter.write(nc_path, content)
                    synced.append(f"{pillar} → {nc_path}")
                    logger.info(
                        "NC back-sync: wrote %s for tenant=%s project=%s",
                        nc_path,
                        tenant_id,
                        project_id,
                    )

                except Exception as pillar_err:
                    errors.append(f"{pillar}: {pillar_err}")
                    logger.warning(
                        "NC back-sync failed for pillar=%s tenant=%s project=%s: %s",
                        pillar,
                        tenant_id,
                        project_id,
                        pillar_err,
                    )

    except Exception as outer_err:
        errors.append(f"outer: {outer_err}")
        logger.warning(
            "NC back-sync outer error tenant=%s project=%s: %s",
            tenant_id,
            project_id,
            outer_err,
        )

    return {"synced": synced, "skipped": skipped, "errors": errors}
