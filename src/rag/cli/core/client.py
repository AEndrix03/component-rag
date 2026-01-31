from __future__ import annotations

import os
import requests
import logging

log = logging.getLogger(__name__)


class RegistryClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def exists(self, name: str, version: str) -> bool:
        r = requests.head(self._url(f"/v1/packages/{name}/{version}"), timeout=10)
        return r.status_code == 200

    def publish(self, name: str, version: str, file_path: str, overwrite: bool = False) -> dict:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "application/gzip")}
            params = {}
            if overwrite:
                params["overwrite"] = "true"

            r = requests.post(
                self._url(f"/v1/packages/{name}/{version}"),
                files=files,
                params=params,
                timeout=120,
            )

        if r.status_code >= 400:
            raise RuntimeError(f"publish failed: {r.status_code} {r.text}")

        return r.json()

    def download(self, name: str, version: str, out_path: str) -> str:
        r = requests.get(self._url(f"/v1/packages/{name}/{version}/download"), stream=True, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"download failed: {r.status_code} {r.text}")

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        return out_path

    def list(self, name: str, include_yanked: bool = False) -> dict:
        r = requests.get(self._url(f"/v1/packages/{name}"), params={"include_yanked": str(include_yanked).lower()}, timeout=10)
        if r.status_code >= 400:
            raise RuntimeError(f"list failed: {r.status_code} {r.text}")
        return r.json()
