# -*- coding: utf-8 -*-
"""
炮镜伪 BLK 元数据解析器。

功能定位:
- 识别 AimerWT 伪 BLK 元数据文件。
- 解析注释块中的 JSON 元数据。
- 校验 files[].path 的安全边界。
- 归一化弹种 ID 与社区常见别名。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.sight_embedded_metadata import (
    SightEmbeddedMetadataError,
    parse_embedded_metadata_bytes as parse_embedded_v2_bytes,
    parse_embedded_metadata_file as parse_embedded_v2_file,
)
from services.sight_vehicle_catalog import normalize_vehicle_id


class SightMetaParser:
    """伪 BLK 元数据文件的识别、解析与匹配工具。"""

    MARKER_PREFIX = "AIMERWT_SIGHT_META_V"
    SUPPORTED_MARKERS = {"AIMERWT_SIGHT_META_V1"}
    MARKER_END = "AIMERWT_SIGHT_META_END"
    MAX_META_FILE_SIZE = 1 * 1024 * 1024

    _marker_re = re.compile(r"AIMERWT_SIGHT_META_V\d+", re.IGNORECASE)
    _separator_re = re.compile(r"[-_\s]+")

    _canonical_ammo_ids = {
        "apfsds",
        "heat",
        "heatfs",
        "aphe",
        "he",
        "atgm",
        "apds",
        "hesh",
        "smoke",
        "universal",
        "ap",
        "apbc",
        "apc",
        "apcbc",
        "aphebc",
        "aphec",
        "aphecbc",
        "sapcbc",
        "apcr",
        "heat_mp",
        "he_or",
        "heat_grenade",
        "he_tf",
        "he_vt",
        "shrapnel",
        "he_grenade",
        "rocket",
        "vog",
        "atgm_tandem",
        "atgm_he",
        "atgm_top_attack",
        "atgm_vt",
        "sam",
    }

    _explicit_ammo_aliases = {
        "apfsds": {"apfsds_t", "ap-fs-ds"},
        "heatfs": {"heat_fs", "heat-fs", "heatfs"},
        "universal": {"general", "default"},
        "ap": {"armor_piercing"},
        "sapcbc": {"sap_cbc"},
        "heat_mp": {"heatmp", "heat-mp"},
        "he_or": {"heor"},
        "heat_grenade": {"heat_grenades"},
        "he_tf": {"hetf", "he-tf"},
        "he_vt": {"hevt", "he-vt", "proxy_he"},
        "he_grenade": {"he_grenades"},
        "vog": {"frag_grenade"},
        "atgm_tandem": {"tandem_atgm"},
        "atgm_he": {"he_atgm"},
        "atgm_top_attack": {"top_attack_atgm"},
        "atgm_vt": {"proximity_atgm", "proxy_atgm"},
        "sam": {"aa_missile"},
    }

    def __init__(self) -> None:
        self._compact_to_canonical = {
            self._compact_ammo_id(ammo_id): ammo_id for ammo_id in self._canonical_ammo_ids
        }
        for canonical, aliases in self._explicit_ammo_aliases.items():
            for alias in aliases:
                self._compact_to_canonical[self._compact_ammo_id(alias)] = canonical

    def is_meta_filename(self, filename: str) -> bool:
        """判断文件名是否符合 AimerWT 伪 BLK 候选规则。"""
        path = Path(filename)
        return path.suffix.lower() == ".blk" and "aimerwt" in path.name.lower()

    def detect_meta_marker(self, file_path: str | Path) -> bool:
        """在公开协议大小上限内判断是否存在完整 AimerWT 元数据标记。"""
        path = Path(file_path)
        try:
            if path.stat().st_size > self.MAX_META_FILE_SIZE:
                return False
            with open(path, "rb") as f:
                raw = f.read(self.MAX_META_FILE_SIZE + 1)
        except OSError:
            return False
        return self.detect_meta_marker_bytes(raw)

    def detect_meta_marker_bytes(self, raw: bytes) -> bool:
        """为文件扫描和 ZIP 成员提供一致的字节级标记识别。"""
        if not isinstance(raw, bytes) or len(raw) > self.MAX_META_FILE_SIZE:
            return False
        text = self._decode_meta_bytes(raw)
        return bool(self._marker_re.search(text)) and self.MARKER_END.lower() in text.lower()

    def is_standalone_meta_file(self, file_path: str | Path) -> bool:
        """判断文件是否为旧版独立伪 BLK 元数据载体。"""
        path = Path(file_path)
        return self.is_meta_filename(path.name) and self.detect_meta_marker(path)

    def is_meta_file(self, file_path: str | Path) -> bool:
        """兼容旧调用方，仅识别独立伪 BLK 元数据文件。"""
        return self.is_standalone_meta_file(file_path)

    def detect_embedded_meta(self, file_path: str | Path) -> bool:
        """判断真实 BLK 尾部是否包含完整的 V2 元数据。"""
        try:
            return bool(parse_embedded_v2_file(file_path)["parsed"])
        except (OSError, SightEmbeddedMetadataError):
            return False

    def parse_embedded_meta_file(
        self,
        file_path: str | Path,
        package_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """读取真实 BLK 尾部的 V2 元数据并转换为统一包结构。"""
        path = Path(file_path)
        warnings: list[str] = []
        try:
            parsed = parse_embedded_v2_file(path)
        except OSError as exc:
            return self._result(False, None, "file_error", [str(exc)])
        except SightEmbeddedMetadataError as exc:
            return self._result(False, None, "embedded_meta_error", [str(exc)])

        if not parsed["parsed"]:
            return self._result(False, None, "missing_embedded_marker", [])

        root = Path(package_root) if package_root is not None else path.parent
        try:
            relative_path = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            relative_path = path.name
            warnings.append("embedded_path_outside_root")
        return self._normalize_embedded_meta(
            parsed["meta"],
            relative_path,
            root,
            warnings,
        )

    def parse_embedded_meta_bytes(
        self,
        raw: bytes,
        *,
        relative_path: str,
        package_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """解析 ZIP 成员等内存中的真实 BLK V2 元数据。"""
        try:
            parsed = parse_embedded_v2_bytes(raw)
        except SightEmbeddedMetadataError as exc:
            return self._result(False, None, "embedded_meta_error", [str(exc)])

        if not parsed["parsed"]:
            return self._result(False, None, "missing_embedded_marker", [])

        candidate_path = str(relative_path or "").replace("\\", "/").strip()
        root = Path(package_root) if package_root is not None else Path(".")
        return self._normalize_embedded_meta(
            parsed["meta"],
            candidate_path,
            root,
            [],
        )

    def merge_embedded_records(
        self,
        records: list[dict[str, Any]],
        *,
        record_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """按稳定 package_id 聚合多个真实 BLK 的规范化 V2 记录。"""
        if not isinstance(records, list) or not records:
            return self._result(False, None, "missing_embedded_records", [])

        source_values = record_sources if isinstance(record_sources, list) else []
        valid_records: list[dict[str, Any]] = []
        valid_sources: list[str] = []
        for record_index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            source = (
                str(source_values[record_index] or "")
                if record_index < len(source_values)
                else ""
            )
            valid_records.append(record)
            valid_sources.append(
                source.replace("\\", "/").strip()
                or f"record:{record_index + 1}"
            )
        if not valid_records:
            return self._result(False, None, "invalid_embedded_records", [])

        package_id = str(valid_records[0].get("package_id") or "").strip()
        if not package_id:
            return self._result(False, None, "missing_package_id", [])

        warnings: list[str] = []
        conflicts: list[dict[str, str]] = []
        package_keys = {
            key
            for record in valid_records
            for key in record
            if key not in {"meta_version", "package_id", "files", "groups"}
        }
        merged: dict[str, Any] = {
            key: value
            for key, value in valid_records[0].items()
            if key not in {"files", "groups"}
        }
        merged["meta_version"] = 2
        merged["package_id"] = package_id
        merged["files"] = []
        merged["groups"] = []

        first_source = valid_sources[0]
        package_field_sources = {
            key: first_source
            for key in package_keys
            if merged.get(key) not in (None, "", [], {})
        }
        files_by_id: dict[str, dict[str, Any]] = {}
        file_sources: dict[str, str] = {}
        groups_by_id: dict[str, dict[str, Any]] = {}
        group_sources: dict[str, str] = {}
        for record, record_source in zip(valid_records, valid_sources):
            record_package_id = str(record.get("package_id") or "").strip()
            if record_package_id != package_id:
                warnings.append("embedded_package_id_conflict")
                conflicts.append({
                    "scope": "package",
                    "identifier": package_id,
                    "field": "package_id",
                    "kept_source": first_source,
                    "incoming_source": record_source,
                })
                return self._result(
                    False,
                    None,
                    "embedded_package_id_conflict",
                    warnings,
                    conflicts,
                )

            for key in package_keys:
                current_value = merged.get(key)
                incoming_value = record.get(key)
                if (
                    current_value in (None, "", [], {})
                    and incoming_value not in (None, "", [], {})
                ):
                    merged[key] = incoming_value
                    package_field_sources[key] = record_source
                elif (
                    incoming_value not in (None, "", [], {})
                    and incoming_value != current_value
                ):
                    warning = f"embedded_package_conflict:{key}"
                    if warning not in warnings:
                        warnings.append(warning)
                    detail = {
                        "scope": "package",
                        "identifier": package_id,
                        "field": str(key),
                        "kept_source": package_field_sources.get(key, first_source),
                        "incoming_source": record_source,
                    }
                    if detail not in conflicts:
                        conflicts.append(detail)

            for file_entry in record.get("files") or []:
                if not isinstance(file_entry, dict):
                    warnings.append("invalid_embedded_file")
                    continue
                file_id = str(
                    file_entry.get("file_id") or file_entry.get("path") or ""
                ).strip()
                if not file_id:
                    warnings.append("missing_embedded_file_id")
                    continue
                existing_file = files_by_id.get(file_id)
                if existing_file is not None:
                    existing_fingerprint = str(
                        existing_file.get("body_sha256") or ""
                    ).strip().lower()
                    incoming_fingerprint = str(
                        file_entry.get("body_sha256") or ""
                    ).strip().lower()
                    same_known_fingerprint = bool(
                        existing_fingerprint
                        and incoming_fingerprint
                        and existing_fingerprint == incoming_fingerprint
                    )
                    if existing_file != file_entry and not same_known_fingerprint:
                        warning = f"embedded_file_conflict:{file_id}"
                        if warning not in warnings:
                            warnings.append(warning)
                        differing_fields = sorted(
                            str(key)
                            for key in set(existing_file) | set(file_entry)
                            if existing_file.get(key) != file_entry.get(key)
                        )
                        conflict_field = (
                            "body_sha256"
                            if "body_sha256" in differing_fields
                            else (differing_fields[0] if differing_fields else "metadata")
                        )
                        detail = {
                            "scope": "file",
                            "identifier": file_id,
                            "field": conflict_field,
                            "kept_source": file_sources.get(file_id, first_source),
                            "incoming_source": record_source,
                        }
                        if detail not in conflicts:
                            conflicts.append(detail)
                    continue
                copied_file = dict(file_entry)
                files_by_id[file_id] = copied_file
                file_sources[file_id] = record_source
                merged["files"].append(copied_file)

            for group_entry in record.get("groups") or []:
                if not isinstance(group_entry, dict):
                    warnings.append("invalid_embedded_group")
                    continue
                group_id = str(group_entry.get("group_id") or "").strip()
                if not group_id:
                    warnings.append("missing_embedded_group_id")
                    continue
                existing_group = groups_by_id.get(group_id)
                if existing_group is None:
                    copied_group = dict(group_entry)
                    copied_group["files"] = list(group_entry.get("files") or [])
                    groups_by_id[group_id] = copied_group
                    group_sources[group_id] = record_source
                    merged["groups"].append(copied_group)
                    continue

                for group_file in group_entry.get("files") or []:
                    if group_file not in existing_group["files"]:
                        existing_group["files"].append(group_file)
                for key, incoming_value in group_entry.items():
                    if key == "files":
                        continue
                    current_value = existing_group.get(key)
                    if (
                        current_value not in (None, "", [], {})
                        and incoming_value not in (None, "", [], {})
                        and incoming_value != current_value
                    ):
                        warning = f"embedded_group_conflict:{group_id}:{key}"
                        if warning not in warnings:
                            warnings.append(warning)
                        detail = {
                            "scope": "group",
                            "identifier": group_id,
                            "field": str(key),
                            "kept_source": group_sources.get(group_id, first_source),
                            "incoming_source": record_source,
                        }
                        if detail not in conflicts:
                            conflicts.append(detail)

        return self._result(True, merged, "", warnings, conflicts)

    def parse_meta_file(self, file_path: str | Path, package_root: str | Path | None = None) -> dict[str, Any]:
        """解析伪 BLK 元数据文件，返回结构化结果。"""
        path = Path(file_path)
        warnings: list[str] = []

        try:
            if path.stat().st_size > self.MAX_META_FILE_SIZE:
                return self._result(False, None, "oversized_meta_file", ["oversized_meta_file"])
        except OSError as exc:
            return self._result(False, None, "file_error", [str(exc)])

        try:
            raw = path.read_bytes()
            text = self._decode_meta_bytes(raw)
        except UnicodeDecodeError:
            return self._result(False, None, "decode_error", [])
        except OSError as exc:
            return self._result(False, None, "file_error", [str(exc)])

        marker_matches = list(self._marker_re.finditer(text))
        if not marker_matches:
            return self._result(False, None, "missing_marker", [])
        if len(marker_matches) > 1:
            warnings.append("multiple_meta_blocks")

        start_match = marker_matches[0]
        marker = start_match.group(0).upper()
        if marker not in self.SUPPORTED_MARKERS:
            warnings.append(f"unsupported_marker:{marker}")

        end_index = text.lower().find(self.MARKER_END.lower(), start_match.end())
        if end_index < 0:
            return self._result(False, None, "missing_end_marker", warnings)

        json_text = text[start_match.end():end_index].strip()
        if "*/" in json_text:
            warnings.append("comment_close_sequence")

        try:
            meta = json.loads(json_text)
        except json.JSONDecodeError:
            return self._result(False, None, "invalid_json", warnings)
        if not isinstance(meta, dict):
            return self._result(False, None, "invalid_json", warnings)

        if "meta_version" not in meta:
            warnings.append("missing_version")
            meta["meta_version"] = 1

        meta = self._normalize_recommendation_fields(meta, warnings, "package")
        normalized_files = self._normalize_files(meta.get("files"), package_root or path.parent, warnings)
        if normalized_files is not None:
            meta["files"] = normalized_files
        normalized_groups = self._normalize_groups(meta.get("groups"), package_root or path.parent, warnings)
        if normalized_groups is not None:
            meta["groups"] = normalized_groups

        return self._result(True, meta, "", warnings)

    def normalize_ammo_type(self, raw: Any) -> str:
        """将弹种输入归一化为 AimerWT 标准 ID。"""
        if raw is None:
            return ""
        value = str(raw).strip()
        if not value:
            return ""
        compact = self._compact_ammo_id(value)
        return self._compact_to_canonical.get(compact, value)

    def resolve_recommendation(
        self,
        package_meta: dict[str, Any] | None,
        group_meta: dict[str, Any] | None = None,
        file_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """按文件、分组、炮镜包顺序解析最终推荐部署目标。"""
        for source_level, raw_entry in (
            ("file", file_meta),
            ("group", group_meta),
            ("package", package_meta),
        ):
            if not isinstance(raw_entry, dict):
                continue
            entry = self._normalize_recommendation_fields(raw_entry, [], source_level)
            apply_mode = str(entry.get("recommended_apply_mode") or "").strip().lower()
            primary_vehicle_id = str(entry.get("primary_vehicle_id") or "").strip()
            compatible_vehicle_ids = list(entry.get("compatible_vehicle_ids") or [])
            if apply_mode == "all_tanks":
                return {
                    "recommended_apply_mode": "all_tanks",
                    "primary_vehicle_id": "",
                    "compatible_vehicle_ids": [],
                    "recommended_vehicles": list(entry.get("recommended_vehicles") or []),
                    "source_level": source_level,
                }
            if apply_mode == "vehicles" or primary_vehicle_id or compatible_vehicle_ids:
                return {
                    "recommended_apply_mode": "vehicles",
                    "primary_vehicle_id": primary_vehicle_id,
                    "compatible_vehicle_ids": compatible_vehicle_ids,
                    "recommended_vehicles": list(entry.get("recommended_vehicles") or []),
                    "source_level": source_level,
                }

        legacy_recommendations: list[str] = []
        if isinstance(package_meta, dict):
            legacy_recommendations = self._normalize_text_list(
                package_meta.get("recommended_vehicles"),
                12,
            )
        return {
            "recommended_apply_mode": "",
            "primary_vehicle_id": "",
            "compatible_vehicle_ids": [],
            "recommended_vehicles": legacy_recommendations,
            "source_level": "",
        }

    def match_files_to_meta(
        self,
        meta: dict[str, Any],
        blk_files: list[str],
        package_root: str | Path | None = None,
    ) -> dict[str, dict[str, Any]]:
        """将元数据 files[] 条目与实际 BLK 文件匹配。"""
        if not isinstance(meta, dict):
            return {}
        entries = meta.get("files")
        if not isinstance(entries, list):
            return {}

        root = Path(package_root) if package_root is not None else None
        exact_entries: dict[str, dict[str, Any]] = {}
        lower_entries: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            rel_path = entry.get("path")
            if not isinstance(rel_path, str) or not rel_path:
                continue
            if root is not None and not self._is_safe_relative_path(rel_path, root):
                continue
            key = self._normalize_relative_key(rel_path)
            exact_entries[key] = entry
            lower_entries[key.lower()] = entry

        matched: dict[str, dict[str, Any]] = {}
        for blk_file in blk_files:
            key = self._normalize_relative_key(str(blk_file))
            entry = exact_entries.get(key)
            if entry is None:
                entry = lower_entries.get(key.lower())
            if entry is not None:
                matched[blk_file] = entry
        return matched

    def _normalize_embedded_meta(
        self,
        raw_meta: Any,
        relative_path: str,
        package_root: str | Path,
        warnings: list[str],
    ) -> dict[str, Any]:
        if not isinstance(raw_meta, dict) or raw_meta.get("meta_version") != 2:
            return self._result(False, None, "invalid_embedded_version", warnings)

        package_id = str(raw_meta.get("package_id") or "").strip()
        package_meta = raw_meta.get("package")
        file_meta = raw_meta.get("file")
        if not package_id:
            return self._result(False, None, "missing_package_id", warnings)
        if not isinstance(package_meta, dict):
            return self._result(False, None, "invalid_embedded_package", warnings)
        if not isinstance(file_meta, dict):
            return self._result(False, None, "invalid_embedded_file", warnings)

        file_id = str(file_meta.get("file_id") or "").strip()
        candidate_path = str(relative_path or "").replace("\\", "/").strip()
        if not file_id:
            return self._result(False, None, "missing_embedded_file_id", warnings)
        if not candidate_path:
            return self._result(False, None, "missing_embedded_file_path", warnings)

        normalized_meta = {
            key: value
            for key, value in package_meta.items()
            if key not in {"meta_version", "package_id", "files", "groups"}
        }
        normalized_meta["meta_version"] = 2
        normalized_meta["package_id"] = package_id
        normalized_meta = self._normalize_recommendation_fields(
            normalized_meta,
            warnings,
            "package",
        )

        normalized_file = dict(file_meta)
        normalized_file["file_id"] = file_id
        normalized_file["path"] = candidate_path
        normalized_files = self._normalize_files(
            [normalized_file],
            package_root,
            warnings,
        )
        if not normalized_files:
            return self._result(False, None, "invalid_embedded_file_path", warnings)
        normalized_path = normalized_files[0]["path"]
        normalized_meta["files"] = normalized_files

        normalized_groups: list[dict[str, Any]] = []
        group_meta = raw_meta.get("group")
        if group_meta is not None:
            if isinstance(group_meta, dict):
                normalized_group = dict(group_meta)
                normalized_group["files"] = [normalized_path]
                normalized_groups = (
                    self._normalize_groups(
                        [normalized_group],
                        package_root,
                        warnings,
                    )
                    or []
                )
            else:
                warnings.append("invalid_embedded_group")
        normalized_meta["groups"] = normalized_groups
        return self._result(True, normalized_meta, "", warnings)

    def _normalize_files(
        self,
        files: Any,
        package_root: str | Path,
        warnings: list[str],
    ) -> list[dict[str, Any]] | None:
        if files is None:
            return None
        if not isinstance(files, list):
            warnings.append("invalid_files")
            return []

        root = Path(package_root)
        normalized: list[dict[str, Any]] = []
        for entry in files:
            if not isinstance(entry, dict):
                warnings.append("invalid_file_entry")
                continue
            rel_path = entry.get("path")
            if not isinstance(rel_path, str) or not rel_path.strip():
                warnings.append("invalid_file_path")
                continue
            rel_path = rel_path.strip()
            if not self._is_safe_relative_path(rel_path, root):
                warnings.append(f"unsafe_file_path:{rel_path}")
                continue

            normalized_entry = dict(entry)
            normalized_entry["path"] = self._normalize_relative_key(rel_path)
            if "ammo_type" in normalized_entry:
                normalized_entry["ammo_type"] = self.normalize_ammo_type(normalized_entry.get("ammo_type"))
            normalized_entry = self._normalize_recommendation_fields(
                normalized_entry,
                warnings,
                "file",
            )
            normalized.append(normalized_entry)
        return normalized

    def _normalize_groups(
        self,
        groups: Any,
        package_root: str | Path,
        warnings: list[str],
    ) -> list[dict[str, Any]] | None:
        if groups is None:
            return None
        if not isinstance(groups, list):
            warnings.append("invalid_groups")
            return []

        root = Path(package_root)
        normalized: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        reserved_ids = {"__all__", "__ungrouped__"}
        for index, entry in enumerate(groups, start=1):
            if not isinstance(entry, dict):
                warnings.append("invalid_group_entry")
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                warnings.append("invalid_group_name")
                continue

            raw_group_id = str(entry.get("group_id") or "").strip()
            base_group_id = self._normalize_group_id(raw_group_id or name, index)
            if base_group_id in reserved_ids:
                base_group_id = self._normalize_group_id(name, index)
            if base_group_id in reserved_ids:
                base_group_id = f"group_{index}"
            group_id = base_group_id
            suffix = 2
            while group_id in used_ids or group_id in reserved_ids:
                group_id = f"{base_group_id}_{suffix}"
                suffix += 1
            used_ids.add(group_id)

            normalized_entry = dict(entry)
            normalized_entry.update({
                "group_id": group_id,
                "name": name[:40],
                "description": str(entry.get("description") or "").strip()[:160],
                "ammo_types": [
                    ammo_type
                    for ammo_type in (self.normalize_ammo_type(value) for value in self._normalize_text_list(entry.get("ammo_types"), 24))
                    if ammo_type
                ],
                "recommended_vehicles": self._normalize_text_list(entry.get("recommended_vehicles"), 12),
                "target_resolutions": self._normalize_text_list(entry.get("target_resolutions"), 12),
                "platforms": self._normalize_text_list(entry.get("platforms"), 12),
                "tags": self._normalize_text_list(entry.get("tags"), 12),
                "featured": bool(entry.get("featured")),
                "sort_order": self._normalize_sort_order(entry.get("sort_order"), index),
                "files": self._normalize_group_files(entry.get("files"), root, warnings),
            })
            normalized_entry = self._normalize_recommendation_fields(
                normalized_entry,
                warnings,
                "group",
            )
            normalized.append(normalized_entry)
        return normalized

    def _normalize_recommendation_fields(
        self,
        entry: dict[str, Any],
        warnings: list[str],
        scope: str,
    ) -> dict[str, Any]:
        normalized = dict(entry)

        if "recommended_vehicles" in normalized:
            normalized["recommended_vehicles"] = self._normalize_text_list(
                normalized.get("recommended_vehicles"),
                12,
            )

        raw_mode = normalized.get("recommended_apply_mode")
        if raw_mode is not None:
            apply_mode = str(raw_mode).strip().lower()
            if apply_mode in {"vehicles", "all_tanks"}:
                normalized["recommended_apply_mode"] = apply_mode
            else:
                warnings.append(f"invalid_recommended_apply_mode:{scope}")
                normalized.pop("recommended_apply_mode", None)

        if "primary_vehicle_id" in normalized:
            raw_primary_vehicle_id = str(normalized.get("primary_vehicle_id") or "").strip()
            if not raw_primary_vehicle_id:
                normalized["primary_vehicle_id"] = ""
            else:
                try:
                    normalized["primary_vehicle_id"] = normalize_vehicle_id(raw_primary_vehicle_id)
                except ValueError:
                    warnings.append(f"invalid_primary_vehicle_id:{scope}")
                    normalized.pop("primary_vehicle_id", None)

        if "compatible_vehicle_ids" in normalized:
            raw_ids = self._normalize_text_list(normalized.get("compatible_vehicle_ids"), 24)
            compatible_vehicle_ids: list[str] = []
            seen: set[str] = set()
            primary_vehicle_id = str(normalized.get("primary_vehicle_id") or "")
            for raw_vehicle_id in raw_ids:
                try:
                    vehicle_id = normalize_vehicle_id(raw_vehicle_id)
                except ValueError:
                    warnings.append(f"invalid_compatible_vehicle_id:{scope}")
                    continue
                if vehicle_id == primary_vehicle_id or vehicle_id in seen:
                    continue
                seen.add(vehicle_id)
                compatible_vehicle_ids.append(vehicle_id)
            normalized["compatible_vehicle_ids"] = compatible_vehicle_ids

        if normalized.get("recommended_apply_mode") == "all_tanks":
            if "primary_vehicle_id" in normalized:
                normalized["primary_vehicle_id"] = ""
            if "compatible_vehicle_ids" in normalized:
                normalized["compatible_vehicle_ids"] = []
        elif (
            "recommended_apply_mode" not in normalized
            and (
                str(normalized.get("primary_vehicle_id") or "").strip()
                or normalized.get("compatible_vehicle_ids")
            )
        ):
            normalized["recommended_apply_mode"] = "vehicles"

        return normalized

    def _normalize_group_files(self, files: Any, package_root: Path, warnings: list[str]) -> list[str]:
        if files is None:
            return []
        if not isinstance(files, list):
            warnings.append("invalid_group_files")
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_path in files:
            if not isinstance(raw_path, str) or not raw_path.strip():
                warnings.append("invalid_group_file_path")
                continue
            rel_path = raw_path.strip()
            if not self._is_safe_relative_path(rel_path, package_root):
                warnings.append(f"unsafe_group_file_path:{rel_path}")
                continue
            key = self._normalize_relative_key(rel_path)
            lower_key = key.lower()
            if lower_key in seen:
                continue
            seen.add(lower_key)
            normalized.append(key)
        return normalized

    def _normalize_text_list(self, value: Any, limit: int) -> list[str]:
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        else:
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _normalize_sort_order(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback * 100

    @staticmethod
    def _normalize_group_id(value: str, fallback_index: int) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", str(value or "").strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
        return cleaned[:48] or f"group_{fallback_index}"

    def _is_safe_relative_path(self, rel_path: str, package_root: Path) -> bool:
        candidate_text = rel_path.replace("\\", "/")
        if not candidate_text or candidate_text.startswith("/"):
            return False
        if re.match(r"^[a-zA-Z]:/", candidate_text):
            return False
        parts = [part for part in candidate_text.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            return False
        try:
            base = package_root.resolve(strict=False)
            candidate = (base / candidate_text).resolve(strict=False)
            return candidate == base or base in candidate.parents
        except (OSError, ValueError):
            return False

    def _decode_meta_bytes(self, raw: bytes) -> str:
        last_error: UnicodeDecodeError | None = None
        for encoding in ("utf-8-sig", "gb18030", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return ""

    def _compact_ammo_id(self, value: str) -> str:
        return self._separator_re.sub("", value.strip().lower())

    def _normalize_relative_key(self, rel_path: str) -> str:
        return rel_path.replace("\\", "/").strip().lstrip("./")

    def _result(
        self,
        parsed: bool,
        meta: dict[str, Any] | None,
        error: str,
        warnings: list[str],
        conflicts: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        result = {
            "parsed": parsed,
            "meta": meta,
            "error": error,
            "warnings": warnings,
        }
        if conflicts is not None:
            result["conflicts"] = conflicts
        return result
