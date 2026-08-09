# -*- coding: utf-8 -*-
"""
作者端炮镜发布适配服务。

功能定位:
- 管理作者端炮镜项目，不读取或写入游戏 UserSights。
- 从文件夹或 ZIP 安全复制真实 BLK、公开伪 BLK和封面素材。
- 维护作者私有项目模型，生成当前主程序可消费的公开伪 BLK。
- 在导出前给出路径、分组、元数据和安装映射兼容报告。
- 白名单构建标准 ZIP，任何失败都不覆盖既有项目与成品。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from services.sight_blk_analyzer import SightBlkAnalyzer
from services.sight_embedded_metadata import (
    SightEmbeddedMetadataConflict,
    SightEmbeddedMetadataError,
    parse_embedded_metadata_file,
    replace_embedded_metadata_bytes,
    write_embedded_metadata_file,
)
from services.sight_meta_parser import SightMetaParser
from services.sight_vehicle_catalog import SightVehicleCatalog, normalize_vehicle_id
from services.sight_package_rules import (
    BLOCKED_ARCHIVE_EXTENSIONS,
    TARGET_DIR_UNSET,
    build_archive_install_mapping,
    is_archive_member_path_safe,
    is_package_cover_asset_name,
    is_unsafe_windows_path_part,
    normalize_safe_relative_path,
)
from utils.logger import get_logger


log = get_logger(__name__)

PROJECT_SCHEMA_VERSION = 2
PROJECT_TYPE = "sight_package"
PROJECT_FILE_NAME = "sight_project.json"
AUTHOR_DIR_NAME = "_aimerwt_author"
SOURCE_DIR_NAME = "source"
SOURCE_ASSET_DIR_NAME = "source_assets"
PUBLIC_META_VERSION = 2
MAX_IMPORT_MEMBER_COUNT = 10_000
MAX_IMPORT_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROJECT_FILE_COUNT = 5_000
ALLOWED_COVER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

PACKAGE_KEYS = {
    "package_name",
    "author",
    "version",
    "description",
    "note",
    "tags",
    "recommended_vehicles",
    "recommended_apply_mode",
    "primary_vehicle_id",
    "compatible_vehicle_ids",
    "target_resolution",
    "target_resolutions",
    "sensitivity",
    "apply_correction_to_gun",
    "hover_text",
    "link_video",
    "link_wtlive",
    "link_bilibili",
}
PUBLIC_TOP_LEVEL_KEYS = {
    \
    *PACKAGE_KEYS,
    "author_note",
    "files",
    "groups",
}
FILE_META_KEYS = {
    \
    "display_name",
    "ammo_type",
    "recommended_vehicles",
    "recommended_apply_mode",
    "primary_vehicle_id",
    "compatible_vehicle_ids",
    "target_resolution",
    "note",
}
GROUP_META_KEYS = {
    "group_id",
    "name",
    "description",
    "ammo_types",
    "recommended_vehicles",
    "recommended_apply_mode",
    "primary_vehicle_id",
    "compatible_vehicle_ids",
    "target_resolutions",
    "platforms",
    "tags",
    "featured",
    "sort_order",
    "files",
}
SAVE_BLOCKING_CODES = {
    "project_schema_invalid",
    "unsafe_source_path",
    "unsafe_output_path",
    "invalid_windows_path",
    "duplicate_output_path",
    "duplicate_install_path",
    "group_id_reserved",
    "group_id_duplicate",
    "group_sort_duplicate",
    "group_file_duplicate",
    "group_file_missing",
    "blocked_archive_file",
}


class AuthorSightService:
    """炮镜作者项目、兼容报告和 ZIP 构建服务。"""

    def __init__(self, app_base_dir: str | Path, web_dir: str | Path | None = None) -> None:
        self.app_base_dir = Path(app_base_dir)
        self.web_dir = Path(web_dir) if web_dir else None
        self.workspace_dir = self.app_base_dir / "AimerWT作者端"
        self.library_dir = self.workspace_dir / "炮镜库"
        self.export_dir = self.workspace_dir / "炮镜导出区"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._meta_parser = SightMetaParser()
        self._vehicle_catalog = SightVehicleCatalog()
        self._blk_analyzer = SightBlkAnalyzer()
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

    def get_workspace_info(self) -> dict[str, Any]:
        return self._success({
            "workspace_dir": str(self.workspace_dir),
            "library_dir": str(self.library_dir),
            "export_dir": str(self.export_dir),
            "schema_version": PROJECT_SCHEMA_VERSION,
            "meta_version": PUBLIC_META_VERSION,
            "vehicle_catalog": self._vehicle_catalog.list_vehicles(),
            "vehicle_catalog_updated_at": self._vehicle_catalog.updated_at,
        })

    def list_projects(self, query: str = "") -> dict[str, Any]:
        q = str(query or "").strip().lower()
        rows: list[dict[str, Any]] = []
        for child in sorted(self.library_dir.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if q and q not in child.name.lower():
                continue
            project_file = self._project_file(child)
            project_error = ""
            try:
                raw = self._read_json(project_file) if project_file.exists() else {}
            except (OSError, ValueError) as exc:
                raw = {}
                project_error = str(exc)
            package = raw.get("package") if isinstance(raw.get("package"), dict) else {}
            files = raw.get("files") if isinstance(raw.get("files"), list) else []
            included_files = [item for item in files if isinstance(item, dict) and item.get("include", True)]
            try:
                modified_at = project_file.stat().st_mtime if project_file.exists() else child.stat().st_mtime
            except OSError:
                modified_at = 0
            rows.append({
                "project_name": child.name,
                "package_name": str(package.get("package_name") or child.name),
                "author": str(package.get("author") or ""),
                "version": str(package.get("version") or ""),
                "file_count": len(included_files),
                "derived_type": "single_sight" if len(included_files) == 1 else "sight_package",
                "has_project_file": project_file.exists(),
                "has_cover": self._resolve_cover_path(child, raw).is_file(),
                "modified_at": modified_at,
                "project_error": project_error,
            })
        return self._success({"projects": rows, "count": len(rows)})

    def create_project(self, project_name: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if project_dir.exists():
            return self._failure("同名炮镜项目已存在", code="project_exists")

        try:
            self._ensure_project_layout(project_dir)
            project = self._build_default_project(safe_name, defaults or {})
            self._atomic_write_json(self._project_file(project_dir), project)
        except Exception:
            self._remove_project_tree(project_dir, allow_missing=True)
            raise
        return self._success({
            "project_name": safe_name,
            "project": project,
            "scan": self._empty_scan(),
            "cover_preview": "",
        }, msg="炮镜项目已创建")

    def rename_project(self, old_name: str, new_name: str) -> dict[str, Any]:
        old_safe = self._validate_project_name(old_name)
        new_safe = self._validate_project_name(new_name)
        old_dir = self._project_dir(old_safe)
        new_dir = self._project_dir(new_safe)
        if not old_dir.is_dir():
            return self._failure("原炮镜项目不存在", code="project_not_found")
        if new_dir.exists():
            return self._failure("目标项目名称已存在", code="project_exists")

        raw = self._read_json(self._project_file(old_dir))
        normalized = self._normalize_project(raw, new_safe)
        normalized["project_name"] = new_safe
        archive_name = str(normalized.get("export", {}).get("archive_name") or "")
        old_default = self._default_archive_name(old_safe)
        if archive_name.lower() == old_default.lower():
            normalized["export"]["archive_name"] = self._default_archive_name(new_safe)

        old_dir.rename(new_dir)
        try:
            self._atomic_write_json(self._project_file(new_dir), normalized)
        except Exception:
            if new_dir.exists() and not old_dir.exists():
                new_dir.rename(old_dir)
            raise
        return self._success({"project_name": new_safe}, msg="炮镜项目已重命名")

    def delete_project(self, project_name: str) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        self._remove_project_tree(project_dir)
        return self._success({"project_name": safe_name}, msg="炮镜项目已删除")

    def open_project_folder(self, project_name: str) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        self._open_folder(project_dir)
        return self._success({"path": str(project_dir)})

    def open_export_folder(self) -> dict[str, Any]:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._open_folder(self.export_dir)
        return self._success({"path": str(self.export_dir)})

    def import_project(
        self,
        source_path: str | Path,
        project_name: str = "",
        defaults: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source = Path(str(source_path or "")).resolve()
        if not source.exists():
            return self._failure("导入来源不存在", code="source_not_found")
        if source.is_file() and source.suffix.lower() not in {".zip", ".blk"}:
            return self._failure("作者端炮镜项目只支持文件夹、ZIP 或单个 BLK", code="unsupported_source")
        if not source.is_dir() and not source.is_file():
            return self._failure("导入来源不是有效文件夹、ZIP 或 BLK", code="unsupported_source")

        derived_name = source.stem if source.is_file() else source.name
        safe_name = self._validate_project_name(project_name or derived_name)
        target_dir = self._project_dir(safe_name)
        if target_dir.exists():
            return self._failure("同名炮镜项目已存在", code="project_exists")

        temp_dir = self.library_dir / f".import_{uuid.uuid4().hex}"
        try:
            self._ensure_project_layout(temp_dir)
            if source.is_dir():
                source_kind = "folder"
                import_summary = self._copy_folder_source(source, temp_dir)
            elif source.suffix.lower() == ".zip":
                source_kind = "zip"
                import_summary = self._copy_zip_source(source, temp_dir)
            else:
                source_kind = "file"
                import_summary = self._copy_single_blk_source(source, temp_dir)
            project, scan, import_warnings = self._build_imported_project(
                temp_dir,
                safe_name,
                defaults or {},
            )
            self._apply_import_origin(project, temp_dir, source, source_kind)
            if scan["real_blk_count"] < 1:
                return self._failure(
                    "导入来源中没有真实 BLK 炮镜文件",
                    code="real_blk_missing",
                    warnings=import_warnings,
                )
            self._atomic_write_json(self._project_file(temp_dir), project)
            temp_dir.rename(target_dir)
        except Exception:
            self._remove_internal_temp_tree(temp_dir)
            raise
        finally:
            if temp_dir.exists():
                self._remove_internal_temp_tree(temp_dir)

        return self._success({
            "project_name": safe_name,
            "project": project,
            "scan": scan,
            "import_summary": import_summary,
            "cover_preview": self._cover_preview_data_url(target_dir, project),
        }, msg="炮镜项目已导入", warnings=import_warnings)

    def load_project(self, project_name: str) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        project_file = self._project_file(project_dir)
        if not project_file.is_file():
            return self._failure("炮镜项目描述不存在", code="project_not_found")
        raw = self._read_json(project_file)
        project = self._normalize_project(raw, safe_name)
        project, scan = self._merge_scan_into_project(project, project_dir)
        return self._success({
            "project_name": safe_name,
            "project": project,
            "scan": scan,
            "cover_preview": self._cover_preview_data_url(project_dir, project),
        })

    def save_project(self, project_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        project = self._normalize_project(payload or {}, safe_name)
        project, scan = self._merge_scan_into_project(project, project_dir)
        report = self._validate_model(project, project_dir, scan=scan)
        save_errors = [item for item in report["errors"] if item.get("code") in SAVE_BLOCKING_CODES]
        if save_errors:
            return self._failure(
                "项目结构存在阻断问题，未写入磁盘",
                code="project_save_blocked",
                errors=save_errors,
                warnings=report["warnings"],
                data={"project": project, "scan": scan, "report": report},
            )
        self._atomic_write_json(self._project_file(project_dir), project)
        return self._success({
            "project_name": safe_name,
            "project": project,
            "scan": scan,
            "report": report,
        }, msg="炮镜项目已保存", warnings=report["warnings"])

    def write_project_blk(
        self,
        project_name: str,
        payload: dict[str, Any],
        file_id: str,
        mode: str,
        destination_path: str | Path = "",
    ) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")

        project = self._normalize_project(payload or {}, safe_name)
        project, scan = self._merge_scan_into_project(project, project_dir)
        row = next(
            (
                item for item in project["files"]
                if str(item.get("file_id") or "") == str(file_id or "")
            ),
            None,
        )
        if row is None:
            return self._failure("没有找到要写入的炮镜文件", code="file_not_found")
        source_file = self._resolve_project_relative(
            project_dir,
            row.get("source_path"),
            require_exists=True,
        )
        if source_file is None or not source_file.is_file():
            return self._failure("作者工作副本不存在", code="source_file_missing")

        write_mode = str(mode or "").strip().lower()
        expected_body_sha256 = ""
        if write_mode == "save_original":
            origin_path = str(row.get("origin_path") or "").strip()
            if not origin_path:
                return self._failure(
                    "该文件不是从可覆写的单个 BLK 或文件夹导入，请使用另存为",
                    code="origin_path_missing",
                )
            write_source = Path(origin_path).resolve()
            destination = write_source
            expected_body_sha256 = str(row.get("origin_body_sha256") or "")
        elif write_mode == "save_as":
            destination_text = str(destination_path or "").strip()
            if not destination_text:
                return self._failure("请选择另存为路径", code="destination_required")
            destination = Path(destination_text).resolve()
            if destination.suffix.lower() != ".blk":
                return self._failure("另存为文件必须使用 .blk 扩展名", code="destination_not_blk")
            write_source = source_file
        else:
            return self._failure("不支持的写入方式", code="write_mode_invalid")

        embedded_meta = self._build_embedded_meta(project, row, self._file_body_sha256(write_source))
        try:
            result = write_embedded_metadata_file(
                write_source,
                embedded_meta,
                destination=destination,
                expected_body_sha256=expected_body_sha256,
            )
        except SightEmbeddedMetadataConflict:
            return self._failure(
                "原 BLK 主体已在外部发生变化，为避免覆盖已停止保存",
                code="origin_body_changed",
            )
        except (OSError, SightEmbeddedMetadataError, ValueError) as exc:
            return self._failure(str(exc), code="blk_write_failed")

        return self._success({
            "project_name": safe_name,
            "project": project,
            "scan": scan,
            "file_id": str(row.get("file_id") or ""),
            "mode": write_mode,
            "output_file": result["path"],
            "body_sha256": result["body_sha256"],
        }, msg="炮镜 BLK 已写入")
    def rescan_project(self, project_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        raw = payload if isinstance(payload, dict) else self._read_json(self._project_file(project_dir))
        project = self._normalize_project(raw, safe_name)
        project, scan = self._merge_scan_into_project(project, project_dir)
        return self._success({
            "project_name": safe_name,
            "project": project,
            "scan": scan,
        }, msg="项目文件状态已重新扫描")

    def analyze_files(
        self,
        project_name: str,
        output_paths: list[str] | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        raw = payload if isinstance(payload, dict) else self._read_json(self._project_file(project_dir))
        project = self._normalize_project(raw, safe_name)
        requested = {
            str(value or "").replace("\\", "/").strip().lower()
            for value in (output_paths or [])
            if str(value or "").strip()
        }
        analyze_all = not requested
        cache = dict(project.get("analysis_cache") or {})
        results: dict[str, dict[str, Any]] = {}
        for item in project["files"]:
            if not item.get("include", True):
                continue
            output_path = str(item.get("output_path") or "")
            if not analyze_all and output_path.lower() not in requested:
                continue
            source_file = self._resolve_project_relative(project_dir, item.get("source_path"), require_exists=True)
            if source_file is None or source_file.suffix.lower() != ".blk":
                results[output_path] = {"error": "源 BLK 不存在"}
                continue
            signature = self._file_signature(source_file)
            cached = cache.get(str(item.get("source_path") or ""))
            if (
                isinstance(cached, dict)
                and self._file_signatures_match(cached, signature)
                and isinstance(cached.get("result"), dict)
            ):
                result = deepcopy(cached["result"])
                result["cached"] = True
            else:
                result = self._blk_analyzer.analyze(source_file)
                result["cached"] = False
                cache[str(item.get("source_path") or "")] = {
                    **signature,
                    "result": deepcopy(result),
                }
            if result.get("confidence") not in {"high", "medium", "low"}:
                result["confidence"] = "low"
                result.setdefault("confidence_reasons", ["legacy_analysis_cache"])
            results[output_path] = result
        project["analysis_cache"] = cache
        has_low_confidence = any(
            result.get("confidence") == "low"
            for result in results.values()
            if isinstance(result, dict) and not result.get("error")
        )
        return self._success({
            "project": project,
            "results": results,
            "analyzed_count": len(results),
        }, warnings=[self._issue(
            "analysis_low_confidence",
            "部分 BLK 可识别特征不足，请由作者人工确认。",
        )] if has_low_confidence else [])

    def validate_project(self, project_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        project = self._normalize_project(payload or {}, safe_name)
        project, scan = self._merge_scan_into_project(project, project_dir)
        report = self._validate_model(project, project_dir, scan=scan)
        return self._success({
            "project": project,
            "scan": scan,
            "report": report,
        }, msg="兼容检查完成", warnings=report["warnings"], errors=report["errors"])

    def import_cover(self, project_name: str, source_path: str | Path) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        source = Path(str(source_path or "")).resolve()
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        if not source.is_file() or source.suffix.lower() not in ALLOWED_COVER_EXTENSIONS:
            return self._failure("请选择 PNG、JPG、JPEG 或 WEBP 图片", code="cover_invalid")

        asset_dir = project_dir / SOURCE_ASSET_DIR_NAME
        asset_dir.mkdir(parents=True, exist_ok=True)
        asset_id = uuid.uuid4().hex
        target = asset_dir / f"cover_{asset_id}{source.suffix.lower()}"
        temp_target = asset_dir / f".cover_{asset_id}{source.suffix.lower()}"
        shutil.copy2(source, temp_target)
        try:
            self._read_image_preview(temp_target, max_size=16)
            os.replace(str(temp_target), str(target))
        finally:
            if temp_target.exists():
                temp_target.unlink()
        cover = {
            "source_path": target.relative_to(project_dir).as_posix(),
            "output_name": "preview.webp",
        }
        return self._success({
            "cover": cover,
            "cover_preview": self._image_preview_data_url(target),
        }, msg="封面素材已复制到炮镜项目")


    def export_project_zip(self, project_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_name = self._validate_project_name(project_name)
        project_dir = self._project_dir(safe_name)
        if not project_dir.is_dir():
            return self._failure("炮镜项目不存在", code="project_not_found")
        project = self._normalize_project(payload or {}, safe_name)
        project, scan = self._merge_scan_into_project(project, project_dir)
        report = self._validate_model(project, project_dir, scan=scan)
        if report["errors"]:
            return self._failure(
                "兼容检查未通过，未生成 ZIP",
                code="export_validation_failed",
                errors=report["errors"],
                warnings=report["warnings"],
                data={"project": project, "scan": scan, "report": report},
            )

        archive_name = self._normalize_archive_name(project["export"].get("archive_name"), safe_name)
        output_path = self.export_dir / archive_name
        temp_zip = self.export_dir / f".{archive_name}.{uuid.uuid4().hex}.tmp"

        self.export_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".sight_build_", dir=self.workspace_dir) as temp_name:
            build_dir = Path(temp_name)
            try:
                for item in project["files"]:
                    if not item.get("include", True):
                        continue
                    source_file = self._resolve_project_relative(
                        project_dir,
                        item.get("source_path"),
                        require_exists=True,
                    )
                    output_rel = normalize_safe_relative_path(item.get("output_path"))
                    target_file = build_dir.joinpath(*PurePosixPath(output_rel).parts)
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    embedded_meta = self._build_embedded_meta(
                        project,
                        item,
                        self._file_body_sha256(source_file),
                    )
                    write_embedded_metadata_file(
                        source_file,
                        embedded_meta,
                        destination=target_file,
                    )

                cover_path = self._resolve_cover_path(project_dir, project)
                if cover_path.is_file():
                    self._write_cover_webp(cover_path, build_dir / "preview.webp")

                members = sorted(
                    [item for item in build_dir.rglob("*") if item.is_file()],
                    key=lambda item: item.relative_to(build_dir).as_posix().lower(),
                )
                with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for file_path in members:
                        zf.write(file_path, arcname=file_path.relative_to(build_dir).as_posix())
                self._validate_export_archive(
                    temp_zip,
                    expected_real_paths=[
                        str(item.get("output_path") or "")
                        for item in project["files"]
                        if item.get("include", True)
                    ],
                    expect_cover=cover_path.is_file(),
                )
                os.replace(str(temp_zip), str(output_path))
            finally:
                if temp_zip.exists():
                    temp_zip.unlink()

        return self._success({
            "project_name": safe_name,
            "output_file": str(output_path),
            "file_name": output_path.name,
            "report": report,
            "real_blk_count": report["summary"]["real_blk_count"],
            "derived_type": report["summary"]["display_type"],
        }, msg="炮镜 ZIP 已导出", warnings=report["warnings"])

    def _build_default_project(self, project_name: str, defaults: dict[str, Any]) -> dict[str, Any]:
        package_defaults = defaults.get("package") if isinstance(defaults.get("package"), dict) else defaults
        return self._normalize_project({
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_type": PROJECT_TYPE,
            "project_name": project_name,
            "package": {
                "package_name": project_name,
                "author": str(package_defaults.get("author") or ""),
                "version": "1.0.0",
                "description": "",
                "note": "",
                "tags": [],
                "recommended_vehicles": [],
                "recommended_apply_mode": "",
                "primary_vehicle_id": "",
                "compatible_vehicle_ids": [],
                "target_resolution": "",
                "target_resolutions": [],
                "sensitivity": "",
                "apply_correction_to_gun": None,
                "hover_text": {
                    "sight_type": "",
                    "gun_correction": "",
                    "target_resolution": "",
                },
                "link_video": "",
                "link_wtlive": str(package_defaults.get("link_wtlive") or ""),
                "link_bilibili": str(package_defaults.get("link_bilibili") or ""),
            },
            "files": [],
            "groups": [],
            "cover": {"source_path": "", "output_name": "preview.webp"},
            "export": {"archive_name": self._default_archive_name(project_name)},
            "extra_meta": {},
            "import_meta": {
                "source_path": "",
                "source_marker": "AIMERWT_SIGHT_META_V1",
                "source_meta_version": 1,
                "migration_required": False,
                "migration_confirmed": True,
            },
            "analysis_cache": {},
        }, project_name)

    def _normalize_project(self, payload: dict[str, Any], project_name: str) -> dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        package = self._normalize_package(data.get("package"))
        files = [
            self._normalize_file_row(item, index)
            for index, item in enumerate(data.get("files") or [], start=1)
            if isinstance(item, dict)
        ][:MAX_PROJECT_FILE_COUNT]
        groups = [
            self._normalize_group_row(item, index)
            for index, item in enumerate(data.get("groups") or [], start=1)
            if isinstance(item, dict)
        ]
        cover_raw = data.get("cover") if isinstance(data.get("cover"), dict) else {}
        export_raw = data.get("export") if isinstance(data.get("export"), dict) else {}
        import_raw = data.get("import_meta") if isinstance(data.get("import_meta"), dict) else {}
        source_origin_raw = (
            data.get("source_origin") if isinstance(data.get("source_origin"), dict) else {}
        )
        source_kind = str(source_origin_raw.get("kind") or "new").strip().lower()
        if source_kind not in {"new", "file", "folder", "zip"}:
            source_kind = "new"
        package_id = str(data.get("package_id") or uuid.uuid4().hex).strip()
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_type": str(data.get("project_type") or PROJECT_TYPE),
            "project_name": project_name,
            "package_id": package_id,
            "source_origin": {
                "kind": source_kind,
                "path": str(source_origin_raw.get("path") or "").strip(),
            },
            "package": package,
            "files": files,
            "groups": groups,
            "cover": {
                "source_path": self._soft_relative_path(cover_raw.get("source_path")),
                "output_name": "preview.webp",
            },
            "export": {
                "archive_name": str(
                    export_raw.get("archive_name") or self._default_archive_name(project_name)
                ).strip(),
            },
            "extra_meta": deepcopy(data.get("extra_meta")) if isinstance(data.get("extra_meta"), dict) else {},
            "import_meta": {
                "source_path": self._soft_relative_path(import_raw.get("source_path")),
                "source_marker": str(import_raw.get("source_marker") or "AIMERWT_SIGHT_META_V1"),
                "source_meta_version": import_raw.get("source_meta_version", 1),
                "migration_required": bool(import_raw.get("migration_required", False)),
                "migration_confirmed": bool(import_raw.get("migration_confirmed", True)),
            },
            "analysis_cache": deepcopy(data.get("analysis_cache"))
            if isinstance(data.get("analysis_cache"), dict)
            else {},
        }

    def _normalize_package(self, raw: Any) -> dict[str, Any]:
        data = raw if isinstance(raw, dict) else {}
        target_resolutions = self._normalize_resolution_list(data.get("target_resolutions"))
        target_resolution = self._normalize_resolution(data.get("target_resolution"))
        if target_resolution and target_resolution not in target_resolutions:
            target_resolutions.insert(0, target_resolution)
        if not target_resolution and target_resolutions:
            target_resolution = target_resolutions[0]

        hover_text = deepcopy(data.get("hover_text")) if isinstance(data.get("hover_text"), dict) else {}
        hover_text["sight_type"] = str(hover_text.get("sight_type") or "").strip()
        hover_text["gun_correction"] = str(
            hover_text.get("gun_correction")
            or hover_text.get("apply_correction_to_gun")
            or ""
        ).strip()
        hover_text["target_resolution"] = str(hover_text.get("target_resolution") or "").strip()
        sensitivity = deepcopy(data.get("sensitivity"))
        apply_correction_to_gun = self._normalize_optional_bool(data.get("apply_correction_to_gun"))
        if not isinstance(sensitivity, (str, dict)):
            sensitivity = str(sensitivity or "")
        recommendation = self._normalize_recommendation_fields(data, 12)
        return {
            "package_name": str(data.get("package_name") or "").strip(),
            "author": str(data.get("author") or "").strip(),
            "version": self._normalize_version(data.get("version")),
            "description": str(data.get("description") or "").strip(),
            "note": str(data.get("note") or data.get("author_note") or "").strip(),
            "tags": self._normalize_text_list(data.get("tags")),
            **recommendation,
            "target_resolution": target_resolution,
            "target_resolutions": target_resolutions,
            "sensitivity": sensitivity,
            "apply_correction_to_gun": apply_correction_to_gun,
            "hover_text": hover_text,
            "link_video": self._normalize_link(data.get("link_video")),
            "link_wtlive": self._normalize_link(data.get("link_wtlive")),
            "link_bilibili": self._normalize_link(data.get("link_bilibili")),
        }

    def _normalize_file_row(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        output_path = self._soft_relative_path(item.get("output_path") or item.get("path"))
        recommendation = self._normalize_recommendation_fields(item, 12)
        origin_body_sha256 = str(item.get("origin_body_sha256") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", origin_body_sha256):
            origin_body_sha256 = ""
        return {
            "file_id": str(item.get("file_id") or uuid.uuid4().hex).strip(),
            "source_path": self._soft_relative_path(item.get("source_path")),
            "origin_path": str(item.get("origin_path") or "").strip(),
            "origin_body_sha256": origin_body_sha256,
            "output_path": output_path,
            "display_name": str(item.get("display_name") or Path(output_path).stem or f"炮镜 {index}").strip(),
            "ammo_type": self._meta_parser.normalize_ammo_type(item.get("ammo_type")),
            **recommendation,
            "target_resolution": self._normalize_resolution(item.get("target_resolution")),
            "note": str(item.get("note") or "").strip(),
            "include": bool(item.get("include", True)),
            "missing_source": bool(item.get("missing_source", False)),
            "signature": deepcopy(item.get("signature")) if isinstance(item.get("signature"), dict) else {},
            "extra_meta": deepcopy(item.get("extra_meta")) if isinstance(item.get("extra_meta"), dict) else {},
        }

    def _normalize_group_row(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        raw_group_id = str(item.get("group_id") or "").strip()
        group_id = raw_group_id or self._normalize_group_id(item.get("name"), index)
        try:
            sort_order = int(item.get("sort_order"))
        except (TypeError, ValueError):
            sort_order = index * 100
        recommendation = self._normalize_recommendation_fields(item, 12)
        return {
            "group_id": group_id[:48],
            "name": str(item.get("name") or f"分组 {index}").strip()[:40],
            "description": str(item.get("description") or "").strip()[:160],
            "ammo_types": [
                value
                for value in (
                    self._meta_parser.normalize_ammo_type(item)
                    for item in self._normalize_text_list(item.get("ammo_types"), 24)
                )
                if value
            ],
            **recommendation,
            "target_resolutions": self._normalize_resolution_list(item.get("target_resolutions"), 12),
            "platforms": self._normalize_text_list(item.get("platforms"), 12),
            "tags": self._normalize_text_list(item.get("tags"), 12),
            "featured": bool(item.get("featured", False)),
            "sort_order": sort_order,
            "files": [self._soft_relative_path(value) for value in self._normalize_text_list(item.get("files"))],
            "extra_meta": deepcopy(item.get("extra_meta")) if isinstance(item.get("extra_meta"), dict) else {},
        }

    def _build_imported_project(
        self,
        project_dir: Path,
        project_name: str,
        defaults: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        project = self._build_default_project(project_name, defaults)
        disk_state = self._scan_project_files(project_dir)
        warnings: list[dict[str, Any]] = []
        parsed_meta: dict[str, Any] | None = None
        parsed_meta_path = ""
        parse_warnings: list[str] = []
        source_root = project_dir / SOURCE_DIR_NAME

        embedded_records: list[dict[str, Any]] = []
        for real_rel in disk_state["real_files"]:
            real_file = project_dir.joinpath(*PurePosixPath(real_rel).parts)
            parsed = self._meta_parser.parse_embedded_meta_file(real_file, package_root=source_root)
            if parsed.get("parsed") and isinstance(parsed.get("meta"), dict):
                embedded_records.append(parsed["meta"])
                parse_warnings.extend(parsed.get("warnings") or [])
        if embedded_records:
            merged_embedded = self._meta_parser.merge_embedded_records(embedded_records)
            if merged_embedded.get("parsed") and isinstance(merged_embedded.get("meta"), dict):
                parsed_meta = merged_embedded["meta"]
                parse_warnings.extend(merged_embedded.get("warnings") or [])
            else:
                warnings.append(self._issue(
                    "embedded_meta_conflict",
                    "真实 BLK 中的 V2 元数据无法聚合为同一炮镜包。",
                    error=str(merged_embedded.get("error") or ""),
                ))

        if parsed_meta is None:
            for meta_rel in disk_state["meta_files"]:
                meta_file = project_dir.joinpath(*PurePosixPath(meta_rel).parts)
                parsed = self._meta_parser.parse_meta_file(meta_file, package_root=source_root)
                if parsed.get("parsed") and isinstance(parsed.get("meta"), dict):
                    if parsed_meta is None:
                        parsed_meta = parsed["meta"]
                        parsed_meta_path = meta_rel
                        parse_warnings = list(parsed.get("warnings") or [])
                    else:
                        warnings.append(self._issue(
                            "meta_file_conflict",
                            f"导入来源包含多个可解析伪 BLK：{meta_rel}",
                            path=meta_rel,
                        ))

        if parsed_meta is not None:
            project = self._project_from_public_meta(
                project,
                parsed_meta,
                parsed_meta_path,
                parse_warnings,
                disk_state["real_files"],
            )
        project, scan = self._merge_scan_into_project(project, project_dir)
        cover_path = self._find_managed_cover_path(project_dir)
        if cover_path.is_file():
            project["cover"] = {
                "source_path": cover_path.relative_to(project_dir).as_posix(),
                "output_name": "preview.webp",
            }
        if parsed_meta is not None:
            matched_count = sum(
                1 for item in project["files"]
                if item.get("source_path") and not item.get("missing_source")
            )
            scan["meta_matched_file_count"] = matched_count
        for warning in parse_warnings:
            warnings.append(self._issue("meta_parser_warning", warning))
        return project, scan, warnings

    def _project_from_public_meta(
        self,
        project: dict[str, Any],
        meta: dict[str, Any],
        meta_source_path: str,
        parser_warnings: list[str],
        real_source_paths: list[str],
    ) -> dict[str, Any]:
        package = {key: deepcopy(meta.get(key)) for key in PACKAGE_KEYS if key in meta}
        if "note" not in package and "author_note" in meta:
            package["note"] = meta.get("author_note")
        project["package"] = self._normalize_package(package)
        project["package_id"] = str(meta.get("package_id") or project.get("package_id") or uuid.uuid4().hex)
        project["extra_meta"] = {
            key: deepcopy(value)
            for key, value in meta.items()
            if key not in PUBLIC_TOP_LEVEL_KEYS
        }
        is_embedded_v2 = meta.get("meta_version") == 2 and bool(meta.get("package_id"))
        migration_required = False if is_embedded_v2 else self._meta_requires_migration(meta, parser_warnings)
        project["import_meta"] = {
            "source_path": meta_source_path,
            "source_marker": "AIMERWT_SIGHT_EMBED_V2"
            if is_embedded_v2
            else self._marker_from_warnings(parser_warnings),
            "source_meta_version": meta.get("meta_version"),
            "migration_required": migration_required,
            "migration_confirmed": not migration_required,
        }

        meta_files = meta.get("files") if isinstance(meta.get("files"), list) else []
        entry_by_path = {
            str(item.get("path") or "").replace("\\", "/").strip().lower(): item
            for item in meta_files
            if isinstance(item, dict) and str(item.get("path") or "").strip()
        }
        rows: list[dict[str, Any]] = []
        matched_paths: set[str] = set()
        for source_path in real_source_paths:
            output_path = str(PurePosixPath(source_path).relative_to(SOURCE_DIR_NAME))
            entry = entry_by_path.get(output_path.lower(), {})
            if entry:
                matched_paths.add(output_path.lower())
            rows.append(self._normalize_file_row({
                "file_id": entry.get("file_id") if isinstance(entry, dict) else "",
                "source_path": source_path,
                "output_path": output_path,
                "display_name": entry.get("display_name") if isinstance(entry, dict) else Path(output_path).stem,
                "ammo_type": entry.get("ammo_type") if isinstance(entry, dict) else "",
                "recommended_vehicles": entry.get("recommended_vehicles") if isinstance(entry, dict) else [],
                "recommended_apply_mode": entry.get("recommended_apply_mode") if isinstance(entry, dict) else "",
                "primary_vehicle_id": entry.get("primary_vehicle_id") if isinstance(entry, dict) else "",
                "compatible_vehicle_ids": entry.get("compatible_vehicle_ids") if isinstance(entry, dict) else [],
                "target_resolution": entry.get("target_resolution") if isinstance(entry, dict) else "",
                "note": entry.get("note") if isinstance(entry, dict) else "",
                "extra_meta": {
                    key: deepcopy(value)
                    for key, value in entry.items()
                    if key not in FILE_META_KEYS
                } if isinstance(entry, dict) else {},
            }, len(rows) + 1))
        for entry in meta_files:
            if not isinstance(entry, dict):
                continue
            output_path = str(entry.get("path") or "").replace("\\", "/").strip()
            if not output_path or output_path.lower() in matched_paths:
                continue
            rows.append(self._normalize_file_row({
                "file_id": entry.get("file_id"),
                "source_path": "",
                "output_path": output_path,
                "display_name": entry.get("display_name"),
                "ammo_type": entry.get("ammo_type"),
                "recommended_vehicles": entry.get("recommended_vehicles"),
                "recommended_apply_mode": entry.get("recommended_apply_mode"),
                "primary_vehicle_id": entry.get("primary_vehicle_id"),
                "compatible_vehicle_ids": entry.get("compatible_vehicle_ids"),
                "target_resolution": entry.get("target_resolution"),
                "note": entry.get("note"),
                "missing_source": True,
                "extra_meta": {
                    key: deepcopy(value)
                    for key, value in entry.items()
                    if key not in FILE_META_KEYS
                },
            }, len(rows) + 1))
        project["files"] = rows

        groups = meta.get("groups") if isinstance(meta.get("groups"), list) else []
        project["groups"] = [
            self._normalize_group_row({
                **item,
                "extra_meta": {
                    key: deepcopy(value)
                    for key, value in item.items()
                    if key not in GROUP_META_KEYS
                },
            }, index)
            for index, item in enumerate(groups, start=1)
            if isinstance(item, dict)
        ]
        return project

    def _merge_scan_into_project(
        self,
        project: dict[str, Any],
        project_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        disk_state = self._scan_project_files(project_dir)
        current_rows = [
            self._normalize_file_row(item, index)
            for index, item in enumerate(project.get("files") or [], start=1)
            if isinstance(item, dict)
        ]
        rows_by_source = {
            str(item.get("source_path") or "").lower(): item
            for item in current_rows
            if str(item.get("source_path") or "")
        }
        rows_by_output = {
            str(item.get("output_path") or "").lower(): item
            for item in current_rows
            if str(item.get("output_path") or "")
        }
        merged: list[dict[str, Any]] = []
        seen_sources: set[str] = set()
        new_files: list[str] = []
        changed_files: list[str] = []
        cache = project.get("analysis_cache") if isinstance(project.get("analysis_cache"), dict) else {}

        for source_path in disk_state["real_files"]:
            output_default = str(PurePosixPath(source_path).relative_to(SOURCE_DIR_NAME))
            row = rows_by_source.get(source_path.lower()) or rows_by_output.get(output_default.lower())
            if row is None:
                row = self._normalize_file_row({
                    "source_path": source_path,
                    "output_path": output_default,
                    "display_name": Path(output_default).stem,
                }, len(merged) + 1)
                new_files.append(source_path)
            else:
                row = deepcopy(row)
                row["source_path"] = source_path
            source_file = project_dir.joinpath(*PurePosixPath(source_path).parts)
            signature = self._file_signature(source_file)
            old_signature = row.get("signature") if isinstance(row.get("signature"), dict) else {}
            if old_signature and not self._file_signatures_match(old_signature, signature):
                changed_files.append(source_path)
                cache.pop(source_path, None)
            row["signature"] = signature
            row["missing_source"] = False
            merged.append(row)
            seen_sources.add(source_path.lower())

        missing_files: list[str] = []
        for row in current_rows:
            source_path = str(row.get("source_path") or "")
            if source_path and source_path.lower() in seen_sources:
                continue
            missing_row = deepcopy(row)
            missing_row["missing_source"] = True
            merged.append(missing_row)
            if source_path:
                missing_files.append(source_path)

        merged.sort(key=lambda item: (
            not bool(item.get("include", True)),
            str(item.get("output_path") or "").lower(),
        ))
        project["files"] = merged[:MAX_PROJECT_FILE_COUNT]
        project["analysis_cache"] = cache
        scan = {
            "real_blk_count": len(disk_state["real_files"]),
            "meta_blk_count": len(disk_state["meta_files"]),
            "meta_files": disk_state["meta_files"],
            "new_files": new_files,
            "missing_files": missing_files,
            "changed_files": changed_files,
            "unmapped_files": [
                item["source_path"] for item in merged
                if item.get("source_path") and not item.get("output_path")
            ],
            "meta_matched_file_count": 0,
        }
        return project, scan

    def _scan_project_files(self, project_dir: Path) -> dict[str, Any]:
        source_root = project_dir / SOURCE_DIR_NAME
        real_files: list[str] = []
        meta_files: list[str] = []
        if not source_root.is_dir():
            return {"real_files": real_files, "meta_files": meta_files}
        candidates = sorted(source_root.rglob("*.blk"), key=lambda item: item.as_posix().lower())
        for file_path in candidates[:MAX_PROJECT_FILE_COUNT]:
            if not file_path.is_file() or file_path.is_symlink():
                continue
            project_rel = file_path.relative_to(project_dir).as_posix()
            if self._meta_parser.is_meta_file(file_path):
                meta_files.append(project_rel)
            else:
                real_files.append(project_rel)
        return {"real_files": real_files, "meta_files": meta_files}

    def _validate_model(
        self,
        project: dict[str, Any],
        project_dir: Path,
        scan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        info: list[dict[str, Any]] = []

        def add_error(code: str, message: str, **context: Any) -> None:
            errors.append(self._issue(code, message, **context))

        def add_warning(code: str, message: str, **context: Any) -> None:
            warnings.append(self._issue(code, message, **context))

        if project.get("schema_version") != PROJECT_SCHEMA_VERSION or project.get("project_type") != PROJECT_TYPE:
            add_error("project_schema_invalid", "项目描述不是当前支持的炮镜项目 schema。")

        package = project["package"]
        if not package.get("package_name"):
            add_error("package_name_required", "请填写作品名称。", field="package.package_name")
        if not package.get("author"):
            add_error("author_required", "请填写作者名称。", field="package.author")

        included = [item for item in project["files"] if item.get("include", True)]
        if not included:
            add_error("real_blk_missing", "项目至少需要一个进入发布包的真实 BLK。")

        output_paths: list[str] = []
        output_seen: dict[str, str] = {}
        valid_output_paths: list[str] = []
        package_size = 0
        for index, item in enumerate(included):
            source_path = str(item.get("source_path") or "")
            output_path = str(item.get("output_path") or "")
            source_file = self._resolve_project_relative(project_dir, source_path, require_exists=False)
            if source_file is None:
                add_error("unsafe_source_path", "源文件路径不在当前炮镜项目内。", index=index, path=source_path)
            elif not source_file.is_file():
                add_error("source_file_missing", "映射的源文件不存在。", index=index, path=source_path)
            elif source_file.suffix.lower() != ".blk":
                add_error("source_not_blk", "映射源文件不是 .blk。", index=index, path=source_path)
            else:
                try:
                    package_size += source_file.stat().st_size
                except OSError:
                    pass

            try:
                normalized_output = normalize_safe_relative_path(output_path)
            except ValueError as exc:
                add_error("unsafe_output_path", str(exc), index=index, path=output_path)
                continue
            if PurePosixPath(normalized_output).suffix.lower() != ".blk":
                add_error("source_not_blk", "导出路径必须以 .blk 结尾。", index=index, path=normalized_output)
            output_paths.append(normalized_output)
            valid_output_paths.append(normalized_output)
            key = normalized_output.lower()
            if key in output_seen:
                add_error(
                    "duplicate_output_path",
                    "多个源文件映射到同一 ZIP 路径。",
                    path=normalized_output,
                    first=output_seen[key],
                )
            else:
                output_seen[key] = source_path

        archive_stem = str(project.get("export", {}).get("archive_name") or "").strip()
        try:
            archive_name = self._normalize_archive_name(archive_stem, project["project_name"])
            archive_stem = Path(archive_name).stem
        except ValueError as exc:
            add_error("invalid_windows_path", str(exc), field="export.archive_name")
            archive_stem = project["project_name"]

        mapping = {
            "target_mode": "archive_folder",
            "target_dir": archive_stem,
            "entries": [],
        }
        if len(valid_output_paths) == len(included):
            try:
                mapping = build_archive_install_mapping(
                    valid_output_paths,
                    archive_stem,
                    requested_target_dir=TARGET_DIR_UNSET,
                )
            except ValueError as exc:
                add_error("invalid_windows_path", str(exc))
            target_seen: dict[str, str] = {}
            for entry in mapping["entries"]:
                target_rel = str(entry.get("target_relative_path") or "")
                key = target_rel.lower()
                if key in target_seen:
                    add_error(
                        "duplicate_install_path",
                        "不同导出文件最终映射到同一安装路径。",
                        path=target_rel,
                        first=target_seen[key],
                    )
                else:
                    target_seen[key] = str(entry.get("source_relative_path") or "")

        meta_files = self._scan_project_files(project_dir)["meta_files"]
        expected_source_meta = str(project.get("import_meta", {}).get("source_path") or "")
        unexpected_meta = [path for path in meta_files if path != expected_source_meta]
        if unexpected_meta:
            add_error(
                "meta_file_conflict",
                "项目源素材包含额外可识别伪 BLK。",
                files=unexpected_meta,
            )

        output_set = {path.lower() for path in valid_output_paths}
        group_ids: set[str] = set()
        sort_orders: set[int] = set()
        assigned_files: dict[str, str] = {}
        reserved_ids = {"__all__", "__ungrouped__"}
        for group in project["groups"]:
            group_id = str(group.get("group_id") or "")
            group_id_key = group_id.lower()
            if group_id_key in reserved_ids:
                add_error("group_id_reserved", "分组使用了客户端保留 ID。", group_id=group_id)
            if group_id_key in group_ids:
                add_error("group_id_duplicate", "分组 ID 必须唯一。", group_id=group_id)
            group_ids.add(group_id_key)
            sort_order = int(group.get("sort_order") or 0)
            if sort_order in sort_orders:
                add_error("group_sort_duplicate", "分组排序值必须唯一。", sort_order=sort_order)
            sort_orders.add(sort_order)
            for file_path in group.get("files") or []:
                key = str(file_path or "").lower()
                if key not in output_set:
                    add_error(
                        "group_file_missing",
                        "分组引用了不存在的导出路径。",
                        group_id=group_id,
                        path=file_path,
                    )
                    continue
                if key in assigned_files:
                    add_error(
                        "group_file_duplicate",
                        "同一 BLK 只能属于一个作者分组。",
                        path=file_path,
                        first_group=assigned_files[key],
                        second_group=group_id,
                    )
                else:
                    assigned_files[key] = group_id

        matched_meta_count = 0
        meta_bytes = 0
        embedded_records: list[dict[str, Any]] = []
        for item in included:
            try:
                output_path = normalize_safe_relative_path(item.get("output_path"))
            except ValueError:
                continue
            source_file = self._resolve_project_relative(
                project_dir,
                item.get("source_path"),
                require_exists=True,
            )
            body_digest = self._file_body_sha256(source_file) if source_file is not None else ""
            embedded_meta = self._build_embedded_meta(project, item, body_digest)
            try:
                generated = replace_embedded_metadata_bytes(b"", embedded_meta)
            except SightEmbeddedMetadataError as exc:
                add_error(
                    "meta_oversized",
                    "某个真实 BLK 的 V2 元数据无法生成。",
                    path=output_path,
                    detail=str(exc),
                )
                continue
            meta_bytes += len(generated)
            roundtrip = self._meta_parser.parse_embedded_meta_bytes(
                generated,
                relative_path=output_path,
                package_root=project_dir,
            )
            if not roundtrip.get("parsed") or not isinstance(roundtrip.get("meta"), dict):
                add_error(
                    "meta_roundtrip_failed",
                    "某个真实 BLK 的 V2 元数据无法被主程序解析器回读。",
                    path=output_path,
                    detail=roundtrip.get("error"),
                )
                continue
            embedded_records.append(roundtrip["meta"])

        if len(embedded_records) == len(valid_output_paths) and embedded_records:
            merged_meta = self._meta_parser.merge_embedded_records(embedded_records)
            if not merged_meta.get("parsed"):
                add_error(
                    "meta_roundtrip_failed",
                    "各真实 BLK 的 V2 元数据无法聚合为同一炮镜包。",
                    detail=merged_meta.get("error"),
                )
            else:
                matched_meta_count = len(merged_meta["meta"].get("files") or [])
                if matched_meta_count != len(valid_output_paths):
                    add_error(
                        "meta_file_unmatched",
                        "V2 元数据没有精确覆盖全部真实 BLK。",
                        matched=matched_meta_count,
                        expected=len(valid_output_paths),
                    )
        import_meta = project.get("import_meta") if isinstance(project.get("import_meta"), dict) else {}
        if import_meta.get("migration_required") and not import_meta.get("migration_confirmed"):
            add_error(
                "unsupported_meta_marker",
                "导入元数据不是可直接重新生成的 V1，请在高级设置中确认迁移。",
                marker=import_meta.get("source_marker"),
            )
            source_version = import_meta.get("source_meta_version")
            if not isinstance(source_version, int) or isinstance(source_version, bool):
                add_error(
                    "meta_version_type_invalid",
                    "导入元数据的 meta_version 不是整数 1。",
                    value=source_version,
                )

        cover_path = self._resolve_cover_path(project_dir, project)
        cover_source_bytes = 0
        if cover_path.is_file():
            try:
                cover_source_bytes = cover_path.stat().st_size
            except OSError:
                cover_source_bytes = 0
        if not cover_path.is_file():
            add_warning("cover_missing", "没有封面，客户端将使用默认图。")
        if not package.get("description"):
            add_warning("description_missing", "作品没有详细说明。")
        category_tags = {"historical", "competitive", "fun"}
        tags = {str(item).lower() for item in package.get("tags") or []}
        if not tags.intersection(category_tags):
            add_warning("category_tag_missing", "没有选择史实、竞技或娱乐主分类。")
            if tags:
                add_warning("custom_tag_only", "自定义标签不会进入客户端三类主筛选。")
        if not any(package.get(key) for key in ("link_video", "link_wtlive", "link_bilibili")):
            add_warning("link_missing", "没有填写视频、WT Live 或 Bilibili 链接。")
        if not package.get("target_resolutions"):
            add_warning("target_resolution_missing", "没有填写目标分辨率。")
        if not any((
            package.get("recommended_vehicles"),
            package.get("primary_vehicle_id"),
            package.get("compatible_vehicle_ids"),
            package.get("recommended_apply_mode") == "all_tanks",
        )):
            add_warning("recommended_vehicle_missing", "没有填写作品级推荐载具。")
        recommendation_entries = [("package", package, "")]
        recommendation_entries.extend(
            ("file", item, str(item.get("output_path") or ""))
            for item in included
        )
        recommendation_entries.extend(
            ("group", group, str(group.get("group_id") or ""))
            for group in project.get("groups") or []
        )
        for scope, entry, value in recommendation_entries:
            if entry.get("recommended_apply_mode") == "vehicles" and not entry.get("primary_vehicle_id"):
                add_warning(
                    "primary_vehicle_missing",
                    "推荐模式为指定车辆，但没有填写主要适配车辆；仍可保存和导出。",
                    scope=scope,
                    value=value,
                )
        canonical_ammo = self._meta_parser._canonical_ammo_ids
        changed_sources = {
            str(path or "").lower()
            for path in ((scan or {}).get("changed_files") or [])
        }
        analysis_cache = project.get("analysis_cache") if isinstance(project.get("analysis_cache"), dict) else {}
        analysis_rows: list[dict[str, Any]] = []
        for item in included:
            ammo_type = str(item.get("ammo_type") or "")
            output_path = str(item.get("output_path") or "")
            source_path = str(item.get("source_path") or "")
            if not ammo_type:
                add_warning("ammo_type_missing", "某个 BLK 没有弹种信息。", path=output_path)
            elif ammo_type not in canonical_ammo:
                add_warning("unknown_ammo_type", "弹种不是当前标准 ID。", path=output_path, value=ammo_type)
            if source_path.lower() in changed_sources:
                add_warning("blk_signature_changed", "源文件自上次扫描后发生变化，建议重新分析。", path=source_path)

            cached = analysis_cache.get(source_path)
            result = cached.get("result") if isinstance(cached, dict) else None
            if not isinstance(result, dict):
                continue
            analysis_row = {
                "output_path": output_path,
                "distance_correction": result.get("distance_correction"),
                "apply_correction_to_gun": result.get("apply_correction_to_gun"),
                "has_variable_range": bool(result.get("has_variable_range")),
                "range_min": result.get("range_min"),
                "range_max": result.get("range_max"),
                "suspected_mask": bool(result.get("suspected_mask")),
                "tail_comment_confidence": str(result.get("tail_comment_confidence") or "unknown"),
                "confidence": str(result.get("confidence") or "low"),
                "confidence_reasons": [
                    str(value)
                    for value in (result.get("confidence_reasons") or [])
                ],
            }
            analysis_rows.append(analysis_row)
            if analysis_row["suspected_mask"]:
                add_warning("suspected_mask", "自动分析发现疑似大尺寸遮罩，请作者人工确认。", path=output_path)
            if analysis_row["tail_comment_confidence"] == "source_hint":
                add_warning(
                    "source_hint_detected",
                    "BLK 尾部注释可能包含来源或作者提示，请核对授权与署名。",
                    path=output_path,
                    comment=result.get("tail_comment"),
                )

        if len(included) > 1:
            ungrouped = [
                path for path in valid_output_paths
                if path.lower() not in assigned_files
            ]
            if ungrouped:
                add_warning("file_ungrouped", "多文件包中存在未分组文件。", files=ungrouped)
        else:
            ungrouped = []
        if mapping["target_mode"] == "archive_folder":
            add_warning("archive_folder_mode", "最终安装路径会额外套用 ZIP 文件名目录。")
        elif mapping["target_mode"] == "single_folder":
            add_warning("ordinary_single_folder", "普通顶层目录会直接成为 UserSights 目录。")
        if project.get("extra_meta") or any(item.get("extra_meta") for item in project["files"]) or any(
            item.get("extra_meta") for item in project["groups"]
        ):
            add_warning("unknown_meta_preserved", "项目包含作者端不认识但会原样保留的公开字段。")
        if any(key in project.get("extra_meta", {}) for key in ("featured", "card_featured", "author_featured")):
            add_warning("top_level_featured_unsupported", "顶层精选字段只保留，不在首版作者端编辑。")
        if analysis_rows:
            info.append(self._issue(
                "analysis_heuristic",
                "BLK 自动分析仅作为作者填写参考，不会覆盖作者声明。",
            ))

        display_type = "single_sight" if len(included) == 1 else "sight_package"
        info.extend([
            self._issue("carrier_type", "官方导出载体为 ZIP 归档包。", value="archive_package"),
            self._issue("display_type", "安装后类型由真实 BLK 数量派生。", value=display_type),
            self._issue("target_mode", "已按主程序默认规则推导安装目标。", value=mapping["target_mode"]),
        ])
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": self._deduplicate_issues(warnings),
            "info": info,
            "summary": {
                "carrier_type": "archive_package",
                "display_type": display_type,
                "real_blk_count": len(included),
                "meta_blk_count": 0,
                "matched_meta_count": matched_meta_count,
                "target_mode": mapping["target_mode"],
                "target_dir": mapping["target_dir"],
                "install_entries": mapping["entries"],
                "group_count": len(project["groups"]),
                "ungrouped_count": len(ungrouped),
                "cover_output": "preview.webp" if cover_path.is_file() else "",
                "export_member_count": len(included) + (1 if cover_path.is_file() else 0),
                "estimated_source_bytes": package_size,
                "estimated_export_input_bytes": package_size + meta_bytes + cover_source_bytes,
                "meta_bytes": meta_bytes,
                "cover_source_bytes": cover_source_bytes,
                "unmatched_real_count": max(0, len(valid_output_paths) - matched_meta_count),
                "analyzed_file_count": len(analysis_rows),
                "analysis_results": analysis_rows[:100],
                "analysis_truncated": len(analysis_rows) > 100,
                "schema_version": project.get("schema_version"),
                "meta_version": PUBLIC_META_VERSION,
                "error_count": len(errors),
                "warning_count": len(self._deduplicate_issues(warnings)),
            },
        }

    def _build_public_meta(self, project: dict[str, Any]) -> dict[str, Any]:
        package = project["package"]
        meta = deepcopy(project.get("extra_meta") or {})
        meta["meta_version"] = PUBLIC_META_VERSION
        meta["package_id"] = str(project.get("package_id") or "")
        meta["package_name"] = str(package.get("package_name") or "")
        meta["author"] = str(package.get("author") or "")

        for key in (
            "version",
            "description",
            "note",
            "tags",
            "recommended_vehicles",
            "recommended_apply_mode",
            "primary_vehicle_id",
            "compatible_vehicle_ids",
            "target_resolution",
            "target_resolutions",
            "sensitivity",
            "apply_correction_to_gun",
            "link_video",
            "link_wtlive",
            "link_bilibili",
        ):
            value = deepcopy(package.get(key))
            if self._has_public_value(value):
                meta[key] = value
            else:
                meta.pop(key, None)

        hover_text = deepcopy(package.get("hover_text") or {})
        hover_text.pop("apply_correction_to_gun", None)
        hover_text = {
            key: value for key, value in hover_text.items()
            if self._has_public_value(value)
        }
        if hover_text:
            meta["hover_text"] = hover_text
        else:
            meta.pop("hover_text", None)

        public_files: list[dict[str, Any]] = []
        for item in project["files"]:
            if not item.get("include", True):
                continue
            row = deepcopy(item.get("extra_meta") or {})
            row["file_id"] = str(item.get("file_id") or "")
            row["path"] = str(item.get("output_path") or "").replace("\\", "/")
            for key in (
                "display_name",
                "ammo_type",
                "recommended_vehicles",
                "recommended_apply_mode",
                "primary_vehicle_id",
                "compatible_vehicle_ids",
                "target_resolution",
                "note",
            ):
                value = deepcopy(item.get(key))
                if self._has_public_value(value):
                    row[key] = value
                else:
                    row.pop(key, None)
            public_files.append(row)
        meta["files"] = public_files

        public_groups: list[dict[str, Any]] = []
        for group in project["groups"]:
            row = deepcopy(group.get("extra_meta") or {})
            for key in (
                "group_id",
                "name",
                "description",
                "ammo_types",
                "recommended_vehicles",
                "recommended_apply_mode",
                "primary_vehicle_id",
                "compatible_vehicle_ids",
                "target_resolutions",
                "platforms",
                "tags",
                "featured",
                "sort_order",
                "files",
            ):
                value = deepcopy(group.get(key))
                if key in {"featured", "sort_order"} or self._has_public_value(value):
                    row[key] = value
                else:
                    row.pop(key, None)
            public_groups.append(row)
        if public_groups:
            meta["groups"] = public_groups
        else:
            meta.pop("groups", None)
        return meta

    def _build_embedded_meta(
        self,
        project: dict[str, Any],
        file_row: dict[str, Any],
        body_sha256_value: str = "",
    ) -> dict[str, Any]:
        public_meta = self._build_public_meta(project)
        package_meta = {
            key: deepcopy(value)
            for key, value in public_meta.items()
            if key not in {"meta_version", "package_id", "files", "groups"}
        }
        file_id = str(file_row.get("file_id") or "")
        public_file = next(
            (
                deepcopy(item)
                for item in public_meta.get("files") or []
                if isinstance(item, dict) and str(item.get("file_id") or "") == file_id
            ),
            {"file_id": file_id},
        )
        public_file.pop("path", None)
        body_digest = str(body_sha256_value or "").strip().lower()
        if body_digest:
            public_file["body_sha256"] = body_digest

        embedded_meta: dict[str, Any] = {
            "meta_version": 2,
            "package_id": str(project.get("package_id") or ""),
            "package": package_meta,
            "file": public_file,
        }
        output_path = str(file_row.get("output_path") or "").replace("\\", "/").lower()
        source_group = next(
            (
                group for group in project.get("groups") or []
                if any(
                    str(path or "").replace("\\", "/").lower() == output_path
                    for path in group.get("files") or []
                )
            ),
            None,
        )
        if isinstance(source_group, dict):
            group_id = str(source_group.get("group_id") or "")
            public_group = next(
                (
                    deepcopy(item)
                    for item in public_meta.get("groups") or []
                    if isinstance(item, dict) and str(item.get("group_id") or "") == group_id
                ),
                None,
            )
            if isinstance(public_group, dict):
                public_group.pop("files", None)
                embedded_meta["group"] = public_group
        return embedded_meta
    def _serialize_public_meta(self, meta: dict[str, Any]) -> str:
        json_text = json.dumps(meta, ensure_ascii=False, indent=2)
        return (
            "/* AIMERWT_SIGHT_META_V1\n"
            f"{json_text}\n"
            "AIMERWT_SIGHT_META_END */\n"
        )

    def _parse_generated_meta(self, project_dir: Path, meta_text: str) -> dict[str, Any]:
        temp_dir = project_dir / AUTHOR_DIR_NAME
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f".meta_roundtrip_{uuid.uuid4().hex}.blk"
        try:
            temp_path.write_text(meta_text, encoding="utf-8")
            return self._meta_parser.parse_meta_file(temp_path, package_root=project_dir)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _validate_export_archive(
        self,
        archive_path: Path,
        expected_real_paths: list[str],
        expect_cover: bool,
    ) -> None:
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = [
                str(info.filename or "").replace("\\", "/")
                for info in zf.infolist()
                if not info.is_dir()
            ]
            expected = {normalize_safe_relative_path(path) for path in expected_real_paths}
            actual_real: set[str] = set()
            embedded_records: list[dict[str, Any]] = []
            for name in names:
                if not is_archive_member_path_safe(name):
                    raise ValueError(f"导出 ZIP 包含不安全成员: {name}")
                suffix = PurePosixPath(name).suffix.lower()
                if suffix in BLOCKED_ARCHIVE_EXTENSIONS:
                    raise ValueError(f"导出 ZIP 包含禁止文件: {name}")
                if suffix != ".blk":
                    continue
                raw = zf.read(name)
                if self._meta_parser.detect_meta_marker_bytes(raw):
                    raise ValueError("V2 导出 ZIP 不得包含独立伪 BLK 元数据文件")
                actual_real.add(name)
                parsed = self._meta_parser.parse_embedded_meta_bytes(
                    raw,
                    relative_path=name,
                    package_root=Path("."),
                )
                if not parsed.get("parsed") or not isinstance(parsed.get("meta"), dict):
                    raise ValueError(f"导出 ZIP 的真实 BLK 缺少可回读 V2 元数据: {name}")
                embedded_records.append(parsed["meta"])

            if actual_real != expected:
                raise ValueError("导出 ZIP 的真实 BLK 成员与项目映射不一致")
            merged = self._meta_parser.merge_embedded_records(embedded_records)
            if not merged.get("parsed"):
                raise ValueError("导出 ZIP 的 V2 元数据无法聚合为同一炮镜包")
            if len(merged["meta"].get("files") or []) != len(expected):
                raise ValueError("导出 ZIP 的 V2 元数据没有覆盖全部真实 BLK")
            if expect_cover != ("preview.webp" in names):
                raise ValueError("导出 ZIP 封面成员与项目封面状态不一致")
    def _copy_single_blk_source(self, source: Path, project_dir: Path) -> dict[str, Any]:
        safe_name = normalize_safe_relative_path(source.name)
        target = project_dir / SOURCE_DIR_NAME / Path(*PurePosixPath(safe_name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return {
            "source_type": "file",
            "copied_blk_count": 1,
            "copied_asset_count": 0,
            "skipped_count": 0,
        }

    def _apply_import_origin(
        self,
        project: dict[str, Any],
        project_dir: Path,
        source: Path,
        source_kind: str,
    ) -> None:
        project["source_origin"] = {
            "kind": source_kind,
            "path": str(source.resolve()),
        }
        for row in project.get("files") or []:
            if not isinstance(row, dict):
                continue
            project_source = self._resolve_project_relative(
                project_dir,
                row.get("source_path"),
                require_exists=True,
            )
            if project_source is None or not project_source.is_file():
                continue
            origin_path = ""
            if source_kind == "file":
                origin_path = str(source.resolve())
            elif source_kind == "folder":
                source_rel = PurePosixPath(str(row.get("source_path") or ""))
                relative_parts = source_rel.parts[1:] if source_rel.parts[:1] == (SOURCE_DIR_NAME,) else ()
                candidate = source.joinpath(*relative_parts) if relative_parts else Path()
                if candidate.is_file():
                    origin_path = str(candidate.resolve())
            row["origin_path"] = origin_path
            row["origin_body_sha256"] = self._file_body_sha256(project_source)

    @staticmethod
    def _file_body_sha256(file_path: Path) -> str:
        body_size = file_path.stat().st_size
        try:
            embedded = parse_embedded_metadata_file(file_path)
            if embedded.get("parsed"):
                body_size = int(embedded.get("block_start", body_size))
        except (OSError, SightEmbeddedMetadataError, TypeError, ValueError):
            body_size = file_path.stat().st_size

        digest = hashlib.sha256()
        remaining = max(0, body_size)
        with file_path.open("rb") as handle:
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
        return digest.hexdigest()
    def _copy_folder_source(self, source: Path, project_dir: Path) -> dict[str, Any]:
        copied_blk = 0
        copied_assets = 0
        skipped = 0
        for file_path in sorted(source.rglob("*"), key=lambda item: item.as_posix().lower()):
            if file_path.is_symlink() or not file_path.is_file():
                continue
            rel = file_path.relative_to(source).as_posix()
            if any(part in {AUTHOR_DIR_NAME, ".git", "__pycache__"} for part in PurePosixPath(rel).parts):
                skipped += 1
                continue
            safe_rel = normalize_safe_relative_path(rel)
            suffix = file_path.suffix.lower()
            if suffix == ".blk":
                target = project_dir / SOURCE_DIR_NAME / Path(*PurePosixPath(safe_rel).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target)
                copied_blk += 1
            elif suffix in ALLOWED_COVER_EXTENSIONS and is_package_cover_asset_name(safe_rel):
                target = self._next_asset_path(project_dir / SOURCE_ASSET_DIR_NAME / Path(safe_rel).name)
                shutil.copy2(file_path, target)
                copied_assets += 1
            else:
                skipped += 1
        return {
            "source_type": "folder",
            "copied_blk_count": copied_blk,
            "copied_asset_count": copied_assets,
            "skipped_count": skipped,
        }

    def _copy_zip_source(self, source: Path, project_dir: Path) -> dict[str, Any]:
        copied_blk = 0
        copied_assets = 0
        skipped = 0
        with zipfile.ZipFile(source, "r") as zf:
            members = [item for item in zf.infolist() if not item.is_dir()]
            if len(members) > MAX_IMPORT_MEMBER_COUNT:
                raise ValueError("ZIP 成员数量超过作者端安全上限")
            total_size = sum(max(0, int(item.file_size)) for item in members)
            if total_size > MAX_IMPORT_UNCOMPRESSED_BYTES:
                raise ValueError("ZIP 解压后体积超过作者端安全上限")

            for member in members:
                name = str(member.filename or "").replace("\\", "/").strip()
                if not name or "__MACOSX" in name or "desktop.ini" in name.lower():
                    skipped += 1
                    continue
                if not is_archive_member_path_safe(name):
                    raise ValueError(f"ZIP 包含不安全路径: {name}")
                if self._zip_info_is_symlink(member):
                    raise ValueError(f"ZIP 包含符号链接: {name}")
                safe_rel = normalize_safe_relative_path(name)
                suffix = PurePosixPath(safe_rel).suffix.lower()
                if suffix in BLOCKED_ARCHIVE_EXTENSIONS:
                    raise ValueError(f"ZIP 包含禁止文件类型: {name}")
                if suffix == ".blk":
                    target = project_dir / SOURCE_DIR_NAME / Path(*PurePosixPath(safe_rel).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                    copied_blk += 1
                elif suffix in ALLOWED_COVER_EXTENSIONS and is_package_cover_asset_name(safe_rel):
                    target = self._next_asset_path(project_dir / SOURCE_ASSET_DIR_NAME / PurePosixPath(safe_rel).name)
                    with zf.open(member, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                    copied_assets += 1
                else:
                    skipped += 1
        return {
            "source_type": "zip",
            "copied_blk_count": copied_blk,
            "copied_asset_count": copied_assets,
            "skipped_count": skipped,
            "uncompressed_bytes": total_size,
        }

    def _resolve_cover_path(self, project_dir: Path, project: dict[str, Any]) -> Path:
        cover = project.get("cover") if isinstance(project.get("cover"), dict) else {}
        source_path = str(cover.get("source_path") or "")
        if not source_path:
            return Path()
        resolved = self._resolve_project_relative(project_dir, source_path, require_exists=False)
        if resolved is not None and resolved.is_file() and resolved.suffix.lower() in ALLOWED_COVER_EXTENSIONS:
            return resolved
        return Path()

    def _find_managed_cover_path(self, project_dir: Path) -> Path:
        asset_dir = project_dir / SOURCE_ASSET_DIR_NAME
        if not asset_dir.is_dir():
            return Path()
        candidates = sorted(
            [
                item for item in asset_dir.iterdir()
                if item.is_file() and item.suffix.lower() in ALLOWED_COVER_EXTENSIONS
            ],
            key=lambda item: (
                0 if item.stem.lower().startswith("preview") else 1,
                item.name.lower(),
            ),
        )
        return candidates[0] if candidates else Path()

    def _cover_preview_data_url(self, project_dir: Path, project: dict[str, Any]) -> str:
        cover_path = self._resolve_cover_path(project_dir, project)
        return self._image_preview_data_url(cover_path) if cover_path.is_file() else ""

    def _image_preview_data_url(self, image_path: Path) -> str:
        try:
            raw, mime = self._read_image_preview(image_path, max_size=420)
            return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        except Exception:
            return ""

    def _read_image_preview(self, image_path: Path, max_size: int) -> tuple[bytes, str]:
        from PIL import Image

        with Image.open(image_path) as image:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"}:
                output = image.convert("RGBA")
                fmt = "PNG"
                mime = "image/png"
            else:
                output = image.convert("RGB")
                fmt = "JPEG"
                mime = "image/jpeg"
            buffer = io.BytesIO()
            output.save(buffer, format=fmt, quality=84)
        return buffer.getvalue(), mime

    def _write_cover_webp(self, source_path: Path, target_path: Path) -> None:
        from PIL import Image

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path) as image:
            if image.mode in {"P", "PA"}:
                image = image.convert("RGBA")
            elif image.mode not in {"RGB", "RGBA", "L", "LA"}:
                image = image.convert("RGBA")
            image.save(target_path, format="WEBP", quality=88, method=6)

    def _resolve_project_relative(
        self,
        project_dir: Path,
        rel_path: Any,
        require_exists: bool,
    ) -> Path | None:
        raw = self._soft_relative_path(rel_path)
        if not raw:
            return None
        try:
            normalized = normalize_safe_relative_path(raw)
        except ValueError:
            return None
        base = project_dir.resolve()
        target = project_dir.joinpath(*PurePosixPath(normalized).parts).resolve(strict=False)
        if target != base and base not in target.parents:
            return None
        if require_exists and not target.is_file():
            return None
        return target

    def _validate_project_name(self, name: Any) -> str:
        value = str(name or "").strip()
        if not value:
            raise ValueError("项目名称不能为空")
        if value in {".", ".."} or Path(value).name != value:
            raise ValueError("项目名称必须是单层目录名")
        if any(char in value for char in '\\/:*?"<>|') or re.search(r"[\x00-\x1f]", value):
            raise ValueError("项目名称包含 Windows 非法字符")
        if is_unsafe_windows_path_part(value):
            raise ValueError("项目名称使用了 Windows 非法名称")
        return value

    def _project_dir(self, project_name: str) -> Path:
        base = self.library_dir.resolve()
        target = (self.library_dir / project_name).resolve(strict=False)
        if target == base or base not in target.parents:
            raise ValueError("炮镜项目路径不在炮镜库内")
        return target

    def _project_file(self, project_dir: Path) -> Path:
        return project_dir / AUTHOR_DIR_NAME / PROJECT_FILE_NAME

    def _ensure_project_layout(self, project_dir: Path) -> None:
        project_dir.mkdir(parents=True, exist_ok=False)
        (project_dir / SOURCE_DIR_NAME).mkdir(parents=True, exist_ok=True)
        (project_dir / SOURCE_ASSET_DIR_NAME).mkdir(parents=True, exist_ok=True)
        (project_dir / AUTHOR_DIR_NAME).mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, file_path: Path, payload: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=file_path.parent,
                prefix=f".{file_path.name}.",
                suffix=".tmp",
                delete=False,
                newline="\n",
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                temp_file.write("\n")
                temp_path = Path(temp_file.name)
            os.replace(str(temp_path), str(file_path))
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        raw = file_path.read_bytes()
        for encoding in ("utf-8-sig", "gb18030", "latin-1"):
            try:
                parsed = json.loads(raw.decode(encoding))
                if isinstance(parsed, dict):
                    return parsed
                raise ValueError("项目描述根节点必须是对象")
            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError as exc:
                raise ValueError(f"项目描述 JSON 无效: {exc}") from exc
        raise ValueError("项目描述编码无法识别")

    def _remove_project_tree(self, project_dir: Path, allow_missing: bool = False) -> None:
        base = self.library_dir.resolve()
        target = project_dir.resolve(strict=False)
        if target == base or base not in target.parents or target.parent != base:
            raise ValueError("拒绝删除炮镜库边界外的目录")
        if not target.exists():
            if allow_missing:
                return
            raise FileNotFoundError(target)
        self._clear_readonly_tree(target)
        shutil.rmtree(target)

    def _remove_internal_temp_tree(self, temp_dir: Path) -> None:
        base = self.library_dir.resolve()
        target = temp_dir.resolve(strict=False)
        if target.parent != base or not target.name.startswith(".import_"):
            raise ValueError("拒绝清理非本次导入临时目录")
        if target.exists():
            self._clear_readonly_tree(target)
            shutil.rmtree(target)

    def _clear_readonly_tree(self, target: Path) -> None:
        for item in [target, *target.rglob("*")]:
            try:
                mode = item.stat().st_mode
                if not mode & stat.S_IWRITE:
                    item.chmod(mode | stat.S_IWRITE)
            except OSError:
                continue

    def _open_folder(self, path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _normalize_archive_name(self, value: Any, project_name: str) -> str:
        raw = str(value or "").strip()
        name = re.sub(r"\.zip$", "", raw, flags=re.IGNORECASE).strip()
        if not name:
            name = re.sub(r"\.zip$", "", self._default_archive_name(project_name), flags=re.IGNORECASE)
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("导出文件名必须是单层文件名")
        if any(char in name for char in '\\/:*?"<>|') or re.search(r"[\x00-\x1f]", name):
            raise ValueError("导出文件名包含 Windows 非法字符")
        if is_unsafe_windows_path_part(name):
            raise ValueError("导出文件名使用了 Windows 非法名称")
        return f"{name}.zip"

    def _public_meta_path(self, project: dict[str, Any]) -> str:
        package = project["package"]
        author_token = self._safe_file_token(package.get("author"), "author")
        project_token = self._safe_file_token(project.get("project_name"), "sight")
        return f"meta/aimerwt_{author_token}_{project_token}.blk"

    @staticmethod
    def _safe_file_token(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
        text = re.sub(r"[\s_]+", "_", text).strip(" ._")
        return (text[:48] or fallback)

    @staticmethod
    def _default_archive_name(project_name: str) -> str:
        return f"{project_name}_AimerWT.zip"

    @staticmethod
    def _soft_relative_path(value: Any) -> str:
        return str(value or "").replace("\\", "/").strip()

    @staticmethod
    def _normalize_text_list(value: Any, limit: int | None = None) -> list[str]:
        if isinstance(value, str):
            source = re.split(r"[,，、;；\n]+", value)
        elif isinstance(value, list):
            source = value
        else:
            source = []
        result: list[str] = []
        seen: set[str] = set()
        for item in source:
            text = str(item or "").strip()
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
            if limit is not None and len(result) >= limit:
                break
        return result

    def _normalize_recommendation_fields(
        self,
        data: dict[str, Any],
        legacy_limit: int,
    ) -> dict[str, Any]:
        mode = str(data.get("recommended_apply_mode") or "").strip().lower()
        if mode not in {"vehicles", "all_tanks"}:
            mode = ""

        primary_vehicle_id = ""
        raw_primary_vehicle_id = str(data.get("primary_vehicle_id") or "").strip()
        if raw_primary_vehicle_id:
            try:
                primary_vehicle_id = normalize_vehicle_id(raw_primary_vehicle_id)
            except ValueError:
                primary_vehicle_id = ""

        compatible_vehicle_ids: list[str] = []
        seen_vehicle_ids: set[str] = set()
        for raw_vehicle_id in self._normalize_text_list(
            data.get("compatible_vehicle_ids"),
            24,
        ):
            try:
                vehicle_id = normalize_vehicle_id(raw_vehicle_id)
            except ValueError:
                continue
            if vehicle_id == primary_vehicle_id or vehicle_id in seen_vehicle_ids:
                continue
            seen_vehicle_ids.add(vehicle_id)
            compatible_vehicle_ids.append(vehicle_id)

        if mode == "all_tanks":
            primary_vehicle_id = ""
            compatible_vehicle_ids = []
        elif not mode and (primary_vehicle_id or compatible_vehicle_ids):
            mode = "vehicles"

        return {
            "recommended_vehicles": self._normalize_text_list(
                data.get("recommended_vehicles"),
                legacy_limit,
            ),
            "recommended_apply_mode": mode,
            "primary_vehicle_id": primary_vehicle_id,
            "compatible_vehicle_ids": compatible_vehicle_ids,
        }

    def _normalize_resolution_list(self, value: Any, limit: int | None = None) -> list[str]:
        result = [
            self._normalize_resolution(item)
            for item in self._normalize_text_list(value)
        ]
        result = [item for item in result if item]
        deduplicated = list(dict.fromkeys(result))
        return deduplicated[:limit] if limit is not None else deduplicated

    @staticmethod
    def _normalize_resolution(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"\s*[×*x]\s*", "x", text)
        return re.sub(r"\s+", "", text)

    @staticmethod
    def _normalize_version(value: Any) -> str:
        text = str(value or "1.0.0").strip()
        return text[1:] if text.lower().startswith("v") else text

    @staticmethod
    def _normalize_link(value: Any) -> str:
        text = str(value or "").strip()
        return text if re.match(r"^https?://", text, re.IGNORECASE) else ""

    @staticmethod
    def _normalize_optional_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None

    @staticmethod
    def _normalize_group_id(value: Any, index: int) -> str:
        text = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", str(value or "").strip().lower())
        text = re.sub(r"_+", "_", text).strip("_-")
        return text[:48] or f"group_{index}"

    @staticmethod
    def _has_public_value(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return value is not None

    @staticmethod
    def _file_signature(file_path: Path) -> dict[str, int | str]:
        stat_result = file_path.stat()
        return {
            "size": int(stat_result.st_size),
            "mtime_ns": str(int(stat_result.st_mtime_ns)),
        }

    @staticmethod
    def _file_signatures_match(
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> bool:
        try:
            if int(first.get("size")) != int(second.get("size")):
                return False
            first_mtime = str(first.get("mtime_ns") or "").strip()
            second_mtime = str(second.get("mtime_ns") or "").strip()
            if not first_mtime or not second_mtime:
                return False
            if first_mtime == second_mtime:
                return True
            if isinstance(first.get("mtime_ns"), str) and isinstance(second.get("mtime_ns"), str):
                return False
            return abs(int(first_mtime) - int(second_mtime)) <= 1_000
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _marker_from_warnings(warnings: list[str]) -> str:
        for warning in warnings:
            if str(warning).startswith("unsupported_marker:"):
                return str(warning).split(":", 1)[1]
        return "AIMERWT_SIGHT_META_V1"

    @staticmethod
    def _meta_requires_migration(meta: dict[str, Any], warnings: list[str]) -> bool:
        version = meta.get("meta_version")
        return (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != PUBLIC_META_VERSION
            or any(str(item).startswith("unsupported_marker:") for item in warnings)
        )

    @staticmethod
    def _zip_info_is_symlink(info: zipfile.ZipInfo) -> bool:
        mode = (info.external_attr >> 16) & 0o170000
        return mode == stat.S_IFLNK

    @staticmethod
    def _next_asset_path(candidate: Path) -> Path:
        if not candidate.exists():
            return candidate
        index = 2
        while True:
            next_path = candidate.with_name(f"{candidate.stem}_{index}{candidate.suffix}")
            if not next_path.exists():
                return next_path
            index += 1

    @staticmethod
    def _empty_scan() -> dict[str, Any]:
        return {
            "real_blk_count": 0,
            "meta_blk_count": 0,
            "meta_files": [],
            "new_files": [],
            "missing_files": [],
            "changed_files": [],
            "unmapped_files": [],
            "meta_matched_file_count": 0,
        }

    @staticmethod
    def _issue(code: str, message: str, **context: Any) -> dict[str, Any]:
        result = {"code": code, "message": message}
        if context:
            result["context"] = context
        return result

    @staticmethod
    def _deduplicate_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in items:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _success(
        data: dict[str, Any] | None = None,
        msg: str = "",
        errors: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "msg": msg,
            "data": data or {},
            "errors": errors or [],
            "warnings": warnings or [],
        }

    @staticmethod
    def _failure(
        msg: str,
        code: str = "",
        data: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_errors = list(errors or [])
        if code and not normalized_errors:
            normalized_errors.append({"code": code, "message": msg})
        return {
            "success": False,
            "msg": msg,
            "data": data or {},
            "errors": normalized_errors,
            "warnings": warnings or [],
        }
