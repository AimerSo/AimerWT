# -*- coding: utf-8 -*-
"""炮镜推荐车辆静态目录与车辆 ID 路径安全校验。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


_vehicle_id_re = re.compile(r"^[a-z0-9][a-z0-9_]{1,79}$")
_reserved_vehicle_ids = {"all_tanks"}


def normalize_vehicle_id(value: Any) -> str:
    """返回可安全用作 UserSights 子目录的结构化车辆 ID。"""
    vehicle_id = str(value or "").strip().lower()
    if vehicle_id in _reserved_vehicle_ids or not _vehicle_id_re.fullmatch(vehicle_id):
        raise ValueError("invalid_vehicle_id")
    return vehicle_id


class SightVehicleCatalog:
    """加载、检索并校验随客户端发布的战争雷霆车辆目录。"""

    def __init__(self, catalog_path: str | Path | None = None) -> None:
        self.catalog_path = Path(catalog_path) if catalog_path else self._default_catalog_path()
        self._data = self._load_catalog()
        self._vehicles = self._validate_vehicles(self._data.get("vehicles"))
        self._vehicle_by_id = {item["vehicle_id"]: item for item in self._vehicles}

    @property
    def schema_version(self) -> int:
        return int(self._data.get("schema_version") or 0)

    @property
    def updated_at(self) -> str:
        return str(self._data.get("updated_at") or "")

    def list_vehicles(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._vehicles]

    def get_vehicle(self, vehicle_id: Any) -> dict[str, Any] | None:
        normalized = normalize_vehicle_id(vehicle_id)
        vehicle = self._vehicle_by_id.get(normalized)
        return dict(vehicle) if vehicle else None

    def validate_vehicle_id(self, vehicle_id: Any) -> dict[str, Any]:
        normalized = normalize_vehicle_id(vehicle_id)
        vehicle = self.get_vehicle(normalized)
        return {
            "vehicle_id": normalized,
            "status": "verified" if vehicle else "unverified_vehicle_id",
            "vehicle": vehicle,
        }

    def search(self, query: Any, limit: int = 50) -> list[dict[str, Any]]:
        text = str(query or "").strip().casefold()
        safe_limit = max(1, min(int(limit or 50), 200))
        if not text:
            return self.list_vehicles()[:safe_limit]
        matches = [
            item
            for item in self._vehicles
            if text in item["vehicle_id"].casefold()
            or text in item["display_name"].casefold()
            or any(text in alias.casefold() for alias in item.get("aliases", []))
        ]
        return [dict(item) for item in matches[:safe_limit]]

    def resolve_display_text(self, value: Any) -> dict[str, Any] | None:
        """只解析目录中唯一的精确名称或 ID，不把任意显示文本当作路径。"""
        text = str(value or "").strip().casefold()
        if not text:
            return None
        matches = [
            item
            for item in self._vehicles
            if text in {
                item["vehicle_id"].casefold(),
                item["display_name"].casefold(),
                *(alias.casefold() for alias in item.get("aliases", [])),
            }
        ]
        return dict(matches[0]) if len(matches) == 1 else None

    @staticmethod
    def _default_catalog_path() -> Path:
        source_path = Path(__file__).with_name("sight_vehicle_catalog.json")
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            bundled = Path(sys._MEIPASS) / "services" / "sight_vehicle_catalog.json"
            if bundled.is_file():
                return bundled
        return source_path

    def _load_catalog(self) -> dict[str, Any]:
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_vehicle_catalog") from exc
        if not isinstance(data, dict):
            raise ValueError("invalid_vehicle_catalog")
        return data

    @staticmethod
    def _validate_vehicles(raw_vehicles: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_vehicles, list):
            raise ValueError("invalid_vehicle_catalog")
        vehicles: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for raw in raw_vehicles:
            if not isinstance(raw, dict):
                raise ValueError("invalid_vehicle_catalog")
            vehicle_id = normalize_vehicle_id(raw.get("vehicle_id"))
            display_name = str(raw.get("display_name") or "").strip()
            wiki_url = str(raw.get("wiki_url") or "").strip()
            raw_aliases = raw.get("aliases") or []
            if not isinstance(raw_aliases, list):
                raise ValueError("invalid_vehicle_aliases")
            if vehicle_id in used_ids:
                raise ValueError("duplicate_vehicle_id")
            if not display_name:
                raise ValueError("missing_vehicle_display_name")
            if wiki_url != f"https://wiki.warthunder.com/unit/{vehicle_id}":
                raise ValueError("invalid_vehicle_wiki_url")
            used_ids.add(vehicle_id)
            item = dict(raw)
            item.update(
                {
                    "vehicle_id": vehicle_id,
                    "display_name": display_name,
                    "wiki_url": wiki_url,
                    "aliases": SightVehicleCatalog._normalize_aliases(raw_aliases),
                }
            )
            vehicles.append(item)
        SightVehicleCatalog._attach_unique_legacy_aliases(vehicles)
        return vehicles

    @staticmethod
    def _normalize_aliases(raw_aliases: list[Any]) -> list[str]:
        aliases: list[str] = []
        seen: set[str] = set()
        for raw_alias in raw_aliases:
            alias = str(raw_alias or "").strip()
            key = alias.casefold()
            if alias and key not in seen:
                seen.add(key)
                aliases.append(alias)
        return aliases

    @staticmethod
    def _legacy_alias_candidates(display_name: str) -> list[str]:
        match = re.match(
            r"^([A-Za-z]+(?:[- ]?\d+)[A-Za-z0-9-]*)",
            display_name,
        )
        if not match:
            return []
        alias = match.group(1).strip()
        return [alias] if alias.casefold() != display_name.casefold() else []

    @classmethod
    def _attach_unique_legacy_aliases(cls, vehicles: list[dict[str, Any]]) -> None:
        alias_candidates: dict[str, list[str]] = {}
        owners: dict[str, set[str]] = {}
        for item in vehicles:
            vehicle_id = item["vehicle_id"]
            candidates = cls._normalize_aliases([
                *item.get("aliases", []),
                *cls._legacy_alias_candidates(item["display_name"]),
            ])
            alias_candidates[vehicle_id] = candidates
            for identity in [vehicle_id, item["display_name"], *candidates]:
                owners.setdefault(identity.casefold(), set()).add(vehicle_id)

        for item in vehicles:
            vehicle_id = item["vehicle_id"]
            item["aliases"] = [
                alias
                for alias in alias_candidates[vehicle_id]
                if owners.get(alias.casefold()) == {vehicle_id}
            ]
