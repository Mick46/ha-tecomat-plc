"""Ručně ukládané verze konfigurace (sdílené pro všechny uživatele, součást záloh HA)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1


class VersionStore:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.versions")
        self.versions: list[dict] = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self.versions = (data or {}).get("versions", [])

    async def _save(self) -> None:
        await self._store.async_save({"versions": self.versions})

    def get(self, vid: str) -> dict | None:
        return next((v for v in self.versions if v["id"] == vid), None)

    async def add(self, name: str, cfg_map: dict, corr: dict, source: str = "plc") -> dict:
        ver = {
            "id": uuid.uuid4().hex,
            "name": name,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "map": dict(cfg_map),
            "corr": {str(k): v for k, v in corr.items()},
        }
        self.versions.insert(0, ver)
        await self._save()
        return ver

    async def delete(self, vid: str) -> bool:
        before = len(self.versions)
        self.versions = [v for v in self.versions if v["id"] != vid]
        if len(self.versions) != before:
            await self._save()
            return True
        return False
