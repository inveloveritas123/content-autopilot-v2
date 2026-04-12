import logging
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import unquote

import httpx

from config import settings

logger = logging.getLogger(__name__)


class NextcloudClient:
    def __init__(self):
        self.base_url = settings.nextcloud_url.rstrip("/")
        self.user = settings.nextcloud_user
        self.password = settings.nextcloud_password
        self.dav_url = f"{self.base_url}/remote.php/dav/files/{self.user}"

    def _auth(self) -> tuple[str, str]:
        return (self.user, self.password)

    async def list_folder(self, path: str = "/") -> list[dict]:
        """List files/folders in a Nextcloud folder via WebDAV PROPFIND."""
        url = f"{self.dav_url}{path}"
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <d:propfind xmlns:d="DAV:">
            <d:prop>
                <d:displayname/>
                <d:getcontentlength/>
                <d:getcontenttype/>
                <d:getlastmodified/>
                <d:resourcetype/>
            </d:prop>
        </d:propfind>"""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    "PROPFIND", url,
                    content=body,
                    headers={"Depth": "1", "Content-Type": "application/xml"},
                    auth=self._auth(),
                )
                resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"d": "DAV:"}
            base_path = f"/remote.php/dav/files/{self.user}"
            entries = []
            for response in root.findall(".//d:response", ns):
                href_el = response.find("d:href", ns)
                href = href_el.text if href_el is not None else ""
                displayname_el = response.find(".//d:displayname", ns)
                is_dir = response.find(".//d:resourcetype/d:collection", ns) is not None

                # Extract clean path
                clean_path = unquote(href.replace(base_path, "")).rstrip("/")
                name = displayname_el.text if displayname_el is not None and displayname_el.text else clean_path.split("/")[-1]

                # Skip the folder itself
                req_path = path.rstrip("/")
                if clean_path == req_path or clean_path == "":
                    continue

                size_el = response.find(".//d:getcontentlength", ns)
                modified_el = response.find(".//d:getlastmodified", ns)

                entries.append({
                    "path": clean_path,
                    "name": name,
                    "is_directory": is_dir,
                    "size": int(size_el.text) if size_el is not None and size_el.text else None,
                    "modified": modified_el.text if modified_el is not None else None,
                })
            return entries
        except Exception as e:
            logger.error(f"Nextcloud list_folder '{path}' failed: {e}")
            return []

    async def search_folders(self, query: str) -> list[dict]:
        """Search for folders matching a query string in Nextcloud."""
        url = f"{self.base_url}/remote.php/dav"
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
        <d:searchrequest xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
            <d:basicsearch>
                <d:select><d:prop><d:displayname/><d:resourcetype/></d:prop></d:select>
                <d:from><d:scope><d:href>/files/{self.user}</d:href><d:depth>infinity</d:depth></d:scope></d:from>
                <d:where>
                    <d:and>
                        <d:like><d:prop><d:displayname/></d:prop><d:literal>%{query}%</d:literal></d:like>
                        <d:is-collection/>
                    </d:and>
                </d:where>
            </d:basicsearch>
        </d:searchrequest>"""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    "SEARCH", url,
                    content=body,
                    headers={"Content-Type": "application/xml"},
                    auth=self._auth(),
                )
            if resp.status_code in (207, 200):
                root = ET.fromstring(resp.text)
                ns = {"d": "DAV:"}
                base_path = f"/remote.php/dav/files/{self.user}"
                results = []
                for response in root.findall(".//d:response", ns):
                    href_el = response.find("d:href", ns)
                    href = href_el.text if href_el is not None else ""
                    clean_path = unquote(href.replace(base_path, "")).rstrip("/")
                    name = clean_path.split("/")[-1]
                    if name:
                        results.append({"path": clean_path, "name": name, "is_directory": True})
                return results
        except Exception as e:
            logger.warning(f"NC search failed, falling back to manual browse: {e}")

        # Fallback: browse common paths
        return await self._fallback_search(query)

    async def _fallback_search(self, query: str) -> list[dict]:
        """Fallback folder search by browsing top-level folders."""
        results = []
        top = await self.list_folder("/")
        for entry in top:
            if entry["is_directory"]:
                if query.lower() in entry["name"].lower():
                    results.append(entry)
                # Also check one level deep
                sub = await self.list_folder(entry["path"] + "/")
                for s in sub:
                    if s["is_directory"] and query.lower() in s["name"].lower():
                        results.append(s)
        return results

    async def ensure_folder(self, path: str) -> bool:
        """Create folder (and parents) if it doesn't exist."""
        parts = [p for p in path.split("/") if p]
        current = ""
        for part in parts:
            current += f"/{part}"
            url = f"{self.dav_url}{current}"
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.request("MKCOL", url, auth=self._auth())
                    # 201 = created, 405 = already exists
            except Exception:
                pass
        return True

    async def upload_file(self, path: str, content: bytes, content_type: str = "text/plain") -> bool:
        """Upload a file to Nextcloud, creating parent folders if needed."""
        folder = "/".join(path.split("/")[:-1])
        if folder:
            await self.ensure_folder(folder)

        url = f"{self.dav_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.put(
                    url, content=content,
                    headers={"Content-Type": content_type},
                    auth=self._auth(),
                )
                return resp.status_code in (200, 201, 204)
        except Exception as e:
            logger.error(f"Nextcloud upload failed: {e}")
            return False

    async def download_file(self, path: str) -> Optional[bytes]:
        """Download a file from Nextcloud."""
        url = f"{self.dav_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url, auth=self._auth())
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.error(f"Nextcloud download failed: {e}")
            return None

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in Nextcloud."""
        url = f"{self.dav_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.request("HEAD", url, auth=self._auth())
                return resp.status_code == 200
        except Exception:
            return False

    async def list_files_recursive(self, path: str, extension: str = ".txt") -> list[dict]:
        """List all files with given extension in folder and subfolders."""
        results = []
        entries = await self.list_folder(path)
        for entry in entries:
            if entry["is_directory"]:
                sub = await self.list_files_recursive(entry["path"] + "/", extension)
                results.extend(sub)
            elif entry["name"].endswith(extension):
                results.append(entry)
        return results


nextcloud_client = NextcloudClient()
