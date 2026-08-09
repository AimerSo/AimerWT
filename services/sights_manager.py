# -*- coding: utf-8 -*-
"""
炮镜资源管理模组：负责 UserSights 的路径设置、扫描、导入、重命名与封面处理。

功能定位:
- 管理用户指定的 UserSights 目录，并扫描其中的炮镜文件夹以生成前端展示数据。
- 将用户提供的炮镜 ZIP/RAR/7Z 解压写入 AimerWT 炮镜资源库，再安装干净 BLK 到 UserSights。
- 提供炮镜文件夹重命名与资源库封面更新能力，旧 UserSights 封面仅作兼容读取。
- 自动搜索 War Thunder 的 UserSights 路径，支援多 UID 选择。

输入输出:
- 输入: UserSights 路径、炮镜压缩包路径、封面 base64 数据、重命名参数、进度回调。
- 输出: 炮镜列表字典、导入结果字典、UserSights 生效文件与资源库封面更新结果。
- 外部资源/依赖:
  - 目录: UserSights（读写）
  - 文件: 炮镜目录内的 .blk 文件（扫描计数）、资源库封面文件（写入）
  - 系统能力: zipfile/7z 解压、文件系统读写、os.startfile

错误处理策略:
- 文件操作使用具体的异常类型（PermissionError、FileNotFoundError 等）
- 压缩包解压支援路径安全校验
- 所有操作记录完整的错误上下文
"""
import base64
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import tempfile
import time
import uuid
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Callable, Any
from utils.logger import get_logger
from utils.sevenzip import find_7z_executable
from services.resource_index_cache import ResourceIndexCache
from services.sight_blk_analyzer import SightBlkAnalyzer
from services.sight_deployment_rules import build_sight_deployment_preview
from services.sight_embedded_metadata import (
    EMBEDDED_META_END,
    EMBEDDED_META_START,
    MAX_EMBEDDED_META_BYTES,
)
from services.sight_meta_parser import SightMetaParser
from services.sight_package_rules import (
    BLOCKED_ARCHIVE_EXTENSIONS,
    TARGET_DIR_UNSET,
    WINDOWS_RESERVED_NAMES,
    build_archive_install_mapping,
    infer_archive_target,
    is_archive_member_path_safe,
    is_preview_asset_name as is_sight_preview_asset_name,
    is_unsafe_windows_path_part,
    looks_like_vehicle_sight_dir,
    map_archive_member_to_target,
    normalize_sight_target_dir,
)
from services.sights_repository_manager import SightsRepositoryManager

log = get_logger(__name__)


class SightsManagerError(Exception):
    """炮镜管理器相关错误的基类。"""
    pass


class SightsPathError(SightsManagerError):
    """UserSights 路径相关错误。"""
    pass


class SightsImportError(SightsManagerError):
    """炮镜导入相关错误。"""
    pass


class SightsManager:
    """
    面向 UserSights 目录的资源管理器，封装扫描、导入与文件操作能力。
    
    属性:
        _usersights_path: 当前设置的 UserSights 路径
        _cache: 扫描结果缓存
    """
    supported_archive_extensions = (".zip", ".rar", ".7z")
    disabled_suffix = ".AimerWT_BAN"
    resource_ref_prefix = "resource:"
    file_ref_prefix = "file:"
    quick_scan_file_limit = 200
    cover_inline_item_limit = 200
    windows_reserved_names = set(WINDOWS_RESERVED_NAMES)
    
    def __init__(self, cache_dir: str | Path | None = None, sights_library_dir: str | Path | None = None):
        """
        初始化 SightsManager。
        """
        self._usersights_path: Path | None = None
        self._cache: dict | None = None
        self._cache_signature = None
        self._index_cache = ResourceIndexCache("sights_library", cache_dir=cache_dir)
        self._feature_cache = ResourceIndexCache("sights_blk_features", cache_dir=cache_dir)
        self._meta_link_cache = ResourceIndexCache("sights_meta_links", cache_dir=cache_dir)
        self._meta_parser = SightMetaParser()
        self._blk_analyzer = SightBlkAnalyzer()
        self._blk_feature_cache: dict[str, dict[str, Any]] = {}
        self._blk_feature_cache_root = ""
        self._blk_feature_cache_dirty = False
        self._sight_group_model_cache: dict[str, dict[str, Any]] = {}
        self._meta_link_records: dict[str, dict[str, Any]] = {}
        self._meta_link_root = ""
        self._meta_link_dirty = False
        self._sight_task_lock = threading.RLock()
        self._sight_tasks: dict[str, dict[str, Any]] = {}
        self._sights_repo = SightsRepositoryManager(library_dir=sights_library_dir)

    def set_sights_library_dir(self, sights_library_dir: str | Path | None) -> None:
        self._sights_repo = SightsRepositoryManager(library_dir=sights_library_dir)
        self._clear_sights_cache()

    def get_sight_resource_deployment_state(self, resource_id: str) -> dict[str, Any]:
        """返回当前 UserSights 下指定受管资源的真实部署状态。"""
        return self._sights_repo.get_resource_deployment_state(
            str(resource_id or "").strip(),
            self._require_usersights_path(),
        )

    def preview_sight_resource_deployment(
        self,
        resource_id: str,
        deployment_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """预检指定资源的部署目标；不写入 UserSights。"""
        return self._sights_repo.preview_resource_deployment(
            str(resource_id or "").strip(),
            self._require_usersights_path(),
            deployment_request,
        )

    def apply_sight_resource_deployment(
        self,
        resource_id: str,
        deployment_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """按预检一致的部署请求写入或恢复受管炮镜。"""
        result = self._sights_repo.apply_resource_deployment(
            str(resource_id or "").strip(),
            self._require_usersights_path(),
            deployment_request,
        )
        if result.get("success"):
            self._clear_sights_cache()
        return result

    def preview_sight_resource_deployments(self, resource_ids: list[str]) -> dict[str, Any]:
        """批量读取部署动作；已启用和可恢复项不会进入首次选择集合。"""
        items: list[dict[str, Any]] = []
        counts = {
            "already_enabled_count": 0,
            "restorable_count": 0,
            "needs_deployment_choice_count": 0,
            "attention_count": 0,
        }
        seen: set[str] = set()
        for raw_resource_id in resource_ids or []:
            resource_id = str(raw_resource_id or "").strip()
            if not resource_id or resource_id in seen:
                continue
            seen.add(resource_id)
            state = self.get_sight_resource_deployment_state(resource_id)
            action = str(state.get("action") or "")
            if action == "already_enabled":
                counts["already_enabled_count"] += 1
            elif action == "restorable":
                counts["restorable_count"] += 1
            elif action == "confirm_deployment":
                state["action"] = "needs_deployment_choice"
                counts["needs_deployment_choice_count"] += 1
            else:
                counts["attention_count"] += 1
            items.append(state)
        return {"success": True, "items": items, **counts}
    @classmethod
    def _is_unsafe_windows_path_part(cls, part: str) -> bool:
        _ = cls
        return is_unsafe_windows_path_part(part)

    def _clear_sights_cache(self) -> None:
        self._cache = None
        self._cache_signature = None
        self._blk_feature_cache.clear()
        self._blk_feature_cache_root = ""
        self._blk_feature_cache_dirty = False
        self._sight_group_model_cache.clear()
        try:
            self._index_cache.clear()
        except Exception:
            log.debug("清理炮镜索引缓存失败", exc_info=True)

    def _resolve_sight_dir(self, name: str) -> Path:
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        folder_name = str(name or "").strip()
        if not folder_name or Path(folder_name).name != folder_name:
            raise ValueError("炮镜文件夹名称不合法")
        if self._is_unsafe_windows_path_part(folder_name):
            raise ValueError("炮镜文件夹名称不合法")
        sight_dir = usersights_dir / folder_name
        if not sight_dir.exists() or not sight_dir.is_dir():
            raise FileNotFoundError(f"炮镜文件夹不存在: {folder_name}")
        return sight_dir

    def _resolve_sight_detail_dir(self, name: str) -> Path:
        """按 enabled_name 查找炮镜目录，兼容已禁用目录。"""
        try:
            return self._resolve_sight_dir(name)
        except FileNotFoundError:
            usersights_dir = self._usersights_path
            folder_name = str(name or "").strip()
            if not usersights_dir or not folder_name or folder_name.endswith(self.disabled_suffix):
                raise
            disabled_dir = usersights_dir / f"{folder_name}{self.disabled_suffix}"
            if disabled_dir.exists() and disabled_dir.is_dir():
                return disabled_dir
            raise

    def _parse_resource_reference(self, value: str, require_exists: bool = True) -> str:
        reference = str(value or "").strip()
        if not reference.startswith(self.resource_ref_prefix):
            return ""
        resource_id = reference[len(self.resource_ref_prefix):].strip()
        if (
            not resource_id
            or not re.fullmatch(r"[0-9A-Za-z._-]+", resource_id)
            or self._is_unsafe_windows_path_part(resource_id)
        ):
            raise ValueError("炮镜资源引用不合法")
        if require_exists and not self._sights_repo.resource_exists(resource_id):
            raise FileNotFoundError(f"炮镜资源不存在: {resource_id}")
        return resource_id

    def _normalize_external_sight_relative_path(self, value: str) -> str:
        reference = str(value or "").strip()
        if reference.startswith(self.file_ref_prefix):
            reference = reference[len(self.file_ref_prefix):]
        normalized = reference.replace("\\", "/").strip("/")
        if normalized.endswith(self.disabled_suffix):
            normalized = normalized[:-len(self.disabled_suffix)]
        posix_path = PurePosixPath(normalized)
        parts = posix_path.parts
        if (
            not normalized
            or not parts
            or posix_path.is_absolute()
            or any(part in {"", ".", ".."} for part in parts)
            or any(":" in part for part in parts)
            or any(self._is_unsafe_windows_path_part(part) for part in parts)
            or PurePosixPath(normalized).suffix.lower() != ".blk"
        ):
            raise ValueError("炮镜文件引用不合法")
        return str(PurePosixPath(*parts))

    def _external_sight_reference(self, relative_path: str) -> str:
        return f"{self.file_ref_prefix}{self._normalize_external_sight_relative_path(relative_path)}"

    @staticmethod
    def _is_path_within(path: Path, root: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
            return True
        except (OSError, ValueError):
            return False

    def _resolve_external_sight_file(self, value: str) -> tuple[str, Path, bool]:
        usersights_dir = self._require_usersights_path()
        relative_path = self._normalize_external_sight_relative_path(value)
        enabled_path = usersights_dir.joinpath(*PurePosixPath(relative_path).parts)
        disabled_path = Path(f"{enabled_path}{self.disabled_suffix}")
        if enabled_path.is_file():
            if not self._is_path_within(enabled_path, usersights_dir):
                raise ValueError("炮镜文件引用超出 UserSights")
            return self._external_sight_reference(relative_path), enabled_path, False
        if disabled_path.is_file():
            if not self._is_path_within(disabled_path, usersights_dir):
                raise ValueError("炮镜文件引用超出 UserSights")
            return self._external_sight_reference(relative_path), disabled_path, True
        raise FileNotFoundError(f"炮镜文件不存在: {relative_path}")

    def _load_sights_manifest(self) -> dict[str, Any]:
        if not self._usersights_path:
            return {}
        try:
            manifest = self._sights_repo.load_manifest(self._usersights_path)
            return manifest if isinstance(manifest, dict) else {}
        except Exception as exc:
            log.debug(f"读取炮镜安装清单失败，已继续扫描外部炮镜: {exc}")
            return {}

    def _manifest_managed_target_paths(self, manifest: dict[str, Any]) -> set[str]:
        targets: set[str] = set()
        for record in (manifest.get("resources") or {}).values():
            if not isinstance(record, dict):
                continue
            for entry in record.get("files") or []:
                if not isinstance(entry, dict):
                    continue
                target = str(entry.get("target_relative_path") or "").replace("\\", "/").strip("/")
                if target.endswith(self.disabled_suffix):
                    target = target[:-len(self.disabled_suffix)]
                if target:
                    targets.add(target.lower())
        return targets

    def _build_managed_resource_sight(
        self,
        resource_id: str,
        manifest_record: dict[str, Any],
        skip_cover_data: bool,
    ) -> dict[str, Any] | None:
        try:
            resource, resource_dir = self._sights_repo.load_resource(resource_id)
        except (FileNotFoundError, OSError, ValueError) as exc:
            log.debug(f"忽略无法读取的炮镜资源 {resource_id}: {exc}")
            return None

        resource_files = [entry for entry in resource.get("files") or [] if isinstance(entry, dict)]
        file_count = len(resource_files)
        resource_type = str(
            resource.get("resource_type")
            or manifest_record.get("resource_type")
            or ("single" if file_count == 1 else "package")
        )
        display_name = str(
            resource.get("display_name")
            or manifest_record.get("display_name")
            or resource_id
        )
        metadata_record = self._sights_repo.find_resource_metadata(resource_id)
        metadata = metadata_record.get("meta") if isinstance(metadata_record, dict) else None
        metadata_warnings = self._unique_text_list(
            metadata_record.get("warnings") if isinstance(metadata_record, dict) else []
        )
        meta_summary = (
            self._build_meta_summary_from_meta(metadata, metadata_warnings)
            if isinstance(metadata, dict)
            else self._empty_meta_summary()
        )
        repository_cover = self._sights_repo.find_resource_cover(resource_id)
        preview_path = Path(repository_cover["path"]) if repository_cover.get("path") else None
        cover_fields = self._build_sight_cover_fields(
            preview_path,
            skip_cover_data,
            str(repository_cover.get("cover_source") or "default"),
        )
        try:
            deployment_state = self._sights_repo.get_resource_deployment_state(
                resource_id,
                self._require_usersights_path(),
            )
        except Exception as exc:
            log.debug(f"读取炮镜资源部署状态失败 {resource_id}: {exc}")
            deployment_state = {
                "state": "target_missing",
                "action": "repair_deployment",
                "enabled_count": 0,
                "disabled_count": 0,
                "missing_count": file_count,
                "conflict_count": 0,
                "expected_count": file_count,
            }
        state_name = str(deployment_state.get("state") or "target_missing")
        enabled_count = int(deployment_state.get("enabled_count") or 0)
        disabled_count = int(deployment_state.get("disabled_count") or 0)
        missing_count = int(deployment_state.get("missing_count") or 0)
        conflict_count = int(deployment_state.get("conflict_count") or 0)
        size_bytes = 0
        for entry in resource_files:
            source_relative_path = str(entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
            if not source_relative_path:
                continue
            source_path = resource_dir.joinpath(*PurePosixPath(source_relative_path).parts)
            try:
                size_bytes += source_path.stat().st_size
            except OSError:
                continue
        try:
            mtime = resource_dir.stat().st_mtime
        except OSError:
            mtime = 0
        reference = f"{self.resource_ref_prefix}{resource_id}"
        return {
            "name": reference,
            "enabled_name": reference,
            "display_name": display_name,
            "path": str(resource_dir),
            "item_kind": "managed_resource",
            "resource_type": resource_type,
            "resource_id": resource_id,
            "resource_ids": [resource_id],
            "resource_file_count": file_count,
            "file_count": file_count,
            "file_count_known": True,
            "has_meta": isinstance(metadata, dict),
            "meta_summary": meta_summary,
            "disabled": state_name == "disabled",
            "legacy_disabled": False,
            "managed_by_aimerwt": True,
            "install_status": state_name,
            "deployment_state": state_name,
            "deployment_action": str(deployment_state.get("action") or ""),
            "deployment_states": [deployment_state],
            "deployment_should_prompt": bool(deployment_state.get("should_prompt")),
            "installed_file_count": enabled_count + disabled_count,
            "expected_file_count": int(deployment_state.get("expected_count") or file_count),
            "missing_count": missing_count,
            "conflict_count": conflict_count,
            "size_bytes": size_bytes,
            "mtime": mtime,
            "can_edit": False,
            "can_rename": False,
            **cover_fields,
        }

    def _is_shared_sight_directory(self, directory_name: str, managed_targets: set[str]) -> bool:
        enabled_name = (
            directory_name[:-len(self.disabled_suffix)]
            if directory_name.endswith(self.disabled_suffix)
            else directory_name
        )
        normalized_name = enabled_name.lower()
        if normalized_name == "all_tanks" or self._looks_like_vehicle_sight_dir(enabled_name):
            return True
        return any(target.split("/", 1)[0] == normalized_name for target in managed_targets)

    def _scan_external_sight_files(
        self,
        sight_dir: Path,
        managed_targets: set[str],
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[dict[str, Any]]:
        def iter_candidate_files():
            for path in sight_dir.rglob("*"):
                if path.is_file():
                    yield path

        def report_scan_progress(checked_count: int):
            if not progress_callback:
                return
            try:
                progress_callback(checked_count)
            except Exception as exc:
                log.debug(f"炮镜文件扫描进度回调失败，已忽略: {exc}")

        usersights_dir = self._require_usersights_path()
        by_relative_path: dict[str, tuple[str, Path, bool]] = {}
        checked_count = 0
        for checked_count, file_path in enumerate(iter_candidate_files(), start=1):
            if checked_count % 100 == 0:
                report_scan_progress(checked_count)
            lower_name = file_path.name.lower()
            disabled = lower_name.endswith(f".blk{self.disabled_suffix.lower()}")
            if not disabled and not lower_name.endswith(".blk"):
                continue
            if not self._is_path_within(file_path, usersights_dir):
                continue
            disk_relative_path = self._relative_sight_path(file_path, usersights_dir)
            enabled_relative_path = (
                disk_relative_path[:-len(self.disabled_suffix)]
                if disabled
                else disk_relative_path
            )
            if enabled_relative_path.lower() in managed_targets:
                continue
            if self._meta_parser.is_standalone_meta_file(file_path):
                continue
            key = enabled_relative_path.lower()
            current = by_relative_path.get(key)
            if current and not current[2]:
                continue
            by_relative_path[key] = (enabled_relative_path, file_path, disabled)

        if checked_count and checked_count % 100 != 0:
            report_scan_progress(checked_count)

        items: list[dict[str, Any]] = []
        for enabled_relative_path, file_path, disabled in sorted(
            by_relative_path.values(),
            key=lambda item: item[0].lower(),
        ):
            try:
                stat = file_path.stat()
                mtime = stat.st_mtime
                size_bytes = stat.st_size
            except OSError:
                mtime = 0
                size_bytes = 0
            reference = self._external_sight_reference(enabled_relative_path)
            items.append({
                "name": reference,
                "enabled_name": reference,
                "display_name": PurePosixPath(enabled_relative_path).stem,
                "path": str(file_path),
                "item_kind": "external_file",
                "resource_type": "single",
                "resource_ids": [],
                "resource_file_count": 1,
                "file_count": 1,
                "file_count_known": True,
                "has_meta": False,
                "meta_summary": self._empty_meta_summary(),
                "disabled": disabled,
                "legacy_disabled": disabled,
                "managed_by_aimerwt": False,
                "install_status": "legacy_disabled" if disabled else "external",
                "deployment_state": "disabled" if disabled else "enabled",
                "deployment_action": "restorable" if disabled else "already_enabled",
                "deployment_states": [],
                "needs_deployment_choice": False,
                "deployment_should_prompt": False,
                "installed_file_count": 1,
                "expected_file_count": 1,
                "missing_count": 0,
                "conflict_count": 0,
                "size_bytes": size_bytes,
                "mtime": mtime,
                "can_edit": False,
                "can_rename": False,
                **self._build_sight_cover_fields(None, False, "default"),
            })
        return items

    def _quick_scan_sight_dir(self, sight_dir: Path, install_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        """快速扫描炮镜目录的直接子项，避免首页递归遍历大目录。"""
        file_count = 0
        file_count_known = True
        has_meta = False
        meta_candidates: list[Path] = []
        try:
            for child in sight_dir.iterdir():
                if child.is_dir():
                    file_count_known = False
                    continue
                if not child.is_file() or child.suffix.lower() != ".blk":
                    continue
                meta_candidates.append(child)
                if "aimerwt" in child.name.lower():
                    has_meta = True
                if file_count < self.quick_scan_file_limit:
                    file_count += 1
                else:
                    file_count_known = False
        except PermissionError:
            log.warning(f"无法快速扫描目录 {sight_dir.name}（权限不足）")
            file_count_known = False
        except OSError as e:
            log.debug(f"快速扫描炮镜目录失败 {sight_dir}: {e}")
            file_count_known = False
        meta_summary = self._build_sight_meta_summary(sight_dir, meta_candidates, install_summary)
        if meta_summary["parse_status"] == "has_meta":
            has_meta = True
        return {
            "file_count": file_count,
            "file_count_known": file_count_known,
            "has_meta": has_meta,
            "meta_summary": meta_summary,
        }

    def _empty_meta_summary(self, status: str = "no_meta", error: str = "", warnings: list[str] | None = None) -> dict[str, Any]:
        return {
            "parse_status": status,
            "author": "",
            "package_name": "",
            "description": "",
            "tags": [],
            "ammo_types": [],
            "recommended_vehicles": [],
            "target_resolution": "",
            "target_resolutions": [],
            "hover_text": {},
            "apply_correction_to_gun": None,
            "sensitivity": "",
            "link_video": "",
            "link_wtlive": "",
            "link_bilibili": "",
            "error": error,
            "warnings": warnings or [],
        }

    def _build_meta_summary_from_meta(
        self,
        meta: dict[str, Any],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        files = meta.get("files") if isinstance(meta.get("files"), list) else []
        ammo_types = []
        recommended_vehicles = []
        for entry in files:
            if not isinstance(entry, dict):
                continue
            ammo_types.append(entry.get("ammo_type"))
            recommended_vehicles.extend(entry.get("recommended_vehicles") or [])
        recommended_vehicles.extend(meta.get("recommended_vehicles") or [])
        summary = self._empty_meta_summary("has_meta", warnings=warnings or [])
        summary.update({
            "author": str(meta.get("author") or ""),
            "package_name": str(meta.get("package_name") or ""),
            "description": str(meta.get("description") or ""),
            "tags": self._unique_text_list(meta.get("tags")),
            "ammo_types": self._unique_text_list(ammo_types),
            "recommended_vehicles": self._unique_text_list(recommended_vehicles),
            "target_resolution": str(meta.get("target_resolution") or ""),
            "target_resolutions": self._unique_text_list(meta.get("target_resolutions")),
            "hover_text": meta.get("hover_text") if isinstance(meta.get("hover_text"), dict) else {},
            "apply_correction_to_gun": (
                meta.get("apply_correction_to_gun") if isinstance(meta.get("apply_correction_to_gun"), bool) else None
            ),
            "sensitivity": meta.get("sensitivity") if meta.get("sensitivity") is not None else "",
            "link_video": str(meta.get("link_video") or ""),
            "link_wtlive": str(meta.get("link_wtlive") or ""),
            "link_bilibili": str(meta.get("link_bilibili") or ""),
        })
        return summary

    def _collect_sight_metadata_records(
        self,
        sight_dir: Path,
        candidates: list[Path] | None = None,
    ) -> dict[str, Any]:
        """采集目录中的内嵌 V2 与旧版独立 V1，并返回统一元数据。"""
        warnings: list[str] = []
        errors: list[str] = []
        v2_records: list[dict[str, Any]] = []
        v1_records: list[dict[str, Any]] = []
        v2_files: list[str] = []
        v1_files: list[str] = []
        try:
            scan_files = candidates if candidates is not None else [
                path for path in sight_dir.rglob("*.blk") if path.is_file()
            ]
            scan_files = sorted(
                scan_files,
                key=lambda path: self._relative_sight_path(path, sight_dir).lower(),
            )
        except OSError as exc:
            return {
                "meta": {},
                "warnings": [str(exc)],
                "error": "scan_meta_failed",
                "status": "meta_error",
                "v2_records": [],
                "v1_records": [],
                "metadata_files": [],
            }

        for file_path in scan_files:
            embedded = self._meta_parser.parse_embedded_meta_file(
                file_path,
                package_root=sight_dir,
            )
            if embedded.get("parsed"):
                v2_records.append(dict(embedded.get("meta") or {}))
                v2_files.append(self._relative_sight_path(file_path, sight_dir))
                warnings.extend(embedded.get("warnings") or [])
                continue
            if embedded.get("error") == "embedded_meta_error":
                errors.append("embedded_meta_error")
                warnings.extend(embedded.get("warnings") or [])

            if not self._meta_parser.is_meta_filename(file_path.name):
                continue
            legacy = self._meta_parser.parse_meta_file(
                file_path,
                package_root=sight_dir,
            )
            if legacy.get("parsed"):
                v1_records.append(dict(legacy.get("meta") or {}))
                v1_files.append(self._relative_sight_path(file_path, sight_dir))
                warnings.extend(legacy.get("warnings") or [])
                continue
            errors.append(str(legacy.get("error") or "meta_error"))
            warnings.extend(legacy.get("warnings") or [])

        return self._merge_collected_sight_metadata(
            v2_records,
            v1_records,
            warnings,
            errors,
            v2_files + v1_files,
            v2_sources=v2_files,
        )

    def _merge_collected_sight_metadata(
        self,
        v2_records: list[dict[str, Any]],
        v1_records: list[dict[str, Any]],
        warnings: list[str],
        errors: list[str],
        metadata_files: list[str],
        *,
        v2_sources: list[str] | None = None,
    ) -> dict[str, Any]:
        source_values = v2_sources if isinstance(v2_sources, list) else []
        packages: dict[str, list[tuple[dict[str, Any], str]]] = {}
        for record_index, record in enumerate(v2_records):
            package_id = str(record.get("package_id") or "").strip()
            if not package_id:
                continue
            source = (
                str(source_values[record_index] or "")
                if record_index < len(source_values)
                else ""
            )
            packages.setdefault(package_id, []).append((
                record,
                source.replace("\\", "/").strip()
                or f"record:{record_index + 1}",
            ))

        merged_packages: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        for package_items in packages.values():
            package_records = [item[0] for item in package_items]
            package_sources = [item[1] for item in package_items]
            merged = self._meta_parser.merge_embedded_records(
                package_records,
                record_sources=package_sources,
            )
            warnings.extend(merged.get("warnings") or [])
            for detail in merged.get("conflicts") or []:
                if isinstance(detail, dict) and detail not in conflicts:
                    conflicts.append(dict(detail))
            if merged.get("parsed"):
                merged_packages.append(dict(merged.get("meta") or {}))
            elif merged.get("error"):
                errors.append(str(merged["error"]))

        if len(merged_packages) > 1:
            warnings.append("multiple_embedded_packages")
        meta = merged_packages[0] if merged_packages else {}
        if v1_records:
            if meta:
                meta = self._merge_legacy_meta_into_embedded(meta, v1_records[0], warnings)
            else:
                meta = deepcopy(v1_records[0])

        status = "has_meta" if meta else ("meta_error" if errors else "no_meta")
        return {
            "meta": meta,
            "warnings": self._unique_text_list(warnings),
            "conflicts": conflicts,
            "error": "" if meta else (errors[0] if errors else ""),
            "status": status,
            "v2_records": v2_records,
            "v1_records": v1_records,
            "metadata_files": self._unique_text_list(metadata_files),
        }

    def _merge_legacy_meta_into_embedded(
        self,
        embedded_meta: dict[str, Any],
        legacy_meta: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        """以 V2 为准，并保留 V1 中未被 V2 描述的真实文件。"""
        merged = deepcopy(embedded_meta)
        for key, value in legacy_meta.items():
            if key in {"meta_version", "files", "groups"}:
                continue
            if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                merged[key] = deepcopy(value)

        embedded_paths = {
            str(entry.get("path") or "").replace("\\", "/").strip().lower()
            for entry in merged.get("files") or []
            if isinstance(entry, dict)
        }
        v2_paths = set(embedded_paths)
        merged_files = list(merged.get("files") or [])
        for entry in legacy_meta.get("files") or []:
            if not isinstance(entry, dict):
                continue
            path_key = str(entry.get("path") or "").replace("\\", "/").strip().lower()
            if not path_key:
                continue
            if path_key in embedded_paths:
                warnings.append(f"legacy_meta_shadowed:{path_key}")
                continue
            embedded_paths.add(path_key)
            merged_files.append(deepcopy(entry))
        merged["files"] = merged_files

        groups = list(merged.get("groups") or [])
        used_group_ids = {
            str(group.get("group_id") or "")
            for group in groups
            if isinstance(group, dict)
        }
        for group in legacy_meta.get("groups") or []:
            if not isinstance(group, dict):
                continue
            remaining_files = [
                path
                for path in group.get("files") or []
                if str(path or "").replace("\\", "/").strip().lower() not in v2_paths
            ]
            if not remaining_files:
                continue
            copied = deepcopy(group)
            copied["files"] = remaining_files
            group_id = str(copied.get("group_id") or "")
            if group_id in used_group_ids:
                copied["group_id"] = f"legacy_{group_id}"
            used_group_ids.add(str(copied.get("group_id") or ""))
            groups.append(copied)
        merged["groups"] = groups
        return merged

    def _build_sight_meta_summary(
        self,
        sight_dir: Path,
        candidates: list[Path],
        install_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """读取顶层 V2/V1 或 AimerWT 内部映射的轻量摘要。"""
        collected = self._collect_sight_metadata_records(sight_dir, candidates)
        if collected["status"] == "has_meta":
            return self._build_meta_summary_from_meta(
                collected["meta"],
                collected["warnings"],
            )
        if collected["status"] == "meta_error":
            return self._empty_meta_summary(
                "meta_error",
                error=collected["error"] or "meta_error",
                warnings=collected["warnings"],
            )
        repository = self._load_repository_sight_meta(sight_dir, install_summary)
        if repository is not None:
            return self._build_meta_summary_from_meta(repository["meta"], repository["warnings"])
        linked = self._load_linked_sight_meta(sight_dir)
        if linked is not None:
            return self._build_meta_summary_from_meta(linked["meta"], linked["warnings"])
        return self._empty_meta_summary()

    @staticmethod
    def _unique_text_list(value: Any) -> list[str]:
        raw_items = value if isinstance(value, list) else [value]
        seen: set[str] = set()
        items: list[str] = []
        for item in raw_items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(text)
        return items

    def _build_sight_cover_fields(
        self,
        preview_path: Path | None,
        skip_cover_data: bool,
        cover_source: str | None = None,
    ) -> dict[str, Any]:
        """生成炮镜卡片封面字段，大规模库列表阶段避免同步 base64 编码。"""
        preview_value = str(preview_path) if preview_path else ""
        source_value = str(cover_source or ("legacy_usersights" if preview_path else "default"))
        if skip_cover_data:
            cover_pending = bool(preview_path)
            return {
                "cover_url": "",
                "cover_is_default": not bool(preview_path),
                "preview_path": preview_value,
                "cover_pending": cover_pending,
                "cover_type": "pending" if cover_pending else "default",
                "cover_source": source_value,
            }

        cover_url = ""
        cover_is_default = not bool(preview_path)
        cover_type = "custom" if preview_path else "default"
        if preview_path:
            cover_url = self._to_data_url(preview_path)
        return {
            "cover_url": cover_url,
            "cover_is_default": cover_is_default,
            "preview_path": preview_value,
            "cover_pending": False,
            "cover_type": cover_type,
            "cover_source": source_value,
        }

    def discover_usersights_paths(self, configured_sights_path: str | None = None) -> list[dict[str, Any]]:
        """
        自动搜索系统中所有可能的 War Thunder UserSights 路径。

        官方路径格式：
        - Windows: Documents/My Games/WarThunder/Saves/<UID>/production/UserSights
        - Linux: ~/.config/WarThunder/Saves/<UID>/production/UserSights
        - macOS: ~/My Games/WarThunder/Saves/<UID>/production/UserSights
        Args:
            configured_sights_path: 用户配置的炮镜路径（可选）
        Returns:
            包含 uid, path, exists 的列表
        """
        results = []
        system = platform.system()
        
        # 根据平台确定基础路径
        possible_bases = []
        # 从配置路径推导 Saves 基础目录
        if configured_sights_path:
            try:
                p = Path(str(configured_sights_path)).expanduser()

                if p.is_dir():
                    if p.name.lower() == "saves":
                        possible_bases.append(p)
                    else:
                        for child_name in ("Saves", "saves"):
                            cand = p / child_name
                            if cand.exists() and cand.is_dir():
                                possible_bases.append(cand)
                                break

                    if p.name.lower() == "usersights" and p.parent.name.lower() == "production":
                        try:
                            base = p.parents[2]
                            if base.exists() and base.is_dir():
                                possible_bases.append(base)
                        except Exception:
                            pass

                    try:
                        checked = 0
                        for child in p.iterdir():
                            if not child.is_dir():
                                continue
                            checked += 1
                            if (child / "production").exists():
                                possible_bases.append(p)
                                break
                            if checked >= 10:
                                break
                    except Exception:
                        pass

                for cand in [p] + list(p.parents):
                    if cand.name.lower() == "saves":
                        possible_bases.append(cand)
                        break
            except Exception as e:
                log.debug(f"解析配置炮镜路径失败，略过: {e}")

        if system == "Windows":
            # Windows 官方路径
            docs_dir = None
            try:
                import ctypes.wintypes
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                # CSIDL_PERSONAL = 5 (My Documents), SHGFP_TYPE_CURRENT = 0
                if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) != 0:
                    raise OSError("无法通过 Windows API 获取文档路径")

                if not buf.value:
                    raise OSError("获取到的 Windows 文档路径为空")
                     
                docs_dir = Path(buf.value)
            except Exception as e:
                log.warning(f"获取 Windows 文档目录失败，略过默认搜索路径: {e}")

            if not docs_dir:
                docs_dir = Path.home() / "Documents"

            possible_bases.append(docs_dir / "My Games" / "WarThunder" / "Saves")
        elif system == "Darwin":
            # macOS 官方路径
            possible_bases.append(Path.home() / "My Games" / "WarThunder" / "Saves")
            # 备选：Documents 下
            possible_bases.append(Path.home() / "Documents" / "My Games" / "WarThunder" / "Saves")
        else:
            # Linux 官方原生路径
            possible_bases.append(Path.home() / ".config" / "WarThunder" / "Saves")
            # Linux - Wine/Proton 路径（Steam）
            possible_bases.append(
                Path.home() / ".local" / "share" / "Steam" / "steamapps" / "compatdata" / "236390" / "pfx" / "drive_c" / "users" / "steamuser" / "Documents" / "My Games" / "WarThunder" / "Saves"
            )
            # 备选：Documents 下
            possible_bases.append(Path.home() / "Documents" / "My Games" / "WarThunder" / "Saves")
        
        # 搜索所有可能的基础路径
        uid_map = set()
        seen_bases = set()
        
        for base_path in possible_bases:
            try:
                base_key = str(base_path.resolve())
            except Exception:
                base_key = str(base_path)

            if base_key in seen_bases:
                continue
            seen_bases.add(base_key)

            if not base_path.exists():
                continue
            
            try:
                # 遍历 Saves 目录下的所有 UID 文件夹
                for uid_dir in base_path.iterdir():
                    if not uid_dir.is_dir():
                        continue
                    
                    uid = uid_dir.name
                    
                    # 跳过已处理的 UID
                    if uid in uid_map:
                        continue
                    
                    # 构建 UserSights 路径
                    usersights_path = uid_dir / "production" / "UserSights"
                    
                    results.append({
                        "uid": uid,
                        "path": str(usersights_path),
                        "exists": usersights_path.exists()
                    })
                    uid_map.add(uid)
                    
            except PermissionError as e:
                log.error(f"搜索 {base_path} 失败（权限不足）: {e}")
            except Exception as e:
                log.error(f"搜索 {base_path} 失败: {type(e).__name__}: {e}")
        
        if not results:
            log.info("未找到任何 War Thunder Saves 目录")
        
        # 按 UID 排序
        results.sort(key=lambda x: x["uid"])
        return results
    
    def select_uid_path(self, uid: str, configured_sights_path: str | None = None) -> str:
        """
        根据 UID 选择并设置对应的 UserSights 路径。
        如果路径不存在，会自动创建。
        
        Args:
            uid: 用户 UID
            
        Returns:
            设置后的 UserSights 路径
            
        Raises:
            ValueError: 找不到指定的 UID
            SightsPathError: 无法创建目录
        """
        discovered = self.discover_usersights_paths(configured_sights_path=configured_sights_path)
        
        # 查找匹配的 UID
        target = None
        for item in discovered:
            if item["uid"] == uid:
                target = item
                break
        
        if not target:
            raise ValueError(f"未找到 UID: {uid}")
        
        path = Path(target["path"])
        
        # 如果路径不存在，创建它
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                log.info(f"已创建 UserSights 目录: {path}")
            except PermissionError as e:
                raise SightsPathError(f"无法创建 UserSights 目录（权限不足）: {e}")
            except OSError as e:
                raise SightsPathError(f"无法创建 UserSights 目录: {e}")
        
        # 设置路径
        self.set_usersights_path(path)
        return str(path)
    
    def set_usersights_path(self, path: str | Path) -> bool:
        """
        设置并校验 UserSights 工作目录路径。
        
        Args:
            path: UserSights 路径
            
        Returns:
            是否设置成功
            
        Raises:
            ValueError: 路径无效
            SightsPathError: 无法创建目录
        """
        path = Path(path)
        
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                log.info(f"已创建 UserSights 文件夹: {path}")
            except PermissionError as e:
                raise SightsPathError(f"无法创建 UserSights 文件夹（权限不足）: {e}")
            except OSError as e:
                raise SightsPathError(f"无法创建 UserSights 文件夹: {e}")
        
        if not path.is_dir():
            raise ValueError("选择的路径不是文件夹")
        
        self._usersights_path = path
        self._clear_sights_cache()
        log.info(f"UserSights 路径已设置: {path}")
        return True
    
    def get_usersights_path(self) -> Path | None:
        """
        获取当前设置的 UserSights 目录路径。
        
        Returns:
            UserSights 路径或 None
        """
        return self._usersights_path

    def create_sight_repository_task(
        self,
        action: str,
        name: str | None = None,
        resource_ids: list[str] | None = None,
        deployment_requests: dict[str, dict[str, Any]] | None = None,
        external_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """创建炮镜资源库写任务，先登记状态，不立即执行。"""
        action_name = self._normalize_sight_repository_task_action(action)
        usersights_dir = self._require_usersights_path()
        enabled_name = self._normalize_batch_sight_name(name) if name else ""
        resolved_external_refs: list[str] = []
        if action_name == "adopt_external":
            seen_refs: set[str] = set()
            for raw_reference in external_refs or []:
                normalized_reference = self._normalize_batch_sight_name(raw_reference)
                if not normalized_reference.startswith(self.file_ref_prefix):
                    raise ValueError("只能纳管 UserSights 中的外部炮镜文件")
                if normalized_reference in seen_refs:
                    continue
                seen_refs.add(normalized_reference)
                resolved_external_refs.append(normalized_reference)
            if not resolved_external_refs:
                raise ValueError("没有可纳管的外部炮镜")
            resolved_resource_ids = []
            total_count = len(resolved_external_refs)
        elif resource_ids is None and enabled_name:
            summary = self._sights_repo.summarize_target_group(usersights_dir, enabled_name)
            if summary.get("manifest_corrupt"):
                error_item = {
                    "resource_id": "",
                    "error": str(summary.get("manifest_error") or "manifest_corrupt"),
                    "error_code": "manifest_corrupt",
                }
                return self._create_failed_sight_repository_task(
                    action_name,
                    enabled_name,
                    error_item,
                    {"manifest_corrupt_count": 1},
                )
            summary_resource_ids = [str(resource_id) for resource_id in summary.get("resource_ids") or [] if str(resource_id)]
            if action_name in {"accept_current_state", "clear_install_record", "resync_resource"} and len(summary_resource_ids) > 1:
                error_item = {
                    "resource_id": "",
                    "resource_ids": summary_resource_ids,
                    "error": "target_group 解析到多个炮镜资源，必须传入明确 resource_ids",
                    "error_code": "ambiguous_target_group",
                }
                return self._create_failed_sight_repository_task(
                    action_name,
                    enabled_name,
                    error_item,
                    {"ambiguous_target_group_count": 1},
                )
        if action_name != "adopt_external":
            resolved_resource_ids = self._resolve_sight_repository_task_resource_ids(
                usersights_dir,
                enabled_name,
                resource_ids,
            )
            total_count = self._count_sight_repository_task_files(usersights_dir, resolved_resource_ids)
        now = self._task_timestamp()
        task_id = f"sight_repo_{uuid.uuid4().hex}"
        task = {
            "success": True,
            "task_id": task_id,
            "action": action_name,
            "name": enabled_name,
            "resource_ids": resolved_resource_ids,
            "external_refs": resolved_external_refs,
            "deployment_requests": {
                resource_id: dict((deployment_requests or {}).get(resource_id) or {})
                for resource_id in resolved_resource_ids
                if isinstance((deployment_requests or {}).get(resource_id), dict)
            },
            "status": "queued",
            "cancel_requested": False,
            "total_count": total_count,
            "processed_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "skipped_count": 0,
            "conflict_count": 0,
            "error_count": 0,
            "errors": [],
            "results": [],
            "result": {},
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "finished_at": "",
        }
        with self._sight_task_lock:
            self._sight_tasks[task_id] = task
            return self._copy_sight_task(task)

    def _create_failed_sight_repository_task(
        self,
        action_name: str,
        enabled_name: str,
        error_item: dict[str, str],
        aggregate: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        now = self._task_timestamp()
        task_id = f"sight_repo_{uuid.uuid4().hex}"
        errors = [dict(error_item)]
        result = self._build_sight_task_result(aggregate or {}, [], errors)
        task = {
            "success": True,
            "task_id": task_id,
            "action": action_name,
            "name": enabled_name,
            "resource_ids": [],
            "status": "failed",
            "cancel_requested": False,
            "total_count": 0,
            "processed_count": 0,
            "success_count": 0,
            "fail_count": 1,
            "skipped_count": 0,
            "conflict_count": 0,
            "error_count": len(errors),
            "errors": errors,
            "results": [],
            "result": result,
            "created_at": now,
            "updated_at": now,
            "started_at": "",
            "finished_at": now,
        }
        with self._sight_task_lock:
            self._sight_tasks[task_id] = task
            return self._copy_sight_task(task)

    def start_sight_repository_task(
        self,
        action: str,
        name: str | None = None,
        resource_ids: list[str] | None = None,
        deployment_requests: dict[str, dict[str, Any]] | None = None,
        external_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """创建并启动炮镜资源库写任务，返回 task_id 供前端查询。"""
        task = self.create_sight_repository_task(
            action,
            name=name,
            resource_ids=resource_ids,
            deployment_requests=deployment_requests,
            external_refs=external_refs,
        )
        if task.get("status") != "queued":
            return task
        thread = threading.Thread(
            target=self.run_sight_repository_task,
            args=(task["task_id"],),
            name=f"SightRepositoryTask-{task['action']}",
            daemon=True,
        )
        thread.start()
        return task

    def start_sight_adoption_task(self, external_refs: list[str]) -> dict[str, Any]:
        """批量纳管当前 UserSights 中的外部 BLK，并保持每个文件的启停状态。"""
        return self.start_sight_repository_task(
            "adopt_external",
            external_refs=external_refs,
        )

    def run_sight_repository_task(self, task_id: str) -> dict[str, Any]:
        """执行已创建的炮镜资源库任务；测试和后台线程共用此入口。"""
        with self._sight_task_lock:
            task = self._sight_tasks.get(str(task_id or ""))
            if not isinstance(task, dict):
                raise FileNotFoundError(f"炮镜资源库任务不存在: {task_id}")
            if task["status"] == "canceled":
                return self._copy_sight_task(task)
            if task["status"] != "queued":
                raise RuntimeError(f"炮镜资源库任务状态不可执行: {task['status']}")
            now = self._task_timestamp()
            task["status"] = "running"
            task["started_at"] = now
            task["updated_at"] = now
            action_name = str(task["action"])
            resource_ids = list(task.get("resource_ids") or [])
            external_refs = list(task.get("external_refs") or [])
            work_items = external_refs if action_name == "adopt_external" else resource_ids
            deployment_requests = dict(task.get("deployment_requests") or {})
            total_count = int(task.get("total_count") or len(work_items))

        aggregate: dict[str, int] = {}
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        success_count = 0
        fail_count = 0
        processed_count = 0
        skipped_count = 0
        usersights_dir = self._require_usersights_path()

        for index, work_item in enumerate(work_items):
            with self._sight_task_lock:
                if task.get("cancel_requested"):
                    task["status"] = "canceled"
                    skipped_count = max(0, total_count - processed_count)
                    task["skipped_count"] = skipped_count
                    task["updated_at"] = self._task_timestamp()
                    break
            try:
                resource_total = (
                    1
                    if action_name == "adopt_external"
                    else self._count_sight_repository_task_files(usersights_dir, [work_item])
                )
                resource_base_processed = processed_count

                def _should_cancel() -> bool:
                    with self._sight_task_lock:
                        return bool(task.get("cancel_requested"))

                def _on_resource_progress(event: dict[str, Any]) -> None:
                    try:
                        resource_processed = int(event.get("processed_count") or 0)
                    except (TypeError, ValueError):
                        resource_processed = 0
                    try:
                        resource_skipped = int(event.get("skipped_count") or 0)
                    except (TypeError, ValueError):
                        resource_skipped = 0
                    with self._sight_task_lock:
                        task["processed_count"] = resource_base_processed + resource_processed
                        task["skipped_count"] = resource_skipped
                        task["updated_at"] = self._task_timestamp()

                result = self._execute_sight_repository_task_action(
                    action_name,
                    work_item,
                    deployment_request=deployment_requests.get(work_item),
                    should_cancel=_should_cancel,
                    progress_callback=_on_resource_progress,
                )
                results.append(result)
                try:
                    result_processed = int(result.get("processed_count") or 0)
                except (TypeError, ValueError):
                    result_processed = 0
                processed_count += result_processed or resource_total or 1
                if result.get("success"):
                    success_count += 1
                else:
                    fail_count += 1
                self._accumulate_sight_task_result(aggregate, result)
                if result.get("canceled"):
                    remaining_items = work_items[index + 1:]
                    remaining_count = (
                        len(remaining_items)
                        if action_name == "adopt_external"
                        else self._count_sight_repository_task_files(usersights_dir, remaining_items)
                    )
                    try:
                        result_skipped = int(result.get("skipped_count") or 0)
                    except (TypeError, ValueError):
                        result_skipped = 0
                    skipped_count = result_skipped + remaining_count
                    with self._sight_task_lock:
                        task["status"] = "canceled"
                        task["skipped_count"] = skipped_count
                    break
            except Exception as e:
                resource_total = (
                    1
                    if action_name == "adopt_external"
                    else self._count_sight_repository_task_files(usersights_dir, [work_item])
                )
                processed_count += resource_total or 1
                fail_count += 1
                error_item = {"resource_id": str(work_item), "error": str(e)}
                if isinstance(e, FileNotFoundError) and "炮镜资源不存在" in str(e):
                    error_item["error_code"] = "resource_missing"
                    aggregate["resource_missing_count"] = int(aggregate.get("resource_missing_count") or 0) + 1
                errors.append(error_item)
            with self._sight_task_lock:
                task["processed_count"] = processed_count
                task["success_count"] = success_count
                task["fail_count"] = fail_count
                task["skipped_count"] = skipped_count
                task["error_count"] = len(errors)
                task["conflict_count"] = int(aggregate.get("conflict_count") or 0)
                task["errors"] = list(errors)
                task["results"] = list(results)
                task["result"] = self._build_sight_task_result(aggregate, results, errors)
                task["updated_at"] = self._task_timestamp()

        with self._sight_task_lock:
            if task["status"] != "canceled":
                task["status"] = "failed" if errors or fail_count else "succeeded"
            task["finished_at"] = self._task_timestamp()
            task["updated_at"] = task["finished_at"]
            task["processed_count"] = processed_count
            task["success_count"] = success_count
            task["fail_count"] = fail_count
            task["skipped_count"] = skipped_count
            task["error_count"] = len(errors)
            task["conflict_count"] = int(aggregate.get("conflict_count") or 0)
            task["errors"] = list(errors)
            task["results"] = list(results)
            task["result"] = self._build_sight_task_result(aggregate, results, errors)
            final_task = self._copy_sight_task(task)

        if processed_count:
            self._clear_sights_cache()
        return final_task

    def get_sight_repository_task(self, task_id: str) -> dict[str, Any]:
        """读取炮镜资源库任务状态。"""
        with self._sight_task_lock:
            task = self._sight_tasks.get(str(task_id or ""))
            if not isinstance(task, dict):
                return {"success": False, "task_id": str(task_id or ""), "status": "missing", "msg": "任务不存在"}
            return self._copy_sight_task(task)

    def cancel_sight_repository_task(self, task_id: str) -> dict[str, Any]:
        """请求取消炮镜资源库任务；已完成任务只返回当前状态。"""
        with self._sight_task_lock:
            task = self._sight_tasks.get(str(task_id or ""))
            if not isinstance(task, dict):
                return {"success": False, "task_id": str(task_id or ""), "status": "missing", "msg": "任务不存在"}
            if task["status"] == "queued":
                task["status"] = "canceled"
                task["finished_at"] = self._task_timestamp()
            if task["status"] in {"queued", "running", "canceled"}:
                task["cancel_requested"] = True
            task["updated_at"] = self._task_timestamp()
            return self._copy_sight_task(task)

    def _normalize_sight_repository_task_action(self, action: str) -> str:
        action_name = str(action or "").strip()
        allowed_actions = {
            "adopt_external",
            "install_resource",
            "enable_resource",
            "disable_resource",
            "uninstall_resource",
            "resync_resource",
            "accept_current_state",
            "clear_install_record",
            "apply_deployment",
        }
        if action_name not in allowed_actions:
            raise ValueError(f"炮镜资源库任务类型不支持: {action_name}")
        return action_name

    def _require_usersights_path(self) -> Path:
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        return usersights_dir

    def _resolve_sight_repository_task_resource_ids(
        self,
        usersights_dir: Path,
        enabled_name: str,
        resource_ids: list[str] | None,
    ) -> list[str]:
        if resource_ids is not None:
            resolved = [str(resource_id).strip() for resource_id in resource_ids if str(resource_id).strip()]
        else:
            if not enabled_name:
                raise ValueError("必须提供炮镜名称或资源 ID")
            summary = self._sights_repo.summarize_target_group(usersights_dir, enabled_name)
            resolved = [str(resource_id) for resource_id in summary.get("resource_ids") or [] if str(resource_id)]
        if not resolved:
            raise FileNotFoundError(f"没有找到 AimerWT 安装记录: {enabled_name or 'resource_ids'}")
        return resolved

    @staticmethod
    def _ambiguous_target_group_result(enabled_name: str, resource_ids: list[str]) -> dict[str, Any]:
        return {
            "success": False,
            "name": enabled_name,
            "resource_ids": list(resource_ids),
            "error_code": "ambiguous_target_group",
            "msg": "该炮镜目录包含多个 AimerWT 资源，请先明确选择要处理的炮镜资源",
            "conflict_count": 1,
            "conflicts": [{"target_relative_path": enabled_name, "reason": "ambiguous_target_group"}],
        }

    def _count_sight_repository_task_files(self, usersights_dir: Path, resource_ids: list[str]) -> int:
        total = 0
        manifest = self._sights_repo.load_manifest(usersights_dir)
        for resource_id in resource_ids:
            resource_key = str(resource_id or "").strip()
            if not resource_key:
                continue
            resource_record = manifest.get("resources", {}).get(resource_key)
            if isinstance(resource_record, dict):
                files = [entry for entry in resource_record.get("files") or [] if isinstance(entry, dict)]
                if files:
                    total += len(files)
                    continue
            try:
                resource, _resource_dir = self._sights_repo.load_resource(resource_key)
                files = [entry for entry in resource.get("files") or [] if isinstance(entry, dict)]
                total += len(files) or 1
            except Exception:
                total += 1
        return total or len(resource_ids)

    def _execute_sight_repository_task_action(
        self,
        action_name: str,
        resource_id: str,
        deployment_request: dict[str, Any] | None = None,
        should_cancel: Any = None,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        usersights_dir = self._require_usersights_path()
        if action_name == "adopt_external":
            normalized_reference, _file_path, _disabled = self._resolve_external_sight_file(resource_id)
            target_relative_path = self._normalize_external_sight_relative_path(normalized_reference)
            return self._sights_repo.adopt_external_file(
                target_relative_path,
                usersights_dir,
                display_name=PurePosixPath(target_relative_path).stem,
            )
        if action_name in {"install_resource", "resync_resource"}:
            return self._sights_repo.install_resource_batched(
                resource_id,
                usersights_dir,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
        if action_name == "enable_resource":
            return self._sights_repo.enable_resource_batched(
                resource_id,
                usersights_dir,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
        if action_name == "disable_resource":
            return self._sights_repo.disable_resource_batched(
                resource_id,
                usersights_dir,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
        if action_name == "uninstall_resource":
            return self._sights_repo.uninstall_resource_batched(
                resource_id,
                usersights_dir,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
        if action_name == "apply_deployment":
            if callable(should_cancel) and should_cancel():
                return {"success": True, "canceled": True, "processed_count": 0, "skipped_count": 1}
            return self._sights_repo.apply_resource_deployment(
                resource_id,
                usersights_dir,
                deployment_request,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
        if action_name == "accept_current_state":
            return self._sights_repo.accept_current_state(resource_id, usersights_dir)
        if action_name == "clear_install_record":
            return self._sights_repo.clear_resource_record(resource_id, usersights_dir)
        raise ValueError(f"炮镜资源库任务类型不支持: {action_name}")

    def _accumulate_sight_task_result(self, aggregate: dict[str, int], result: dict[str, Any]) -> None:
        count_keys = (
            "adopted_count",
            "already_managed_count",
            "enabled_count",
            "disabled_count",
            "installed_count",
            "restored_count",
            "renamed_count",
            "copied_count",
            "reused_count",
            "deleted_count",
            "accepted_count",
            "cleared_count",
            "missing_count",
            "modified_count",
            "conflict_count",
            "kept_shared_count",
            "already_disabled_count",
            "processed_count",
            "total_count",
            "skipped_count",
            "backup_count",
            "resource_missing_count",
        )
        for key in count_keys:
            try:
                aggregate[key] = int(aggregate.get(key) or 0) + int(result.get(key) or 0)
            except (TypeError, ValueError):
                continue

    def _build_sight_task_result(
        self,
        aggregate: dict[str, int],
        results: list[dict[str, Any]],
        errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        conflicts: list[dict[str, Any]] = []
        for result in results:
            conflicts.extend([item for item in result.get("conflicts") or [] if isinstance(item, dict)])
        payload = {key: int(value) for key, value in aggregate.items()}
        payload.update({
            "success_count": sum(1 for item in results if item.get("success")),
            "fail_count": sum(1 for item in results if not item.get("success")) + len(errors),
            "error_count": len(errors),
            "results": list(results),
            "conflicts": conflicts,
            "errors": list(errors),
        })
        return payload

    @staticmethod
    def _copy_sight_task(task: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(task)

    @staticmethod
    def _task_timestamp() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    
    def scan_sights(self, force_refresh: bool = False,
                    default_cover_path: Path | None = None,
                    progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        """
        扫描 UserSights 目录下的炮镜文件夹并生成前端展示用列表数据。
        
        Args:
            force_refresh: 是否强制刷新缓存
            default_cover_path: 默认封面路径
            
        Returns:
            包含 exists, path, items 的字典
        """
        def _report_progress(processed: int, total: int, message: str) -> None:
            if not progress_callback:
                return
            safe_processed = max(0, int(processed or 0))
            safe_total = max(0, int(total or 0))
            if safe_total > 0:
                safe_processed = min(safe_processed, safe_total)
                report_step = max(1, (safe_total + 49) // 50)
                if safe_processed not in (0, safe_total) and safe_processed % report_step != 0:
                    return
            try:
                progress_callback({
                    "processed": safe_processed,
                    "total": safe_total,
                    "message": str(message or ""),
                })
            except Exception as exc:
                log.debug(f"炮镜扫描进度回调失败，已忽略: {exc}")

        if not self._usersights_path or not self._usersights_path.exists():
            return {'exists': False, 'path': '', 'items': []}

        _report_progress(0, 0, "正在建立炮镜索引...")
        root_signature = self._index_cache.build_root_signature(self._usersights_path)
        if (
            not force_refresh
            and self._cache is not None
            and self._cache_signature == root_signature
            and self._cache.get("path") == str(self._usersights_path)
        ):
            cached_items = list(self._cache.get("items") or [])
            _report_progress(len(cached_items), len(cached_items), "炮镜索引已就绪")
            return self._cache

        sights = []
        cached_records = self._index_cache.load_records(self._usersights_path)
        next_records: dict[str, dict] = {}
        skip_cover_data = len(root_signature) > self.cover_inline_item_limit
        scan_error = ""
        try:
            manifest = self._load_sights_manifest()
            resource_records = manifest.get("resources") if isinstance(manifest.get("resources"), dict) else {}
            skip_cover_data = (
                len(root_signature) + len(resource_records) > self.cover_inline_item_limit
            )
            managed_targets = self._manifest_managed_target_paths(manifest)
            signature_by_name = {
                str(entry.get("name") or ""): entry
                for entry in root_signature
                if isinstance(entry, dict)
            }
            total_work = len(resource_records)
            for entry in root_signature:
                if not isinstance(entry, dict):
                    total_work += 1
                    continue
                directory_name = str(entry.get("name") or "")
                if self._is_shared_sight_directory(directory_name, managed_targets):
                    total_work += max(1, int(entry.get("content_file_count") or 0))
                else:
                    total_work += 1
            total_work = max(1, total_work)
            processed_work = 0
            _report_progress(0, total_work, "正在检查炮镜文件...")
            for resource_id, manifest_record in resource_records.items():
                if isinstance(manifest_record, dict):
                    sight = self._build_managed_resource_sight(
                        str(resource_id),
                        manifest_record,
                        skip_cover_data,
                    )
                    if sight is not None:
                        sights.append(sight)
                processed_work += 1
                _report_progress(processed_work, total_work, "正在检查炮镜文件...")
            for item in self._usersights_path.iterdir():
                if not item.is_dir():
                    continue
                if self._is_shared_sight_directory(item.name, managed_targets):
                    signature_entry = signature_by_name.get(item.name, {})
                    shared_work = max(1, int(signature_entry.get("content_file_count") or 0))
                    shared_base = processed_work
                    external_items = self._scan_external_sight_files(
                        item,
                        managed_targets,
                        progress_callback=lambda checked: _report_progress(
                            shared_base + min(checked, shared_work),
                            total_work,
                            "正在检查炮镜文件...",
                        ),
                    )
                    sights.extend(external_items)
                    processed_work += shared_work
                    _report_progress(processed_work, total_work, "正在检查炮镜文件...")
                    continue

                item_mtime = item.stat().st_mtime
                enabled_name = item.name[:-len(self.disabled_suffix)] if item.name.endswith(self.disabled_suffix) else item.name
                install_summary = self._get_install_summary(enabled_name)
                repository_cover = self._find_repository_cover_from_summary(install_summary)
                legacy_preview_path = self._find_preview_image(item)
                preview_path = Path(repository_cover["path"]) if repository_cover.get("path") else legacy_preview_path
                cover_source = str(
                    repository_cover.get("cover_source")
                    or ("legacy_usersights" if legacy_preview_path else "default")
                )
                signature = self._index_cache.build_item_signature(item, preview_path)
                sight = self._index_cache.get_cached_item(cached_records, item.name, signature)
                quick_info = self._quick_scan_sight_dir(item, install_summary)

                if sight is None:
                    cover_fields = self._build_sight_cover_fields(
                        preview_path,
                        skip_cover_data,
                        cover_source,
                    )
                    sight = {
                        'name': item.name,
                        'path': str(item),
                        'disabled': item.name.endswith(self.disabled_suffix),
                        'enabled_name': enabled_name,
                        'file_count': quick_info["file_count"],
                        'file_count_known': quick_info["file_count_known"],
                        'has_meta': quick_info["has_meta"],
                        'meta_summary': quick_info["meta_summary"],
                        'cover_url': cover_fields["cover_url"],
                        'cover_is_default': cover_fields["cover_is_default"],
                        'preview_path': cover_fields["preview_path"],
                        'cover_pending': cover_fields["cover_pending"],
                        'cover_type': cover_fields["cover_type"],
                        'cover_source': cover_fields["cover_source"],
                        'mtime': item_mtime,
                    }
                else:
                    cover_fields = None
                    if skip_cover_data or "preview_path" not in sight or "cover_pending" not in sight or "cover_type" not in sight or "cover_source" not in sight:
                        cover_fields = self._build_sight_cover_fields(
                            preview_path,
                            skip_cover_data,
                            cover_source,
                        )
                    sight['name'] = item.name
                    sight['path'] = str(item)
                    sight['disabled'] = item.name.endswith(self.disabled_suffix)
                    sight['enabled_name'] = enabled_name
                    sight['file_count'] = quick_info["file_count"]
                    sight['file_count_known'] = quick_info["file_count_known"]
                    sight['has_meta'] = quick_info["has_meta"]
                    sight['meta_summary'] = quick_info["meta_summary"]
                    if cover_fields is not None:
                        sight['cover_url'] = cover_fields["cover_url"]
                        sight['cover_is_default'] = cover_fields["cover_is_default"]
                        sight['preview_path'] = cover_fields["preview_path"]
                        sight['cover_pending'] = cover_fields["cover_pending"]
                        sight['cover_type'] = cover_fields["cover_type"]
                        sight['cover_source'] = cover_fields["cover_source"]
                    sight['mtime'] = item_mtime

                sight["item_kind"] = "legacy_folder"
                sight["resource_type"] = "single" if quick_info["file_count"] == 1 and quick_info["file_count_known"] else "package"
                sight["display_name"] = enabled_name
                sight["can_edit"] = True
                sight["can_rename"] = True
                sight['size_bytes'] = int(signature.get("content_size") or 0)
                self._apply_install_summary(sight, install_summary)
                sights.append(sight)
                next_records[item.name] = self._index_cache.make_record(signature, sight)
                processed_work += 1
                _report_progress(processed_work, total_work, "正在检查炮镜文件...")
        except PermissionError as e:
            log.error(f"扫描炮镜失败（权限不足）: {e}")
            scan_error = str(e)
        except OSError as e:
            log.error(f"扫描炮镜失败（系统错误）: {e}")
            scan_error = str(e)

        if scan_error:
            if self._cache is not None and self._cache.get("path") == str(self._usersights_path):
                fallback = deepcopy(self._cache)
            else:
                fallback = {
                    'exists': True,
                    'path': str(self._usersights_path),
                    'items': [],
                }
            fallback["scan_error"] = scan_error
            return fallback
        
        result = {
            'exists': True,
            'path': str(self._usersights_path),
            'items': sorted(
                sights,
                key=lambda x: str(x.get("display_name") or x.get("name") or "").lower(),
            )
        }
        item_total = len(result.get("items") or [])
        _report_progress(item_total, item_total, "炮镜列表已准备完成")
        self._cache = result
        self._cache_signature = root_signature
        self._index_cache.save_records(self._usersights_path, next_records)
        return result

    def _get_install_summary(self, target_group: str) -> dict[str, Any]:
        if not self._usersights_path:
            return {}
        try:
            return self._sights_repo.summarize_target_group(
                self._usersights_path,
                str(target_group or ""),
            )
        except Exception as e:
            log.debug(f"读取炮镜安装摘要失败，已按外部资源处理: {e}")
            return {}

    def _find_repository_cover_from_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        resource_ids = summary.get("resource_ids") if isinstance(summary, dict) else []
        if not isinstance(resource_ids, list):
            return {}
        for resource_id in resource_ids:
            cover = self._sights_repo.find_resource_cover(str(resource_id))
            if cover.get("path"):
                return cover
        return {}

    def _apply_install_summary(self, sight: dict[str, Any], summary: dict[str, Any] | None = None) -> None:
        """把安装清单状态补充到列表项，兼容旧 UserSights 目录扫描结果。"""
        if not self._usersights_path and summary is None:
            return
        if summary is None:
            summary = self._get_install_summary(str(sight.get("enabled_name") or sight.get("name") or ""))
        if sight.get("disabled") and not summary.get("managed_by_aimerwt"):
            summary["install_status"] = "legacy_disabled"
            summary["legacy_disabled"] = True
        else:
            summary["legacy_disabled"] = bool(sight.get("disabled"))
        sight.update(summary)
        resource_ids = [str(value) for value in summary.get("resource_ids") or [] if str(value)]
        deployment_states: list[dict[str, Any]] = []
        for resource_id in resource_ids:
            try:
                deployment_states.append(
                    self._sights_repo.get_resource_deployment_state(resource_id, self._usersights_path)
                )
            except Exception as exc:
                log.debug(f"读取炮镜部署状态失败 {resource_id}: {exc}")
        if deployment_states:
            state_names = {str(item.get("state") or "") for item in deployment_states}
            action_names = {str(item.get("action") or "") for item in deployment_states}
            if state_names == {"enabled"}:
                deployment_state = "enabled"
                deployment_action = "already_enabled"
            elif state_names == {"disabled"}:
                deployment_state = "disabled"
                deployment_action = "restorable"
            elif "conflict" in state_names:
                deployment_state = "conflict"
                deployment_action = "resolve_conflict"
            elif "target_missing" in state_names:
                deployment_state = "target_missing"
                deployment_action = "repair_deployment"
            else:
                deployment_state = "partial"
                deployment_action = "restorable" if action_names <= {"already_enabled", "restorable"} else "repair_deployment"
        else:
            deployment_state = "disabled" if sight.get("disabled") else "enabled"
            deployment_action = "restorable" if sight.get("disabled") else "already_enabled"
        sight.update({
            "deployment_state": deployment_state,
            "deployment_action": deployment_action,
            "deployment_states": deployment_states,
            "needs_deployment_choice": deployment_action == "needs_deployment_choice",
            "deployment_should_prompt": deployment_action in {"needs_deployment_choice", "repair_deployment", "resolve_conflict"},
        })

    def build_sights_source_index(
        self,
        names: list[str] | None = None,
        limit_per_sight: int = 2,
    ) -> dict[str, Any]:
        """后台索引每个炮镜包的少量尾部来源注释，供前端来源搜索使用。"""
        if not self._usersights_path or not self._usersights_path.exists():
            return {"success": False, "items": [], "error": "usersights_not_set"}

        safe_limit = max(1, min(int(limit_per_sight or 2), 10))
        items: list[dict[str, Any]] = []
        for sight_dir in self._resolve_source_index_dirs(names):
            source_hints: list[str] = []
            source_files: list[str] = []
            indexed_file_count = 0

            for file_path in self._iter_real_blk_files_for_source_index(sight_dir, safe_limit):
                indexed_file_count += 1
                comment = self._blk_analyzer.extract_tail_comment(file_path)
                if self._blk_analyzer.classify_tail_comment(comment) != "source_hint":
                    continue
                text = str(comment or "").strip()
                if not text or text in source_hints:
                    continue
                source_hints.append(text)
                source_files.append(self._relative_sight_path(file_path, sight_dir))

            enabled_name = sight_dir.name[:-len(self.disabled_suffix)] if sight_dir.name.endswith(self.disabled_suffix) else sight_dir.name
            items.append({
                "name": sight_dir.name,
                "enabled_name": enabled_name,
                "source_hints": source_hints,
                "source_files": source_files,
                "source_indexed": True,
                "indexed_file_count": indexed_file_count,
            })

        return {"success": True, "items": items, "limit_per_sight": safe_limit}

    def _resolve_source_index_dirs(self, names: list[str] | None) -> list[Path]:
        """解析来源索引目标目录；未传 names 时索引当前 UserSights 顶层目录。"""
        if not self._usersights_path:
            return []
        if names:
            dirs: list[Path] = []
            seen: set[str] = set()
            for raw_name in names:
                try:
                    sight_dir = self._resolve_sight_detail_dir(str(raw_name or ""))
                except Exception:
                    continue
                key = str(sight_dir.resolve(strict=False)).lower()
                if key in seen:
                    continue
                seen.add(key)
                dirs.append(sight_dir)
            return dirs
        try:
            return [item for item in self._usersights_path.iterdir() if item.is_dir()]
        except OSError:
            return []

    def _iter_real_blk_files_for_source_index(self, sight_dir: Path, limit: int):
        """懒遍历真实 BLK 文件，达到每包限量后立即停止。"""
        found = 0
        try:
            iterator = sight_dir.rglob("*.blk")
            for file_path in iterator:
                if not file_path.is_file():
                    continue
                if self._meta_parser.is_standalone_meta_file(file_path):
                    continue
                yield file_path
                found += 1
                if found >= limit:
                    return
        except OSError:
            return

    def _resolve_sight_detail_context(self, sight_name: str) -> dict[str, Any]:
        reference = str(sight_name or "").strip()
        resource_id = self._parse_resource_reference(reference) if reference.startswith(self.resource_ref_prefix) else ""
        if resource_id:
            resource, resource_dir = self._sights_repo.load_resource(resource_id)
            metadata_record = self._sights_repo.find_resource_metadata(resource_id)
            metadata = metadata_record.get("meta") if isinstance(metadata_record, dict) else None
            metadata_warnings = self._unique_text_list(
                metadata_record.get("warnings") if isinstance(metadata_record, dict) else []
            )
            meta_info = {
                "meta": dict(metadata) if isinstance(metadata, dict) else {},
                "warnings": metadata_warnings,
                "error": "",
                "status": "has_meta" if isinstance(metadata, dict) else "no_meta",
            }
            blk_entries = self._list_resource_blk_feature_entries(
                resource,
                resource_dir,
                meta_info["meta"],
            )
            group_model = self._build_sight_group_model(resource_dir, meta_info["meta"], blk_entries)
            deployment_state = self._sights_repo.get_resource_deployment_state(
                resource_id,
                self._require_usersights_path(),
            )
            state_name = str(deployment_state.get("state") or "target_missing")
            return {
                "sight_dir": resource_dir,
                "name": reference,
                "enabled_name": reference,
                "disabled": state_name == "disabled",
                "item_kind": "managed_resource",
                "resource_id": resource_id,
                "meta_info": meta_info,
                "blk_entries": blk_entries,
                "group_model": group_model,
                "install_fields": {
                    "managed_by_aimerwt": True,
                    "resource_id": resource_id,
                    "resource_ids": [resource_id],
                    "resource_type": str(resource.get("resource_type") or ("single" if len(blk_entries) == 1 else "package")),
                    "resource_file_count": len(blk_entries),
                    "install_status": state_name,
                    "deployment_state": state_name,
                    "deployment_action": str(deployment_state.get("action") or ""),
                    "deployment_states": [deployment_state],
                    "deployment_should_prompt": bool(deployment_state.get("should_prompt")),
                    "installed_file_count": int(deployment_state.get("enabled_count") or 0)
                        + int(deployment_state.get("disabled_count") or 0),
                    "expected_file_count": int(deployment_state.get("expected_count") or len(blk_entries)),
                    "missing_count": int(deployment_state.get("missing_count") or 0),
                    "conflict_count": int(deployment_state.get("conflict_count") or 0),
                    "legacy_disabled": False,
                },
            }

        if reference.startswith(self.file_ref_prefix):
            normalized_reference, file_path, disabled = self._resolve_external_sight_file(reference)
            disk_relative_path = file_path.name
            relative_path = (
                disk_relative_path[:-len(self.disabled_suffix)]
                if disabled
                else disk_relative_path
            )
            blk_entries = [{
                "path": file_path,
                "relative_path": relative_path,
                "disk_relative_path": disk_relative_path,
                "filename": relative_path,
                "file_status": "disabled_by_rename" if disabled else "enabled",
                "disabled": disabled,
            }]
            meta_info = {
                "meta": {},
                "warnings": [],
                "error": "",
                "status": "no_meta",
            }
            group_model = self._build_sight_group_model(file_path.parent, {}, blk_entries)
            return {
                "sight_dir": file_path.parent,
                "name": normalized_reference,
                "enabled_name": normalized_reference,
                "disabled": disabled,
                "item_kind": "external_file",
                "resource_id": "",
                "meta_info": meta_info,
                "blk_entries": blk_entries,
                "group_model": group_model,
                "install_fields": {
                    "managed_by_aimerwt": False,
                    "resource_ids": [],
                    "resource_type": "single",
                    "resource_file_count": 1,
                    "install_status": "legacy_disabled" if disabled else "external",
                    "deployment_state": "disabled" if disabled else "enabled",
                    "deployment_action": "restorable" if disabled else "already_enabled",
                    "deployment_states": [],
                    "needs_deployment_choice": False,
                    "deployment_should_prompt": False,
                    "installed_file_count": 1,
                    "expected_file_count": 1,
                    "missing_count": 0,
                    "conflict_count": 0,
                    "legacy_disabled": disabled,
                },
            }

        sight_dir = self._resolve_sight_detail_dir(reference)
        disabled = sight_dir.name.endswith(self.disabled_suffix)
        enabled_name = sight_dir.name[:-len(self.disabled_suffix)] if disabled else sight_dir.name
        meta_info = self._load_sight_meta(sight_dir)
        group_context = self._get_sight_group_context(sight_dir, meta_info["meta"])
        return {
            "sight_dir": sight_dir,
            "name": sight_dir.name,
            "enabled_name": enabled_name,
            "disabled": disabled,
            "item_kind": "legacy_folder",
            "resource_id": "",
            "meta_info": meta_info,
            "blk_entries": group_context["blk_entries"],
            "group_model": group_context["group_model"],
            "install_fields": None,
        }

    def get_sight_detail(self, sight_name: str, limit: int = 50) -> dict[str, Any]:
        """按需返回单个炮镜包的元数据和第一页 BLK 特征。"""
        context = self._resolve_sight_detail_context(sight_name)
        sight_dir = context["sight_dir"]
        disabled = bool(context["disabled"])
        enabled_name = str(context["enabled_name"])
        meta_info = context["meta_info"]
        blk_entries = context["blk_entries"]
        group_model = context["group_model"]
        page = self._build_blk_features_page(
            sight_dir,
            meta_info["meta"],
            cursor=0,
            limit=limit,
            group_id=group_model["selected_group_id"],
            blk_entries=blk_entries,
            group_model=group_model,
        )
        try:
            mtime = sight_dir.stat().st_mtime
        except OSError:
            mtime = 0
        detail = {
            "success": True,
            "name": str(context["name"]),
            "item_kind": str(context["item_kind"]),
            "can_edit": context["item_kind"] == "legacy_folder",
            "can_rename": context["item_kind"] == "legacy_folder",
            "enabled_name": enabled_name,
            "path": str(sight_dir),
            "disabled": disabled,
            "mtime": mtime,
            "package_blk_total": len(blk_entries),
            "meta": meta_info["meta"],
            "groups": group_model["groups"],
            "selected_group_id": group_model["selected_group_id"],
            "meta_error": meta_info["error"],
            "meta_warnings": meta_info["warnings"],
            "parse_status": meta_info["status"],
            **page,
        }
        install_fields = context.get("install_fields")
        if isinstance(install_fields, dict):
            detail.update(install_fields)
        else:
            self._apply_install_summary(detail, self._get_install_summary(enabled_name))
            detail.setdefault("install_status", "disabled" if disabled else "enabled")
        return detail

    def get_sight_blk_features_page(
        self,
        sight_name: str,
        cursor: str | int | None = None,
        limit: int = 50,
        group_id: str | None = None,
    ) -> dict[str, Any]:
        """分页返回指定炮镜目录内真实 BLK 的特征列表。"""
        context = self._resolve_sight_detail_context(sight_name)
        sight_dir = context["sight_dir"]
        meta_info = context["meta_info"]
        blk_entries = context["blk_entries"]
        group_model = context["group_model"]
        enabled_name = str(context["enabled_name"])
        normalized_group_id = str(group_id or "").strip()
        if normalized_group_id and normalized_group_id != "__all__" and normalized_group_id not in group_model["group_name_map"]:
            return {
                "success": False,
                "error": "group_not_found",
                "error_code": "group_not_found",
                "name": str(context["name"]),
                "enabled_name": enabled_name,
                "blk_feature_total": 0,
                "blk_feature_limit": max(1, min(int(limit or 50), 100)),
                "blk_feature_cursor": None,
                "blk_features": [],
            }
        offset = self._parse_feature_cursor(cursor)
        page = self._build_blk_features_page(
            sight_dir,
            meta_info["meta"],
            cursor=offset,
            limit=limit,
            group_id=normalized_group_id or None,
            blk_entries=blk_entries,
            group_model=group_model,
        )
        return {
            "success": True,
            "name": str(context["name"]),
            "enabled_name": enabled_name,
            **page,
        }

    def _get_sight_group_context(self, sight_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
        """缓存 BLK 列表和分组模型，避免详情页分页反复重建分组关系。"""
        cache_key = self._sight_group_cache_key(sight_dir)
        meta_signature = self._build_sight_group_meta_signature(meta)
        cached = self._sight_group_model_cache.get(cache_key)
        if (
            isinstance(cached, dict)
            and cached.get("meta_signature") == meta_signature
            and self._sight_group_context_cache_current(cached)
        ):
            return {
                "blk_entries": cached.get("blk_entries") or [],
                "group_model": cached.get("group_model") or self._build_sight_group_model(sight_dir, meta, []),
            }

        blk_entries = self._list_real_blk_feature_entries(sight_dir)
        group_model = self._build_sight_group_model(sight_dir, meta, blk_entries)
        self._sight_group_model_cache[cache_key] = {
            "meta_signature": meta_signature,
            "blk_entries": blk_entries,
            "group_model": group_model,
            "file_signatures": self._build_sight_group_file_signatures(blk_entries),
            "directory_signatures": self._build_sight_group_directory_signatures(sight_dir),
        }
        return {"blk_entries": blk_entries, "group_model": group_model}

    def _sight_group_context_cache_current(self, cached: dict[str, Any]) -> bool:
        file_signatures = cached.get("file_signatures")
        directory_signatures = cached.get("directory_signatures")
        if not isinstance(file_signatures, dict) or not isinstance(directory_signatures, dict):
            return False
        for path_text, signature in directory_signatures.items():
            if not self._path_stat_matches_signature(Path(path_text), signature):
                return False
        for path_text, signature in file_signatures.items():
            if not self._path_stat_matches_signature(Path(path_text), signature):
                return False
        return True

    def _build_sight_group_file_signatures(self, blk_entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        signatures: dict[str, dict[str, Any]] = {}
        for entry in blk_entries:
            path = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(path, Path):
                continue
            signature = self._build_path_stat_signature(path)
            if signature is None:
                continue
            signature.update({
                "relative_path": str(entry.get("relative_path") or ""),
                "disk_relative_path": str(entry.get("disk_relative_path") or ""),
                "file_status": str(entry.get("file_status") or ""),
                "disabled": bool(entry.get("disabled")),
            })
            signatures[self._sight_group_path_key(path)] = signature
        return signatures

    def _build_sight_group_directory_signatures(self, sight_dir: Path) -> dict[str, dict[str, Any]]:
        directories = [sight_dir]
        try:
            directories.extend(path for path in sight_dir.rglob("*") if path.is_dir())
        except OSError:
            pass
        signatures: dict[str, dict[str, Any]] = {}
        for directory in directories:
            signature = self._build_path_stat_signature(directory)
            if signature is not None:
                signatures[self._sight_group_path_key(directory)] = signature
        return signatures

    @staticmethod
    def _build_sight_group_meta_signature(meta: dict[str, Any]) -> str:
        if not isinstance(meta, dict):
            return ""
        payload = {
            "files": meta.get("files"),
            "groups": meta.get("groups"),
        }
        try:
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return str(payload)

    @staticmethod
    def _build_path_stat_signature(path: Path) -> dict[str, Any] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return {
            "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
            "size": stat.st_size,
        }

    def _path_stat_matches_signature(self, path: Path, signature: Any) -> bool:
        if not isinstance(signature, dict):
            return False
        current = self._build_path_stat_signature(path)
        if current is None:
            return False
        return current.get("mtime_ns") == signature.get("mtime_ns") and current.get("size") == signature.get("size")

    @staticmethod
    def _sight_group_path_key(path: Path) -> str:
        try:
            return str(path.resolve())
        except OSError:
            return str(path)

    def _sight_group_cache_key(self, sight_dir: Path) -> str:
        return self._sight_group_path_key(sight_dir)

    def _load_sight_meta(self, sight_dir: Path) -> dict[str, Any]:
        """读取当前炮镜包内聚合后的 V2/V1 AimerWT 元数据。"""
        collected = self._collect_sight_metadata_records(sight_dir)
        if collected["status"] != "no_meta":
            return {
                "meta": collected["meta"],
                "warnings": collected["warnings"],
                "conflicts": list(collected.get("conflicts") or []),
                "error": collected["error"],
                "status": collected["status"],
            }
        repository = self._load_repository_sight_meta(sight_dir)
        if repository is not None:
            return {
                "meta": repository["meta"],
                "warnings": repository["warnings"],
                "conflicts": [],
                "error": "",
                "status": "has_meta",
            }
        linked = self._load_linked_sight_meta(sight_dir)
        if linked is not None:
            return {
                "meta": linked["meta"],
                "warnings": linked["warnings"],
                "conflicts": [],
                "error": "",
                "status": "has_meta",
            }
        return {
            "meta": {},
            "warnings": [],
            "conflicts": [],
            "error": "",
            "status": "no_meta",
        }

    def _load_repository_sight_meta(
        self,
        sight_dir: Path,
        install_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """从资源库 package_index 读取作者元数据，避免依赖 UserSights 伪 BLK。"""
        summary = install_summary if isinstance(install_summary, dict) else self._get_install_summary(
            sight_dir.name[:-len(self.disabled_suffix)] if sight_dir.name.endswith(self.disabled_suffix) else sight_dir.name
        )
        resource_ids = summary.get("resource_ids") if isinstance(summary, dict) else []
        if not isinstance(resource_ids, list):
            return None
        target_group = sight_dir.name[:-len(self.disabled_suffix)] if sight_dir.name.endswith(self.disabled_suffix) else sight_dir.name
        for resource_id in resource_ids:
            record = self._sights_repo.find_resource_metadata(str(resource_id), target_group)
            meta = record.get("meta") if isinstance(record, dict) else None
            if not isinstance(meta, dict):
                continue
            warnings = self._unique_text_list(record.get("warnings"))
            warnings.extend(self._validate_repository_meta_file_signatures(sight_dir, record))
            return {"meta": dict(meta), "warnings": self._unique_text_list(warnings)}
        return None

    def _validate_repository_meta_file_signatures(self, sight_dir: Path, record: dict[str, Any]) -> list[str]:
        signatures = record.get("file_signatures")
        if not isinstance(signatures, dict) or not signatures:
            return []
        existing_count = 0
        signature_changed = False
        for rel_path, saved_signature in signatures.items():
            if not isinstance(rel_path, str) or not isinstance(saved_signature, dict):
                continue
            target_file = sight_dir / rel_path
            if not target_file.is_file():
                continue
            existing_count += 1
            current_signature = self._build_meta_link_file_signature(target_file)
            if (
                current_signature.get("size") != saved_signature.get("size")
                or current_signature.get("mtime_ns") != saved_signature.get("mtime_ns")
            ):
                signature_changed = True
        if existing_count == 0:
            return ["repository_meta_target_missing"]
        if signature_changed:
            return ["repository_meta_signature_changed"]
        return []

    def _load_linked_sight_meta(self, sight_dir: Path) -> dict[str, Any] | None:
        """从 AimerWT 内部映射读取导入时保存的元数据。"""
        self._ensure_meta_link_cache_loaded()
        record = self._meta_link_records.get(self._meta_link_key(sight_dir.name))
        if not isinstance(record, dict):
            return None
        meta = record.get("meta")
        if not isinstance(meta, dict):
            return None

        warnings = self._unique_text_list(record.get("warnings"))
        signatures = record.get("file_signatures")
        if isinstance(signatures, dict) and signatures:
            existing_count = 0
            signature_changed = False
            for rel_path, saved_signature in signatures.items():
                if not isinstance(rel_path, str) or not isinstance(saved_signature, dict):
                    continue
                target_file = sight_dir / rel_path
                if not target_file.is_file():
                    continue
                existing_count += 1
                current_signature = self._build_meta_link_file_signature(target_file)
                if (
                    current_signature.get("size") != saved_signature.get("size")
                    or current_signature.get("mtime_ns") != saved_signature.get("mtime_ns")
                ):
                    signature_changed = True
            if existing_count == 0:
                return None
            if signature_changed:
                warnings.append("meta_link_signature_changed")

        return {"meta": dict(meta), "warnings": warnings}

    def _ensure_meta_link_cache_loaded(self) -> None:
        """按当前 UserSights 根目录懒加载炮镜元数据映射。"""
        if not self._usersights_path:
            return
        try:
            root_key = str(self._usersights_path.resolve())
        except OSError:
            root_key = str(self._usersights_path)
        if self._meta_link_root == root_key:
            return
        self._meta_link_records = self._meta_link_cache.load_records(self._usersights_path)
        self._meta_link_root = root_key
        self._meta_link_dirty = False

    def _save_meta_link_cache(self) -> None:
        """保存导入流程生成的炮镜元数据映射。"""
        if not self._usersights_path or not self._meta_link_dirty:
            return
        self._meta_link_cache.save_records(self._usersights_path, self._meta_link_records)
        self._meta_link_dirty = False

    def _meta_link_key(self, sight_name: str) -> str:
        key = str(sight_name or "").strip()
        if key.endswith(self.disabled_suffix):
            key = key[:-len(self.disabled_suffix)]
        return key

    def _build_blk_features_page(
        self,
        sight_dir: Path,
        meta: dict[str, Any],
        cursor: int,
        limit: int,
        group_id: str | None = None,
        blk_entries: list[dict[str, Any]] | None = None,
        group_model: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构建真实 BLK 特征分页，只有当前页会进入内容解析。"""
        entries = blk_entries if blk_entries is not None else self._list_real_blk_feature_entries(sight_dir)
        if group_model is None:
            group_model = self._build_sight_group_model(sight_dir, meta, entries)
        active_group_id = str(group_id or "").strip()
        if active_group_id and active_group_id != "__all__":
            file_group_map = group_model.get("file_group_map") or {}
            entries = [
                entry for entry in entries
                if file_group_map.get(self._normalize_sight_group_file_key(str(entry["relative_path"]))) == active_group_id
            ]
        total = len(entries)
        safe_limit = max(1, min(int(limit or 50), 100))
        safe_cursor = max(0, min(int(cursor or 0), total))
        page_entries = entries[safe_cursor:safe_cursor + safe_limit]
        relative_files = [str(entry["relative_path"]) for entry in entries]
        matched_meta = self._meta_parser.match_files_to_meta(meta, relative_files, package_root=sight_dir)
        file_group_map = group_model.get("file_group_map") or {}
        group_name_map = group_model.get("group_name_map") or {}

        features = []
        for entry in page_entries:
            file_path = entry["path"]
            rel_path = str(entry["relative_path"])
            item = self._get_cached_blk_features(file_path)
            entry_meta = matched_meta.get(rel_path) or {}
            item["filename"] = str(entry["filename"])
            item["relative_path"] = rel_path
            item["disk_relative_path"] = str(entry["disk_relative_path"])
            item["file_status"] = str(entry["file_status"])
            item["disabled"] = bool(entry["disabled"])
            item["matched_ammo_type"] = entry_meta.get("ammo_type", "")
            item["display_name"] = entry_meta.get("display_name", "")
            item["recommended_vehicles"] = entry_meta.get("recommended_vehicles", [])
            item["target_resolution"] = entry_meta.get("target_resolution", "")
            item["note"] = entry_meta.get("note", "")
            item["meta_matched"] = bool(entry_meta)
            item["parse_status"] = "analyzed"
            entry_group_id = file_group_map.get(self._normalize_sight_group_file_key(rel_path), "__all__")
            item["group_id"] = entry_group_id
            item["group_name"] = group_name_map.get(entry_group_id, "")
            features.append(item)

        self._save_blk_feature_cache()
        next_cursor = safe_cursor + len(page_entries)
        return {
            "blk_feature_total": total,
            "blk_feature_limit": safe_limit,
            "blk_feature_cursor": str(next_cursor) if next_cursor < total else None,
            "blk_features": features,
        }

    def _build_sight_group_model(
        self,
        sight_dir: Path,
        meta: dict[str, Any],
        blk_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        relative_files = [str(entry["relative_path"]) for entry in blk_entries]
        matched_meta = self._meta_parser.match_files_to_meta(meta, relative_files, package_root=sight_dir)
        normalized_entries = [
            {
                "entry": entry,
                "key": self._normalize_sight_group_file_key(str(entry["relative_path"])),
                "meta": matched_meta.get(str(entry["relative_path"])) or {},
            }
            for entry in blk_entries
        ]
        author_groups = meta.get("groups") if isinstance(meta, dict) else None
        groups: list[dict[str, Any]] = []
        file_group_map: dict[str, str] = {}

        if isinstance(author_groups, list) and author_groups:
            for index, group in enumerate(author_groups):
                if not isinstance(group, dict):
                    continue
                group_id = str(group.get("group_id") or "").strip()
                name = str(group.get("name") or group_id).strip()
                if not group_id or not name:
                    continue
                groups.append({
                    "group_id": group_id,
                    "name": name,
                    "description": str(group.get("description") or ""),
                    "ammo_types": list(group.get("ammo_types") or []),
                    "recommended_vehicles": list(group.get("recommended_vehicles") or []),
                    "target_resolutions": list(group.get("target_resolutions") or []),
                    "platforms": list(group.get("platforms") or []),
                    "tags": list(group.get("tags") or []),
                    "featured": bool(group.get("featured")),
                    "sort_order": self._safe_int(group.get("sort_order"), (index + 1) * 100),
                    "file_keys": [
                        self._normalize_sight_group_file_key(str(path))
                        for path in (group.get("files") or [])
                        if isinstance(path, str) and path.strip()
                    ],
                })
            groups.sort(key=lambda item: (item["sort_order"], item["name"].lower()))
            existing_keys = {item["key"] for item in normalized_entries}
            for group in groups:
                for key in group.get("file_keys") or []:
                    if key in existing_keys and key not in file_group_map:
                        file_group_map[key] = group["group_id"]
        else:
            groups = self._build_default_sight_groups(normalized_entries)
            if len(groups) == 1 and groups[0]["group_id"] == "__all__":
                file_group_map = {item["key"]: "__all__" for item in normalized_entries}
            else:
                for item in normalized_entries:
                    group_id = self._default_group_id_for_entry(item)
                    file_group_map[item["key"]] = group_id if any(group["group_id"] == group_id for group in groups) else "__ungrouped__"

        assigned_ids = set(file_group_map.values())
        if normalized_entries and any(item["key"] not in file_group_map for item in normalized_entries):
            groups.append({
                "group_id": "__ungrouped__",
                "name": "未分组",
                "description": "未被作者分组命中的炮镜文件。",
                "ammo_types": [],
                "recommended_vehicles": [],
                "target_resolutions": [],
                "platforms": [],
                "tags": [],
                "featured": False,
                "sort_order": 999999,
                "file_keys": [],
            })
            for item in normalized_entries:
                file_group_map.setdefault(item["key"], "__ungrouped__")
            assigned_ids.add("__ungrouped__")

        groups = [self._summarize_sight_group(group, normalized_entries, file_group_map) for group in groups]
        groups = [group for group in groups if group["file_count"] > 0 or group["group_id"] in assigned_ids]
        groups = [group for group in groups if group["group_id"] != "__all__"]
        groups.sort(key=lambda item: (item["sort_order"], item["name"].lower()))
        all_group = {
            "group_id": "__all__",
            "name": "全部炮镜",
            "description": "查看包内全部炮镜文件。",
            "ammo_types": [],
            "recommended_vehicles": [],
            "target_resolutions": [],
            "platforms": [],
            "tags": [],
            "featured": False,
            "sort_order": 0,
            "file_count": len(normalized_entries),
            "enabled_count": sum(1 for item in normalized_entries if not item["entry"].get("disabled")),
            "disabled_count": sum(1 for item in normalized_entries if item["entry"].get("disabled")),
            "needs_attention_count": 0,
        }
        groups.insert(0, all_group)
        selected_group_id = "__all__"
        group_name_map = {group["group_id"]: group["name"] for group in groups}
        return {
            "groups": groups,
            "file_group_map": file_group_map,
            "group_name_map": group_name_map,
            "selected_group_id": selected_group_id,
        }

    def _build_default_sight_groups(self, normalized_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not normalized_entries:
            return [{
                "group_id": "__all__",
                "name": "全部炮镜",
                "description": "",
                "ammo_types": [],
                "recommended_vehicles": [],
                "target_resolutions": [],
                "platforms": [],
                "tags": [],
                "featured": False,
                "sort_order": 0,
                "file_keys": [],
            }]
        ammo_ids = []
        for item in normalized_entries:
            ammo_id = str(item["meta"].get("ammo_type") or "").strip()
            if ammo_id and ammo_id not in ammo_ids:
                ammo_ids.append(ammo_id)
        if ammo_ids:
            groups = [
                {
                    "group_id": f"ammo_{ammo_id}",
                    "name": ammo_id.upper(),
                    "description": "",
                    "ammo_types": [ammo_id],
                    "recommended_vehicles": [],
                    "target_resolutions": [],
                    "platforms": [],
                    "tags": [],
                    "featured": False,
                    "sort_order": index * 100,
                    "file_keys": [],
                }
                for index, ammo_id in enumerate(ammo_ids, start=1)
            ]
            groups.append({
                "group_id": "__ungrouped__",
                "name": "未分组",
                "description": "未被作者分组命中的炮镜文件。",
                "ammo_types": [],
                "recommended_vehicles": [],
                "target_resolutions": [],
                "platforms": [],
                "tags": [],
                "featured": False,
                "sort_order": 999999,
                "file_keys": [],
            })
            return groups
        directory_names = []
        for item in normalized_entries:
            rel_path = str(item["entry"]["relative_path"])
            parts = PurePosixPath(rel_path).parts
            if len(parts) > 1 and parts[0] not in directory_names:
                directory_names.append(parts[0])
        if directory_names:
            return [
                {
                    "group_id": f"dir_{self._normalize_sight_group_id(name, index)}",
                    "name": name,
                    "description": "",
                    "ammo_types": [],
                    "recommended_vehicles": [],
                    "target_resolutions": [],
                    "platforms": [],
                    "tags": [],
                    "featured": False,
                    "sort_order": index * 100,
                    "file_keys": [],
                }
                for index, name in enumerate(directory_names, start=1)
            ]
        return [{
            "group_id": "__all__",
            "name": "全部炮镜",
            "description": "",
            "ammo_types": [],
            "recommended_vehicles": [],
            "target_resolutions": [],
            "platforms": [],
            "tags": [],
            "featured": False,
            "sort_order": 0,
            "file_keys": [],
        }]

    def _default_group_id_for_entry(self, item: dict[str, Any]) -> str:
        ammo_id = str(item["meta"].get("ammo_type") or "").strip()
        if ammo_id:
            return f"ammo_{ammo_id}"
        rel_path = str(item["entry"]["relative_path"])
        parts = PurePosixPath(rel_path).parts
        if len(parts) > 1:
            return f"dir_{self._normalize_sight_group_id(parts[0], 1)}"
        return "__ungrouped__"

    def _summarize_sight_group(
        self,
        group: dict[str, Any],
        normalized_entries: list[dict[str, Any]],
        file_group_map: dict[str, str],
    ) -> dict[str, Any]:
        group_id = str(group["group_id"])
        entries = [item for item in normalized_entries if file_group_map.get(item["key"]) == group_id]
        enabled_count = sum(1 for item in entries if not item["entry"].get("disabled"))
        disabled_count = sum(1 for item in entries if item["entry"].get("disabled"))
        summary = {key: value for key, value in group.items() if key != "file_keys"}
        summary.update({
            "file_count": len(entries),
            "enabled_count": enabled_count,
            "disabled_count": disabled_count,
            "needs_attention_count": 0,
        })
        return summary

    def _get_cached_blk_features(self, file_path: Path) -> dict[str, Any]:
        """按文件签名缓存 BLK 自动特征，避免详情分页反复解析同一文件。"""
        try:
            stat = file_path.stat()
            signature = {
                "path": str(file_path.resolve()),
                "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
                "size": stat.st_size,
            }
        except OSError:
            return dict(self._blk_analyzer.analyze(file_path))

        self._ensure_blk_feature_cache_loaded()
        cache_key = signature["path"]
        cached = self._blk_feature_cache.get(cache_key)
        if cached and cached.get("signature") == signature:
            return dict(cached.get("features") or {})

        features = dict(self._blk_analyzer.analyze(file_path))
        self._blk_feature_cache[cache_key] = {
            "signature": signature,
            "features": dict(features),
        }
        self._blk_feature_cache_dirty = True
        return features

    def _ensure_blk_feature_cache_loaded(self) -> None:
        """按当前 UserSights 根目录懒加载 BLK 特征缓存。"""
        if not self._usersights_path:
            return
        try:
            root_key = str(self._usersights_path.resolve())
        except OSError:
            root_key = str(self._usersights_path)
        if self._blk_feature_cache_root == root_key:
            return
        self._blk_feature_cache = self._feature_cache.load_records(self._usersights_path)
        self._blk_feature_cache_root = root_key
        self._blk_feature_cache_dirty = False

    def _save_blk_feature_cache(self) -> None:
        """将当前 UserSights 的 BLK 特征缓存写入独立索引文件。"""
        if not self._usersights_path or not self._blk_feature_cache_dirty:
            return
        self._feature_cache.save_records(self._usersights_path, self._blk_feature_cache)
        self._blk_feature_cache_dirty = False

    @staticmethod
    def _safe_int(value: Any, fallback: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _normalize_sight_group_file_key(rel_path: str) -> str:
        return str(rel_path or "").replace("\\", "/").strip().lstrip("./").lower()

    @staticmethod
    def _normalize_sight_group_id(value: str, fallback_index: int) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", str(value or "").strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
        return cleaned[:48] or f"group_{fallback_index}"

    def _list_real_blk_files(self, sight_dir: Path) -> list[Path]:
        """列出真实 BLK，排除 AimerWT 伪 BLK 元数据文件。"""
        return [entry["path"] for entry in self._list_real_blk_feature_entries(sight_dir)]

    def _list_resource_blk_feature_entries(
        self,
        resource: dict[str, Any],
        resource_dir: Path,
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """按资源索引的公开路径列出真实 BLK，避免资源库存储前缀影响元数据匹配。"""
        meta_paths_by_file_id: dict[str, str] = {}
        for file_meta in meta.get("files") or []:
            if not isinstance(file_meta, dict):
                continue
            file_id = str(file_meta.get("file_id") or "").strip()
            if not file_id:
                continue
            try:
                meta_paths_by_file_id[file_id] = self._normalize_external_sight_relative_path(
                    str(file_meta.get("path") or "")
                )
            except ValueError:
                continue

        entries_by_rel: dict[str, dict[str, Any]] = {}
        for file_entry in resource.get("files") or []:
            if not isinstance(file_entry, dict):
                continue
            try:
                storage_relative_path = self._normalize_external_sight_relative_path(
                    str(file_entry.get("source_relative_path") or "")
                )
            except ValueError:
                continue
            file_path = resource_dir.joinpath(*PurePosixPath(storage_relative_path).parts)
            if not file_path.is_file() or not self._is_path_within(file_path, resource_dir):
                continue
            if self._meta_parser.is_standalone_meta_file(file_path):
                continue

            sight_file_id = str(file_entry.get("sight_file_id") or "").strip()
            storage_public_path = (
                storage_relative_path[6:]
                if storage_relative_path.startswith("files/")
                else storage_relative_path
            )
            public_candidates = [
                meta_paths_by_file_id.get(sight_file_id, ""),
                str(file_entry.get("original_source_relative_path") or ""),
                str(file_entry.get("target_relative_path") or ""),
                storage_public_path,
            ]
            public_relative_path = ""
            for candidate in public_candidates:
                try:
                    public_relative_path = self._normalize_external_sight_relative_path(candidate)
                    break
                except ValueError:
                    continue
            if not public_relative_path:
                continue

            entries_by_rel[public_relative_path.lower()] = {
                "path": file_path,
                "relative_path": public_relative_path,
                "disk_relative_path": storage_relative_path,
                "filename": PurePosixPath(public_relative_path).name,
                "file_status": "enabled",
                "disabled": False,
            }

        if entries_by_rel:
            return sorted(
                entries_by_rel.values(),
                key=lambda entry: str(entry["relative_path"]).lower(),
            )
        return self._list_real_blk_feature_entries(resource_dir)

    def _list_real_blk_feature_entries(self, sight_dir: Path) -> list[dict[str, Any]]:
        """列出详情页可展示的真实 BLK，包含快速停用的 .AimerWT_BAN 文件。"""
        try:
            candidates = [path for path in sight_dir.rglob("*.blk") if path.is_file()]
            disabled_candidates = [path for path in sight_dir.rglob(f"*.blk{self.disabled_suffix}") if path.is_file()]
        except OSError:
            return []
        entries_by_rel: dict[str, dict[str, Any]] = {}
        for path in candidates + disabled_candidates:
            disk_rel = self._relative_sight_path(path, sight_dir)
            disabled = disk_rel.endswith(self.disabled_suffix)
            rel_path = disk_rel[:-len(self.disabled_suffix)] if disabled else disk_rel
            filename = PurePosixPath(rel_path).name
            if disabled:
                if self._meta_parser.detect_meta_marker(path):
                    continue
            elif self._meta_parser.is_standalone_meta_file(path):
                continue
            key = rel_path.lower()
            entry = {
                "path": path,
                "relative_path": rel_path,
                "disk_relative_path": disk_rel,
                "filename": filename,
                "file_status": "disabled_by_rename" if disabled else "enabled",
                "disabled": disabled,
            }
            current = entries_by_rel.get(key)
            if current and not current.get("disabled"):
                continue
            entries_by_rel[key] = entry
        return sorted(entries_by_rel.values(), key=lambda entry: str(entry["relative_path"]).lower())

    @staticmethod
    def _parse_feature_cursor(cursor: str | int | None) -> int:
        try:
            return max(0, int(cursor or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _relative_sight_path(path: Path, sight_dir: Path) -> str:
        try:
            return str(path.relative_to(sight_dir)).replace("\\", "/")
        except ValueError:
            return path.name

    def rename_sight(self, old_name: str, new_name: str) -> bool:
        """
        在 UserSights 目录内安全重命名炮镜文件夹。

        Args:
            old_name: 原文件夹名称
            new_name: 新文件夹名称

        Returns:
            是否重命名成功

        Raises:
            ValueError: 路径未设置或名称不合法
            FileNotFoundError: 源文件夹不存在
            FileExistsError: 目标名称已存在
            OSError: 重命名操作失败
        """
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        if str(old_name or "").startswith((self.resource_ref_prefix, self.file_ref_prefix)):
            raise ValueError("资源卡片不能重命名物理文件夹，请修改资源来源名称")

        old_dir = self._resolve_sight_dir(old_name)
        enabled_name = self._normalize_batch_sight_name(old_dir.name)
        install_summary = self._get_install_summary(enabled_name)
        if install_summary.get("managed_by_aimerwt") or install_summary.get("resource_ids"):
            raise ValueError("AimerWT 管理的炮镜不能重命名物理文件夹，请修改显示名称")

        if not new_name or len(new_name) > 255:
            raise ValueError("名称长度不合法")

        if re.search(r'[<>:"/\\|?*]', new_name):
            raise ValueError('名称包含非法字符 (不能包含 < > : " / \\ | ? *)')
        if self._is_unsafe_windows_path_part(new_name) or Path(new_name).name != new_name:
            raise ValueError("名称不合法")

        new_dir = usersights_dir / new_name

        if new_dir.exists():
            raise FileExistsError(f"目标名称已存在: {new_name}")

        try:
            old_dir.rename(new_dir)
            self._cache = None
            self._cache_signature = None
            self._index_cache.clear()
            log.info(f"已重命名炮镜: {old_dir.name} -> {new_name}")
            return True
        except PermissionError as e:
            raise OSError(f"重命名失败（权限不足）: {e}")
        except OSError as e:
            raise OSError(f"重命名失败: {e}")

    def disable_sight(self, name: str) -> dict[str, Any]:
        enabled_name = self._normalize_batch_sight_name(name)
        result, did_change = self._disable_sight_by_enabled_name(enabled_name)
        if did_change:
            self._clear_sights_cache()
        return result

    def enable_sight(self, name: str) -> dict[str, Any]:
        enabled_name = self._normalize_batch_sight_name(name)
        result, did_change = self._enable_sight_by_enabled_name(enabled_name)
        if did_change:
            self._clear_sights_cache()
        return result

    def _normalize_sight_file_targets(self, sight_name: str, relative_paths: Any) -> tuple[Path, str, list[str]]:
        """把详情页包内相对 BLK 路径转换为 UserSights 内规范目标路径。"""
        usersights_dir = self._require_usersights_path()
        enabled_name = self._normalize_batch_sight_name(sight_name)
        if isinstance(relative_paths, (str, os.PathLike)):
            raw_paths = [relative_paths]
        else:
            raw_paths = list(relative_paths or [])
        if not raw_paths:
            raise ValueError("必须提供炮镜文件路径")

        target_paths: list[str] = []
        seen: set[str] = set()
        for raw_path in raw_paths:
            normalized = str(raw_path or "").replace("\\", "/").strip("/")
            if normalized.endswith(self.disabled_suffix):
                normalized = normalized[:-len(self.disabled_suffix)]
            posix_path = PurePosixPath(normalized)
            parts = posix_path.parts
            if (
                not normalized
                or not parts
                or posix_path.is_absolute()
                or any(part in {"", ".", ".."} for part in parts)
                or any(":" in part for part in parts)
                or any(self._is_unsafe_windows_path_part(part) for part in parts)
            ):
                raise ValueError(f"炮镜文件路径不合法: {raw_path}")
            if parts[0] == enabled_name:
                target_rel = str(PurePosixPath(*parts))
            else:
                target_rel = str(PurePosixPath(enabled_name, *parts))
            if target_rel not in seen:
                seen.add(target_rel)
                target_paths.append(target_rel)
        return usersights_dir, enabled_name, target_paths

    def _resolve_sight_file_resource_targets(
        self,
        usersights_dir: Path,
        enabled_name: str,
        target_paths: list[str],
    ) -> tuple[dict[str, list[str]], list[str], list[str]]:
        """按安装清单把目标文件归到对应资源 ID。"""
        summary = self._sights_repo.summarize_target_group(usersights_dir, enabled_name)
        resource_ids = [str(resource_id) for resource_id in summary.get("resource_ids") or [] if str(resource_id)]
        if not resource_ids:
            raise FileNotFoundError(f"没有找到 AimerWT 安装记录: {enabled_name}")

        target_set = set(target_paths)
        matched_targets: set[str] = set()
        resource_targets: dict[str, list[str]] = {}
        manifest = self._sights_repo.load_manifest(usersights_dir)
        resources = manifest.get("resources", {})
        for resource_id in resource_ids:
            resource_record = resources.get(resource_id)
            if not isinstance(resource_record, dict):
                continue
            for entry in resource_record.get("files") or []:
                if not isinstance(entry, dict):
                    continue
                target_rel = str(entry.get("target_relative_path") or "")
                if target_rel in target_set:
                    resource_targets.setdefault(resource_id, []).append(target_rel)
                    matched_targets.add(target_rel)

        missing_targets = sorted(target_set - matched_targets)
        if not resource_targets and missing_targets:
            raise FileNotFoundError(f"没有找到可操作的炮镜文件记录: {', '.join(missing_targets)}")
        return resource_targets, missing_targets, resource_ids

    def _resolve_resource_file_targets(self, resource_id: str, relative_paths: Any) -> list[str]:
        if isinstance(relative_paths, (str, os.PathLike)):
            raw_paths = [relative_paths]
        else:
            raw_paths = list(relative_paths or [])
        if not raw_paths:
            raise ValueError("必须提供炮镜文件路径")

        selected_keys: set[str] = set()
        for raw_path in raw_paths:
            normalized = str(raw_path or "").replace("\\", "/").strip("/")
            if normalized.endswith(self.disabled_suffix):
                normalized = normalized[:-len(self.disabled_suffix)]
            posix_path = PurePosixPath(normalized)
            if (
                not normalized
                or posix_path.is_absolute()
                or any(part in {"", ".", ".."} or ":" in part for part in posix_path.parts)
            ):
                raise ValueError(f"炮镜文件路径不合法: {raw_path}")
            selected_keys.add(normalized.lower())

        resource, _resource_dir = self._sights_repo.load_resource(resource_id)
        manifest = self._sights_repo.load_manifest(self._require_usersights_path())
        resource_record = (manifest.get("resources") or {}).get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"没有找到 AimerWT 安装记录: {resource_id}")
        manifest_files = [entry for entry in resource_record.get("files") or [] if isinstance(entry, dict)]
        selected_targets: set[str] = set()
        for resource_entry in resource.get("files") or []:
            if not isinstance(resource_entry, dict):
                continue
            storage_path = str(resource_entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
            public_path = str(resource_entry.get("original_source_relative_path") or "").replace("\\", "/").strip("/")
            if not public_path:
                public_path = storage_path[6:] if storage_path.startswith("files/") else storage_path
            aliases = {
                storage_path.lower(),
                public_path.lower(),
                PurePosixPath(storage_path).name.lower(),
                PurePosixPath(public_path).name.lower(),
            }
            if not aliases.intersection(selected_keys):
                continue
            for manifest_entry in manifest_files:
                manifest_source = str(manifest_entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
                if manifest_source.lower() not in aliases and PurePosixPath(manifest_source).name.lower() not in aliases:
                    continue
                target_path = str(manifest_entry.get("target_relative_path") or "").replace("\\", "/").strip("/")
                if target_path:
                    selected_targets.add(target_path)
        if not selected_targets:
            raise FileNotFoundError("没有找到可操作的炮镜文件记录")
        return sorted(selected_targets)

    def _run_reference_sight_file_operation(
        self,
        sight_name: str,
        relative_paths: Any,
        enabled: bool,
    ) -> dict[str, Any] | None:
        reference = str(sight_name or "").strip()
        if reference.startswith(self.resource_ref_prefix):
            resource_id = self._parse_resource_reference(reference)
            target_paths = self._resolve_resource_file_targets(resource_id, relative_paths)
            operation = self._sights_repo.enable_resource_files if enabled else self._sights_repo.disable_resource_files
            result = operation(resource_id, self._require_usersights_path(), target_paths)
            self._clear_sights_cache()
            return {
                **result,
                "name": reference,
                "resource_ids": [resource_id],
                "target_relative_paths": target_paths,
                "selected_count": len(target_paths),
            }
        if reference.startswith(self.file_ref_prefix):
            normalized_reference, file_path, disabled = self._resolve_external_sight_file(reference)
            requested = [relative_paths] if isinstance(relative_paths, (str, os.PathLike)) else list(relative_paths or [])
            expected_name = file_path.name[:-len(self.disabled_suffix)] if disabled else file_path.name
            if not requested or not any(PurePosixPath(str(path or "").replace("\\", "/")).name == expected_name for path in requested):
                raise ValueError("所选炮镜文件与卡片不匹配")
            result = self.enable_sight(normalized_reference) if enabled else self.disable_sight(normalized_reference)
            return {
                **result,
                "target_relative_paths": [self._normalize_external_sight_relative_path(normalized_reference)],
                "selected_count": 1,
                "renamed_count": 0 if result.get("already") else 1,
                "resource_ids": [],
            }
        return None

    def _run_sight_file_operation(
        self,
        sight_name: str,
        relative_paths: Any,
        enabled: bool,
    ) -> dict[str, Any]:
        reference_result = self._run_reference_sight_file_operation(sight_name, relative_paths, enabled)
        if reference_result is not None:
            return reference_result
        usersights_dir, enabled_name, target_paths = self._normalize_sight_file_targets(sight_name, relative_paths)
        resource_targets, missing_targets, resource_ids = self._resolve_sight_file_resource_targets(
            usersights_dir,
            enabled_name,
            target_paths,
        )
        operation = self._sights_repo.enable_resource_files if enabled else self._sights_repo.disable_resource_files
        count_keys = (
            "installed_count",
            "copied_count",
            "reused_count",
            "restored_count",
            "renamed_count",
            "already_disabled_count",
            "missing_count",
            "modified_count",
            "conflict_count",
            "kept_shared_count",
        )
        aggregate = {key: 0 for key in count_keys}
        results: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        success = not missing_targets
        for resource_id, selected_targets in resource_targets.items():
            result = operation(resource_id, usersights_dir, selected_targets)
            results.append(result)
            success = success and bool(result.get("success"))
            for key in count_keys:
                try:
                    aggregate[key] += int(result.get(key) or 0)
                except (TypeError, ValueError):
                    continue
            conflicts.extend([item for item in result.get("conflicts") or [] if isinstance(item, dict)])
        for target_rel in missing_targets:
            aggregate["conflict_count"] += 1
            conflicts.append({"target_relative_path": target_rel, "reason": "target_not_in_manifest"})
        if results:
            self._clear_sights_cache()
        return {
            "success": success,
            "name": enabled_name,
            "resource_ids": resource_ids,
            "target_relative_paths": target_paths,
            "selected_count": len(target_paths),
            "results": results,
            "conflicts": conflicts,
            **aggregate,
        }

    def _run_sight_repository_resource_action(
        self,
        resource_id: str,
        action_name: str,
        reference: str | None = None,
    ) -> dict[str, Any]:
        usersights_dir = self._require_usersights_path()
        if action_name == "disable_resource":
            result = self._sights_repo.disable_resource_batched(resource_id, usersights_dir)
            disabled = True
        elif action_name == "enable_resource":
            result = self._sights_repo.enable_resource_batched(resource_id, usersights_dir)
            disabled = False
        elif action_name == "uninstall_resource":
            result = self._sights_repo.uninstall_resource_batched(resource_id, usersights_dir)
            disabled = False
        else:
            raise ValueError(f"炮镜资源库操作不支持: {action_name}")
        self._clear_sights_cache()
        return {
            **result,
            "name": reference or f"{self.resource_ref_prefix}{resource_id}",
            "disabled": disabled,
            "resource_ids": [resource_id],
            "managed_by_aimerwt": True,
            "repository_action": action_name,
        }

    def _run_sight_repository_group_action(self, enabled_name: str, action_name: str) -> dict[str, Any] | None:
        if str(enabled_name or "").startswith(self.resource_ref_prefix):
            resource_id = self._parse_resource_reference(enabled_name)
            return self._run_sight_repository_resource_action(resource_id, action_name, enabled_name)
        usersights_dir = self._require_usersights_path()
        summary = self._sights_repo.summarize_target_group(usersights_dir, enabled_name)
        resource_ids = [str(resource_id) for resource_id in summary.get("resource_ids") or [] if str(resource_id)]
        if not resource_ids:
            return None
        if len(resource_ids) > 1:
            return self._ambiguous_target_group_result(enabled_name, resource_ids)

        resource_id = resource_ids[0]
        if action_name == "disable_resource":
            result = self._sights_repo.disable_resource_batched(resource_id, usersights_dir)
            disabled = True
        elif action_name == "enable_resource":
            result = self._sights_repo.enable_resource_batched(resource_id, usersights_dir)
            disabled = False
        elif action_name == "uninstall_resource":
            result = self._sights_repo.uninstall_resource_batched(resource_id, usersights_dir)
            disabled = False
        else:
            raise ValueError(f"炮镜资源库操作不支持: {action_name}")

        self._clear_sights_cache()
        return {
            **result,
            "name": enabled_name,
            "disabled": disabled,
            "resource_ids": [resource_id],
            "managed_by_aimerwt": True,
            "repository_action": action_name,
        }

    def enable_sight_files(self, sight_name: str, relative_paths: Any) -> dict[str, Any]:
        """按文件粒度启用详情页中的 BLK 文件。"""
        return self._run_sight_file_operation(sight_name, relative_paths, enabled=True)

    def disable_sight_files(self, sight_name: str, relative_paths: Any) -> dict[str, Any]:
        """按文件粒度停用详情页中的 BLK 文件。"""
        return self._run_sight_file_operation(sight_name, relative_paths, enabled=False)

    def accept_sight_current_state(self, name: str) -> dict[str, Any]:
        """以当前 UserSights 文件 fingerprint 更新对应安装记录，不移动磁盘文件。"""
        if not self._usersights_path or not self._usersights_path.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        enabled_name = self._normalize_batch_sight_name(name)
        if enabled_name.startswith(self.resource_ref_prefix):
            resource_ids = [self._parse_resource_reference(enabled_name)]
        else:
            summary = self._sights_repo.summarize_target_group(self._usersights_path, enabled_name)
            resource_ids = list(summary.get("resource_ids") or [])
        if not resource_ids:
            raise FileNotFoundError(f"没有找到 AimerWT 安装记录: {enabled_name}")
        if len(resource_ids) > 1:
            return self._ambiguous_target_group_result(enabled_name, resource_ids)
        accepted_count = 0
        missing_count = 0
        results = []
        for resource_id in resource_ids:
            result = self._sights_repo.accept_current_state(resource_id, self._usersights_path)
            accepted_count += int(result.get("accepted_count") or 0)
            missing_count += int(result.get("missing_count") or 0)
            results.append(result)
        self._clear_sights_cache()
        return {
            "success": True,
            "name": enabled_name,
            "resource_ids": resource_ids,
            "accepted_count": accepted_count,
            "missing_count": missing_count,
            "results": results,
        }

    def clear_sight_install_records(self, name: str) -> dict[str, Any]:
        """仅移除 AimerWT 安装记录，保留 UserSights 中的实际文件。"""
        if not self._usersights_path or not self._usersights_path.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        enabled_name = self._normalize_batch_sight_name(name)
        if enabled_name.startswith(self.resource_ref_prefix):
            resource_ids = [self._parse_resource_reference(enabled_name)]
        else:
            summary = self._sights_repo.summarize_target_group(self._usersights_path, enabled_name)
            resource_ids = list(summary.get("resource_ids") or [])
        if not resource_ids:
            raise FileNotFoundError(f"没有找到 AimerWT 安装记录: {enabled_name}")
        if len(resource_ids) > 1:
            return self._ambiguous_target_group_result(enabled_name, resource_ids)
        cleared_count = 0
        results = []
        for resource_id in resource_ids:
            result = self._sights_repo.clear_resource_record(resource_id, self._usersights_path)
            cleared_count += int(result.get("cleared_count") or 0)
            results.append(result)
        self._clear_sights_cache()
        return {
            "success": True,
            "name": enabled_name,
            "resource_ids": resource_ids,
            "cleared_count": cleared_count,
            "results": results,
        }

    def batch_disable_sights(self, names: list[str]) -> dict[str, Any]:
        """按 enabled_name 批量禁用炮镜，单项失败不影响整批。"""
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        changed = False
        for raw_name in names or []:
            enabled_name = self._normalize_batch_sight_name(raw_name)
            try:
                result, did_change = self._disable_sight_by_enabled_name(enabled_name)
                if result.get("success", False):
                    results.append(result)
                else:
                    failures.append({
                        "name": str(raw_name),
                        "error": str(result.get("msg") or result.get("error_code") or "禁用失败"),
                        "error_code": str(result.get("error_code") or ""),
                    })
                changed = changed or did_change
            except Exception as e:
                failures.append({"name": str(raw_name), "error": str(e)})
        if changed:
            self._clear_sights_cache()
        return {
            "success_count": len(results),
            "fail_count": len(failures),
            "results": results,
            "failures": failures,
        }

    def batch_enable_sights(self, names: list[str]) -> dict[str, Any]:
        """按 enabled_name 批量启用炮镜，单项失败不影响整批。"""
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        changed = False
        for raw_name in names or []:
            enabled_name = self._normalize_batch_sight_name(raw_name)
            try:
                result, did_change = self._enable_sight_by_enabled_name(enabled_name)
                if result.get("success", False):
                    results.append(result)
                else:
                    failures.append({
                        "name": str(raw_name),
                        "error": str(result.get("msg") or result.get("error_code") or "启用失败"),
                        "error_code": str(result.get("error_code") or ""),
                    })
                changed = changed or did_change
            except Exception as e:
                failures.append({"name": str(raw_name), "error": str(e)})
        if changed:
            self._clear_sights_cache()
        return {
            "success_count": len(results),
            "fail_count": len(failures),
            "results": results,
            "failures": failures,
        }

    def _normalize_batch_sight_name(self, name: str) -> str:
        enabled_name = str(name or "").strip()
        if enabled_name.startswith(self.resource_ref_prefix):
            resource_id = self._parse_resource_reference(enabled_name)
            return f"{self.resource_ref_prefix}{resource_id}"
        if enabled_name.startswith(self.file_ref_prefix):
            normalized_reference, _file_path, _disabled = self._resolve_external_sight_file(enabled_name)
            return normalized_reference
        if enabled_name.endswith(self.disabled_suffix):
            enabled_name = enabled_name[:-len(self.disabled_suffix)]
        if not enabled_name or Path(enabled_name).name != enabled_name:
            raise ValueError("炮镜文件夹名称不合法")
        return enabled_name

    def _disable_sight_by_enabled_name(self, enabled_name: str) -> tuple[dict[str, Any], bool]:
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        if enabled_name.startswith(self.file_ref_prefix):
            normalized_reference, enabled_file, disabled = self._resolve_external_sight_file(enabled_name)
            if disabled:
                return {
                    "success": True,
                    "name": normalized_reference,
                    "disabled": True,
                    "already": True,
                }, False
            disabled_file = Path(f"{enabled_file}{self.disabled_suffix}")
            if disabled_file.exists():
                raise FileExistsError(f"已存在禁用状态炮镜文件: {disabled_file.name}")
            enabled_file.rename(disabled_file)
            return {
                "success": True,
                "name": normalized_reference,
                "disabled": True,
            }, True
        repository_result = self._run_sight_repository_group_action(enabled_name, "disable_resource")
        if repository_result is not None:
            return repository_result, True
        enabled_dir = usersights_dir / enabled_name
        disabled_dir = usersights_dir / f"{enabled_name}{self.disabled_suffix}"
        if disabled_dir.exists() and not enabled_dir.exists():
            return {"success": True, "name": disabled_dir.name, "disabled": True, "already": True}, False
        if not enabled_dir.exists() or not enabled_dir.is_dir():
            raise FileNotFoundError(f"炮镜文件夹不存在: {enabled_name}")
        if disabled_dir.exists():
            raise FileExistsError(f"已存在禁用状态文件夹: {disabled_dir.name}")
        enabled_dir.rename(disabled_dir)
        return {"success": True, "name": disabled_dir.name, "disabled": True}, True

    def _enable_sight_by_enabled_name(self, enabled_name: str) -> tuple[dict[str, Any], bool]:
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        if enabled_name.startswith(self.file_ref_prefix):
            normalized_reference, disabled_file, disabled = self._resolve_external_sight_file(enabled_name)
            if not disabled:
                return {
                    "success": True,
                    "name": normalized_reference,
                    "disabled": False,
                    "already": True,
                }, False
            enabled_file = Path(str(disabled_file)[:-len(self.disabled_suffix)])
            if enabled_file.exists():
                raise FileExistsError(f"已存在启用状态炮镜文件: {enabled_file.name}")
            disabled_file.rename(enabled_file)
            return {
                "success": True,
                "name": normalized_reference,
                "disabled": False,
            }, True
        repository_result = self._run_sight_repository_group_action(enabled_name, "enable_resource")
        if repository_result is not None:
            return repository_result, True
        enabled_dir = usersights_dir / enabled_name
        disabled_dir = usersights_dir / f"{enabled_name}{self.disabled_suffix}"
        if enabled_dir.exists() and not disabled_dir.exists():
            return {"success": True, "name": enabled_dir.name, "disabled": False, "already": True}, False
        if not disabled_dir.exists() or not disabled_dir.is_dir():
            raise FileNotFoundError(f"炮镜文件夹不存在: {enabled_name}")
        if enabled_dir.exists():
            raise FileExistsError(f"已存在启用状态文件夹: {enabled_dir.name}")
        disabled_dir.rename(enabled_dir)
        return {"success": True, "name": enabled_dir.name, "disabled": False}, True

    def delete_sight(self, name: str) -> dict[str, Any]:
        enabled_name = self._normalize_batch_sight_name(name)
        if enabled_name.startswith(self.file_ref_prefix):
            normalized_reference, file_path, _disabled = self._resolve_external_sight_file(enabled_name)
            try:
                file_path.unlink()
            except (PermissionError, OSError) as exc:
                raise SightsManagerError(f"删除炮镜文件失败: {exc}") from exc
            finally:
                self._clear_sights_cache()
            return {"success": True, "name": normalized_reference}
        repository_result = self._run_sight_repository_group_action(enabled_name, "uninstall_resource")
        if repository_result is not None:
            return repository_result
        sight_dir = self._resolve_sight_detail_dir(name)
        try:
            shutil.rmtree(sight_dir)
        except (PermissionError, OSError) as e:
            log.error(f"删除炮镜失败 {sight_dir}: {e}")
            raise SightsManagerError(f"删除炮镜失败: {e}") from e
        finally:
            self._clear_sights_cache()
        return {"success": True, "name": sight_dir.name}

    def open_sight_folder(self, name: str) -> bool:
        reference = str(name or "").strip()
        if reference.startswith(self.resource_ref_prefix):
            _resource, sight_dir = self._sights_repo.load_resource(self._parse_resource_reference(reference))
        elif reference.startswith(self.file_ref_prefix):
            _normalized_reference, file_path, _disabled = self._resolve_external_sight_file(reference)
            sight_dir = file_path.parent
        else:
            sight_dir = self._resolve_sight_detail_dir(name)
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(str(sight_dir))
            elif system == "Darwin":
                subprocess.run(["open", str(sight_dir)], check=True)
            else:
                subprocess.run(["xdg-open", str(sight_dir)], check=True)
            return True
        except FileNotFoundError as e:
            log.error(f"打开炮镜文件夹失败（找不到启动器）: {e}")
            return False
        except subprocess.CalledProcessError as e:
            log.error(f"打开炮镜文件夹失败: {e}")
            return False
        except OSError as e:
            log.error(f"打开炮镜文件夹失败: {e}")
            return False

    def update_sight_cover_data(self, sight_name: str, data_url: str) -> bool:
        """
        将前端传入的 base64 图片数据写入资源库封面，旧外部炮镜保留 UserSights 写入兼容。
        
        Args:
            sight_name: 炮镜文件夹名称
            data_url: base64 编码的图片数据 URL
            
        Returns:
            是否更新成功
            
        Raises:
            ValueError: 路径未设置或数据格式错误
            FileNotFoundError: 炮镜文件夹不存在
            SightsManagerError: 封面更新失败
        """
        sight_dir = self._resolve_sight_detail_dir(sight_name)
        enabled_name = self._normalize_batch_sight_name(sight_dir.name)

        data_url = str(data_url or "")
        if ";base64," not in data_url:
            raise ValueError("图片数据格式错误")

        _prefix, b64 = data_url.split(";base64,", 1)
        try:
            raw = base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise ValueError(f"图片数据解析失败: {e}")

        summary = self._get_install_summary(enabled_name)
        resource_ids = summary.get("resource_ids") if isinstance(summary, dict) else []
        if isinstance(resource_ids, list) and resource_ids:
            extension = self._cover_extension_from_data_url(data_url)
            try:
                cover_result = self._sights_repo.save_resource_cover(str(resource_ids[0]), raw, extension)
                self._cache = None
                self._cache_signature = None
                self._index_cache.clear()
                log.info(f"已更新炮镜资源库封面: {sight_name} -> {cover_result.get('path')}")
                return True
            except (FileNotFoundError, ValueError, OSError) as e:
                raise SightsManagerError(f"资源库封面更新失败: {e}")

        dst = sight_dir / "preview.png"
        try:
            with open(dst, "wb") as f:
                f.write(raw)
            self._cache = None
            self._cache_signature = None
            self._index_cache.clear()
            log.info(f"已更新炮镜封面: {sight_name}")
            return True
        except PermissionError as e:
            raise SightsManagerError(f"封面更新失败（权限不足）: {e}")
        except OSError as e:
            raise SightsManagerError(f"封面更新失败: {e}")

    @staticmethod
    def _cover_extension_from_data_url(data_url: str) -> str:
        prefix = str(data_url or "").split(";base64,", 1)[0].lower()
        if prefix.endswith("image/jpeg") or prefix.endswith("image/jpg"):
            return ".jpg"
        if prefix.endswith("image/webp"):
            return ".webp"
        if prefix.endswith("image/png"):
            return ".png"
        return ".png"

    def _find_preview_image(self, dir_path: Path) -> Path | None:
        """
        在炮镜目录中查找可用的预览图文件。
        
        Args:
            dir_path: 炮镜目录路径
            
        Returns:
            预览图路径或 None
        """
        candidates = []
        for pat in ("preview.*", "icon.*", "*.jpg", "*.jpeg", "*.png", "*.webp"):
            try:
                candidates.extend(dir_path.glob(pat))
            except OSError:
                continue

        for p in candidates:
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return p
        return None

    def _to_data_url(self, file_path: Path) -> str:
        """
        将图片文件读取并编码为 data URL，供前端直接展示。
        
        Args:
            file_path: 图片文件路径
            
        Returns:
            data URL 字符串，失败时返回空字符串
        """
        ext = file_path.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        try:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return f"data:image/{ext};base64,{b64}"
        except (OSError, PermissionError) as e:
            log.warning(f"读取图片失败 {file_path}: {e}")
            return ""
    
    def open_usersights_folder(self) -> bool:
        """
        打开当前设置的 UserSights 目录。
        
        Returns:
            是否成功打开
            
        Raises:
            ValueError: 路径未设置或不存在
        """
        if not self._usersights_path or not self._usersights_path.exists():
            raise ValueError("UserSights 路径未设置或不存在")
        
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(str(self._usersights_path))
            elif system == "Darwin":
                subprocess.run(["open", str(self._usersights_path)], check=True)
            else:
                subprocess.run(["xdg-open", str(self._usersights_path)], check=True)
            return True
        except FileNotFoundError as e:
            log.error(f"打开文件夹失败（找不到启动器）: {e}")
            return False
        except subprocess.CalledProcessError as e:
            log.error(f"打开文件夹失败: {e}")
            return False
        except OSError as e:
            log.error(f"打开文件夹失败: {e}")
            return False

    def _find_7z(self) -> str | None:
        return find_7z_executable()

    def _run_7z(self, args: list[str]) -> tuple[int, str]:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=300,
            )
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode("utf-8", "ignore") if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = e.stderr.decode("utf-8", "ignore") if isinstance(e.stderr, bytes) else (e.stderr or "")
            output = stdout + "\n" + stderr
            raise SightsImportError(output.strip() or "7z 解压超时") from e
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        return result.returncode, output.strip()

    def _is_archive_member_path_safe(self, filename: str) -> bool:
        return is_archive_member_path_safe(filename)

    def _validate_7z_archive_entries(self, seven_zip: str, archive_path: Path, blocked_ext: set[str]) -> None:
        code, output = self._run_7z([seven_zip, "l", "-slt", "-p", str(archive_path)])
        if code != 0:
            raise SightsImportError(output or "无法读取压缩包目录")

        in_entries = False
        unsafe_files: list[str] = []
        blocked_files: list[str] = []
        for line in output.splitlines():
            if line.startswith("----------"):
                in_entries = True
                continue
            if not in_entries or not line.startswith("Path = "):
                continue

            filename = line[7:].strip()
            if not filename or filename.endswith(("/", "\\")):
                continue
            if "__MACOSX" in filename or "desktop.ini" in filename.lower():
                continue
            if not self._is_archive_member_path_safe(filename):
                unsafe_files.append(filename)
                continue

            ext = Path(filename).suffix.lower()
            if ext in blocked_ext:
                blocked_files.append(filename)

        if unsafe_files:
            file_list = "\n".join(f"  - {f}" for f in unsafe_files[:10])
            raise SightsImportError(f"压缩包路径不安全，已拒绝导入:\n{file_list}")
        if blocked_files:
            file_list = "\n".join(f"  - {f}" for f in blocked_files[:10])
            raise SightsImportError(f"检测到不允许的文件类型:\n{file_list}")

    def _extract_with_7z(
        self,
        archive_path: Path,
        target_dir: Path,
        blocked_ext: set[str],
        progress_callback: Callable[[int, str], None] | None = None,
        base_progress: int = 0,
        share_progress: int = 100,
    ) -> None:
        seven_zip = self._find_7z()
        if not seven_zip:
            raise SightsImportError("未检测到 7z 解压组件，RAR/7Z 导入需要安装 7-Zip")

        self._validate_7z_archive_entries(seven_zip, archive_path, blocked_ext)
        if progress_callback:
            progress_callback(base_progress, f"开始解压: {archive_path.name}")

        args = [
            seven_zip,
            "x",
            "-y",
            "-p",
            f"-o{str(target_dir)}",
            str(archive_path),
        ]
        code, output = self._run_7z(args)
        if code != 0:
            lower = output.lower()
            if "password" in lower or "encrypted" in lower or "wrong password" in lower:
                raise SightsImportError("压缩包需要密码，当前炮镜导入暂不支持加密压缩包")
            raise SightsImportError(output or "解压失败")

        if progress_callback:
            progress_callback(base_progress + share_progress, f"解压完成: {archive_path.name}")

    def _validate_extracted_sights_files(self, base_dir: Path, blocked_ext: set[str]) -> None:
        blocked_files = []
        for file_path in base_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(base_dir))
            if "__MACOSX" in rel_path or "desktop.ini" in rel_path.lower():
                continue
            if file_path.suffix.lower() in blocked_ext:
                blocked_files.append(rel_path)

        if blocked_files:
            file_list = "\n".join(f"  - {f}" for f in blocked_files[:10])
            raise SightsImportError(f"检测到不允许的文件类型:\n{file_list}")

    def _looks_like_blk_sight(self, file_path: Path) -> bool:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")[:4096].lower()
        except Exception:
            return False
        indicators = ("crosshair", "drawlines", "rangefinder", "thousandth", "matchexpclass", "fontsize")
        return any(word in content for word in indicators)

    def _backup_existing_file(self, target_path: Path) -> Path | None:
        if not target_path.exists():
            return None
        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = target_path.with_name(f"{target_path.name}.bak_{stamp}")
        index = 1
        while backup_path.exists():
            backup_path = target_path.with_name(f"{target_path.name}.bak_{stamp}_{index}")
            index += 1
        target_path.rename(backup_path)
        return backup_path

    def _normalize_sight_target_dir(self, target_dir: Any = None) -> str:
        return normalize_sight_target_dir(target_dir)

    def _looks_like_vehicle_sight_dir(self, name: str) -> bool:
        return looks_like_vehicle_sight_dir(name)

    def _merge_directory_contents(
        self,
        source_dir: Path,
        target_dir: Path,
        source_root: Path | None = None,
        target_root: Path | None = None,
        installed_sources: list[dict[str, str]] | None = None,
    ) -> tuple[int, int]:
        installed_count = 0
        backup_count = 0
        source_root = source_root or source_dir
        target_root = target_root or target_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for child in source_dir.iterdir():
            target_path = target_dir / child.name
            if child.is_dir():
                child_installed, child_backups = self._merge_directory_contents(
                    child,
                    target_path,
                    source_root=source_root,
                    target_root=target_root,
                    installed_sources=installed_sources,
                )
                installed_count += child_installed
                backup_count += child_backups
                continue
            if not child.is_file():
                continue
            backup_path = self._backup_existing_file(target_path)
            if backup_path:
                backup_count += 1
            shutil.move(str(child), str(target_path))
            installed_count += 1
            if installed_sources is not None and target_path.suffix.lower() == ".blk":
                self._append_installed_meta_source(
                    installed_sources,
                    source_file=child,
                    source_root=source_root,
                    target_file=target_path,
                    target_root=target_root,
                )
        return installed_count, backup_count

    def _collect_import_meta_files(self, base_dir: Path) -> list[dict[str, Any]]:
        """读取导入目录中的聚合 V2/V1 元数据，后续转换为内部映射。"""
        collected = self._collect_sight_metadata_records(base_dir)
        if collected["status"] != "has_meta":
            return []
        metadata_files = collected.get("metadata_files") or []
        return [{
            "meta": collected["meta"],
            "warnings": collected["warnings"],
            "meta_file": metadata_files[0] if metadata_files else "",
        }]

    def _append_installed_meta_source(
        self,
        installed_sources: list[dict[str, str]],
        source_file: Path,
        source_root: Path,
        target_file: Path,
        target_root: Path,
    ) -> None:
        target_dir = target_root.name
        installed_sources.append({
            "source_rel": self._relative_sight_path(source_file, source_root),
            "target_dir": target_dir,
            "target_rel": self._relative_sight_path(target_file, target_root),
            "target_path": str(target_file),
        })

    def _record_bulk_move_meta_sources(
        self,
        installed_sources: list[dict[str, str]],
        source_dir: Path,
        source_root: Path,
        target_dir: Path,
        target_rel_root: Path,
    ) -> None:
        for source_file in sorted(source_dir.rglob("*.blk"), key=lambda p: str(p).lower()):
            if not source_file.is_file():
                continue
            target_file = target_dir / Path(self._relative_sight_path(source_file, target_rel_root))
            self._append_installed_meta_source(
                installed_sources,
                source_file=source_file,
                source_root=source_root,
                target_file=target_file,
                target_root=target_dir,
            )

    def _save_import_meta_links(
        self,
        import_meta_entries: list[dict[str, Any]],
        installed_sources: list[dict[str, str]],
        archive_name: str,
        resource_id: str = "",
    ) -> int:
        if not import_meta_entries or not installed_sources or not self._usersights_path:
            return 0

        resource_metadata_entries = [
            {
                "meta": dict(entry.get("meta") or {}),
                "warnings": self._unique_text_list(entry.get("warnings")),
                "meta_file": str(entry.get("meta_file") or ""),
                "source": "package_asset",
            }
            for entry in import_meta_entries
            if isinstance(entry, dict) and isinstance(entry.get("meta"), dict)
        ]

        grouped_sources: dict[str, list[dict[str, str]]] = {}
        for item in installed_sources:
            target_dir = item.get("target_dir") or ""
            if not target_dir:
                continue
            grouped_sources.setdefault(target_dir, []).append(item)

        candidate_links: dict[str, list[dict[str, Any]]] = {}
        single_target = len(grouped_sources) == 1
        for meta_entry in import_meta_entries:
            meta = meta_entry.get("meta") if isinstance(meta_entry, dict) else None
            if not isinstance(meta, dict):
                continue
            for target_dir, target_sources in grouped_sources.items():
                linked_meta, matched_count, warnings = self._build_linked_import_meta(
                    meta,
                    target_sources,
                    allow_single_target_fallback=single_target,
                )
                if matched_count <= 0 and not single_target:
                    continue
                source_warnings = self._unique_text_list(meta_entry.get("warnings"))
                source_warnings.extend(warnings)
                candidate_links.setdefault(target_dir, []).append({
                    "matched_count": matched_count,
                    "meta": linked_meta,
                    "warnings": self._unique_text_list(source_warnings),
                    "meta_file": str(meta_entry.get("meta_file") or ""),
                })

        if not candidate_links:
            if resource_id and resource_metadata_entries:
                self._save_resource_metadata_links(resource_id, resource_metadata_entries, {})
            return 0

        self._ensure_meta_link_cache_loaded()
        saved_count = 0
        resource_metadata_by_target: dict[str, dict[str, Any]] = {}
        for target_dir, candidates in candidate_links.items():
            best = max(candidates, key=lambda item: (int(item.get("matched_count") or 0), item.get("meta_file") or ""))
            target_sources = grouped_sources.get(target_dir) or []
            file_signatures = self._build_meta_link_file_signatures(target_sources)
            self._meta_link_records[self._meta_link_key(target_dir)] = {
                "meta": best["meta"],
                "warnings": best["warnings"],
                "meta_file": best["meta_file"],
                "archive_name": archive_name,
                "linked_at": int(time.time()),
                "file_signatures": file_signatures,
            }
            resource_metadata_by_target[target_dir] = {
                "matched_count": int(best.get("matched_count") or 0),
                "meta": best["meta"],
                "warnings": best["warnings"],
                "meta_file": best["meta_file"],
                "archive_name": archive_name,
                "linked_at": int(time.time()),
                "file_signatures": file_signatures,
                "source": "package_asset",
            }
            saved_count += 1
        self._meta_link_dirty = True
        self._save_meta_link_cache()
        if resource_id and resource_metadata_entries:
            self._save_resource_metadata_links(resource_id, resource_metadata_entries, resource_metadata_by_target)
        return saved_count

    def _save_resource_metadata_links(
        self,
        resource_id: str,
        metadata_entries: list[dict[str, Any]],
        metadata_by_target: dict[str, dict[str, Any]],
    ) -> None:
        try:
            self._sights_repo.save_resource_metadata_links(resource_id, metadata_entries, metadata_by_target)
        except (FileNotFoundError, ValueError, OSError) as e:
            log.warning(f"保存炮镜资源库元数据索引失败: {e}")

    def _build_linked_import_meta(
        self,
        meta: dict[str, Any],
        target_sources: list[dict[str, str]],
        allow_single_target_fallback: bool,
    ) -> tuple[dict[str, Any], int, list[str]]:
        linked_meta = dict(meta)
        file_entries = meta.get("files") if isinstance(meta.get("files"), list) else []
        if not file_entries:
            return linked_meta, len(target_sources), []

        matched_entries: list[dict[str, Any]] = []
        used_target_rel: set[str] = set()
        for entry in file_entries:
            if not isinstance(entry, dict):
                continue
            match = self._find_meta_target_source(entry.get("path"), target_sources)
            if match is None:
                continue
            target_rel = match["target_rel"]
            if target_rel in used_target_rel:
                continue
            normalized_entry = dict(entry)
            normalized_entry["path"] = target_rel
            matched_entries.append(normalized_entry)
            used_target_rel.add(target_rel)

        warnings: list[str] = []
        if not matched_entries and allow_single_target_fallback and len(file_entries) == 1 and len(target_sources) == 1:
            normalized_entry = dict(file_entries[0])
            normalized_entry["path"] = target_sources[0]["target_rel"]
            matched_entries.append(normalized_entry)
            used_target_rel.add(target_sources[0]["target_rel"])
            warnings.append("meta_link_single_file_fallback")

        if matched_entries:
            linked_meta["files"] = matched_entries
            return linked_meta, len(matched_entries), warnings

        linked_meta["files"] = []
        warnings.append("meta_link_unmatched_files")
        return linked_meta, 0, warnings

    def _find_meta_target_source(
        self,
        entry_path: Any,
        target_sources: list[dict[str, str]],
    ) -> dict[str, str] | None:
        key = self._normalize_meta_link_path(entry_path)
        if not key:
            return None

        for source in target_sources:
            source_key = self._normalize_meta_link_path(source.get("source_rel"))
            target_key = self._normalize_meta_link_path(source.get("target_rel"))
            if key in {source_key, target_key}:
                return source
            if source_key.endswith(f"/{key}") or key.endswith(f"/{source_key}"):
                return source
            if target_key.endswith(f"/{key}") or key.endswith(f"/{target_key}"):
                return source

        basename = PurePosixPath(key).name.lower()
        basename_matches = [
            source for source in target_sources
            if PurePosixPath(self._normalize_meta_link_path(source.get("target_rel"))).name.lower() == basename
            or PurePosixPath(self._normalize_meta_link_path(source.get("source_rel"))).name.lower() == basename
        ]
        return basename_matches[0] if len(basename_matches) == 1 else None

    def _build_meta_link_file_signatures(self, target_sources: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
        signatures: dict[str, dict[str, Any]] = {}
        for item in target_sources:
            target_rel = item.get("target_rel") or ""
            target_path = item.get("target_path") or ""
            if not target_rel or not target_path:
                continue
            signature = self._build_meta_link_file_signature(Path(target_path))
            if signature:
                signatures[target_rel] = signature
        return signatures

    @staticmethod
    def _build_meta_link_file_signature(file_path: Path) -> dict[str, Any]:
        try:
            stat = file_path.stat()
        except OSError:
            return {}
        return {
            "size": int(stat.st_size),
            "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
        }

    @staticmethod
    def _normalize_meta_link_path(value: Any) -> str:
        text = str(value or "").replace("\\", "/").strip().lstrip("./")
        while "//" in text:
            text = text.replace("//", "/")
        return text.lower()

    def _remove_import_meta_files(self, base_dir: Path) -> int:
        """清理导入临时目录中的 AimerWT 伪 BLK，避免安装成游戏炮镜。"""
        removed_count = 0
        for file_path in sorted(base_dir.rglob("*.blk"), key=lambda p: str(p).lower()):
            if not file_path.is_file():
                continue
            if not self._meta_parser.is_meta_file(file_path):
                continue
            try:
                file_path.unlink()
                removed_count += 1
            except PermissionError as e:
                raise SightsImportError(f"无法跳过伪 BLK 元数据文件（权限不足）: {file_path.name}: {e}") from e
            except OSError as e:
                raise SightsImportError(f"无法跳过伪 BLK 元数据文件: {file_path.name}: {e}") from e
        for dir_path in sorted(
            [path for path in base_dir.rglob("*") if path.is_dir()],
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                dir_path.rmdir()
            except OSError:
                pass
        return removed_count

    @staticmethod
    def _has_real_blk_files(base_dir: Path) -> bool:
        return any(path.is_file() and path.suffix.lower() == ".blk" for path in base_dir.rglob("*.blk"))

    def preview_sight_import(self, file_path: str | Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._usersights_path or not self._usersights_path.exists():
            return {"success": False, "error_code": "usersights_not_set", "msg": "请先设置有效的 UserSights 路径"}

        source_path = Path(file_path)
        if not source_path.exists():
            return {"success": False, "error_code": "file_not_found", "msg": "文件不存在"}

        ext = source_path.suffix.lower()
        if ext == ".blk":
            return self._preview_blk_import(source_path, options=options)
        if ext in self.supported_archive_extensions:
            if ext == ".zip":
                return self._preview_zip_import(source_path, options=options)
            return self._preview_generic_archive_import(source_path, options=options)
        return {"success": False, "error_code": "unsupported_file_type", "msg": "仅支持 .blk/.zip/.rar/.7z 炮镜文件"}

    def _blocked_archive_extensions(self) -> set[str]:
        return set(BLOCKED_ARCHIVE_EXTENSIONS)

    def _preview_generic_archive_import(self, source_path: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        target_dir = ""
        target_mode = "archive_package"
        if "target_dir" in options:
            target_dir = self._normalize_sight_target_dir(options.get("target_dir"))
            target_mode = "specified_dir"

        seven_zip = self._find_7z()
        if not seven_zip:
            return {
                "success": True,
                "file_path": str(source_path),
                "file_name": source_path.name,
                "file_type": source_path.suffix.lower().lstrip("."),
                "detected_type": "archive_package",
                "target_mode": target_mode,
                "target_dir": target_dir,
                "target_root": str(self._usersights_path),
                "install_entries": [],
                "install_entry_limit": 0,
                "total_entry_count": 0,
                "blk_count": 0,
                "real_blk_count": 0,
                "meta_blk_count": 0,
                "matched_meta_count": 0,
                "unmatched_meta_count": 0,
                "preview_asset_count": 0,
                "conflict_count": 0,
                "warnings": ["未检测到 7z 组件，RAR/7Z 预检只能显示基础信息，导入时会再次校验"],
            }

        listing = self._list_generic_archive_entries(seven_zip, source_path)
        if not listing.get("success"):
            return listing

        blocked_ext = self._blocked_archive_extensions()
        unsafe_entries: list[str] = []
        blocked_entries: list[str] = []
        archive_items: list[dict[str, Any]] = []
        for filename in listing["entries"]:
            if not self._is_archive_member_path_safe(filename):
                unsafe_entries.append(filename)
                continue
            member_path = PurePosixPath(filename.replace("\\", "/"))
            suffix = member_path.suffix.lower()
            if suffix in blocked_ext:
                blocked_entries.append(filename)
                continue
            is_meta = suffix == ".blk" and self._meta_parser.is_meta_filename(member_path.name)
            archive_items.append({
                "name": str(member_path),
                "path": member_path,
                "suffix": suffix,
                "is_meta": is_meta,
                "is_real_blk": suffix == ".blk" and not is_meta,
                "is_preview_asset": self._is_preview_asset_name(member_path),
            })

        if unsafe_entries:
            return {
                "success": False,
                "error_code": "unsafe_archive_path",
                "msg": "压缩包路径不安全，已拒绝导入:\n" + "\n".join(unsafe_entries[:10]),
                "unsafe_entries": unsafe_entries[:20],
            }
        if blocked_entries:
            return {
                "success": False,
                "error_code": "blocked_archive_file",
                "msg": "检测到不允许的文件类型:\n" + "\n".join(blocked_entries[:10]),
                "blocked_entries": blocked_entries[:20],
            }

        real_blk_items = [item for item in archive_items if item["is_real_blk"]]
        meta_items = [item for item in archive_items if item["is_meta"]]
        deployment_preview = self._build_generic_archive_deployment_preview(source_path, options)
        target_mode, target_dir = self._infer_zip_preview_target(source_path, real_blk_items, options)
        install_entries = self._build_zip_preview_install_entries(real_blk_items, target_mode, target_dir, source_path)
        conflict_count = sum(1 for entry in install_entries if entry["exists"])
        warnings = ["压缩包将先保存到 AimerWT 炮镜库，再安装干净 BLK 到 UserSights"]
        if meta_items:
            warnings.append("RAR/7Z 预检无法读取伪 BLK 内容，元数据匹配数量会在导入解压后校验")
        if not real_blk_items:
            warnings.insert(0, "压缩包内未找到真实 .blk 炮镜文件")
        if len(install_entries) > 20:
            warnings.append(f"预检仅展示前 20 个安装项，完整数量为 {len(install_entries)}")

        return {
            "success": True,
            "file_path": str(source_path),
            "file_name": source_path.name,
            "file_type": source_path.suffix.lower().lstrip("."),
            "detected_type": "archive_package",
            "target_mode": target_mode,
            "target_dir": target_dir,
            "target_root": str(self._usersights_path),
            "install_entries": install_entries[:20],
            "install_entry_limit": 20,
            "total_entry_count": len(real_blk_items) + len(meta_items),
            "blk_count": len(real_blk_items),
            "real_blk_count": len(real_blk_items),
            "meta_blk_count": len(meta_items),
            "matched_meta_count": 0,
            "unmatched_meta_count": len(meta_items),
            "preview_asset_count": sum(1 for item in archive_items if item["is_preview_asset"]),
            "conflict_count": conflict_count,
            "warnings": warnings,
            "deployment_preview": deployment_preview,
            "author_recommendation_available": bool(deployment_preview.get("summary", {}).get("author_recommended_file_count")),
        }

    def _build_generic_archive_deployment_preview(
        self,
        source_path: Path,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        """在临时目录只读解析 RAR/7Z 的作者推荐和 BLK 兼容性。"""
        resource_files: list[dict[str, Any]] = []
        public_meta: dict[str, Any] = {}
        try:
            with tempfile.TemporaryDirectory(prefix="aimerwt_sight_archive_preview_") as tmp:
                preview_root = Path(tmp)
                blocked_ext = self._blocked_archive_extensions()
                self._extract_with_7z(source_path, preview_root, blocked_ext)
                self._validate_extracted_sights_files(preview_root, blocked_ext)
                meta_entries = self._collect_import_meta_files(preview_root)
                if meta_entries:
                    public_meta = dict(meta_entries[0].get("meta") or {})
                for file_path in self._list_real_blk_files(preview_root):
                    resource_files.append({
                        "source_relative_path": self._relative_sight_path(file_path, preview_root),
                        "match_exp_class_status": self._blk_analyzer.check_match_exp_class(file_path),
                    })
        except Exception as exc:
            log.debug(f"RAR/7Z 部署预检降级: {exc}")
        deployment_request = options.get("deployment_request")
        if not isinstance(deployment_request, dict):
            deployment_request = {"mode": "author_recommended", "remember": True}
        return build_sight_deployment_preview(resource_files, public_meta, deployment_request)

    def _list_generic_archive_entries(self, seven_zip: str, source_path: Path) -> dict[str, Any]:
        code, output = self._run_7z([seven_zip, "l", "-slt", "-p", str(source_path)])
        if code != 0:
            return {"success": False, "error_code": "archive_list_failed", "msg": output or "无法读取压缩包目录"}
        return {"success": True, "entries": self._parse_7z_listing_paths(output)}

    def _parse_7z_listing_paths(self, output: str) -> list[str]:
        entries: list[str] = []
        in_entries = False
        current: dict[str, str] | None = None

        def flush_current() -> None:
            if not current:
                return
            path = str(current.get("path") or "").replace("\\", "/").strip()
            if not path or path.endswith("/") or current.get("folder") == "+":
                return
            if "__MACOSX" in path or "desktop.ini" in path.lower():
                return
            entries.append(path)

        for raw_line in str(output or "").splitlines():
            line = raw_line.strip()
            if line.startswith("----------"):
                in_entries = True
                current = None
                continue
            if not in_entries:
                continue
            if line.startswith("Path = "):
                flush_current()
                current = {"path": line[7:].strip()}
                continue
            if current is not None and line.startswith("Folder = "):
                current["folder"] = line[9:].strip()
        flush_current()
        return entries

    def _collect_zip_metadata_records(
        self,
        zf: zipfile.ZipFile,
        real_names: set[str],
    ) -> dict[str, Any]:
        """从 ZIP 真实 BLK 尾部读取 V2，并兼容独立 V1 元数据成员。"""
        v2_records: list[dict[str, Any]] = []
        v2_files: list[str] = []
        v1_records: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        metadata_files: list[str] = []
        with tempfile.TemporaryDirectory(prefix="aimerwt_zip_meta_") as tmp:
            package_root = Path(tmp)
            for info in zf.infolist():
                filename = str(info.filename or "").replace("\\", "/").strip()
                if (
                    info.is_dir()
                    or not filename
                    or not self._is_archive_member_path_safe(filename)
                ):
                    continue
                member_path = PurePosixPath(filename)
                if member_path.suffix.lower() != ".blk":
                    continue

                if filename in real_names:
                    try:
                        tail = self._read_zip_member_tail(zf, info)
                    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                        errors.append("zip_embedded_meta_read_failed")
                        warnings.append(str(exc))
                        continue
                    embedded = self._meta_parser.parse_embedded_meta_bytes(
                        tail,
                        relative_path=filename,
                        package_root=package_root,
                    )
                    if embedded.get("parsed"):
                        v2_records.append(dict(embedded.get("meta") or {}))
                        v2_files.append(filename)
                        metadata_files.append(filename)
                        warnings.extend(embedded.get("warnings") or [])
                    elif embedded.get("error") == "embedded_meta_error":
                        errors.append("embedded_meta_error")
                        warnings.extend(embedded.get("warnings") or [])
                    continue

                if not self._meta_parser.is_meta_filename(member_path.name):
                    continue
                if not self._zip_member_has_meta_marker(zf, info):
                    continue
                if info.file_size > self._meta_parser.MAX_META_FILE_SIZE:
                    errors.append("oversized_meta_file")
                    continue
                try:
                    target = package_root.joinpath(*member_path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(info))
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    errors.append("zip_legacy_meta_read_failed")
                    warnings.append(str(exc))
                    continue
                legacy = self._meta_parser.parse_meta_file(
                    target,
                    package_root=package_root,
                )
                if legacy.get("parsed"):
                    v1_records.append(dict(legacy.get("meta") or {}))
                    metadata_files.append(filename)
                    warnings.extend(legacy.get("warnings") or [])
                else:
                    errors.append(str(legacy.get("error") or "meta_error"))
                    warnings.extend(legacy.get("warnings") or [])

        return self._merge_collected_sight_metadata(
            v2_records,
            v1_records,
            warnings,
            errors,
            metadata_files,
            v2_sources=v2_files,
        )

    @staticmethod
    def _read_zip_member_tail(
        zf: zipfile.ZipFile,
        info: zipfile.ZipInfo,
    ) -> bytes:
        tail_limit = (
            MAX_EMBEDDED_META_BYTES
            + len(EMBEDDED_META_START)
            + len(EMBEDDED_META_END)
            + 4096
        )
        with zf.open(info, "r") as source:
            if info.file_size > tail_limit:
                source.seek(info.file_size - tail_limit)
            return source.read(tail_limit)

    def _preview_zip_import(self, source_path: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        blocked_ext = self._blocked_archive_extensions()
        unsafe_entries: list[str] = []
        blocked_entries: list[str] = []
        archive_items: list[dict[str, Any]] = []
        meta_paths: set[str] = set()
        zip_metadata: dict[str, Any] = {
            "meta": {},
            "warnings": [],
            "conflicts": [],
            "error": "",
            "status": "no_meta",
        }

        try:
            with zipfile.ZipFile(source_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    filename = str(info.filename or "").replace("\\", "/").strip()
                    if not filename or filename.endswith("/") or "__MACOSX" in filename or "desktop.ini" in filename.lower():
                        continue
                    if not self._is_archive_member_path_safe(filename):
                        unsafe_entries.append(filename)
                        continue

                    member_path = PurePosixPath(filename)
                    suffix = member_path.suffix.lower()
                    if suffix in blocked_ext:
                        blocked_entries.append(filename)
                        continue

                    is_meta = False
                    if suffix == ".blk" and self._meta_parser.is_meta_filename(member_path.name):
                        is_meta = self._zip_member_has_meta_marker(zf, info)
                        if is_meta:
                            meta_paths.update(self._extract_meta_paths_from_zip_member(zf, info))

                    archive_items.append({
                        "name": filename,
                        "path": member_path,
                        "suffix": suffix,
                        "is_meta": is_meta,
                        "is_real_blk": suffix == ".blk" and not is_meta,
                        "is_preview_asset": self._is_preview_asset_name(member_path),
                    })
                real_names = {
                    item["name"] for item in archive_items if item["is_real_blk"]
                }
                zip_metadata = self._collect_zip_metadata_records(zf, real_names)
        except zipfile.BadZipFile as e:
            return {"success": False, "error_code": "bad_zip", "msg": f"无效的 ZIP 文件: {e}"}
        except zipfile.LargeZipFile as e:
            return {"success": False, "error_code": "large_zip", "msg": f"ZIP 文件过大: {e}"}
        except OSError as e:
            return {"success": False, "error_code": "read_failed", "msg": f"读取 ZIP 失败: {e}"}

        if unsafe_entries:
            return {
                "success": False,
                "error_code": "unsafe_archive_path",
                "msg": f"压缩包包含不安全路径，已拒绝预检: {unsafe_entries[0]}",
                "unsafe_entries": unsafe_entries[:10],
            }
        if blocked_entries:
            return {
                "success": False,
                "error_code": "blocked_archive_file",
                "msg": "压缩包包含不允许的文件类型，已拒绝预检",
                "blocked_entries": blocked_entries[:10],
            }

        real_blk_items = [item for item in archive_items if item["is_real_blk"]]
        meta_items = [item for item in archive_items if item["is_meta"]]
        public_meta = dict(zip_metadata.get("meta") or {})
        deployment_preview = self._build_zip_deployment_preview(
            source_path,
            real_blk_items,
            options,
            public_meta,
        )
        target_mode, target_dir_name = self._infer_zip_preview_target(source_path, real_blk_items, options)
        install_entries = self._build_zip_preview_install_entries(real_blk_items, target_mode, target_dir_name, source_path)
        conflict_count = sum(1 for entry in install_entries if entry["exists"])
        real_paths = {item["name"] for item in real_blk_items}
        matched_meta_count = len(meta_paths.intersection(real_paths)) + len(zip_metadata.get("v2_records") or [])
        warnings = ["压缩包将先保存到 AimerWT 炮镜库，再安装干净 BLK 到 UserSights"]
        warnings.extend(zip_metadata.get("warnings") or [])
        if not real_blk_items:
            warnings.insert(0, "压缩包内未找到真实 .blk 炮镜文件")
        if len(install_entries) > 20:
            warnings.append(f"预检仅展示前 20 个安装项，完整数量为 {len(install_entries)}")

        return {
            "success": True,
            "file_path": str(source_path),
            "file_name": source_path.name,
            "file_type": "zip",
            "detected_type": "archive_package",
            "target_mode": target_mode,
            "target_dir": target_dir_name,
            "target_root": str(self._usersights_path),
            "install_entries": install_entries[:20],
            "install_entry_limit": 20,
            "total_entry_count": len(real_blk_items) + len(meta_items),
            "blk_count": len(real_blk_items),
            "real_blk_count": len(real_blk_items),
            "meta_blk_count": len(meta_items),
            "matched_meta_count": matched_meta_count,
            "unmatched_meta_count": max(0, len(meta_paths) - matched_meta_count),
            "preview_asset_count": sum(1 for item in archive_items if item["is_preview_asset"]),
            "conflict_count": conflict_count,
            "warnings": warnings,
            "public_meta": public_meta,
            "metadata_conflicts": list(zip_metadata.get("conflicts") or []),
            "metadata_status": zip_metadata.get("status") or "no_meta",
            "deployment_preview": deployment_preview,
            "author_recommendation_available": bool(deployment_preview.get("summary", {}).get("author_recommended_file_count")),
        }

    def _build_zip_deployment_preview(
        self,
        source_path: Path,
        real_blk_items: list[dict[str, Any]],
        options: dict[str, Any],
        public_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """只解出受限大小的 BLK 供作者推荐和 matchExpClass 预检。"""
        resolved_public_meta = dict(public_meta or {})
        resource_files: list[dict[str, Any]] = []
        real_names = {str(item.get("name") or "") for item in real_blk_items}
        with tempfile.TemporaryDirectory(prefix="aimerwt_sight_preview_") as tmp:
            preview_root = Path(tmp)
            try:
                with zipfile.ZipFile(source_path, "r") as zf:
                    for info in zf.infolist():
                        filename = str(info.filename or "").replace("\\", "/").strip()
                        if info.is_dir() or not filename or not self._is_archive_member_path_safe(filename):
                            continue
                        member_path = PurePosixPath(filename)
                        is_real = filename in real_names
                        is_meta = (
                            member_path.suffix.lower() == ".blk"
                            and self._meta_parser.is_meta_filename(member_path.name)
                            and self._zip_member_has_meta_marker(zf, info)
                        )
                        if not is_real and not is_meta:
                            continue
                        if info.file_size > 4 * 1024 * 1024:
                            if is_real:
                                resource_files.append({
                                    "source_relative_path": filename,
                                    "match_exp_class_status": "unknown_unreadable",
                                })
                            continue
                        target = preview_root.joinpath(*member_path.parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(zf.read(info))
                        if is_real:
                            resource_files.append({
                                "source_relative_path": filename,
                                "match_exp_class_status": self._blk_analyzer.check_match_exp_class(target),
                            })
                        elif not resolved_public_meta:
                            parsed = self._meta_parser.parse_meta_file(target, package_root=preview_root)
                            if parsed.get("parsed"):
                                resolved_public_meta = dict(parsed.get("meta") or {})
            except (OSError, zipfile.BadZipFile, RuntimeError):
                resource_files = [
                    {"source_relative_path": name, "match_exp_class_status": "unknown_unreadable"}
                    for name in sorted(real_names)
                ]
        deployment_request = options.get("deployment_request")
        if not isinstance(deployment_request, dict):
            deployment_request = {"mode": "author_recommended", "remember": True}
        return build_sight_deployment_preview(resource_files, resolved_public_meta, deployment_request)

    def _zip_member_has_meta_marker(self, zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bool:
        try:
            raw = zf.read(info)
        except (RuntimeError, OSError, zipfile.BadZipFile):
            return False
        return self._meta_parser.detect_meta_marker_bytes(raw)

    def _extract_meta_paths_from_zip_member(self, zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> set[str]:
        try:
            raw = zf.read(info)
        except (RuntimeError, OSError, zipfile.BadZipFile):
            return set()
        if len(raw) > self._meta_parser.MAX_META_FILE_SIZE:
            return set()
        text = self._meta_parser._decode_meta_bytes(raw)
        marker = self._meta_parser._marker_re.search(text)
        if not marker:
            return set()
        end_index = text.lower().find(self._meta_parser.MARKER_END.lower(), marker.end())
        if end_index < 0:
            return set()
        try:
            meta = json.loads(text[marker.end():end_index].strip())
        except json.JSONDecodeError:
            return set()
        if not isinstance(meta, dict) or not isinstance(meta.get("files"), list):
            return set()
        paths = set()
        for entry in meta["files"]:
            if not isinstance(entry, dict):
                continue
            rel_path = str(entry.get("path") or "").replace("\\", "/").strip()
            if rel_path and self._is_archive_member_path_safe(rel_path):
                paths.add(str(PurePosixPath(rel_path)))
        return paths

    def _infer_zip_preview_target(
        self,
        source_path: Path,
        archive_items: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> tuple[str, str]:
        requested_target_dir = options.get("target_dir") if "target_dir" in options else TARGET_DIR_UNSET
        return infer_archive_target(
            [item["path"] for item in archive_items],
            source_path.stem,
            requested_target_dir=requested_target_dir,
        )

    def _build_zip_preview_install_entries(
        self,
        real_blk_items: list[dict[str, Any]],
        target_mode: str,
        target_dir_name: str,
        source_path: Path,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in real_blk_items:
            member_path: PurePosixPath = item["path"]
            target_rel = PurePosixPath(map_archive_member_to_target(
                member_path,
                target_mode,
                target_dir_name,
                source_path.stem,
            ))
            target_path = self._usersights_path / Path(*target_rel.parts)
            parent_text = "" if str(target_rel.parent) == "." else str(target_rel.parent)
            entries.append({
                "source": item["name"],
                "target_dir": parent_text,
                "target_name": target_rel.name,
                "target_path": str(target_path),
                "exists": target_path.exists(),
                "is_blk": True,
            })
        return entries

    def _find_package_upgrade_retained_file_targets(
        self,
        display_name: str,
        current_resource_id: str,
    ) -> list[dict[str, str]]:
        """同名包升级时，把旧受管文件的用户目标转换回包内公开相对路径。"""
        if not self._usersights_path:
            return []
        with self._sights_repo._get_manifest_lock(self._usersights_path):
            manifest = self._sights_repo.load_manifest(self._usersights_path)
        candidates: list[tuple[str, dict[str, Any]]] = []
        for resource_id, record in (manifest.get("resources") or {}).items():
            if (
                not isinstance(record, dict)
                or str(resource_id) == str(current_resource_id)
                or str(record.get("resource_type") or "") != "package"
                or str(record.get("display_name") or "") != str(display_name or "")
                or not isinstance(record.get("deployment"), dict)
            ):
                continue
            candidates.append((str(resource_id), record))
        candidates.sort(key=lambda pair: str(pair[1].get("updated_at") or ""), reverse=True)
        for resource_id, record in candidates:
            try:
                old_resource, _ = self._sights_repo.load_resource(resource_id)
            except Exception:
                continue
            public_by_storage: dict[str, str] = {}
            for entry in old_resource.get("files") or []:
                if not isinstance(entry, dict):
                    continue
                storage_path = str(entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
                public_path = str(entry.get("original_source_relative_path") or "").replace("\\", "/").strip("/")
                if storage_path and public_path:
                    public_by_storage[storage_path.lower()] = public_path
            retained: list[dict[str, str]] = []
            for item in record.get("deployment", {}).get("file_targets") or []:
                if not isinstance(item, dict):
                    continue
                storage_path = str(item.get("source_relative_path") or "").replace("\\", "/").strip("/")
                target_path = str(item.get("target_relative_path") or "").replace("\\", "/").strip("/")
                public_path = public_by_storage.get(storage_path.lower())
                if public_path and target_path:
                    retained.append({
                        "source_relative_path": public_path,
                        "target_relative_path": target_path,
                    })
            if retained:
                return retained
        return []
    def _retire_superseded_package_records(
        self,
        display_name: str,
        current_resource_id: str,
    ) -> int:
        """新包部署成功后移除同名旧清单归属；磁盘文件和资源库源文件均保留。"""
        if not self._usersights_path:
            return 0
        with self._sights_repo._get_manifest_lock(self._usersights_path):
            manifest = self._sights_repo.load_manifest(self._usersights_path)
            retired_count = 0
            for resource_id, record in list((manifest.get("resources") or {}).items()):
                if (
                    not isinstance(record, dict)
                    or str(resource_id) == str(current_resource_id)
                    or str(record.get("resource_type") or "") != "package"
                    or str(record.get("display_name") or "") != str(display_name or "")
                ):
                    continue
                for entry in record.get("files") or []:
                    if not isinstance(entry, dict):
                        continue
                    target_path = str(entry.get("target_relative_path") or "")
                    file_record = manifest.get("file_map", {}).get(target_path)
                    if not isinstance(file_record, dict):
                        continue
                    owners = [
                        str(owner)
                        for owner in file_record.get("owners") or []
                        if str(owner) and str(owner) != str(resource_id)
                    ]
                    if owners:
                        file_record["owners"] = owners
                        manifest["file_map"][target_path] = file_record
                    else:
                        manifest["file_map"].pop(target_path, None)
                manifest["resources"].pop(resource_id, None)
                retired_count += 1
            if retired_count:
                self._sights_repo.save_manifest(self._usersights_path, manifest)
            return retired_count
    def _build_archive_repository_install_entries(
        self,
        extract_dir: Path,
        archive_path: Path,
        requested_target_dir: Any = None,
    ) -> list[dict[str, str]]:
        real_blk_files = self._list_real_blk_files(extract_dir)
        if not real_blk_files:
            return []

        real_rel_paths = [
            PurePosixPath(self._relative_sight_path(path, extract_dir))
            for path in real_blk_files
        ]
        target_override = requested_target_dir if requested_target_dir is not None else TARGET_DIR_UNSET
        mapping = build_archive_install_mapping(
            real_rel_paths,
            archive_path.stem,
            requested_target_dir=target_override,
        )
        return list(mapping["entries"])

    def _build_installed_meta_sources_from_install_entries(
        self,
        install_entries: list[dict[str, str]],
        usersights_dir: Path,
    ) -> list[dict[str, str]]:
        installed_sources: list[dict[str, str]] = []
        for entry in install_entries:
            source_rel = str(entry.get("source_relative_path") or "")
            target_rel = str(entry.get("target_relative_path") or "")
            target_parts = PurePosixPath(target_rel).parts
            if not source_rel or not target_parts:
                continue
            target_dir = target_parts[0]
            inner_target = str(PurePosixPath(*target_parts[1:])) if len(target_parts) > 1 else target_parts[0]
            target_path = usersights_dir.joinpath(*target_parts)
            installed_sources.append({
                "source_rel": source_rel,
                "target_dir": target_dir,
                "target_rel": inner_target,
                "target_path": str(target_path),
            })
        return installed_sources

    def _count_import_meta_files(self, base_dir: Path) -> int:
        count = 0
        for file_path in sorted(base_dir.rglob("*.blk"), key=lambda p: str(p).lower()):
            if file_path.is_file() and self._meta_parser.is_meta_file(file_path):
                count += 1
        return count

    @staticmethod
    def _archive_target_dir_result(usersights_dir: Path, install_entries: list[dict[str, str]]) -> Path:
        target_dirs = sorted({
            PurePosixPath(str(entry.get("target_relative_path") or "")).parts[0]
            for entry in install_entries
            if PurePosixPath(str(entry.get("target_relative_path") or "")).parts
        })
        if len(target_dirs) == 1:
            return usersights_dir / target_dirs[0]
        return usersights_dir

    @staticmethod
    def _is_preview_asset_name(member_path: PurePosixPath) -> bool:
        return is_sight_preview_asset_name(member_path)

    def _preview_blk_import(self, source_path: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        target_dir = self._normalize_sight_target_dir((options or {}).get("target_dir"))
        target_path = self._usersights_path / target_dir / source_path.name
        if target_dir == "all_tanks":
            warnings = ["将安装为全载具可选炮镜，安装后需要在游戏内选择并保存炮镜"]
        else:
            warnings = [f"将安装到特定载具目录 {target_dir}，安装后需要在该载具的 Sight Settings 中选择并保存"]
        if not self._looks_like_blk_sight(source_path):
            warnings.insert(0, "该文件内容不像标准炮镜配置，请确认文件是否正确")
        deployment_request = (options or {}).get("deployment_request")
        if not isinstance(deployment_request, dict):
            deployment_request = {"mode": "author_recommended", "remember": True}
        deployment_preview = build_sight_deployment_preview(
            [{
                "source_relative_path": source_path.name,
                "match_exp_class_status": self._blk_analyzer.check_match_exp_class(source_path),
            }],
            {},
            deployment_request,
        )

        return {
            "success": True,
            "file_path": str(source_path),
            "file_name": source_path.name,
            "file_type": "blk",
            "detected_type": "single_blk",
            "target_root": str(self._usersights_path),
            "install_entries": [{
                "source": source_path.name,
                "target_dir": target_dir,
                "target_name": source_path.name,
                "target_path": str(target_path),
                "exists": target_path.exists(),
                "is_blk": True,
            }],
            "blk_count": 1,
            "conflict_count": 1 if target_path.exists() else 0,
            "warnings": warnings,
            "deployment_preview": deployment_preview,
            "author_recommendation_available": False,
        }

    def import_sight_file(
        self,
        file_path: str | Path,
        options: dict[str, Any] | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        conflict_strategy = str(options.get("conflict_strategy") or "backup")
        if conflict_strategy != "backup":
            raise ValueError("首版仅支持 backup 冲突策略")

        source_path = Path(file_path)
        ext = source_path.suffix.lower()
        if ext == ".blk":
            target_dir = self._normalize_sight_target_dir(options.get("target_dir"))
            return self._import_blk_file(
                source_path,
                target_dir=target_dir,
                deployment_request=options.get("deployment_request"),
                progress_callback=progress_callback,
            )
        if ext in self.supported_archive_extensions:
            target_dir = options.get("target_dir") if "target_dir" in options else None
            result = self.import_sights_zip(
                source_path,
                progress_callback=progress_callback,
                overwrite=False,
                target_dir=target_dir,
                deployment_request=options.get("deployment_request"),
            )
            return {
                "success": bool(result.get("ok")),
                "installed_count": int(result.get("installed_count") or 0),
                "backup_count": int(result.get("backup_count") or 0),
                "target_root": str(self._usersights_path or ""),
                "installed_dirs": [Path(str(result.get("target_dir") or "")).name] if result.get("target_dir") else [],
                "message": "炮镜压缩包已导入",
                **result,
            }
        raise ValueError("仅支持 .blk/.zip/.rar/.7z 炮镜文件")

    def _import_blk_file(
        self,
        source_path: Path,
        target_dir: str = "all_tanks",
        deployment_request: dict[str, Any] | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        if not self._usersights_path or not self._usersights_path.exists():
            raise ValueError("请先设置有效的 UserSights 路径")
        if not source_path.exists():
            raise ValueError(f"炮镜文件不存在: {source_path}")
        if source_path.suffix.lower() != ".blk":
            raise ValueError("请选择有效的 .blk 炮镜文件")
        if self._meta_parser.is_meta_file(source_path):
            raise SightsImportError("AimerWT 伪 BLK 元数据文件不会作为炮镜安装，请和真实 BLK 一起导入")

        target_dir_name = self._normalize_sight_target_dir(target_dir)
        target_dir_path = self._usersights_path / target_dir_name
        target_path = target_dir_path / source_path.name
        if progress_callback:
            progress_callback(5, f"准备安装炮镜: {source_path.name}")
        try:
            resource = self._sights_repo.import_single_blk(
                source_path,
                target_dir=target_dir_name,
                display_name=source_path.stem,
            )
            if progress_callback:
                progress_callback(45, "炮镜已写入资源库")
            if isinstance(deployment_request, dict):
                install_result = self._sights_repo.apply_resource_deployment(
                    resource["resource_id"],
                    self._usersights_path,
                    deployment_request,
                )
            else:
                install_result = self._sights_repo.install_resource(
                    resource["resource_id"],
                    self._usersights_path,
                )
        except PermissionError as e:
            raise SightsImportError(f"安装炮镜失败（权限不足）: {e}") from e
        except OSError as e:
            raise SightsImportError(f"安装炮镜失败: {e}") from e

        if install_result.get("conflict_count") and not install_result.get("installed_count"):
            raise SightsImportError("UserSights 中存在同名不同内容炮镜，请先处理冲突")

        self._clear_sights_cache()
        if progress_callback:
            progress_callback(100, "炮镜安装完成")

        warnings = []
        if not self._looks_like_blk_sight(source_path):
            warnings.append("该文件内容不像标准炮镜配置，请确认文件是否正确")
        deployment_preview = install_result.get("preview") if isinstance(install_result.get("preview"), dict) else {}
        deployment_targets = deployment_preview.get("file_targets") or []
        installed_dirs = list(dict.fromkeys(
            PurePosixPath(str(item.get("target_relative_path") or "")).parts[0]
            for item in deployment_targets
            if PurePosixPath(str(item.get("target_relative_path") or "")).parts
        ))
        if not installed_dirs:
            installed_dirs = [target_dir_name]
        if deployment_targets:
            first_parts = PurePosixPath(str(deployment_targets[0].get("target_relative_path") or "")).parts
            if first_parts:
                target_path = self._usersights_path.joinpath(*first_parts)

        return {
            "success": bool(install_result.get("success")),
            "installed_count": int(install_result.get("installed_count") or 0),
            "backup_count": 0,
            "target_root": str(self._usersights_path),
            "installed_dirs": installed_dirs,
            "target_path": str(target_path),
            "deployment_preview": deployment_preview,
            "backup_path": "",
            "resource_id": resource["resource_id"],
            "resource_path": resource["resource_path"],
            "expected_file_count": int(install_result.get("expected_file_count") or 0),
            "conflict_count": int(install_result.get("conflict_count") or 0),
            "install_status": str(install_result.get("install_status") or ""),
            "warnings": warnings,
            "message": f"已安装炮镜文件: {source_path.name}",
        }

    def import_sights_zip(
        self,
        zip_path: str | Path,
        progress_callback: Callable[[int, str], None] | None = None,
        overwrite: bool = False,
        target_dir: Any = None,
        deployment_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        将炮镜压缩包解压写入资源库，再按安装清单安装干净 BLK 到 UserSights。
        
        Args:
            zip_path: ZIP/RAR/7Z 文件路径
            progress_callback: 进度回调函数 (percentage, message)
            overwrite: 是否复盖同名文件夹
            target_dir: 指定目标目录时，仅提取压缩包内 .blk 文件并安装到该目录
            
        Returns:
            包含 ok 和 target_dir 的字典
            
        Raises:
            ValueError: 路径未设置或文件无效
            FileExistsError: 目标文件夹已存在且未允许复盖
            SightsImportError: 导入过程失败
        """
        if not self._usersights_path or not self._usersights_path.exists():
            raise ValueError("请先设置有效的 UserSights 路径")

        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise ValueError(f"压缩包文件不存在: {zip_path}")
        archive_ext = zip_path.suffix.lower()
        if archive_ext not in self.supported_archive_extensions:
            raise ValueError("请选择有效的 .zip/.rar/.7z 文件")

        usersights_dir = self._usersights_path
        try:
            usersights_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise SightsImportError(f"无法创建目标目录（权限不足）: {e}")
        except OSError as e:
            raise SightsImportError(f"无法创建目标目录: {e}")

        blocked_ext = self._blocked_archive_extensions()

        tmp_dir = usersights_dir / f".__tmp_extract__{zip_path.stem}"
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except OSError as e:
                log.warning(f"清理临时目录失败: {e}")
        
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise SightsImportError(f"无法创建临时目录: {e}")

        requested_target_dir = target_dir
        import_meta_entries: list[dict[str, Any]] = []
        installed_meta_sources: list[dict[str, str]] = []
        skipped_meta_count = 0
        
        try:
            if progress_callback:
                progress_callback(1, f"准备解压炮镜包: {zip_path.name}")

            if archive_ext == ".zip":
                try:
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        members = [m for m in zf.infolist() if not m.is_dir()]
                        total = max(len(members), 1)
                        extracted = 0

                        for m in members:
                            filename = str(m.filename or "").replace("\\", "/").strip()
                            if not filename or "__MACOSX" in filename or "desktop.ini" in filename.lower():
                                continue
                            if filename.endswith("/"):
                                continue
                            if not self._is_archive_member_path_safe(filename):
                                raise SightsImportError(f"压缩包路径不安全（路径遍历）: {filename}")

                            member_path = PurePosixPath(filename)
                            ext = member_path.suffix.lower()
                            if ext in blocked_ext:
                                raise SightsImportError(f"检测到不允许的文件类型: {filename}")

                            target_path = tmp_dir.joinpath(*member_path.parts)

                            try:
                                target_path.parent.mkdir(parents=True, exist_ok=True)
                                with zf.open(m, "r") as src, open(target_path, "wb") as dst:
                                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                            except PermissionError as e:
                                raise SightsImportError(f"解压失败（权限不足）: {filename}: {e}")
                            except OSError as e:
                                raise SightsImportError(f"解压失败: {filename}: {e}")

                            extracted += 1
                            if progress_callback:
                                pct = 2 + int((extracted / total) * 90)
                                progress_callback(pct, f"解压中: {Path(filename).name}")

                except zipfile.BadZipFile as e:
                    raise SightsImportError(f"无效的 ZIP 文件: {e}")
                except zipfile.LargeZipFile as e:
                    raise SightsImportError(f"ZIP 文件过大: {e}")
            else:
                self._extract_with_7z(
                    zip_path,
                    tmp_dir,
                    blocked_ext,
                    progress_callback=progress_callback,
                    base_progress=2,
                    share_progress=90,
                )
            self._validate_extracted_sights_files(tmp_dir, blocked_ext)
            import_meta_entries = self._collect_import_meta_files(tmp_dir)
            skipped_meta_count = self._count_import_meta_files(tmp_dir)
            install_entries = self._build_archive_repository_install_entries(
                tmp_dir,
                zip_path,
                requested_target_dir=requested_target_dir,
            )
            if not install_entries:
                raise SightsImportError("压缩包内未找到真实 .blk 炮镜文件")

            if progress_callback:
                progress_callback(92, "炮镜包写入资源库")
            resource = self._sights_repo.import_package_directory(
                tmp_dir,
                install_entries,
                display_name=zip_path.stem,
                archive_name=zip_path.name,
            )
            resource_metadata_entries = [
                {
                    "meta": dict(entry.get("meta") or {}),
                    "warnings": self._unique_text_list(entry.get("warnings")),
                    "meta_file": str(entry.get("meta_file") or ""),
                    "source": "package_asset",
                }
                for entry in import_meta_entries
                if isinstance(entry, dict) and isinstance(entry.get("meta"), dict)
            ]
            if resource_metadata_entries:
                self._save_resource_metadata_links(resource["resource_id"], resource_metadata_entries, {})

            if not isinstance(deployment_request, dict):
                deployment_request = None
            else:
                deployment_request = dict(deployment_request)
                if str(deployment_request.get("mode") or "") == "author_recommended":
                    retained_targets = self._find_package_upgrade_retained_file_targets(
                        resource.get("display_name") or zip_path.stem,
                        resource["resource_id"],
                    )
                    if retained_targets:
                        deployment_request["retained_file_targets"] = retained_targets
            if deployment_request is None:
                install_result = self._sights_repo.install_resource(
                    resource["resource_id"],
                    usersights_dir,
                )
                target_dir = self._archive_target_dir_result(usersights_dir, install_entries)
                installed_meta_sources = self._build_installed_meta_sources_from_install_entries(
                    install_entries,
                    usersights_dir,
                )
            else:
                install_result = self._sights_repo.apply_resource_deployment(
                    resource["resource_id"],
                    usersights_dir,
                    deployment_request,
                )
                deployment_preview = install_result.get("preview") or {}
                deployment_targets = deployment_preview.get("file_targets") or []
                installed_meta_sources = []
                for item in deployment_targets:
                    target_rel = str(item.get("target_relative_path") or "")
                    parts = PurePosixPath(target_rel).parts
                    if not parts:
                        continue
                    installed_meta_sources.append({
                        "source_rel": str(item.get("source_relative_path") or ""),
                        "target_dir": parts[0],
                        "target_rel": str(PurePosixPath(*parts[1:])) if len(parts) > 1 else parts[0],
                        "target_path": str(usersights_dir.joinpath(*parts)),
                    })
                target_dir = self._archive_target_dir_result(
                    usersights_dir,
                    [{"target_relative_path": str(item.get("target_relative_path") or "")} for item in deployment_targets],
                )
                if install_result.get("success"):
                    install_result["superseded_resource_count"] = self._retire_superseded_package_records(
                        resource.get("display_name") or zip_path.stem,
                        resource["resource_id"],
                    )

            if progress_callback:
                progress_callback(98, "完成安装")

        finally:
            # 清理临时目录
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
            except OSError as e:
                log.warning(f"清理临时目录失败: {e}")

        if progress_callback:
            progress_callback(100, "导入完成")

        linked_meta_count = self._save_import_meta_links(
            import_meta_entries,
            installed_meta_sources,
            archive_name=zip_path.name,
            resource_id=str(resource.get("resource_id") or ""),
        )
        self._clear_sights_cache()
        log.info(f"炮镜导入成功: {target_dir}")
        return {
            "ok": bool(install_result.get("success")),
            "target_dir": str(target_dir),
            "installed_count": int(install_result.get("installed_count") or 0),
            "backup_count": 0,
            "skipped_meta_count": skipped_meta_count,
            "linked_meta_count": linked_meta_count,
            "resource_id": resource["resource_id"],
            "resource_path": resource["resource_path"],
            "expected_file_count": int(install_result.get("expected_file_count") or 0),
            "conflict_count": int(install_result.get("conflict_count") or 0),
            "conflicts": install_result.get("conflicts") or [],
            "install_status": str(install_result.get("install_status") or ""),
            "asset_count": int(resource.get("asset_count") or 0),
            "deployment_preview": install_result.get("preview") or {},
            "deployment": install_result.get("deployment") or {},
            "superseded_resource_count": int(install_result.get("superseded_resource_count") or 0),
        }
