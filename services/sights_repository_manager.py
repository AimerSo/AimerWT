# -*- coding: utf-8 -*-
"""
炮镜资源库管理模组：维护 WT炮镜库 与 UserSights 安装清单之间的关系。

功能定位:
- 在 AimerWT 资源库中保存炮镜源资产。
- 将资源库中的纯游戏文件安装到当前 UserSights。
- 使用按 UID/路径分片的 JSON 安装清单记录文件归属与 fingerprint。

业务关联:
- 上游由 SightsManager 调用。
- 下游写入 UserSights，但只写入游戏实际读取的 .blk 文件。
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any

from services.resource_path_manager import DIR_SIGHTS_LIBRARY
from services.sight_blk_analyzer import SightBlkAnalyzer
from services.sight_deployment_rules import build_sight_deployment_preview
from services.sight_embedded_metadata import (
    SightEmbeddedMetadataError,
    parse_embedded_metadata_file,
)
from services.sight_package_rules import DETAIL_ASSET_NAMES, DETAIL_OUTPUT_NAME
from utils.logger import get_logger
from utils.utils import get_app_data_dir

log = get_logger(__name__)


class SightsRepositoryError(Exception):
    """炮镜资源库相关错误的基类。"""
    pass


def _locked_manifest_write(method):
    @wraps(method)
    def wrapper(self, resource_id: str, usersights_path: str | Path, *args, **kwargs):
        lock = self._get_manifest_lock(usersights_path)
        if not lock.acquire(blocking=False):
            return self._operation_busy_result(resource_id)
        try:
            return method(self, resource_id, usersights_path, *args, **kwargs)
        finally:
            lock.release()

    return wrapper


class JsonSightsManifestStore:
    """
    JSON 安装清单存储边界。

    功能定位:
    - 保持当前单文件 JSON 清单行为不变。
    - 将清单路径、legacy 查找、读取、备份查询和保存收口到可替换对象。
    """

    storage_kind = "json"

    def __init__(self, manager: "SightsRepositoryManager"):
        self.manager = manager

    def get_path(self, usersights_path: str | Path) -> Path:
        return self.manager.manifests_dir / f"{self.manager.get_manifest_id(usersights_path)}.json"

    def find_path(self, usersights_path: str | Path) -> Path:
        manifest_name = f"{self.manager.get_manifest_id(usersights_path)}.json"
        preferred_path = self.manager.manifests_dir / manifest_name
        if preferred_path.exists():
            return preferred_path
        legacy_path = self.manager.legacy_manifests_dir / manifest_name
        if legacy_path.exists():
            return legacy_path
        return preferred_path

    def backup_paths(self, usersights_path: str | Path, manifest_path: Path | None = None) -> list[Path]:
        path = manifest_path or self.find_path(usersights_path)
        candidates = [
            path.with_suffix(f"{path.suffix}.bak"),
            path.with_suffix(f"{path.suffix}.bak2"),
        ]
        return [candidate for candidate in candidates if candidate.exists()]

    def collect_metrics(self, usersights_path: str | Path) -> dict[str, Any]:
        path = self.get_path(usersights_path)
        backup_paths = self.backup_paths(usersights_path, manifest_path=path)
        backup_size = sum(item.stat().st_size for item in backup_paths)
        return {
            "storage_kind": self.storage_kind,
            "path": str(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "actual_backup_count": len(backup_paths),
            "actual_backup_size_bytes": backup_size,
            "actual_backup_paths": [str(item) for item in backup_paths],
        }

    def load(self, usersights_path: str | Path) -> dict[str, Any]:
        path = self.find_path(usersights_path)
        if not path.exists():
            return self.manager._empty_manifest(usersights_path)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"炮镜安装清单读取失败，使用空清单: {e}")
            return self.manager._corrupt_manifest_fallback(usersights_path, path, str(e))
        return self.manager._normalize_loaded_manifest(usersights_path, path, data)

    def save(self, usersights_path: str | Path, manifest: dict[str, Any]) -> None:
        self.manager._save_json_atomic(self.get_path(usersights_path), manifest)


class ShardedJsonSightsManifestStore:
    """
    分片 JSON 安装清单原型。

    功能定位:
    - 用于阶段 8 对照压测，不作为默认生产存储。
    - 验证 manifest store 契约能在不同物理落点之间保持稳定。
    """

    storage_kind = "sharded_json"

    def __init__(self, manager: "SightsRepositoryManager"):
        self.manager = manager

    def get_path(self, usersights_path: str | Path) -> Path:
        return self.manager.manifests_dir / f"{self.manager.get_manifest_id(usersights_path)}.manifest"

    def find_path(self, usersights_path: str | Path) -> Path:
        return self.get_path(usersights_path)

    def _backup_path(self, usersights_path: str | Path, index: int = 1) -> Path:
        path = self.get_path(usersights_path)
        suffix = f"{path.suffix}.bak" if index == 1 else f"{path.suffix}.bak{index}"
        return path.with_suffix(suffix)

    @staticmethod
    def _dir_size(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        if not path.exists():
            return 0
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total

    @staticmethod
    def _file_count(path: Path) -> int:
        if path.is_file():
            return 1
        if not path.exists():
            return 0
        return sum(1 for item in path.rglob("*") if item.is_file())

    def _shard_paths(self, path: Path) -> dict[str, Path]:
        return {
            "meta": path / "meta.json",
            "resources": path / "resources.json",
            "file_map": path / "file_map.json",
        }

    def backup_paths(self, usersights_path: str | Path, manifest_path: Path | None = None) -> list[Path]:
        path = manifest_path or self.get_path(usersights_path)
        candidates = [
            path.with_suffix(f"{path.suffix}.bak"),
            path.with_suffix(f"{path.suffix}.bak2"),
        ]
        return [candidate for candidate in candidates if candidate.exists()]

    def collect_metrics(self, usersights_path: str | Path) -> dict[str, Any]:
        path = self.get_path(usersights_path)
        backup_paths = self.backup_paths(usersights_path, manifest_path=path)
        backup_size = sum(self._dir_size(item) for item in backup_paths)
        return {
            "storage_kind": self.storage_kind,
            "path": str(path),
            "size_bytes": self._dir_size(path),
            "shard_count": self._file_count(path),
            "actual_backup_count": len(backup_paths),
            "actual_backup_size_bytes": backup_size,
            "actual_backup_paths": [str(item) for item in backup_paths],
        }

    def load(self, usersights_path: str | Path) -> dict[str, Any]:
        path = self.find_path(usersights_path)
        if not path.exists():
            return self.manager._empty_manifest(usersights_path)
        if not path.is_dir():
            return self.manager._corrupt_manifest_fallback(usersights_path, path, "sharded_manifest_not_directory")
        shards = self._shard_paths(path)
        try:
            with open(shards["meta"], "r", encoding="utf-8") as fh:
                data = json.load(fh)
            with open(shards["resources"], "r", encoding="utf-8") as fh:
                resources = json.load(fh)
            with open(shards["file_map"], "r", encoding="utf-8") as fh:
                file_map = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"炮镜分片安装清单读取失败，使用空清单: {e}")
            return self.manager._corrupt_manifest_fallback(usersights_path, path, str(e))
        if not isinstance(data, dict):
            return self.manager._corrupt_manifest_fallback(usersights_path, path, "sharded_manifest_meta_not_object")
        data["resources"] = resources if isinstance(resources, dict) else {}
        data["file_map"] = file_map if isinstance(file_map, dict) else {}
        return self.manager._normalize_loaded_manifest(usersights_path, path, data)

    def save(self, usersights_path: str | Path, manifest: dict[str, Any]) -> None:
        path = self.get_path(usersights_path)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        backup_path = self._backup_path(usersights_path, 1)
        backup_path_2 = self._backup_path(usersights_path, 2)
        if tmp_path.exists():
            shutil.rmtree(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)

        meta = dict(manifest)
        resources = meta.pop("resources", {})
        file_map = meta.pop("file_map", {})
        shards = self._shard_paths(tmp_path)
        for shard_path, data in (
            (shards["meta"], meta),
            (shards["resources"], resources if isinstance(resources, dict) else {}),
            (shards["file_map"], file_map if isinstance(file_map, dict) else {}),
        ):
            with open(shard_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)

        if path.exists():
            if backup_path_2.exists():
                shutil.rmtree(backup_path_2)
            if backup_path.exists():
                shutil.copytree(backup_path, backup_path_2)
                shutil.rmtree(backup_path)
            shutil.copytree(path, backup_path)
            shutil.rmtree(path)
        tmp_path.replace(path)


class SQLiteSightsManifestStore:
    """
    SQLite 安装清单原型。

    功能定位:
    - 用于阶段 8 存储层对照压测，不作为默认生产存储。
    - 以表结构保存资源、file_map 和 manifest 元信息，验证同一 store 契约可落到 SQLite。
    """

    storage_kind = "sqlite"

    def __init__(self, manager: "SightsRepositoryManager"):
        self.manager = manager

    def get_path(self, usersights_path: str | Path) -> Path:
        return self.manager.manifests_dir / f"{self.manager.get_manifest_id(usersights_path)}.sqlite"

    def find_path(self, usersights_path: str | Path) -> Path:
        return self.get_path(usersights_path)

    def backup_paths(self, usersights_path: str | Path, manifest_path: Path | None = None) -> list[Path]:
        path = manifest_path or self.get_path(usersights_path)
        candidates = [
            path.with_suffix(f"{path.suffix}.bak"),
            path.with_suffix(f"{path.suffix}.bak2"),
        ]
        return [candidate for candidate in candidates if candidate.exists()]

    def _ensure_schema(self, db: sqlite3.Connection) -> None:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS manifest_meta (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS resources (
                resource_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS file_map (
                target_relative_path TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            )
            """
        )

    def collect_metrics(self, usersights_path: str | Path) -> dict[str, Any]:
        path = self.get_path(usersights_path)
        backup_paths = self.backup_paths(usersights_path, manifest_path=path)
        metrics = {
            "storage_kind": self.storage_kind,
            "path": str(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "sqlite_table_count": 0,
            "resource_count": 0,
            "file_map_count": 0,
            "actual_backup_count": len(backup_paths),
            "actual_backup_size_bytes": sum(item.stat().st_size for item in backup_paths),
            "actual_backup_paths": [str(item) for item in backup_paths],
        }
        if not path.exists():
            return metrics
        db = sqlite3.connect(path)
        try:
            self._ensure_schema(db)
            metrics["sqlite_table_count"] = int(db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0])
            metrics["resource_count"] = int(db.execute("SELECT COUNT(*) FROM resources").fetchone()[0])
            metrics["file_map_count"] = int(db.execute("SELECT COUNT(*) FROM file_map").fetchone()[0])
        except sqlite3.Error:
            pass
        finally:
            db.close()
        return metrics

    def load(self, usersights_path: str | Path) -> dict[str, Any]:
        path = self.find_path(usersights_path)
        if not path.exists():
            return self.manager._empty_manifest(usersights_path)
        db = sqlite3.connect(path)
        try:
            self._ensure_schema(db)
            row = db.execute(
                "SELECT value_json FROM manifest_meta WHERE key = ?",
                ("meta",),
            ).fetchone()
            if not row:
                return self.manager._corrupt_manifest_fallback(usersights_path, path, "sqlite_manifest_meta_missing")
            data = json.loads(str(row[0]))
            resources = {
                str(resource_id): json.loads(str(payload))
                for resource_id, payload in db.execute("SELECT resource_id, payload_json FROM resources")
            }
            file_map = {
                str(target_path): json.loads(str(payload))
                for target_path, payload in db.execute("SELECT target_relative_path, payload_json FROM file_map")
            }
        except (json.JSONDecodeError, OSError, sqlite3.Error) as e:
            log.warning(f"炮镜 SQLite 安装清单读取失败，使用空清单: {e}")
            return self.manager._corrupt_manifest_fallback(usersights_path, path, str(e))
        finally:
            db.close()
        if not isinstance(data, dict):
            return self.manager._corrupt_manifest_fallback(usersights_path, path, "sqlite_manifest_meta_not_object")
        data["resources"] = resources
        data["file_map"] = file_map
        return self.manager._normalize_loaded_manifest(usersights_path, path, data)

    def save(self, usersights_path: str | Path, manifest: dict[str, Any]) -> None:
        path = self.get_path(usersights_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = path.with_suffix(f"{path.suffix}.bak")
        backup_path_2 = path.with_suffix(f"{path.suffix}.bak2")
        if path.exists():
            if backup_path_2.exists():
                backup_path_2.unlink()
            if backup_path.exists():
                shutil.copy2(backup_path, backup_path_2)
            shutil.copy2(path, backup_path)

        meta = dict(manifest)
        resources = meta.pop("resources", {})
        file_map = meta.pop("file_map", {})
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        if tmp_path.exists():
            tmp_path.unlink()
        db = sqlite3.connect(tmp_path)
        try:
            self._ensure_schema(db)
            with db:
                db.execute("DELETE FROM manifest_meta")
                db.execute("DELETE FROM resources")
                db.execute("DELETE FROM file_map")
                db.execute(
                    "INSERT INTO manifest_meta (key, value_json) VALUES (?, ?)",
                    ("meta", json.dumps(meta, ensure_ascii=False)),
                )
                db.executemany(
                    "INSERT INTO resources (resource_id, payload_json) VALUES (?, ?)",
                    [
                        (str(resource_id), json.dumps(payload, ensure_ascii=False))
                        for resource_id, payload in (resources.items() if isinstance(resources, dict) else [])
                    ],
                )
                db.executemany(
                    "INSERT INTO file_map (target_relative_path, payload_json) VALUES (?, ?)",
                    [
                        (str(target_path), json.dumps(payload, ensure_ascii=False))
                        for target_path, payload in (file_map.items() if isinstance(file_map, dict) else [])
                    ],
                )
        finally:
            db.close()
        tmp_path.replace(path)


class SightsRepositoryManager:
    """
    管理 WT炮镜库 的资源实体和当前 UID 的安装清单。
    """

    schema_version = 1
    windows_reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    preferred_subdirs = {
        "packages": "炮镜包",
        "singles": "单独炮镜",
        "manifests": "安装清单",
        "covers": "封面",
        "cache": "缓存",
    }
    legacy_subdirs = {
        "packages": "packages",
        "singles": "singles",
        "manifests": "manifests",
        "covers": "covers",
        "cache": "cache",
    }
    resource_subdirs = tuple(preferred_subdirs.values())
    cover_suffixes = (".jpg", ".jpeg", ".png", ".webp")

    def __init__(self, root_dir: str | Path | None = None, library_dir: str | Path | None = None):
        base_dir = Path(root_dir) if root_dir else get_app_data_dir()
        self.library_dir = Path(library_dir) if library_dir else base_dir / DIR_SIGHTS_LIBRARY
        self.packages_dir = self.library_dir / self.preferred_subdirs["packages"]
        self.singles_dir = self.library_dir / self.preferred_subdirs["singles"]
        self.manifests_dir = self.library_dir / self.preferred_subdirs["manifests"]
        self.covers_dir = self.library_dir / self.preferred_subdirs["covers"]
        self.cache_dir = self.library_dir / self.preferred_subdirs["cache"]
        self.legacy_packages_dir = self.library_dir / self.legacy_subdirs["packages"]
        self.legacy_singles_dir = self.library_dir / self.legacy_subdirs["singles"]
        self.legacy_manifests_dir = self.library_dir / self.legacy_subdirs["manifests"]
        self.legacy_covers_dir = self.library_dir / self.legacy_subdirs["covers"]
        self.legacy_cache_dir = self.library_dir / self.legacy_subdirs["cache"]
        self._manifest_locks: dict[str, threading.RLock] = {}
        self._manifest_locks_guard = threading.RLock()
        self._blk_analyzer = SightBlkAnalyzer()
        self.manifest_store = JsonSightsManifestStore(self)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for name in self.resource_subdirs:
            (self.library_dir / name).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now_iso() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())

    @staticmethod
    def _safe_id_part(value: str, fallback: str = "sight") -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9._-]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("._-")
        return text[:80] or fallback

    @staticmethod
    def _norm_path_key(path: Path) -> str:
        try:
            raw = str(path.resolve(strict=False))
        except Exception:
            raw = str(path)
        return os.path.normcase(os.path.normpath(raw))

    @staticmethod
    def _is_path_within(path: Path, root: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
            return True
        except (OSError, ValueError):
            return False

    @staticmethod
    def _posix_parts(relative_path: str) -> list[str]:
        normalized = str(relative_path or "").replace("\\", "/").strip()
        if normalized.startswith("//") or (len(normalized) > 1 and normalized[1] == ":"):
            raise ValueError("相对路径不合法")
        posix = PurePosixPath(normalized)
        if (
            posix.is_absolute()
            or any(part in {"", ".", ".."} for part in posix.parts)
            or any(":" in part for part in posix.parts)
        ):
            raise ValueError("相对路径不合法")
        return list(posix.parts)

    @classmethod
    def _normalize_target_relative_path(cls, target_dir: str, file_name: str) -> str:
        target = cls._normalize_single_target_dir(target_dir)
        name = Path(str(file_name or "").strip()).name
        if not target or not name:
            raise ValueError("炮镜目标路径不合法")
        return str(PurePosixPath(target) / name)

    @classmethod
    def _normalize_single_target_dir(cls, target_dir: str) -> str:
        raw_target = str(target_dir or "")
        target = raw_target.strip()
        if not target:
            raise ValueError("炮镜目标目录不合法")
        if raw_target != target:
            raise ValueError("炮镜目标目录包含非法首尾字符")
        normalized = target.replace("\\", "/")
        posix = PurePosixPath(normalized)
        if (
            target in {".", ".."}
            or "/" in normalized
            or posix.is_absolute()
            or any(part in {"", ".", ".."} for part in posix.parts)
            or any(":" in part for part in posix.parts)
            or re.search(r'[<>:"|?*\x00-\x1f]', target)
        ):
            raise ValueError("炮镜目标目录不合法")
        cls._validate_safe_path_parts([target])
        if Path(target).name != target:
            raise ValueError("炮镜目标目录不合法")
        return target

    @staticmethod
    def _disabled_relative_path(target_relative_path: str) -> str:
        normalized = str(target_relative_path or "").replace("\\", "/").strip("/")
        return f"{normalized}.AimerWT_BAN"

    @classmethod
    def _path_from_posix(cls, root: Path, relative_path: str) -> Path:
        result = root
        for part in cls._posix_parts(relative_path):
            result = result / part
        return result

    @classmethod
    def _light_fingerprint(cls, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    @classmethod
    def _full_fingerprint(cls, path: Path) -> dict[str, Any]:
        fingerprint = cls._light_fingerprint(path)
        digest = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        fingerprint["sha1"] = digest.hexdigest()
        return fingerprint

    @classmethod
    def _file_fingerprint(cls, path: Path) -> dict[str, Any]:
        return cls._full_fingerprint(path)

    @staticmethod
    def _same_fingerprint(first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool:
        if not first or not second:
            return False
        if first.get("sha1") and second.get("sha1"):
            return first.get("sha1") == second.get("sha1")
        return first.get("size") == second.get("size") and first.get("mtime_ns") == second.get("mtime_ns")

    @staticmethod
    def _is_file_locked_error(error: OSError) -> bool:
        return isinstance(error, PermissionError) or getattr(error, "winerror", None) in {5, 32}

    @staticmethod
    def _record_file_locked_conflict(
        conflicts: list[dict[str, str]],
        target_relative_path: str,
        entry: dict[str, Any],
        action: str = "",
    ) -> None:
        conflict = {"target_relative_path": target_relative_path, "reason": "file_locked"}
        if action:
            conflict["action"] = action
        conflicts.append(conflict)
        entry["file_status"] = "needs_attention"
        entry["conflict"] = True
        entry["conflict_reason"] = "file_locked"

    @classmethod
    def _normalize_target_filter(cls, target_relative_paths: list[str] | tuple[str, ...] | set[str] | None) -> set[str]:
        result: set[str] = set()
        for value in target_relative_paths or []:
            raw_value = str(value or "")
            if raw_value != raw_value.strip():
                raise ValueError("相对路径包含非法首尾字符")
            parts = cls._posix_parts(raw_value)
            cls._validate_safe_path_parts(parts)
            result.add(str(PurePosixPath(*parts)))
        return result

    @classmethod
    def _validate_safe_path_parts(cls, parts: list[str]) -> None:
        for part in parts:
            text = str(part or "")
            base_name = text.split(".", 1)[0].upper()
            if (
                text != text.strip()
                or text.endswith(".")
                or text.endswith(" ")
                or base_name in cls.windows_reserved_names
            ):
                raise ValueError("相对路径包含 Windows 非法名称")

    @classmethod
    def _resource_status_from_files(cls, files: list[dict[str, Any]], preferred_partial: str = "enabled") -> str:
        expected_count = len(files)
        enabled_count = 0
        disabled_count = 0
        attention_count = 0
        for entry in files:
            status = str(entry.get("file_status") or "").strip()
            if entry.get("conflict") or status in {"needs_attention", "conflict", "modified"}:
                attention_count += 1
            elif status == "enabled":
                enabled_count += 1
            elif status in {"disabled_by_rename", "disabled_shared"}:
                disabled_count += 1
        if attention_count:
            return "needs_attention"
        if expected_count and enabled_count == expected_count:
            return "enabled"
        if expected_count and disabled_count == expected_count:
            return "disabled_by_rename"
        if enabled_count and disabled_count:
            return "partial_disabled" if preferred_partial == "disabled" else "partial_enabled"
        if enabled_count:
            return "partial_enabled"
        if disabled_count:
            return "partial_disabled"
        return "disabled"

    def _allocate_resource_id(self, resource_type: str, base_id: str) -> str:
        base = self._safe_id_part(base_id)
        candidate = base
        index = 2
        roots = self._resource_roots(resource_type)
        while any((root / candidate).exists() for root in roots):
            candidate = f"{base}_{index}"
            index += 1
        return candidate

    def _resource_root(self, resource_type: str) -> Path:
        return self.singles_dir if resource_type == "single" else self.packages_dir

    def _resource_roots(self, resource_type: str) -> list[Path]:
        if resource_type == "single":
            roots = [self.singles_dir, self.legacy_singles_dir]
        else:
            roots = [self.packages_dir, self.legacy_packages_dir]
        unique_roots: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = self._norm_path_key(root)
            if key in seen:
                continue
            seen.add(key)
            unique_roots.append(root)
        return unique_roots

    @classmethod
    def _replace_path_with_retry(cls, source_path: Path, target_path: Path) -> None:
        retry_delays = (0.02, 0.04, 0.08, 0.12, 0.18, 0.25)
        for attempt in range(len(retry_delays) + 1):
            try:
                os.replace(source_path, target_path)
                return
            except OSError as error:
                if not cls._is_file_locked_error(error) or attempt >= len(retry_delays):
                    raise
                time.sleep(retry_delays[attempt])

    def _save_json_atomic(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
        )
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            if path.exists():
                backup_path = path.with_suffix(f"{path.suffix}.bak")
                backup_path_2 = path.with_suffix(f"{path.suffix}.bak2")
                if backup_path.exists():
                    shutil.copy2(backup_path, backup_path_2)
                shutil.copy2(path, backup_path)
            self._replace_path_with_retry(tmp_path, path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    log.warning("清理炮镜 JSON 临时文件失败: %s", tmp_path)

    def _get_manifest_lock(self, usersights_path: str | Path) -> threading.RLock:
        manifest_id = self.get_manifest_id(usersights_path)
        with self._manifest_locks_guard:
            lock = self._manifest_locks.get(manifest_id)
            if lock is None:
                lock = threading.RLock()
                self._manifest_locks[manifest_id] = lock
            return lock

    @staticmethod
    def _operation_busy_result(resource_id: str) -> dict[str, Any]:
        return {
            "success": False,
            "resource_id": resource_id,
            "conflict_count": 1,
            "conflicts": [{"target_relative_path": "", "reason": "operation_busy"}],
            "install_status": "needs_attention",
            "msg": "同一 UserSights 正在执行写任务，请稍后重试",
        }

    @classmethod
    def _normalize_adoption_target_relative_path(cls, target_relative_path: str) -> str:
        raw_path = str(target_relative_path or "")
        if raw_path != raw_path.strip():
            raise ValueError("炮镜目标路径包含非法首尾字符")
        parts = cls._posix_parts(raw_path)
        cls._validate_safe_path_parts(parts)
        normalized = str(PurePosixPath(*parts))
        if PurePosixPath(normalized).suffix.lower() != ".blk":
            raise ValueError("请选择有效的 .blk 炮镜文件")
        return normalized

    @staticmethod
    def _embedded_body_sha256(file_path: Path, block_start: int) -> str:
        digest = hashlib.sha256()
        remaining = max(0, int(block_start))
        with file_path.open("rb") as source:
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
        if remaining:
            raise OSError(f"炮镜主体读取不完整: {file_path}")
        return digest.hexdigest()

    def _read_embedded_sight_identity(self, file_path: Path) -> dict[str, Any]:
        try:
            parsed = parse_embedded_metadata_file(file_path)
        except (OSError, SightEmbeddedMetadataError):
            return {}
        if not parsed.get("parsed"):
            return {}

        meta = parsed.get("meta")
        file_meta = meta.get("file") if isinstance(meta, dict) else None
        package_id = str(meta.get("package_id") or "").strip() if isinstance(meta, dict) else ""
        file_id = str(file_meta.get("file_id") or "").strip() if isinstance(file_meta, dict) else ""
        if not package_id or not file_id:
            return {}

        actual_body_sha256 = self._embedded_body_sha256(
            file_path,
            int(parsed.get("block_start") or 0),
        )
        declared_body_sha256 = str(file_meta.get("body_sha256") or "").strip().lower()
        warnings: list[str] = []
        if declared_body_sha256 and declared_body_sha256 != actual_body_sha256:
            warnings.append("embedded_body_sha256_mismatch")
        return {
            "package_id": package_id,
            "file_id": file_id,
            "body_sha256": actual_body_sha256,
            "declared_body_sha256": declared_body_sha256,
            "warnings": warnings,
        }

    @staticmethod
    def _embedded_resource_identity_fields(
        identities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        valid = [
            identity
            for identity in identities
            if isinstance(identity, dict)
            and str(identity.get("package_id") or "").strip()
            and str(identity.get("file_id") or "").strip()
            and str(identity.get("body_sha256") or "").strip()
        ]
        if not valid:
            return {}

        package_ids = sorted({
            str(identity["package_id"]).strip()
            for identity in valid
        })
        file_ids = sorted({
            str(identity["file_id"]).strip()
            for identity in valid
        })
        fingerprints: dict[str, str] = {}
        warnings: list[str] = []
        for identity in valid:
            file_id = str(identity["file_id"]).strip()
            fingerprint = str(identity["body_sha256"]).strip().lower()
            current = fingerprints.get(file_id)
            if current and current != fingerprint:
                warnings.append(f"embedded_file_conflict:{file_id}")
                continue
            fingerprints[file_id] = fingerprint
            warnings.extend(identity.get("warnings") or [])
        if len(package_ids) > 1:
            warnings.append("multiple_embedded_packages")

        return {
            "sight_package_id": package_ids[0] if len(package_ids) == 1 else "",
            "sight_file_ids": file_ids,
            "sight_file_fingerprints": fingerprints,
            "metadata_source": "embedded_v2",
            "metadata_warnings": list(dict.fromkeys(
                str(item) for item in warnings if str(item)
            )),
        }

    @staticmethod
    def _apply_file_identity(
        file_entry: dict[str, Any],
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(file_entry)
        if identity:
            result["sight_file_id"] = str(identity.get("file_id") or "")
            result["sight_body_sha256"] = str(identity.get("body_sha256") or "")
        return result

    def _find_resource_by_embedded_identity(
        self,
        identity: dict[str, Any],
        resource_types: set[str],
    ) -> dict[str, Any] | None:
        package_id = str(identity.get("package_id") or "").strip()
        file_id = str(identity.get("file_id") or "").strip()
        fingerprint = str(identity.get("body_sha256") or "").strip().lower()
        if not package_id or not file_id or not fingerprint:
            return None

        roots = []
        if "single" in resource_types:
            roots.extend([self.singles_dir, self.legacy_singles_dir])
        if "package" in resource_types:
            roots.extend([self.packages_dir, self.legacy_packages_dir])
        seen: set[str] = set()
        for root in roots:
            root_key = self._norm_path_key(root)
            if root_key in seen or not root.exists() or not root.is_dir():
                continue
            seen.add(root_key)
            try:
                resource_dirs = sorted(
                    (path for path in root.iterdir() if path.is_dir()),
                    key=lambda path: path.name.lower(),
                )
            except OSError:
                continue
            for resource_dir in resource_dirs:
                try:
                    with (resource_dir / "package_index.json").open(
                        "r",
                        encoding="utf-8",
                    ) as source:
                        resource = json.load(source)
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(resource, dict):
                    continue
                if str(resource.get("resource_type") or "") not in resource_types:
                    continue
                if str(resource.get("sight_package_id") or "") != package_id:
                    continue
                fingerprints = resource.get("sight_file_fingerprints")
                if not isinstance(fingerprints, dict):
                    continue
                if str(fingerprints.get(file_id) or "").lower() != fingerprint:
                    continue
                matched_file = next(
                    (
                        entry
                        for entry in resource.get("files") or []
                        if isinstance(entry, dict)
                        and str(entry.get("sight_file_id") or "") == file_id
                        and str(entry.get("sight_body_sha256") or "").lower() == fingerprint
                    ),
                    None,
                )
                if matched_file is None:
                    continue
                return {
                    "resource_id": str(resource.get("resource_id") or resource_dir.name),
                    "resource_type": str(resource.get("resource_type") or ""),
                    "display_name": str(resource.get("display_name") or resource_dir.name),
                    "resource_path": str(resource_dir),
                    "files": [
                        entry
                        for entry in resource.get("files") or []
                        if isinstance(entry, dict)
                    ],
                    "matched_file": dict(matched_file),
                    "sight_package_id": package_id,
                    "sight_file_ids": list(resource.get("sight_file_ids") or []),
                    "sight_file_fingerprints": dict(fingerprints),
                    "metadata_source": str(resource.get("metadata_source") or ""),
                }
        return None

    def _refresh_single_resource_identity_match(
        self,
        matched: dict[str, Any],
        source: Path,
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        resource_id = str(matched["resource_id"])
        resource, resource_dir = self.load_resource(resource_id)
        matched_file = matched.get("matched_file")
        if not isinstance(matched_file, dict):
            return matched
        source_relative_path = str(matched_file.get("source_relative_path") or "")
        resource_file = self._path_from_posix(resource_dir, source_relative_path)
        resource_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, resource_file)
        fingerprint = self._file_fingerprint(resource_file)

        updated_files: list[dict[str, Any]] = []
        for entry in resource.get("files") or []:
            if not isinstance(entry, dict):
                continue
            updated = dict(entry)
            if str(entry.get("source_relative_path") or "") == source_relative_path:
                updated.update({
                    "size": fingerprint["size"],
                    "mtime_ns": fingerprint["mtime_ns"],
                    "sha1": fingerprint["sha1"],
                })
                updated = self._apply_file_identity(updated, identity)
            updated_files.append(updated)
        resource["files"] = updated_files
        resource.update(self._embedded_resource_identity_fields([identity]))
        resource["updated_at"] = self._now_iso()
        self._save_json_atomic(resource_dir / "resource.json", resource)
        self._save_json_atomic(resource_dir / "package_index.json", resource)
        refreshed = self._find_resource_by_embedded_identity(identity, {"single"})
        return refreshed or matched

    def _import_single_blk_target(
        self,
        source_path: str | Path,
        target_relative_path: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"炮镜文件不存在: {source}")
        target_relative_path = self._normalize_adoption_target_relative_path(target_relative_path)
        embedded_identity = self._read_embedded_sight_identity(source)
        if embedded_identity:
            matched = self._find_resource_by_embedded_identity(
                embedded_identity,
                {"single"},
            )
            if matched:
                return self._refresh_single_resource_identity_match(
                    matched,
                    source,
                    embedded_identity,
                )
        fingerprint = self._file_fingerprint(source)
        title = str(display_name or PurePosixPath(target_relative_path).stem).strip() or PurePosixPath(target_relative_path).stem
        resource_id = self._allocate_resource_id("single", f"{title}_{fingerprint['sha1'][:10]}")
        resource_dir = self.singles_dir / resource_id
        source_relative_path = str(PurePosixPath("files") / target_relative_path)
        resource_file = self._path_from_posix(resource_dir, source_relative_path)
        resource_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, resource_file)

        now = self._now_iso()
        file_entry = self._apply_file_identity(
            {
                "source_relative_path": source_relative_path,
                "target_relative_path": target_relative_path,
                "size": fingerprint["size"],
                "mtime_ns": fingerprint["mtime_ns"],
                "sha1": fingerprint["sha1"],
            },
            embedded_identity,
        )
        resource = {
            "schema_version": self.schema_version,
            "resource_id": resource_id,
            "resource_type": "single",
            "display_name": title,
            "imported_at": now,
            "updated_at": now,
            "files": [file_entry],
        }
        resource.update(
            self._embedded_resource_identity_fields([embedded_identity])
        )
        self._save_json_atomic(resource_dir / "resource.json", resource)
        self._save_json_atomic(resource_dir / "package_index.json", resource)
        return {
            "resource_id": resource_id,
            "resource_type": "single",
            "display_name": title,
            "resource_path": str(resource_dir),
            "files": resource["files"],
            "sight_package_id": str(resource.get("sight_package_id") or ""),
            "sight_file_ids": list(resource.get("sight_file_ids") or []),
            "sight_file_fingerprints": dict(
                resource.get("sight_file_fingerprints") or {}
            ),
            "metadata_source": str(resource.get("metadata_source") or ""),
            "matched_file": dict(resource["files"][0]),
        }

    def _find_matching_single_resource(
        self,
        target_relative_path: str,
        fingerprint: dict[str, Any],
        display_name: str,
    ) -> dict[str, Any] | None:
        base_id = self._safe_id_part(
            f"{display_name}_{str(fingerprint.get('sha1') or '')[:10]}"
        )
        candidate_dirs: list[Path] = []
        candidate_pattern = re.compile(rf"^{re.escape(base_id)}(?:_\d+)?$")
        for root in self._resource_roots("single"):
            if not root.exists() or not root.is_dir():
                continue
            try:
                candidate_dirs.extend(
                    path
                    for path in root.iterdir()
                    if path.is_dir() and candidate_pattern.fullmatch(path.name)
                )
            except OSError:
                continue

        for resource_dir in sorted(candidate_dirs, key=lambda path: path.name.lower()):
            index_path = resource_dir / "package_index.json"
            try:
                with open(index_path, "r", encoding="utf-8") as fh:
                    resource = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(resource, dict) or str(resource.get("resource_type") or "") != "single":
                continue
            files = [item for item in resource.get("files") or [] if isinstance(item, dict)]
            if len(files) != 1:
                continue
            entry = files[0]
            if (
                str(entry.get("target_relative_path") or "") != target_relative_path
                or not self._same_fingerprint(entry, fingerprint)
            ):
                continue
            source_relative_path = str(entry.get("source_relative_path") or "")
            try:
                resource_file = self._path_from_posix(resource_dir, source_relative_path)
            except ValueError:
                continue
            if not resource_file.is_file():
                continue
            try:
                if not self._same_fingerprint(self._file_fingerprint(resource_file), fingerprint):
                    continue
            except OSError:
                continue
            return {
                "resource_id": str(resource.get("resource_id") or resource_dir.name),
                "resource_type": "single",
                "display_name": str(resource.get("display_name") or display_name),
                "resource_path": str(resource_dir),
                "files": files,
            }
        return None

    def import_single_blk(
        self,
        source_path: str | Path,
        target_dir: str = "all_tanks",
        display_name: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"炮镜文件不存在: {source}")
        if source.suffix.lower() != ".blk":
            raise ValueError("请选择有效的 .blk 炮镜文件")

        target_relative_path = self._normalize_target_relative_path(target_dir, source.name)
        return self._import_single_blk_target(source, target_relative_path, display_name)

    def adopt_external_file(
        self,
        target_relative_path: str,
        usersights_path: str | Path,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        if not usersights.exists() or not usersights.is_dir():
            raise FileNotFoundError(f"UserSights 路径不存在: {usersights}")
        target_rel = self._normalize_adoption_target_relative_path(target_relative_path)
        disabled_rel = self._disabled_relative_path(target_rel)
        target_file = self._path_from_posix(usersights, target_rel)
        disabled_file = self._path_from_posix(usersights, disabled_rel)
        if not self._is_path_within(target_file, usersights) or not self._is_path_within(disabled_file, usersights):
            raise ValueError("炮镜目标路径超出 UserSights")

        lock = self._get_manifest_lock(usersights)
        if not lock.acquire(blocking=False):
            result = self._operation_busy_result(target_rel)
            result.update({
                "adopted_count": 0,
                "already_managed_count": 0,
                "processed_count": 1,
                "total_count": 1,
            })
            return result

        try:
            if target_file.is_file() and disabled_file.is_file():
                return {
                    "success": False,
                    "resource_id": "",
                    "target_relative_path": target_rel,
                    "adopted_count": 0,
                    "already_managed_count": 0,
                    "enabled_count": 0,
                    "disabled_count": 0,
                    "conflict_count": 1,
                    "conflicts": [{
                        "target_relative_path": target_rel,
                        "reason": "enabled_and_disabled_both_exist",
                    }],
                    "processed_count": 1,
                    "total_count": 1,
                }

            current_file = target_file if target_file.is_file() else disabled_file if disabled_file.is_file() else None
            if current_file is None:
                raise FileNotFoundError(f"炮镜文件不存在: {target_rel}")
            current_status = "enabled" if current_file == target_file else "disabled_by_rename"
            current_fp = self._file_fingerprint(current_file)
            manifest = self.load_manifest(usersights)
            if manifest.get("manifest_corrupt"):
                return {
                    "success": False,
                    "resource_id": "",
                    "target_relative_path": target_rel,
                    "adopted_count": 0,
                    "already_managed_count": 0,
                    "conflict_count": 1,
                    "conflicts": [{
                        "target_relative_path": target_rel,
                        "reason": "manifest_corrupt",
                    }],
                    "processed_count": 1,
                    "total_count": 1,
                }

            file_record = manifest.get("file_map", {}).get(target_rel)
            owners = []
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners") or [] if str(owner)]
            existing_owner = next(
                (owner for owner in owners if isinstance(manifest.get("resources", {}).get(owner), dict)),
                "",
            )
            if existing_owner:
                return {
                    "success": True,
                    "resource_id": existing_owner,
                    "resource_ids": [existing_owner],
                    "target_relative_path": target_rel,
                    "adopted_count": 0,
                    "already_managed_count": 1,
                    "enabled_count": 1 if current_status == "enabled" else 0,
                    "disabled_count": 1 if current_status == "disabled_by_rename" else 0,
                    "conflict_count": 0,
                    "conflicts": [],
                    "processed_count": 1,
                    "total_count": 1,
                    "install_status": current_status,
                }
            if owners:
                return {
                    "success": False,
                    "resource_id": "",
                    "target_relative_path": target_rel,
                    "adopted_count": 0,
                    "already_managed_count": 0,
                    "conflict_count": 1,
                    "conflicts": [{
                        "target_relative_path": target_rel,
                        "reason": "target_already_managed",
                    }],
                    "processed_count": 1,
                    "total_count": 1,
                }

            resource_title = str(
                display_name or PurePosixPath(target_rel).stem
            ).strip() or PurePosixPath(target_rel).stem
            embedded_identity = self._read_embedded_sight_identity(current_file)
            imported = None
            if embedded_identity:
                imported = self._find_resource_by_embedded_identity(
                    embedded_identity,
                    {"single", "package"},
                )
            if not imported:
                imported = self._find_matching_single_resource(
                    target_rel,
                    current_fp,
                    resource_title,
                )
            reused_resource_count = 1 if imported else 0
            if not imported:
                imported = self._import_single_blk_target(
                    current_file,
                    target_rel,
                    resource_title,
                )
            resource_id = str(imported["resource_id"])
            matched_file = imported.get("matched_file")
            if not isinstance(matched_file, dict):
                matched_file = imported["files"][0]
            source_rel = str(matched_file["source_relative_path"])
            now = self._now_iso()
            managed_entry = self._apply_file_identity(
                {
                    "source_relative_path": source_rel,
                    "target_relative_path": target_rel,
                    "disabled_relative_path": disabled_rel,
                    "file_status": current_status,
                    "size": current_fp["size"],
                    "mtime_ns": current_fp["mtime_ns"],
                    "sha1": current_fp["sha1"],
                    "managed": True,
                    "conflict": False,
                    "conflict_reason": "",
                    "last_verified_at": now,
                },
                embedded_identity,
            )
            manifest["file_map"][target_rel] = {
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
                "file_status": current_status,
                "size": current_fp["size"],
                "mtime_ns": current_fp["mtime_ns"],
                "sha1": current_fp["sha1"],
                "owners": [resource_id],
                "updated_at": now,
            }
            manifest_resource = {
                "resource_id": resource_id,
                "resource_type": str(imported.get("resource_type") or "single"),
                "display_name": str(imported.get("display_name") or PurePosixPath(target_rel).stem),
                "installed_at": now,
                "updated_at": now,
                "status": current_status,
                "baseline_source": "adopted_current_state",
                "expected_file_count": 1,
                "conflict_count": 0,
                "conflicts": [],
                "files": [managed_entry],
            }
            for key in (
                "sight_package_id",
                "sight_file_ids",
                "sight_file_fingerprints",
                "metadata_source",
            ):
                if imported.get(key) not in (None, "", [], {}):
                    manifest_resource[key] = imported[key]
            manifest["resources"][resource_id] = manifest_resource
            self.save_manifest(usersights, manifest)
            return {
                "success": True,
                "resource_id": resource_id,
                "resource_ids": [resource_id],
                "target_relative_path": target_rel,
                "adopted_count": 1,
                "already_managed_count": 0,
                "reused_resource_count": reused_resource_count,
                "enabled_count": 1 if current_status == "enabled" else 0,
                "disabled_count": 1 if current_status == "disabled_by_rename" else 0,
                "conflict_count": 0,
                "conflicts": [],
                "processed_count": 1,
                "total_count": 1,
                "install_status": current_status,
            }
        finally:
            lock.release()

    def import_package_directory(
        self,
        source_dir: str | Path,
        install_entries: list[dict[str, Any]],
        display_name: str | None = None,
        archive_name: str | None = None,
    ) -> dict[str, Any]:
        source_root = Path(source_dir)
        if not source_root.exists() or not source_root.is_dir():
            raise FileNotFoundError(f"炮镜包目录不存在: {source_root}")
        if not install_entries:
            raise ValueError("炮镜包内未找到可安装文件")

        title = str(display_name or archive_name or source_root.name).strip() or source_root.name
        normalized_entries: list[dict[str, Any]] = []
        digest = hashlib.sha1()
        for entry in install_entries:
            source_rel = str(entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
            target_rel = str(entry.get("target_relative_path") or "").replace("\\", "/").strip("/")
            source_file = self._path_from_posix(source_root, source_rel)
            self._posix_parts(target_rel)
            if not source_file.exists() or not source_file.is_file():
                raise FileNotFoundError(f"炮镜包源文件不存在: {source_rel}")
            if source_file.suffix.lower() != ".blk":
                raise ValueError(f"炮镜包安装文件不是 .blk: {source_rel}")
            fingerprint = self._file_fingerprint(source_file)
            digest.update(source_rel.encode("utf-8", errors="ignore"))
            digest.update(target_rel.encode("utf-8", errors="ignore"))
            digest.update(str(fingerprint["size"]).encode("ascii"))
            digest.update(str(fingerprint["sha1"]).encode("ascii"))
            normalized_entries.append({
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
                "size": fingerprint["size"],
                "mtime_ns": fingerprint["mtime_ns"],
                "sha1": fingerprint["sha1"],
                "_embedded_identity": self._read_embedded_sight_identity(source_file),
            })

        resource_id = self._allocate_resource_id("package", f"{title}_{digest.hexdigest()[:10]}")
        resource_dir = self.packages_dir / resource_id
        assets_dir = resource_dir / "assets"
        shutil.copytree(source_root, assets_dir)

        asset_files: list[dict[str, Any]] = []
        for asset_file in sorted(assets_dir.rglob("*"), key=lambda p: str(p.relative_to(assets_dir)).lower()):
            if not asset_file.is_file():
                continue
            rel_path = self._relative_to_posix(asset_file, assets_dir)
            asset_fp = self._light_fingerprint(asset_file)
            asset_files.append({
                "source_relative_path": str(PurePosixPath("assets") / rel_path),
                "original_relative_path": rel_path,
                "size": asset_fp["size"],
                "mtime_ns": asset_fp["mtime_ns"],
            })

        files = []
        embedded_identities: list[dict[str, Any]] = []
        for entry in normalized_entries:
            embedded_identity = entry.get("_embedded_identity")
            if isinstance(embedded_identity, dict) and embedded_identity:
                embedded_identities.append(embedded_identity)
            file_entry = self._apply_file_identity(
                {
                    "source_relative_path": str(PurePosixPath("assets") / entry["source_relative_path"]),
                    "original_source_relative_path": entry["source_relative_path"],
                    "target_relative_path": entry["target_relative_path"],
                    "size": entry["size"],
                    "mtime_ns": entry["mtime_ns"],
                    "sha1": entry["sha1"],
                },
                embedded_identity if isinstance(embedded_identity, dict) else {},
            )
            files.append(file_entry)

        now = self._now_iso()
        resource = {
            "schema_version": self.schema_version,
            "resource_id": resource_id,
            "resource_type": "package",
            "display_name": title,
            "archive_name": str(archive_name or ""),
            "imported_at": now,
            "updated_at": now,
            "asset_root_relative_path": "assets",
            "asset_files": asset_files,
            "files": files,
        }
        resource.update(
            self._embedded_resource_identity_fields(embedded_identities)
        )
        self._save_json_atomic(resource_dir / "resource.json", resource)
        self._save_json_atomic(resource_dir / "package_index.json", resource)
        return {
            "resource_id": resource_id,
            "resource_type": "package",
            "display_name": title,
            "resource_path": str(resource_dir),
            "files": files,
            "asset_count": len(asset_files),
            "sight_package_id": str(resource.get("sight_package_id") or ""),
            "sight_file_ids": list(resource.get("sight_file_ids") or []),
            "sight_file_fingerprints": dict(
                resource.get("sight_file_fingerprints") or {}
            ),
            "metadata_source": str(resource.get("metadata_source") or ""),
        }

    @classmethod
    def _is_cover_asset_path(cls, relative_path: str) -> bool:
        name = PurePosixPath(str(relative_path or "").replace("\\", "/")).name.lower()
        suffix = PurePosixPath(name).suffix.lower()
        return suffix in cls.cover_suffixes and (
            name.startswith("preview.") or name.startswith("icon.")
        )

    @classmethod
    def _is_detail_asset_path(cls, relative_path: str) -> bool:
        name = PurePosixPath(str(relative_path or "").replace("\\", "/")).name.lower()
        return name in DETAIL_ASSET_NAMES

    @classmethod
    def _cover_extension_from_name(cls, name: str) -> str:
        suffix = PurePosixPath(str(name or "")).suffix.lower()
        return suffix if suffix in cls.cover_suffixes else ".png"

    def _find_cover_file(self, cover_dir: Path) -> Path | None:
        if not cover_dir.exists() or not cover_dir.is_dir():
            return None
        preferred_names = [
            "preview.png",
            "preview.jpg",
            "preview.jpeg",
            "preview.webp",
            "icon.png",
            "icon.jpg",
            "icon.jpeg",
            "icon.webp",
        ]
        for name in preferred_names:
            candidate = cover_dir / name
            if candidate.is_file():
                return candidate
        try:
            candidates = sorted(
                (
                    path
                    for path in cover_dir.iterdir()
                    if path.is_file()
                    and path.suffix.lower() in self.cover_suffixes
                    and path.name.lower() not in DETAIL_ASSET_NAMES
                ),
                key=lambda path: path.name.lower(),
            )
        except OSError:
            return None
        return candidates[0] if candidates else None

    def find_resource_cover(self, resource_id: str) -> dict[str, Any]:
        resource_key = str(resource_id or "").strip()
        if not resource_key:
            return {}

        for root, source in (
            (self.covers_dir, "library_cover"),
            (self.legacy_covers_dir, "library_cover"),
        ):
            cover_path = self._find_cover_file(root / resource_key)
            if cover_path:
                return {
                    "resource_id": resource_key,
                    "cover_source": source,
                    "path": str(cover_path),
                }

        try:
            resource, resource_dir = self.load_resource(resource_key)
        except (FileNotFoundError, json.JSONDecodeError, OSError, SightsRepositoryError):
            return {}

        cover_record = resource.get("cover") if isinstance(resource.get("cover"), dict) else {}
        indexed_rel = str(cover_record.get("relative_path") or "").strip()
        if indexed_rel:
            try:
                indexed_path = self._path_from_posix(self.library_dir, indexed_rel)
                if indexed_path.is_file():
                    return {
                        "resource_id": resource_key,
                        "cover_source": str(cover_record.get("source") or "library_cover"),
                        "path": str(indexed_path),
                    }
            except ValueError:
                pass

        for entry in resource.get("asset_files", []):
            if not isinstance(entry, dict):
                continue
            source_rel = str(entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
            original_rel = str(entry.get("original_relative_path") or source_rel).replace("\\", "/").strip("/")
            if not source_rel or not self._is_cover_asset_path(original_rel):
                continue
            try:
                asset_path = self._path_from_posix(resource_dir, source_rel)
            except ValueError:
                continue
            if asset_path.is_file():
                return {
                    "resource_id": resource_key,
                    "cover_source": "package_asset",
                    "path": str(asset_path),
                }
        return {}

    def find_resource_detail_image(self, resource_id: str) -> dict[str, Any]:
        """从炮镜包资源资产中查找详情页专用图，不回退到封面目录。"""
        resource_key = str(resource_id or "").strip()
        if not resource_key:
            return {}

        try:
            resource, resource_dir = self.load_resource(resource_key)
        except (FileNotFoundError, json.JSONDecodeError, OSError, SightsRepositoryError):
            return {}

        preferred_names = (
            DETAIL_OUTPUT_NAME,
            "detail.png",
            "detail.jpg",
            "detail.jpeg",
        )
        assets_dir = resource_dir / "assets"
        for name in preferred_names:
            candidate = assets_dir / name
            if candidate.is_file() and not candidate.is_symlink():
                return {
                    "resource_id": resource_key,
                    "detail_source": "package_asset",
                    "path": str(candidate),
                }

        for entry in resource.get("asset_files", []):
            if not isinstance(entry, dict):
                continue
            source_rel = str(entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
            original_rel = str(entry.get("original_relative_path") or source_rel).replace("\\", "/").strip("/")
            if not source_rel or not self._is_detail_asset_path(original_rel):
                continue
            try:
                asset_path = self._path_from_posix(resource_dir, source_rel)
            except ValueError:
                continue
            if asset_path.is_file() and not asset_path.is_symlink():
                return {
                    "resource_id": resource_key,
                    "detail_source": "package_asset",
                    "path": str(asset_path),
                }
        return {}

    def save_resource_cover(self, resource_id: str, raw: bytes, extension: str = ".png") -> dict[str, Any]:
        resource_key = str(resource_id or "").strip()
        if not resource_key:
            raise ValueError("炮镜资源 ID 不能为空")
        resource, resource_dir = self.load_resource(resource_key)
        suffix = self._cover_extension_from_name(f"preview{extension}")
        cover_dir = self.covers_dir / resource_key
        cover_dir.mkdir(parents=True, exist_ok=True)
        dst = cover_dir / f"preview{suffix}"
        with open(dst, "wb") as fh:
            fh.write(raw)

        relative_path = self._relative_to_posix(dst, self.library_dir)
        now = self._now_iso()
        resource["cover"] = {
            "source": "library_cover",
            "relative_path": relative_path,
            "updated_at": now,
        }
        resource["updated_at"] = now
        self._save_json_atomic(resource_dir / "resource.json", resource)
        self._save_json_atomic(resource_dir / "package_index.json", resource)
        return {
            "resource_id": resource_key,
            "cover_source": "library_cover",
            "path": str(dst),
            "relative_path": relative_path,
        }

    def save_resource_metadata_links(
        self,
        resource_id: str,
        metadata_entries: list[dict[str, Any]],
        metadata_by_target: dict[str, dict[str, Any]],
    ) -> None:
        resource_key = str(resource_id or "").strip()
        if not resource_key:
            raise ValueError("炮镜资源 ID 不能为空")
        resource, resource_dir = self.load_resource(resource_key)
        entries = [dict(item) for item in metadata_entries if isinstance(item, dict)]
        by_target = {
            str(target): dict(record)
            for target, record in metadata_by_target.items()
            if str(target).strip() and isinstance(record, dict)
        }
        resource["metadata_entries"] = entries
        resource["metadata_by_target"] = by_target
        resource["metadata_source"] = "package_asset"
        resource["updated_at"] = self._now_iso()
        self._save_json_atomic(resource_dir / "resource.json", resource)
        self._save_json_atomic(resource_dir / "package_index.json", resource)

    def find_resource_metadata(self, resource_id: str, target_group: str = "") -> dict[str, Any]:
        resource_key = str(resource_id or "").strip()
        if not resource_key:
            return {}
        try:
            resource, _resource_dir = self.load_resource(resource_key)
        except (FileNotFoundError, json.JSONDecodeError, OSError, SightsRepositoryError):
            return {}

        target_key = str(target_group or "").strip()
        by_target = resource.get("metadata_by_target")
        if isinstance(by_target, dict) and target_key:
            record = by_target.get(target_key)
            if isinstance(record, dict) and isinstance(record.get("meta"), dict):
                result = dict(record)
                result["resource_id"] = resource_key
                result.setdefault("metadata_source", resource.get("metadata_source") or "package_asset")
                return result

        entries = resource.get("metadata_entries")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("meta"), dict):
                    result = dict(entry)
                    result["resource_id"] = resource_key
                    result.setdefault("metadata_source", resource.get("metadata_source") or "package_asset")
                    return result
        return {}

    @staticmethod
    def _relative_to_posix(path: Path, root: Path) -> str:
        return str(path.relative_to(root)).replace("\\", "/")

    def _extract_uid_from_usersights_path(self, usersights_path: Path) -> str:
        try:
            path = usersights_path.resolve(strict=False)
            if path.name.lower() == "usersights" and path.parent.name.lower() == "production":
                return path.parent.parent.name
        except Exception:
            pass
        return ""

    def get_manifest_id(self, usersights_path: str | Path) -> str:
        path = Path(usersights_path)
        uid = self._extract_uid_from_usersights_path(path)
        if uid:
            return f"uid_{self._safe_id_part(uid, fallback='unknown')}"
        digest = hashlib.sha1(self._norm_path_key(path).encode("utf-8", errors="ignore")).hexdigest()
        return f"path_{digest[:12]}"

    def get_manifest_path(self, usersights_path: str | Path) -> Path:
        return self.manifest_store.get_path(usersights_path)

    def _manifest_backup_paths(self, usersights_path: str | Path, manifest_path: Path | None = None) -> list[Path]:
        return self.manifest_store.backup_paths(usersights_path, manifest_path=manifest_path)

    def _find_manifest_path(self, usersights_path: str | Path) -> Path:
        return self.manifest_store.find_path(usersights_path)

    def collect_manifest_storage_metrics(self, usersights_path: str | Path) -> dict[str, Any]:
        return self.manifest_store.collect_metrics(usersights_path)

    def _empty_manifest(self, usersights_path: str | Path) -> dict[str, Any]:
        path = Path(usersights_path)
        uid = self._extract_uid_from_usersights_path(path)
        return {
            "schema_version": self.schema_version,
            "uid": uid,
            "usersights_path": str(path),
            "updated_at": self._now_iso(),
            "resources": {},
            "file_map": {},
            "manifest_corrupt": False,
            "manifest_error": "",
            "manifest_backup_count": 0,
            "manifest_backup_paths": [],
        }

    def _corrupt_manifest_fallback(self, usersights_path: str | Path, manifest_path: Path, error: str) -> dict[str, Any]:
        manifest = self._empty_manifest(usersights_path)
        backup_paths = self._manifest_backup_paths(usersights_path, manifest_path=manifest_path)
        manifest.update({
            "manifest_corrupt": True,
            "manifest_error": str(error),
            "manifest_backup_count": len(backup_paths),
            "manifest_backup_paths": [str(path) for path in backup_paths],
        })
        return manifest

    def _normalize_loaded_manifest(self, usersights_path: str | Path, manifest_path: Path, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return self._corrupt_manifest_fallback(usersights_path, manifest_path, "manifest_root_not_object")
        data.setdefault("schema_version", self.schema_version)
        data.setdefault("uid", self._extract_uid_from_usersights_path(Path(usersights_path)))
        data["usersights_path"] = str(Path(usersights_path))
        data.setdefault("updated_at", self._now_iso())
        data.setdefault("manifest_corrupt", False)
        data.setdefault("manifest_error", "")
        data.setdefault("manifest_backup_count", 0)
        data.setdefault("manifest_backup_paths", [])
        if not isinstance(data.get("resources"), dict):
            data["resources"] = {}
        if not isinstance(data.get("file_map"), dict):
            data["file_map"] = {}
        return data

    def load_manifest(self, usersights_path: str | Path) -> dict[str, Any]:
        return self.manifest_store.load(usersights_path)

    def save_manifest(self, usersights_path: str | Path, manifest: dict[str, Any]) -> None:
        with self._get_manifest_lock(usersights_path):
            manifest["schema_version"] = self.schema_version
            manifest["uid"] = self._extract_uid_from_usersights_path(Path(usersights_path))
            manifest["usersights_path"] = str(Path(usersights_path))
            manifest["updated_at"] = self._now_iso()
            manifest["manifest_corrupt"] = False
            manifest["manifest_error"] = ""
            manifest["manifest_backup_count"] = 0
            manifest["manifest_backup_paths"] = []
            self.manifest_store.save(usersights_path, manifest)

    def load_resource(self, resource_id: str) -> tuple[dict[str, Any], Path]:
        resource_key = str(resource_id or "").strip()
        roots = [
            self.singles_dir,
            self.packages_dir,
            self.legacy_singles_dir,
            self.legacy_packages_dir,
        ]
        seen: set[str] = set()
        for root in roots:
            key = self._norm_path_key(root)
            if key in seen:
                continue
            seen.add(key)
            resource_dir = root / resource_key
            index_path = resource_dir / "package_index.json"
            if index_path.exists():
                try:
                    with open(index_path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except json.JSONDecodeError as e:
                    raise SightsRepositoryError(f"炮镜资源索引损坏: {resource_id}") from e
                except OSError as e:
                    raise SightsRepositoryError(f"炮镜资源索引读取失败: {resource_id}") from e
                if not isinstance(data, dict):
                    raise SightsRepositoryError("炮镜资源索引格式无效")
                return data, resource_dir
        raise FileNotFoundError(f"炮镜资源不存在: {resource_id}")

    def resource_exists(self, resource_id: str) -> bool:
        resource_key = str(resource_id or "").strip()
        if not resource_key:
            return False
        roots = [
            self.singles_dir,
            self.packages_dir,
            self.legacy_singles_dir,
            self.legacy_packages_dir,
        ]
        seen: set[str] = set()
        for root in roots:
            key = self._norm_path_key(root)
            if key in seen:
                continue
            seen.add(key)
            if (root / resource_key / "package_index.json").exists():
                return True
        return False

    def _resource_deployment_inputs(
        self,
        resource: dict[str, Any],
        resource_dir: Path,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in resource.get("files") or []:
            if not isinstance(entry, dict):
                continue
            storage_path = str(entry.get("source_relative_path") or "").replace("\\", "/").strip("/")
            if not storage_path:
                continue
            public_path = str(entry.get("original_source_relative_path") or "").replace("\\", "/").strip("/")
            if not public_path:
                public_path = storage_path[6:] if storage_path.startswith("files/") else storage_path
            source_file = self._path_from_posix(resource_dir, storage_path)
            status = self._blk_analyzer.check_match_exp_class(source_file)
            rows.append({
                "source_relative_path": public_path,
                "source_storage_relative_path": storage_path,
                "match_exp_class_status": status,
            })
        return rows

    @staticmethod
    def _resource_public_meta(resource: dict[str, Any]) -> dict[str, Any]:
        for entry in resource.get("metadata_entries") or []:
            if not isinstance(entry, dict):
                continue
            meta = entry.get("meta")
            if isinstance(meta, dict):
                return meta
        metadata_by_target = resource.get("metadata_by_target")
        if isinstance(metadata_by_target, dict):
            for entry in metadata_by_target.values():
                if isinstance(entry, dict) and isinstance(entry.get("meta"), dict):
                    return entry["meta"]
        return {}

    def _legacy_deployment_from_files(
        self,
        files: list[dict[str, Any]],
        source: str = "legacy_manifest",
    ) -> dict[str, Any]:
        file_targets: list[dict[str, str]] = []
        selected_vehicle_ids: list[str] = []
        seen_vehicle_ids: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict):
                continue
            source_rel = str(entry.get("source_relative_path") or "")
            target_rel = str(entry.get("target_relative_path") or "")
            if not source_rel or not target_rel:
                continue
            file_targets.append({
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
            })
            parts = PurePosixPath(target_rel.replace("\\", "/")).parts
            if parts and parts[0] not in seen_vehicle_ids:
                seen_vehicle_ids.add(parts[0])
                selected_vehicle_ids.append(parts[0])
        return {
            "schema_version": 1,
            "mode": "legacy_existing",
            "source": source,
            "remember": True,
            "selected_vehicle_ids": selected_vehicle_ids,
            "file_targets": file_targets,
        }

    def get_resource_deployment_state(
        self,
        resource_id: str,
        usersights_path: str | Path,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        resource_record = manifest.get("resources", {}).get(resource_id)
        if isinstance(resource_record, dict):
            files = [entry for entry in resource_record.get("files") or [] if isinstance(entry, dict)]
            deployment = resource_record.get("deployment")
            if not isinstance(deployment, dict):
                deployment = self._legacy_deployment_from_files(files)
            enabled_count = 0
            disabled_count = 0
            missing_count = 0
            conflict_count = 0
            for entry in files:
                target_rel = str(entry.get("target_relative_path") or "")
                if not target_rel:
                    missing_count += 1
                    continue
                disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
                target_file = self._path_from_posix(usersights, target_rel)
                disabled_file = self._path_from_posix(usersights, disabled_rel)
                baseline = manifest.get("file_map", {}).get(target_rel)
                if not isinstance(baseline, dict):
                    baseline = entry
                if target_file.exists() and disabled_file.exists():
                    conflict_count += 1
                elif str(entry.get("file_status") or "") == "disabled_shared" and target_file.exists():
                    current = self._file_fingerprint(target_file)
                    if self._same_fingerprint(baseline, current):
                        disabled_count += 1
                    else:
                        conflict_count += 1
                elif target_file.exists():
                    current = self._file_fingerprint(target_file)
                    if self._same_fingerprint(baseline, current):
                        enabled_count += 1
                    else:
                        conflict_count += 1
                elif disabled_file.exists():
                    current = self._file_fingerprint(disabled_file)
                    if self._same_fingerprint(baseline, current):
                        disabled_count += 1
                    else:
                        conflict_count += 1
                else:
                    missing_count += 1
            expected_count = len(files)
            if conflict_count:
                state = "conflict"
            elif expected_count and enabled_count == expected_count:
                state = "enabled"
            elif expected_count and disabled_count == expected_count:
                state = "disabled"
            elif enabled_count or disabled_count:
                state = "partial"
            else:
                state = "target_missing"
            should_prompt = state in {"target_missing", "conflict"}
            action = {
                "enabled": "already_enabled",
                "disabled": "restorable",
                "partial": "restorable",
                "target_missing": "repair_deployment",
                "conflict": "resolve_conflict",
            }[state]
            return {
                "resource_id": resource_id,
                "manifest_id": self.get_manifest_id(usersights),
                "managed_by_aimerwt": True,
                "state": state,
                "action": action,
                "should_prompt": should_prompt,
                "deployment": deployment,
                "enabled_count": enabled_count,
                "disabled_count": disabled_count,
                "missing_count": missing_count,
                "conflict_count": conflict_count,
                "expected_count": expected_count,
            }

        default_files = []
        enabled_count = 0
        disabled_count = 0
        conflict_count = 0
        for entry in resource.get("files") or []:
            if not isinstance(entry, dict):
                continue
            source_rel = str(entry.get("source_relative_path") or "")
            target_rel = str(entry.get("target_relative_path") or "")
            if not source_rel or not target_rel:
                continue
            source_file = self._path_from_posix(resource_dir, source_rel)
            if not source_file.is_file():
                continue
            source_fp = self._file_fingerprint(source_file)
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_rel = self._disabled_relative_path(target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            default_files.append({
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
            })
            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
            elif target_file.exists():
                if self._same_fingerprint(source_fp, self._file_fingerprint(target_file)):
                    enabled_count += 1
                else:
                    conflict_count += 1
            elif disabled_file.exists():
                if self._same_fingerprint(source_fp, self._file_fingerprint(disabled_file)):
                    disabled_count += 1
                else:
                    conflict_count += 1
        expected_count = len(default_files)
        if conflict_count:
            state = "conflict"
        elif expected_count and enabled_count == expected_count:
            state = "enabled"
        elif expected_count and disabled_count == expected_count:
            state = "disabled"
        elif enabled_count or disabled_count:
            state = "partial"
        else:
            state = "not_deployed"
        action = {
            "enabled": "already_enabled",
            "disabled": "restorable",
            "partial": "restorable",
            "conflict": "resolve_conflict",
            "not_deployed": "confirm_deployment",
        }[state]
        return {
            "resource_id": resource_id,
            "manifest_id": self.get_manifest_id(usersights),
            "managed_by_aimerwt": False,
            "state": state,
            "action": action,
            "should_prompt": state in {"not_deployed", "conflict"},
            "deployment": self._legacy_deployment_from_files(default_files, source="matching_existing_files"),
            "enabled_count": enabled_count,
            "disabled_count": disabled_count,
            "missing_count": max(0, expected_count - enabled_count - disabled_count - conflict_count),
            "conflict_count": conflict_count,
            "expected_count": expected_count,
        }

    def _apply_retained_package_targets(
        self,
        preview: dict[str, Any],
        resource_inputs: list[dict[str, Any]],
        retained_targets: Any,
    ) -> None:
        """用旧包已确认目标覆盖同源文件的新作者推荐，新增文件保持新预检结果。"""
        if not isinstance(retained_targets, list):
            return
        inputs_by_public = {
            str(item.get("source_relative_path") or "").lower(): item
            for item in resource_inputs
            if str(item.get("source_relative_path") or "")
        }
        retained_rows: list[dict[str, Any]] = []
        retained_sources: set[str] = set()
        for item in retained_targets:
            if not isinstance(item, dict):
                continue
            source_path = str(item.get("source_relative_path") or "").replace("\\", "/").strip("/")
            target_path = str(item.get("target_relative_path") or "").replace("\\", "/").strip("/")
            source_input = inputs_by_public.get(source_path.lower())
            if not source_input:
                continue
            try:
                target_parts = self._posix_parts(target_path)
            except ValueError:
                continue
            if len(target_parts) < 2 or PurePosixPath(source_path).name.lower() != target_parts[-1].lower():
                continue
            retained_sources.add(source_path.lower())
            retained_rows.append({
                "source_relative_path": source_path,
                "source_storage_relative_path": str(source_input.get("source_storage_relative_path") or source_path),
                "target_relative_path": str(PurePosixPath(*target_parts)),
                "target_vehicle_id": target_parts[0],
                "recommendation_source": "retained_existing_deployment",
                "match_exp_class_status": str(source_input.get("match_exp_class_status") or "unknown_unreadable"),
            })
        if not retained_rows:
            return

        merged = [
            dict(item)
            for item in preview.get("file_targets") or []
            if str(item.get("source_relative_path") or "").lower() not in retained_sources
        ]
        merged.extend(retained_rows)
        by_target: dict[str, list[dict[str, Any]]] = {}
        unique_rows: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for item in merged:
            pair = (
                str(item.get("source_relative_path") or "").lower(),
                str(item.get("target_relative_path") or "").lower(),
            )
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            unique_rows.append(item)
            by_target.setdefault(pair[1], []).append(item)
        collided: set[str] = set()
        errors = list(preview.get("errors") or [])
        for target_key, rows in by_target.items():
            sources = sorted({str(row.get("source_relative_path") or "") for row in rows})
            if len(sources) < 2:
                continue
            collided.add(target_key)
            errors.append({
                "code": "filename_collision",
                "message": "包升级后的多个炮镜源文件会写入同一目标，已阻断覆盖。",
                "target_relative_path": str(rows[0].get("target_relative_path") or ""),
                "source_relative_paths": sources,
            })
        preview["file_targets"] = [
            item for item in unique_rows
            if str(item.get("target_relative_path") or "").lower() not in collided
        ]
        selected_vehicle_ids: list[str] = []
        for item in preview["file_targets"]:
            vehicle_id = str(item.get("target_vehicle_id") or "")
            if vehicle_id and vehicle_id not in selected_vehicle_ids:
                selected_vehicle_ids.append(vehicle_id)
        preview["selected_vehicle_ids"] = selected_vehicle_ids
        preview["errors"] = errors
        preview["success"] = not errors
        summary = preview.setdefault("summary", {})
        summary["target_count"] = len(preview["file_targets"])
        summary["retained_existing_file_count"] = len(retained_sources)
        summary["filename_collision_count"] = int(summary.get("filename_collision_count") or 0) + len(collided)
        warnings = preview.setdefault("warnings", [])
        warnings.append({
            "code": "package_upgrade_targets_retained",
            "message": f"包升级保留了 {len(retained_sources)} 个旧文件的用户部署位置。",
            "retained_file_count": len(retained_sources),
        })
    def _managed_package_upgrade_targets(
        self,
        resource: dict[str, Any],
        usersights: Path,
        retained_targets: Any,
    ) -> set[str]:
        """只允许同名旧包中仍与清单基线一致的目标被新版内容替换。"""
        if (
            str(resource.get("resource_type") or "") != "package"
            or not isinstance(retained_targets, list)
        ):
            return set()
        display_name = str(resource.get("display_name") or "")
        if not display_name:
            return set()
        manifest = self.load_manifest(usersights)
        allowed: set[str] = set()
        for item in retained_targets:
            if not isinstance(item, dict):
                continue
            target_value = str(item.get("target_relative_path") or "")
            try:
                target_rel = str(PurePosixPath(*self._posix_parts(target_value)))
            except ValueError:
                continue
            file_record = manifest.get("file_map", {}).get(target_rel)
            if not isinstance(file_record, dict):
                continue
            matching_owner = any(
                isinstance(manifest.get("resources", {}).get(str(owner)), dict)
                and str(manifest["resources"][str(owner)].get("resource_type") or "") == "package"
                and str(manifest["resources"][str(owner)].get("display_name") or "") == display_name
                for owner in file_record.get("owners") or []
            )
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(
                usersights,
                self._disabled_relative_path(target_rel),
            )
            if (
                matching_owner
                and target_file.is_file()
                and not disabled_file.exists()
                and self._same_fingerprint(
                    file_record,
                    self._file_fingerprint(target_file),
                )
            ):
                allowed.add(target_rel.lower())
        return allowed
    def preview_resource_deployment(
        self,
        resource_id: str,
        usersights_path: str | Path,
        deployment_request: dict[str, Any] | None,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        request = dict(deployment_request or {})
        state = self.get_resource_deployment_state(resource_id, usersights)
        change_existing = bool(request.get("change_existing"))
        if not change_existing and state["action"] in {"already_enabled", "restorable"}:
            deployment = state.get("deployment") or {}
            file_targets = list(deployment.get("file_targets") or [])
            return {
                "success": True,
                **state,
                "file_targets": file_targets,
                "warnings": [],
                "errors": [],
                "summary": {
                    "resource_file_count": state.get("expected_count", 0),
                    "target_count": len(file_targets),
                    "author_recommended_file_count": 0,
                    "fallback_all_tanks_count": 0,
                    "filename_collision_count": 0,
                    "match_exp_class_status_counts": {},
                },
            }
        if not change_existing and state["state"] == "conflict":
            return {
                "success": False,
                **state,
                "file_targets": [],
                "warnings": [],
                "errors": [{
                    "code": "existing_deployment_conflict",
                    "message": "现有炮镜文件与安装清单指纹不一致，不能自动覆盖。",
                }],
                "summary": {},
            }

        resource, resource_dir = self.load_resource(resource_id)
        resource_inputs = self._resource_deployment_inputs(resource, resource_dir)
        managed_replace_targets = self._managed_package_upgrade_targets(
            resource,
            usersights,
            request.get("retained_file_targets"),
        )
        preview = build_sight_deployment_preview(
            resource_inputs,
            self._resource_public_meta(resource),
            request,
        )
        self._apply_retained_package_targets(
            preview,
            resource_inputs,
            request.get("retained_file_targets"),
        )
        preview.update({
            "resource_id": resource_id,
            "manifest_id": self.get_manifest_id(usersights),
            "managed_by_aimerwt": state["managed_by_aimerwt"],
            "state": state["state"],
            "action": "repair_deployment" if state["state"] == "target_missing" else "confirm_deployment",
            "should_prompt": True,
            "deployment": state.get("deployment"),
        })
        self._append_target_preflight_conflicts(
            preview,
            usersights,
            resource_dir,
            managed_replace_targets,
        )
        preview["managed_replace_target_count"] = len(managed_replace_targets)
        token_payload = {
            "resource_id": resource_id,
            "manifest_id": preview["manifest_id"],
            "mode": preview.get("mode"),
            "file_targets": preview.get("file_targets"),
        }
        preview["preview_token"] = hashlib.sha1(
            json.dumps(token_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return preview

    def _append_target_preflight_conflicts(
        self,
        preview: dict[str, Any],
        usersights: Path,
        resource_dir: Path,
        managed_replace_targets: set[str] | None = None,
    ) -> None:
        errors = preview.setdefault("errors", [])
        replace_targets = managed_replace_targets or set()
        for target in preview.get("file_targets") or []:
            source_rel = str(target.get("source_storage_relative_path") or target.get("source_relative_path") or "")
            target_rel = str(target.get("target_relative_path") or "")
            if not source_rel or not target_rel:
                continue
            source_file = self._path_from_posix(resource_dir, source_rel)
            if not source_file.is_file():
                errors.append({
                    "code": "source_missing",
                    "message": "资源库中的炮镜源文件不存在。",
                    "source_relative_path": source_rel,
                })
                continue
            source_fp = self._file_fingerprint(source_file)
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, self._disabled_relative_path(target_rel))
            reason = ""
            if target_file.exists() and disabled_file.exists():
                reason = "enabled_and_disabled_both_exist"
            elif (
                target_file.exists()
                and target_rel.lower() not in replace_targets
                and not self._same_fingerprint(source_fp, self._file_fingerprint(target_file))
            ):
                reason = "target_conflict"
            elif disabled_file.exists() and not self._same_fingerprint(source_fp, self._file_fingerprint(disabled_file)):
                reason = "disabled_target_conflict"
            if reason:
                errors.append({
                    "code": reason,
                    "message": "目标位置已有不同内容的炮镜文件，预检已阻止覆盖。",
                    "target_relative_path": target_rel,
                })
        preview["success"] = not errors

    @_locked_manifest_write
    def apply_resource_deployment(
        self,
        resource_id: str,
        usersights_path: str | Path,
        deployment_request: dict[str, Any] | None,
        should_cancel: Any = None,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        request = dict(deployment_request or {})
        state = self.get_resource_deployment_state(resource_id, usersights)
        change_existing = bool(request.get("change_existing"))
        if not change_existing and state["action"] == "already_enabled":
            return {
                "success": True,
                "resource_id": resource_id,
                "action": "already_enabled",
                "install_status": "enabled",
                "deployment": state.get("deployment"),
            }
        if not change_existing and state["action"] == "restorable":
            if state["managed_by_aimerwt"]:
                result = self.enable_resource(resource_id, usersights)
            else:
                result = self.install_resource(resource_id, usersights)
            self._persist_legacy_deployment(resource_id, usersights)
            result["action"] = "restored_existing"
            return result
        if not change_existing and state["state"] == "conflict":
            return {
                "success": False,
                "resource_id": resource_id,
                "error_code": "existing_deployment_conflict",
                "msg": "现有炮镜文件已被修改或发生冲突，未执行覆盖。",
            }

        previous_targets: list[dict[str, Any]] = []
        if change_existing and state["managed_by_aimerwt"]:
            manifest_before = self.load_manifest(usersights)
            record_before = manifest_before.get("resources", {}).get(resource_id)
            if isinstance(record_before, dict):
                previous_targets = [dict(item) for item in record_before.get("files") or [] if isinstance(item, dict)]

        preview_request = dict(request)
        preview_request["change_existing"] = True
        preview = self.preview_resource_deployment(resource_id, usersights, preview_request)
        if not preview.get("success"):
            first_error = next(iter(preview.get("errors") or []), {})
            return {
                "success": False,
                "resource_id": resource_id,
                "error_code": str(first_error.get("code") or "deployment_preflight_failed"),
                "msg": str(first_error.get("message") or "炮镜部署预检失败。"),
                "preview": preview,
            }

        if (
            change_existing
            and state["managed_by_aimerwt"]
            and state["state"] in {"enabled", "partial", "conflict"}
        ):
            disabled = self.disable_resource(resource_id, usersights)
            if not disabled.get("success"):
                return {
                    "success": False,
                    "resource_id": resource_id,
                    "error_code": "existing_deployment_conflict",
                    "msg": "旧部署包含用户修改或冲突文件，未迁移应用车辆。",
                    "conflicts": disabled.get("conflicts") or [],
                }

        usersights.mkdir(parents=True, exist_ok=True)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        now = self._now_iso()
        resource_files: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        copied_count = 0
        replaced_count = 0
        reused_count = 0
        restored_count = 0
        processed_count = 0
        canceled = False
        remaining_targets: list[dict[str, Any]] = []
        planned_targets = list(preview.get("file_targets") or [])
        managed_replace_targets = self._managed_package_upgrade_targets(
            resource,
            usersights,
            request.get("retained_file_targets"),
        )
        for target_index, target in enumerate(planned_targets):
            if callable(should_cancel) and should_cancel():
                canceled = True
                remaining_targets = planned_targets[target_index:]
                break
            source_rel = str(target.get("source_storage_relative_path") or target.get("source_relative_path") or "")
            target_rel = str(target.get("target_relative_path") or "")
            disabled_rel = self._disabled_relative_path(target_rel)
            source_file = self._path_from_posix(resource_dir, source_rel)
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            source_fp = self._file_fingerprint(source_file)
            target_fp = None
            conflict_reason = ""
            if target_file.exists() and disabled_file.exists():
                conflict_reason = "enabled_and_disabled_both_exist"
            elif target_file.exists():
                target_fp = self._file_fingerprint(target_file)
                if self._same_fingerprint(source_fp, target_fp):
                    reused_count += 1
                elif (
                    target_rel.lower() in managed_replace_targets
                    and isinstance(manifest.get("file_map", {}).get(target_rel), dict)
                    and self._same_fingerprint(
                        manifest["file_map"][target_rel],
                        target_fp,
                    )
                ):
                    try:
                        shutil.copy2(source_file, target_file)
                    except OSError as exc:
                        if not self._is_file_locked_error(exc):
                            raise
                        conflict_reason = "file_locked"
                    else:
                        target_fp = self._file_fingerprint(target_file)
                        replaced_count += 1
                else:
                    conflict_reason = "target_conflict"
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(source_fp, disabled_fp):
                    conflict_reason = "disabled_target_conflict"
                else:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        disabled_file.rename(target_file)
                    except OSError as exc:
                        if not self._is_file_locked_error(exc):
                            raise
                        conflict_reason = "file_locked"
                    else:
                        target_fp = self._file_fingerprint(target_file)
                        restored_count += 1
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source_file, target_file)
                except OSError as exc:
                    if not self._is_file_locked_error(exc):
                        raise
                    conflict_reason = "file_locked"
                else:
                    target_fp = self._file_fingerprint(target_file)
                    copied_count += 1
            base_entry = {
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
            }
            if conflict_reason:
                conflicts.append({"target_relative_path": target_rel, "reason": conflict_reason})
                base_entry.update({
                    "managed": False,
                    "conflict": True,
                    "conflict_reason": conflict_reason,
                    "file_status": "needs_attention",
                    "last_verified_at": now,
                })
                resource_files.append(base_entry)
                processed_count += 1
                if callable(progress_callback):
                    progress_callback({
                        "processed_count": processed_count,
                        "total_count": len(planned_targets),
                        "skipped_count": 0,
                    })
                continue
            resource_files.append(self._mark_entry_enabled(
                manifest,
                resource_id,
                target_rel,
                disabled_rel,
                target_fp,
                base_entry,
                now,
            ))
            processed_count += 1
            if callable(progress_callback):
                progress_callback({
                    "processed_count": processed_count,
                    "total_count": len(planned_targets),
                    "skipped_count": 0,
                })

        for target in remaining_targets:
            target_rel = str(target.get("target_relative_path") or "")
            source_rel = str(target.get("source_storage_relative_path") or target.get("source_relative_path") or "")
            if not target_rel or not source_rel:
                continue
            resource_files.append({
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
                "disabled_relative_path": self._disabled_relative_path(target_rel),
                "managed": False,
                "file_status": "canceled_before_write",
                "last_verified_at": now,
            })
        if canceled and callable(progress_callback):
            progress_callback({
                "processed_count": processed_count,
                "total_count": len(planned_targets),
                "skipped_count": len(remaining_targets),
            })

        new_target_paths = {
            str(item.get("target_relative_path") or "")
            for item in resource_files
            if str(item.get("target_relative_path") or "")
        }
        for old_entry in previous_targets:
            old_target = str(old_entry.get("target_relative_path") or "")
            if not old_target or old_target in new_target_paths:
                continue
            old_record = manifest.get("file_map", {}).get(old_target)
            if not isinstance(old_record, dict):
                continue
            remaining_owners = [
                str(owner)
                for owner in old_record.get("owners") or []
                if str(owner) and str(owner) != resource_id
            ]
            if remaining_owners:
                old_record["owners"] = remaining_owners
                old_record["updated_at"] = now
                manifest["file_map"][old_target] = old_record
            else:
                manifest["file_map"].pop(old_target, None)

        status = self._resource_status_from_files(resource_files, preferred_partial="enabled")
        existing_record = manifest.get("resources", {}).get(resource_id)
        if not isinstance(existing_record, dict):
            existing_record = {}
        deployment_targets = [{
            "source_relative_path": str(item.get("source_storage_relative_path") or item.get("source_relative_path") or ""),
            "target_relative_path": str(item.get("target_relative_path") or ""),
        } for item in preview.get("file_targets") or []]
        deployment = {
            "schema_version": 1,
            "mode": str(preview.get("mode") or request.get("mode") or ""),
            "source": "user_confirmed",
            "remember": bool(request.get("remember", True)),
            "selected_vehicle_ids": list(preview.get("selected_vehicle_ids") or []),
            "file_targets": deployment_targets,
            "updated_at": now,
        }
        if previous_targets:
            deployment["previous_file_targets"] = [{
                "source_relative_path": str(item.get("source_relative_path") or ""),
                "target_relative_path": str(item.get("target_relative_path") or ""),
                "disabled_relative_path": str(item.get("disabled_relative_path") or ""),
            } for item in previous_targets]
        existing_record.update({
            "resource_id": resource_id,
            "resource_type": str(resource.get("resource_type") or existing_record.get("resource_type") or "single"),
            "display_name": str(resource.get("display_name") or existing_record.get("display_name") or resource_id),
            "installed_at": existing_record.get("installed_at") or now,
            "updated_at": now,
            "status": status,
            "baseline_source": "aimerwt_resource",
            "expected_file_count": len(resource_files),
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "files": resource_files,
            "deployment": deployment,
        })
        manifest["resources"][resource_id] = existing_record
        self.save_manifest(usersights, manifest)
        return {
            "success": not conflicts,
            "resource_id": resource_id,
            "action": "deployment_applied",
            "installed_count": len(resource_files) - len(conflicts),
            "copied_count": copied_count,
            "replaced_count": replaced_count,
            "reused_count": reused_count,
            "restored_count": restored_count,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "install_status": status,
            "deployment": deployment,
            "preview": preview,
            "canceled": canceled,
            "processed_count": processed_count,
            "total_count": len(planned_targets),
            "skipped_count": len(remaining_targets),
        }

    def _persist_legacy_deployment(self, resource_id: str, usersights_path: str | Path) -> None:
        manifest = self.load_manifest(usersights_path)
        record = manifest.get("resources", {}).get(resource_id)
        if not isinstance(record, dict) or isinstance(record.get("deployment"), dict):
            return
        files = [item for item in record.get("files") or [] if isinstance(item, dict)]
        record["deployment"] = self._legacy_deployment_from_files(files)
        record["updated_at"] = self._now_iso()
        manifest["resources"][resource_id] = record
        self.save_manifest(usersights_path, manifest)
    @_locked_manifest_write
    def install_resource(self, resource_id: str, usersights_path: str | Path) -> dict[str, Any]:
        usersights = Path(usersights_path)
        usersights.mkdir(parents=True, exist_ok=True)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        files = [entry for entry in resource.get("files", []) if isinstance(entry, dict)]

        installed_count = 0
        copied_count = 0
        reused_count = 0
        restored_count = 0
        conflicts: list[dict[str, str]] = []
        resource_files: list[dict[str, Any]] = []
        now = self._now_iso()

        for entry in files:
            source_rel = str(entry.get("source_relative_path") or "")
            target_rel = str(entry.get("target_relative_path") or "")
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            source_file = self._path_from_posix(resource_dir, source_rel)
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            if not source_file.exists():
                conflicts.append({"target_relative_path": target_rel, "reason": "source_missing"})
                resource_files.append({
                    "source_relative_path": source_rel,
                    "target_relative_path": target_rel,
                    "disabled_relative_path": disabled_rel,
                    "managed": False,
                    "conflict": True,
                    "conflict_reason": "source_missing",
                    "file_status": "needs_attention",
                    "last_verified_at": now,
                })
                continue

            source_fp = self._file_fingerprint(source_file)
            target_fp = None
            if target_file.exists() and disabled_file.exists():
                conflict = {"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"}
                conflicts.append(conflict)
                resource_files.append({
                    "source_relative_path": source_rel,
                    "target_relative_path": target_rel,
                    "disabled_relative_path": disabled_rel,
                    "size": source_fp["size"],
                    "mtime_ns": source_fp["mtime_ns"],
                    "sha1": source_fp["sha1"],
                    "managed": False,
                    "conflict": True,
                    "conflict_reason": "enabled_and_disabled_both_exist",
                    "file_status": "needs_attention",
                    "last_verified_at": now,
                })
                continue
            if target_file.exists():
                target_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(source_fp, target_fp):
                    conflict = {"target_relative_path": target_rel, "reason": "target_conflict"}
                    conflicts.append(conflict)
                    resource_files.append({
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "conflict": True,
                        "conflict_reason": "target_conflict",
                        "file_status": "needs_attention",
                        "last_verified_at": now,
                    })
                    continue
                reused_count += 1
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(source_fp, disabled_fp):
                    conflict = {"target_relative_path": target_rel, "reason": "disabled_target_conflict"}
                    conflicts.append(conflict)
                    resource_files.append({
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "conflict": True,
                        "conflict_reason": "disabled_target_conflict",
                        "file_status": "needs_attention",
                        "last_verified_at": now,
                    })
                    continue
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    disabled_file.rename(target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    locked_entry = {
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "last_verified_at": now,
                    }
                    self._record_file_locked_conflict(conflicts, target_rel, locked_entry)
                    resource_files.append(locked_entry)
                    continue
                target_fp = self._file_fingerprint(target_file)
                restored_count += 1
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source_file, target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    locked_entry = {
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "last_verified_at": now,
                    }
                    self._record_file_locked_conflict(conflicts, target_rel, locked_entry)
                    resource_files.append(locked_entry)
                    continue
                target_fp = self._file_fingerprint(target_file)
                copied_count += 1

            installed_count += 1
            resource_files.append(self._mark_entry_enabled(
                manifest,
                resource_id,
                target_rel,
                disabled_rel,
                target_fp,
                {
                    "source_relative_path": source_rel,
                    "target_relative_path": target_rel,
                    "disabled_relative_path": disabled_rel,
                },
                now,
            ))

        expected_count = len(files)
        if conflicts and not installed_count:
            status = "needs_attention"
        else:
            status = "enabled" if expected_count and installed_count == expected_count else "partial_enabled" if installed_count else "disabled"
        manifest["resources"][resource_id] = {
            "resource_id": resource_id,
            "resource_type": str(resource.get("resource_type") or "single"),
            "display_name": str(resource.get("display_name") or resource_id),
            "installed_at": manifest["resources"].get(resource_id, {}).get("installed_at") or now,
            "updated_at": now,
            "status": status,
            "baseline_source": "aimerwt_resource",
            "expected_file_count": expected_count,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "files": resource_files,
        }
        self.save_manifest(usersights, manifest)
        return {
            "success": len(conflicts) == 0,
            "resource_id": resource_id,
            "installed_count": installed_count,
            "copied_count": copied_count,
            "reused_count": reused_count,
            "restored_count": restored_count,
            "expected_file_count": expected_count,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "install_status": status,
        }

    @_locked_manifest_write
    def install_resource_files(
        self,
        resource_id: str,
        usersights_path: str | Path,
        target_relative_paths: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        usersights.mkdir(parents=True, exist_ok=True)
        selected_targets = self._normalize_target_filter(target_relative_paths)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        files = [entry for entry in resource.get("files", []) if isinstance(entry, dict)]
        existing_record = manifest["resources"].get(resource_id)
        if not isinstance(existing_record, dict):
            existing_record = {
                "resource_id": resource_id,
                "resource_type": str(resource.get("resource_type") or "single"),
                "display_name": str(resource.get("display_name") or resource_id),
                "installed_at": self._now_iso(),
                "status": "disabled",
                "baseline_source": "aimerwt_resource",
                "files": [],
                "conflicts": [],
                "conflict_count": 0,
            }
        existing_by_target = {
            str(entry.get("target_relative_path") or ""): dict(entry)
            for entry in existing_record.get("files") or []
            if isinstance(entry, dict)
        }

        installed_count = 0
        copied_count = 0
        reused_count = 0
        restored_count = 0
        missing_count = 0
        conflict_count = 0
        conflicts: list[dict[str, str]] = []
        resource_files: list[dict[str, Any]] = []
        matched_targets: set[str] = set()
        now = self._now_iso()

        for source_entry in files:
            source_rel = str(source_entry.get("source_relative_path") or "")
            target_rel = str(source_entry.get("target_relative_path") or "")
            if not target_rel:
                continue
            disabled_rel = str(source_entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            updated_entry = dict(existing_by_target.get(target_rel) or {
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
                "file_status": "pending_install",
                "managed": False,
            })
            updated_entry["source_relative_path"] = str(updated_entry.get("source_relative_path") or source_rel)
            updated_entry["target_relative_path"] = target_rel
            updated_entry["disabled_relative_path"] = str(updated_entry.get("disabled_relative_path") or disabled_rel)

            if target_rel not in selected_targets:
                resource_files.append(updated_entry)
                continue
            matched_targets.add(target_rel)
            source_file = self._path_from_posix(resource_dir, source_rel)
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, updated_entry["disabled_relative_path"])
            if not source_file.exists():
                missing_count += 1
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "source_missing"})
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "source_missing"
                resource_files.append(updated_entry)
                continue

            source_fp = self._file_fingerprint(source_file)
            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"})
                updated_entry.update({
                    "size": source_fp["size"],
                    "mtime_ns": source_fp["mtime_ns"],
                    "sha1": source_fp["sha1"],
                    "managed": False,
                    "conflict": True,
                    "conflict_reason": "enabled_and_disabled_both_exist",
                    "file_status": "needs_attention",
                    "last_verified_at": now,
                })
                resource_files.append(updated_entry)
                continue
            if target_file.exists():
                target_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(source_fp, target_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "target_conflict"})
                    updated_entry.update({
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "conflict": True,
                        "conflict_reason": "target_conflict",
                        "file_status": "needs_attention",
                        "last_verified_at": now,
                    })
                    resource_files.append(updated_entry)
                    continue
                reused_count += 1
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(source_fp, disabled_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "disabled_target_conflict"})
                    updated_entry.update({
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "conflict": True,
                        "conflict_reason": "disabled_target_conflict",
                        "file_status": "needs_attention",
                        "last_verified_at": now,
                    })
                    resource_files.append(updated_entry)
                    continue
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    disabled_file.rename(target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    updated_entry.update({
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "last_verified_at": now,
                    })
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    resource_files.append(updated_entry)
                    continue
                target_fp = self._file_fingerprint(target_file)
                restored_count += 1
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source_file, target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    updated_entry.update({
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "last_verified_at": now,
                    })
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    resource_files.append(updated_entry)
                    continue
                target_fp = self._file_fingerprint(target_file)
                copied_count += 1

            installed_count += 1
            resource_files.append(self._mark_entry_enabled(
                manifest,
                resource_id,
                target_rel,
                updated_entry["disabled_relative_path"],
                target_fp,
                {
                    "source_relative_path": updated_entry["source_relative_path"],
                    "target_relative_path": target_rel,
                    "disabled_relative_path": updated_entry["disabled_relative_path"],
                },
                now,
            ))

        missing_targets = sorted(selected_targets - matched_targets)
        for target_rel in missing_targets:
            conflict_count += 1
            conflicts.append({"target_relative_path": target_rel, "reason": "target_not_in_resource"})

        status = self._resource_status_from_files(resource_files, preferred_partial="enabled")
        existing_record.update({
            "resource_id": resource_id,
            "resource_type": str(resource.get("resource_type") or existing_record.get("resource_type") or "single"),
            "display_name": str(resource.get("display_name") or existing_record.get("display_name") or resource_id),
            "updated_at": now,
            "status": status,
            "baseline_source": str(existing_record.get("baseline_source") or "aimerwt_resource"),
            "expected_file_count": len(resource_files),
            "conflict_count": conflict_count,
            "conflicts": conflicts,
            "files": resource_files,
        })
        manifest["resources"][resource_id] = existing_record
        self.save_manifest(usersights, manifest)
        return {
            "success": not (conflict_count or missing_count),
            "resource_id": resource_id,
            "installed_count": installed_count,
            "copied_count": copied_count,
            "reused_count": reused_count,
            "restored_count": restored_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count,
            "conflicts": conflicts,
            "install_status": status,
            "selected_count": len(selected_targets),
        }

    def enable_resource_files(
        self,
        resource_id: str,
        usersights_path: str | Path,
        target_relative_paths: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, Any]:
        return self.install_resource_files(resource_id, usersights_path, target_relative_paths)

    @_locked_manifest_write
    def install_resource_batched(
        self,
        resource_id: str,
        usersights_path: str | Path,
        should_cancel: Any = None,
        progress_callback: Any = None,
        chunk_size: int = 300,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        usersights.mkdir(parents=True, exist_ok=True)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        files = [entry for entry in resource.get("files", []) if isinstance(entry, dict)]
        total_count = len(files)

        installed_count = 0
        copied_count = 0
        reused_count = 0
        restored_count = 0
        conflict_count = 0
        processed_count = 0
        skipped_count = 0
        canceled = False
        conflicts: list[dict[str, str]] = []
        resource_files: list[dict[str, Any]] = []
        now = self._now_iso()
        existing_record = manifest["resources"].get(resource_id)
        if not isinstance(existing_record, dict):
            existing_record = {}
        chunk_size = max(1, int(chunk_size or 300))

        def _pending_install_entry(source_entry: dict[str, Any]) -> dict[str, Any]:
            target_rel = str(source_entry.get("target_relative_path") or "")
            return {
                "source_relative_path": str(source_entry.get("source_relative_path") or ""),
                "target_relative_path": target_rel,
                "disabled_relative_path": str(source_entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel)),
                "file_status": "pending_install",
                "managed": False,
                "last_verified_at": now,
            }

        def _status(expected_count: int) -> str:
            if conflict_count and not installed_count:
                return "needs_attention"
            if expected_count and installed_count == expected_count:
                return "enabled"
            if installed_count:
                return "partial_enabled"
            return "disabled"

        def _commit(remaining_entries: list[dict[str, Any]]) -> None:
            entries = resource_files + [_pending_install_entry(entry) for entry in remaining_entries]
            status = _status(len(entries))
            manifest["resources"][resource_id] = {
                "resource_id": resource_id,
                "resource_type": str(resource.get("resource_type") or "single"),
                "display_name": str(resource.get("display_name") or resource_id),
                "installed_at": existing_record.get("installed_at") or now,
                "updated_at": self._now_iso(),
                "status": status,
                "baseline_source": "aimerwt_resource",
                "expected_file_count": total_count,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
                "files": entries,
            }
            self.save_manifest(usersights, manifest)

        def _notify() -> None:
            if not progress_callback:
                return
            try:
                progress_callback({
                    "resource_id": resource_id,
                    "total_count": total_count,
                    "processed_count": processed_count,
                    "skipped_count": skipped_count,
                    "installed_count": installed_count,
                    "copied_count": copied_count,
                    "reused_count": reused_count,
                    "restored_count": restored_count,
                    "conflict_count": conflict_count,
                    "canceled": canceled,
                })
            except Exception:
                log.debug("炮镜分批安装进度回调失败", exc_info=True)

        for index, entry in enumerate(files):
            if should_cancel and should_cancel():
                canceled = True
                skipped_count = total_count - processed_count
                _commit(files[index:])
                _notify()
                break

            source_rel = str(entry.get("source_relative_path") or "")
            target_rel = str(entry.get("target_relative_path") or "")
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            source_file = self._path_from_posix(resource_dir, source_rel)
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)

            if not source_rel or not target_rel or not source_file.exists():
                reason = "source_missing" if source_rel and target_rel else "invalid_install_entry"
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": reason})
                conflict_entry = _pending_install_entry(entry)
                conflict_entry.update({
                    "conflict": True,
                    "conflict_reason": reason,
                    "file_status": "needs_attention",
                })
                resource_files.append(conflict_entry)
                processed_count += 1
                if processed_count % chunk_size == 0:
                    _commit(files[index + 1:])
                _notify()
                continue

            source_fp = self._file_fingerprint(source_file)
            target_fp = None
            if target_file.exists() and disabled_file.exists():
                reason = "enabled_and_disabled_both_exist"
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": reason})
                resource_files.append({
                    "source_relative_path": source_rel,
                    "target_relative_path": target_rel,
                    "disabled_relative_path": disabled_rel,
                    "size": source_fp["size"],
                    "mtime_ns": source_fp["mtime_ns"],
                    "sha1": source_fp["sha1"],
                    "managed": False,
                    "conflict": True,
                    "conflict_reason": reason,
                    "file_status": "needs_attention",
                    "last_verified_at": now,
                })
                processed_count += 1
                if processed_count % chunk_size == 0:
                    _commit(files[index + 1:])
                _notify()
                continue
            if target_file.exists():
                target_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(source_fp, target_fp):
                    reason = "target_conflict"
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": reason})
                    resource_files.append({
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "conflict": True,
                        "conflict_reason": reason,
                        "file_status": "needs_attention",
                        "last_verified_at": now,
                    })
                    processed_count += 1
                    if processed_count % chunk_size == 0:
                        _commit(files[index + 1:])
                    _notify()
                    continue
                reused_count += 1
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(source_fp, disabled_fp):
                    reason = "disabled_target_conflict"
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": reason})
                    resource_files.append({
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "conflict": True,
                        "conflict_reason": reason,
                        "file_status": "needs_attention",
                        "last_verified_at": now,
                    })
                    processed_count += 1
                    if processed_count % chunk_size == 0:
                        _commit(files[index + 1:])
                    _notify()
                    continue
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    disabled_file.rename(target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    locked_entry = {
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "last_verified_at": now,
                    }
                    self._record_file_locked_conflict(conflicts, target_rel, locked_entry)
                    resource_files.append(locked_entry)
                    processed_count += 1
                    if processed_count % chunk_size == 0:
                        _commit(files[index + 1:])
                    _notify()
                    continue
                target_fp = self._file_fingerprint(target_file)
                restored_count += 1
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source_file, target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    locked_entry = {
                        "source_relative_path": source_rel,
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "size": source_fp["size"],
                        "mtime_ns": source_fp["mtime_ns"],
                        "sha1": source_fp["sha1"],
                        "managed": False,
                        "last_verified_at": now,
                    }
                    self._record_file_locked_conflict(conflicts, target_rel, locked_entry)
                    resource_files.append(locked_entry)
                    processed_count += 1
                    if processed_count % chunk_size == 0:
                        _commit(files[index + 1:])
                    _notify()
                    continue
                target_fp = self._file_fingerprint(target_file)
                copied_count += 1

            installed_count += 1
            resource_files.append(self._mark_entry_enabled(
                manifest,
                resource_id,
                target_rel,
                disabled_rel,
                target_fp,
                {
                    "source_relative_path": source_rel,
                    "target_relative_path": target_rel,
                    "disabled_relative_path": disabled_rel,
                },
                now,
            ))
            processed_count += 1
            if processed_count % chunk_size == 0:
                _commit(files[index + 1:])
            _notify()

        if not canceled:
            skipped_count = 0
            _commit([])

        resource_record = manifest["resources"].get(resource_id)
        status = str(resource_record.get("status") if isinstance(resource_record, dict) else _status(total_count))
        return {
            "success": not (canceled or conflicts),
            "resource_id": resource_id,
            "installed_count": installed_count,
            "copied_count": copied_count,
            "reused_count": reused_count,
            "restored_count": restored_count,
            "expected_file_count": total_count,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "processed_count": processed_count,
            "total_count": total_count,
            "skipped_count": skipped_count,
            "canceled": canceled,
            "install_status": status,
        }

    @_locked_manifest_write
    def disable_resource_files(
        self,
        resource_id: str,
        usersights_path: str | Path,
        target_relative_paths: list[str] | tuple[str, ...] | set[str],
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        selected_targets = self._normalize_target_filter(target_relative_paths)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"安装记录不存在: {resource_id}")

        renamed_count = 0
        already_disabled_count = 0
        modified_count = 0
        missing_count = 0
        conflict_count = 0
        kept_shared_count = 0
        updated_files: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        matched_targets: set[str] = set()
        now = self._now_iso()

        for entry in list(resource_record.get("files") or []):
            if not isinstance(entry, dict):
                continue
            updated_entry = dict(entry)
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                updated_files.append(updated_entry)
                continue
            if target_rel not in selected_targets:
                updated_files.append(updated_entry)
                continue
            matched_targets.add(target_rel)
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            file_record = manifest["file_map"].get(target_rel)
            baseline = file_record if isinstance(file_record, dict) else entry
            owners = []
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners", []) if str(owner)]
            other_owners = [owner for owner in owners if owner != resource_id]

            updated_entry["disabled_relative_path"] = disabled_rel
            if other_owners:
                if isinstance(file_record, dict):
                    file_record["owners"] = other_owners
                    file_record["updated_at"] = now
                    manifest["file_map"][target_rel] = file_record
                updated_entry["file_status"] = "disabled_shared"
                updated_entry["last_verified_at"] = now
                kept_shared_count += 1
                updated_files.append(updated_entry)
                continue

            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"})
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "enabled_and_disabled_both_exist"
                updated_files.append(updated_entry)
                continue

            if target_file.exists():
                current_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(baseline, current_fp):
                    modified_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "fingerprint_mismatch"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "fingerprint_mismatch"
                    updated_files.append(updated_entry)
                    continue
                disabled_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    target_file.rename(disabled_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    updated_files.append(updated_entry)
                    continue
                renamed_count += 1
                disabled_fp = self._file_fingerprint(disabled_file)
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(baseline, disabled_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "disabled_target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "disabled_target_conflict"
                    updated_files.append(updated_entry)
                    continue
                already_disabled_count += 1
            else:
                missing_count += 1
                updated_entry["file_status"] = "missing"
                updated_files.append(updated_entry)
                continue

            manifest["file_map"][target_rel] = {
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
                "file_status": "disabled_by_rename",
                "size": disabled_fp["size"],
                "mtime_ns": disabled_fp["mtime_ns"],
                "sha1": disabled_fp["sha1"],
                "owners": [resource_id],
                "updated_at": now,
            }
            updated_entry.update({
                "disabled_relative_path": disabled_rel,
                "file_status": "disabled_by_rename",
                "size": disabled_fp["size"],
                "mtime_ns": disabled_fp["mtime_ns"],
                "sha1": disabled_fp["sha1"],
                "managed": True,
                "conflict": False,
                "conflict_reason": "",
                "last_verified_at": now,
            })
            updated_files.append(updated_entry)

        missing_targets = sorted(selected_targets - matched_targets)
        for target_rel in missing_targets:
            conflict_count += 1
            conflicts.append({"target_relative_path": target_rel, "reason": "target_not_in_resource"})

        status = self._resource_status_from_files(updated_files, preferred_partial="disabled")
        resource_record["files"] = updated_files
        resource_record["status"] = status
        resource_record["conflict_count"] = conflict_count + modified_count
        resource_record["conflicts"] = conflicts
        resource_record["updated_at"] = now
        manifest["resources"][resource_id] = resource_record
        self.save_manifest(usersights, manifest)
        return {
            "success": not (modified_count or conflict_count or missing_count),
            "resource_id": resource_id,
            "renamed_count": renamed_count,
            "already_disabled_count": already_disabled_count,
            "modified_count": modified_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count + modified_count,
            "kept_shared_count": kept_shared_count,
            "install_status": status,
            "conflicts": conflicts,
            "selected_count": len(selected_targets),
        }

    @_locked_manifest_write
    def disable_resource(self, resource_id: str, usersights_path: str | Path) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"安装记录不存在: {resource_id}")

        renamed_count = 0
        already_disabled_count = 0
        modified_count = 0
        missing_count = 0
        conflict_count = 0
        kept_shared_count = 0
        updated_files: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        now = self._now_iso()

        for entry in list(resource_record.get("files") or []):
            if not isinstance(entry, dict):
                continue
            updated_entry = dict(entry)
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                updated_files.append(updated_entry)
                continue
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            file_record = manifest["file_map"].get(target_rel)
            baseline = file_record if isinstance(file_record, dict) else entry
            owners = []
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners", []) if str(owner)]
            other_owners = [owner for owner in owners if owner != resource_id]

            updated_entry["disabled_relative_path"] = disabled_rel
            if other_owners:
                if isinstance(file_record, dict):
                    file_record["owners"] = other_owners
                    file_record["updated_at"] = now
                    manifest["file_map"][target_rel] = file_record
                updated_entry["file_status"] = "disabled_shared"
                updated_entry["last_verified_at"] = now
                kept_shared_count += 1
                updated_files.append(updated_entry)
                continue

            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"})
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "enabled_and_disabled_both_exist"
                updated_files.append(updated_entry)
                continue

            if target_file.exists():
                current_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(baseline, current_fp):
                    modified_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "fingerprint_mismatch"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "fingerprint_mismatch"
                    updated_files.append(updated_entry)
                    continue
                disabled_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    target_file.rename(disabled_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    updated_files.append(updated_entry)
                    continue
                renamed_count += 1
                disabled_fp = self._file_fingerprint(disabled_file)
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(baseline, disabled_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "disabled_target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "disabled_target_conflict"
                    updated_files.append(updated_entry)
                    continue
                already_disabled_count += 1
            else:
                missing_count += 1
                updated_entry["file_status"] = "missing"
                updated_files.append(updated_entry)
                continue

            file_record = {
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
                "file_status": "disabled_by_rename",
                "size": disabled_fp["size"],
                "mtime_ns": disabled_fp["mtime_ns"],
                "sha1": disabled_fp["sha1"],
                "owners": [resource_id],
                "updated_at": now,
            }
            manifest["file_map"][target_rel] = file_record
            updated_entry.update({
                "disabled_relative_path": disabled_rel,
                "file_status": "disabled_by_rename",
                "size": disabled_fp["size"],
                "mtime_ns": disabled_fp["mtime_ns"],
                "sha1": disabled_fp["sha1"],
                "managed": True,
                "conflict": False,
                "conflict_reason": "",
                "last_verified_at": now,
            })
            updated_files.append(updated_entry)

        expected_count = len(updated_files)
        disabled_count = renamed_count + already_disabled_count + kept_shared_count
        if modified_count or conflict_count:
            status = "needs_attention"
        elif expected_count and disabled_count == expected_count:
            status = "disabled_by_rename"
        elif disabled_count:
            status = "partial_disabled"
        else:
            status = "disabled"

        resource_record["files"] = updated_files
        resource_record["status"] = status
        resource_record["conflict_count"] = conflict_count + modified_count
        resource_record["conflicts"] = conflicts
        resource_record["updated_at"] = now
        manifest["resources"][resource_id] = resource_record
        self.save_manifest(usersights, manifest)
        return {
            "success": not (modified_count or conflict_count or missing_count),
            "resource_id": resource_id,
            "renamed_count": renamed_count,
            "already_disabled_count": already_disabled_count,
            "modified_count": modified_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count + modified_count,
            "kept_shared_count": kept_shared_count,
            "install_status": status,
            "conflicts": conflicts,
        }

    @_locked_manifest_write
    def disable_resource_batched(
        self,
        resource_id: str,
        usersights_path: str | Path,
        should_cancel: Any = None,
        progress_callback: Any = None,
        chunk_size: int = 300,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"安装记录不存在: {resource_id}")

        files = [entry for entry in list(resource_record.get("files") or []) if isinstance(entry, dict)]
        total_count = len(files)
        updated_files: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        renamed_count = 0
        already_disabled_count = 0
        modified_count = 0
        missing_count = 0
        conflict_count = 0
        kept_shared_count = 0
        processed_count = 0
        skipped_count = 0
        canceled = False
        now = self._now_iso()
        chunk_size = max(1, int(chunk_size or 300))

        def _current_status(expected_count: int) -> str:
            disabled_count = renamed_count + already_disabled_count + kept_shared_count
            if modified_count or conflict_count:
                return "needs_attention"
            if expected_count and disabled_count == expected_count:
                return "disabled_by_rename"
            if disabled_count:
                return "partial_disabled"
            return "disabled"

        def _commit(remaining_entries: list[dict[str, Any]]) -> None:
            expected_count = len(updated_files) + len(remaining_entries)
            status = _current_status(expected_count)
            resource_record["files"] = updated_files + [dict(entry) for entry in remaining_entries]
            resource_record["status"] = status
            resource_record["conflict_count"] = conflict_count + modified_count
            resource_record["conflicts"] = conflicts
            resource_record["updated_at"] = self._now_iso()
            manifest["resources"][resource_id] = resource_record
            self.save_manifest(usersights, manifest)

        def _notify() -> None:
            if not progress_callback:
                return
            try:
                progress_callback({
                    "resource_id": resource_id,
                    "total_count": total_count,
                    "processed_count": processed_count,
                    "skipped_count": skipped_count,
                    "renamed_count": renamed_count,
                    "already_disabled_count": already_disabled_count,
                    "modified_count": modified_count,
                    "missing_count": missing_count,
                    "conflict_count": conflict_count + modified_count,
                    "kept_shared_count": kept_shared_count,
                    "canceled": canceled,
                })
            except Exception:
                log.debug("炮镜分批停用进度回调失败", exc_info=True)

        for index, entry in enumerate(files):
            if should_cancel and should_cancel():
                canceled = True
                skipped_count = total_count - processed_count
                _commit(files[index:])
                _notify()
                break

            updated_entry = dict(entry)
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                updated_files.append(updated_entry)
                processed_count += 1
                _notify()
                continue
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            file_record = manifest["file_map"].get(target_rel)
            baseline = file_record if isinstance(file_record, dict) else entry
            owners = []
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners", []) if str(owner)]
            other_owners = [owner for owner in owners if owner != resource_id]

            updated_entry["disabled_relative_path"] = disabled_rel
            if other_owners:
                if isinstance(file_record, dict):
                    file_record["owners"] = other_owners
                    file_record["updated_at"] = now
                    manifest["file_map"][target_rel] = file_record
                updated_entry["file_status"] = "disabled_shared"
                updated_entry["last_verified_at"] = now
                kept_shared_count += 1
                updated_files.append(updated_entry)
            elif target_file.exists() and disabled_file.exists():
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"})
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "enabled_and_disabled_both_exist"
                updated_files.append(updated_entry)
            elif target_file.exists():
                current_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(baseline, current_fp):
                    modified_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "fingerprint_mismatch"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "fingerprint_mismatch"
                    updated_files.append(updated_entry)
                else:
                    disabled_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        target_file.rename(disabled_file)
                    except OSError as e:
                        if not self._is_file_locked_error(e):
                            raise
                        conflict_count += 1
                        self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                        updated_files.append(updated_entry)
                    else:
                        renamed_count += 1
                        disabled_fp = self._file_fingerprint(disabled_file)
                        file_record = {
                            "target_relative_path": target_rel,
                            "disabled_relative_path": disabled_rel,
                            "file_status": "disabled_by_rename",
                            "size": disabled_fp["size"],
                            "mtime_ns": disabled_fp["mtime_ns"],
                            "sha1": disabled_fp["sha1"],
                            "owners": [resource_id],
                            "updated_at": now,
                        }
                        manifest["file_map"][target_rel] = file_record
                        updated_entry.update({
                            "disabled_relative_path": disabled_rel,
                            "file_status": "disabled_by_rename",
                            "size": disabled_fp["size"],
                            "mtime_ns": disabled_fp["mtime_ns"],
                            "sha1": disabled_fp["sha1"],
                            "managed": True,
                            "conflict": False,
                            "conflict_reason": "",
                            "last_verified_at": now,
                        })
                        updated_files.append(updated_entry)
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(baseline, disabled_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "disabled_target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "disabled_target_conflict"
                    updated_files.append(updated_entry)
                else:
                    already_disabled_count += 1
                    file_record = {
                        "target_relative_path": target_rel,
                        "disabled_relative_path": disabled_rel,
                        "file_status": "disabled_by_rename",
                        "size": disabled_fp["size"],
                        "mtime_ns": disabled_fp["mtime_ns"],
                        "sha1": disabled_fp["sha1"],
                        "owners": [resource_id],
                        "updated_at": now,
                    }
                    manifest["file_map"][target_rel] = file_record
                    updated_entry.update({
                        "disabled_relative_path": disabled_rel,
                        "file_status": "disabled_by_rename",
                        "size": disabled_fp["size"],
                        "mtime_ns": disabled_fp["mtime_ns"],
                        "sha1": disabled_fp["sha1"],
                        "managed": True,
                        "conflict": False,
                        "conflict_reason": "",
                        "last_verified_at": now,
                    })
                    updated_files.append(updated_entry)
            else:
                missing_count += 1
                updated_entry["file_status"] = "missing"
                updated_files.append(updated_entry)

            processed_count += 1
            if processed_count % chunk_size == 0:
                _commit(files[index + 1:])
            _notify()

        if not canceled:
            skipped_count = 0
            _commit([])

        status = str(resource_record.get("status") or _current_status(total_count))
        return {
            "success": not (canceled or modified_count or conflict_count or missing_count),
            "resource_id": resource_id,
            "renamed_count": renamed_count,
            "already_disabled_count": already_disabled_count,
            "modified_count": modified_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count + modified_count,
            "kept_shared_count": kept_shared_count,
            "processed_count": processed_count,
            "total_count": total_count,
            "skipped_count": skipped_count,
            "canceled": canceled,
            "install_status": status,
            "conflicts": conflicts,
        }

    @_locked_manifest_write
    def enable_resource(self, resource_id: str, usersights_path: str | Path) -> dict[str, Any]:
        usersights = Path(usersights_path)
        usersights.mkdir(parents=True, exist_ok=True)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"安装记录不存在: {resource_id}")

        resource_files_by_target = {
            str(entry.get("target_relative_path") or ""): entry
            for entry in resource.get("files", [])
            if isinstance(entry, dict)
        }
        renamed_count = 0
        copied_count = 0
        reused_count = 0
        missing_count = 0
        conflict_count = 0
        updated_files: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        now = self._now_iso()

        for entry in list(resource_record.get("files") or []):
            if not isinstance(entry, dict):
                continue
            updated_entry = dict(entry)
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                updated_files.append(updated_entry)
                continue
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            source_entry = resource_files_by_target.get(target_rel) or {}
            source_rel = str(source_entry.get("source_relative_path") or entry.get("source_relative_path") or "")
            source_file = self._path_from_posix(resource_dir, source_rel) if source_rel else None
            baseline = manifest.get("file_map", {}).get(target_rel)
            if not isinstance(baseline, dict):
                baseline = entry

            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"})
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "enabled_and_disabled_both_exist"
                updated_files.append(updated_entry)
                continue

            if target_file.exists():
                target_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(baseline, target_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "target_conflict"
                    updated_files.append(updated_entry)
                    continue
                reused_count += 1
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(baseline, disabled_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "disabled_target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "disabled_target_conflict"
                    updated_files.append(updated_entry)
                    continue
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    disabled_file.rename(target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    updated_files.append(updated_entry)
                    continue
                target_fp = self._file_fingerprint(target_file)
                renamed_count += 1
            elif source_file and source_file.exists():
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source_file, target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    updated_files.append(updated_entry)
                    continue
                target_fp = self._file_fingerprint(target_file)
                copied_count += 1
            else:
                missing_count += 1
                updated_entry["file_status"] = "missing"
                updated_files.append(updated_entry)
                continue

            file_record = manifest["file_map"].get(target_rel)
            if not isinstance(file_record, dict):
                file_record = {"target_relative_path": target_rel, "owners": []}
            owners = [str(owner) for owner in file_record.get("owners", []) if str(owner)]
            if resource_id not in owners:
                owners.append(resource_id)
            file_record.update({
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
                "file_status": "enabled",
                "size": target_fp["size"],
                "mtime_ns": target_fp["mtime_ns"],
                "sha1": target_fp["sha1"],
                "owners": owners,
                "updated_at": now,
            })
            manifest["file_map"][target_rel] = file_record
            updated_entry.update({
                "disabled_relative_path": disabled_rel,
                "file_status": "enabled",
                "size": target_fp["size"],
                "mtime_ns": target_fp["mtime_ns"],
                "sha1": target_fp["sha1"],
                "managed": True,
                "conflict": False,
                "conflict_reason": "",
                "last_verified_at": now,
            })
            updated_files.append(updated_entry)

        expected_count = len(updated_files)
        enabled_count = renamed_count + copied_count + reused_count
        if conflict_count:
            status = "needs_attention"
        elif expected_count and enabled_count == expected_count:
            status = "enabled"
        elif enabled_count:
            status = "partial_enabled"
        else:
            status = "disabled"

        resource_record["files"] = updated_files
        resource_record["status"] = status
        resource_record["conflict_count"] = conflict_count
        resource_record["conflicts"] = conflicts
        resource_record["updated_at"] = now
        if not isinstance(resource_record.get("deployment"), dict):
            resource_record["deployment"] = self._legacy_deployment_from_files(updated_files)
        manifest["resources"][resource_id] = resource_record
        self.save_manifest(usersights, manifest)
        return {
            "success": not (conflict_count or missing_count),
            "resource_id": resource_id,
            "renamed_count": renamed_count,
            "copied_count": copied_count,
            "reused_count": reused_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count,
            "install_status": status,
            "conflicts": conflicts,
        }

    @_locked_manifest_write
    def enable_resource_batched(
        self,
        resource_id: str,
        usersights_path: str | Path,
        should_cancel: Any = None,
        progress_callback: Any = None,
        chunk_size: int = 300,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        usersights.mkdir(parents=True, exist_ok=True)
        resource, resource_dir = self.load_resource(resource_id)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"安装记录不存在: {resource_id}")

        resource_files_by_target = {
            str(entry.get("target_relative_path") or ""): entry
            for entry in resource.get("files", [])
            if isinstance(entry, dict)
        }
        files = [entry for entry in list(resource_record.get("files") or []) if isinstance(entry, dict)]
        total_count = len(files)
        updated_files: list[dict[str, Any]] = []
        conflicts: list[dict[str, str]] = []
        renamed_count = 0
        copied_count = 0
        reused_count = 0
        missing_count = 0
        conflict_count = 0
        processed_count = 0
        skipped_count = 0
        canceled = False
        now = self._now_iso()
        chunk_size = max(1, int(chunk_size or 300))

        def _current_status(entries: list[dict[str, Any]]) -> str:
            expected_count = len(entries)
            enabled_count = renamed_count + copied_count + reused_count
            if conflict_count:
                return "needs_attention"
            if expected_count and enabled_count == expected_count:
                return "enabled"
            if enabled_count:
                return "partial_enabled"
            disabled_count = sum(
                1
                for item in entries
                if str(item.get("file_status") or "") == "disabled_by_rename"
            )
            if expected_count and disabled_count == expected_count:
                return "disabled_by_rename"
            if disabled_count:
                return "partial_disabled"
            return "disabled"

        def _commit(remaining_entries: list[dict[str, Any]]) -> None:
            entries = updated_files + [dict(entry) for entry in remaining_entries]
            status = _current_status(entries)
            resource_record["files"] = entries
            resource_record["status"] = status
            resource_record["conflict_count"] = conflict_count
            resource_record["conflicts"] = conflicts
            resource_record["updated_at"] = self._now_iso()
            manifest["resources"][resource_id] = resource_record
            self.save_manifest(usersights, manifest)

        def _notify() -> None:
            if not progress_callback:
                return
            try:
                progress_callback({
                    "resource_id": resource_id,
                    "total_count": total_count,
                    "processed_count": processed_count,
                    "skipped_count": skipped_count,
                    "renamed_count": renamed_count,
                    "copied_count": copied_count,
                    "reused_count": reused_count,
                    "missing_count": missing_count,
                    "conflict_count": conflict_count,
                    "canceled": canceled,
                })
            except Exception:
                log.debug("炮镜分批启用进度回调失败", exc_info=True)

        for index, entry in enumerate(files):
            if should_cancel and should_cancel():
                canceled = True
                skipped_count = total_count - processed_count
                _commit(files[index:])
                _notify()
                break

            updated_entry = dict(entry)
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                updated_files.append(updated_entry)
                processed_count += 1
                _notify()
                continue

            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            source_entry = resource_files_by_target.get(target_rel) or {}
            source_rel = str(source_entry.get("source_relative_path") or entry.get("source_relative_path") or "")
            source_file = self._path_from_posix(resource_dir, source_rel) if source_rel else None
            baseline = manifest.get("file_map", {}).get(target_rel)
            if not isinstance(baseline, dict):
                baseline = entry

            updated_entry["disabled_relative_path"] = disabled_rel
            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
                conflicts.append({"target_relative_path": target_rel, "reason": "enabled_and_disabled_both_exist"})
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "enabled_and_disabled_both_exist"
                updated_files.append(updated_entry)
            elif target_file.exists():
                target_fp = self._file_fingerprint(target_file)
                if not self._same_fingerprint(baseline, target_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "target_conflict"
                    updated_files.append(updated_entry)
                else:
                    reused_count += 1
                    updated_entry = self._mark_entry_enabled(
                        manifest,
                        resource_id,
                        target_rel,
                        disabled_rel,
                        target_fp,
                        updated_entry,
                        now,
                    )
                    updated_files.append(updated_entry)
            elif disabled_file.exists():
                disabled_fp = self._file_fingerprint(disabled_file)
                if not self._same_fingerprint(baseline, disabled_fp):
                    conflict_count += 1
                    conflicts.append({"target_relative_path": target_rel, "reason": "disabled_target_conflict"})
                    updated_entry["file_status"] = "needs_attention"
                    updated_entry["conflict"] = True
                    updated_entry["conflict_reason"] = "disabled_target_conflict"
                    updated_files.append(updated_entry)
                else:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        disabled_file.rename(target_file)
                    except OSError as e:
                        if not self._is_file_locked_error(e):
                            raise
                        conflict_count += 1
                        self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                        updated_files.append(updated_entry)
                    else:
                        target_fp = self._file_fingerprint(target_file)
                        renamed_count += 1
                        updated_entry = self._mark_entry_enabled(
                            manifest,
                            resource_id,
                            target_rel,
                            disabled_rel,
                            target_fp,
                            updated_entry,
                            now,
                        )
                        updated_files.append(updated_entry)
            elif source_file and source_file.exists():
                target_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(source_file, target_file)
                except OSError as e:
                    if not self._is_file_locked_error(e):
                        raise
                    conflict_count += 1
                    self._record_file_locked_conflict(conflicts, target_rel, updated_entry)
                    updated_files.append(updated_entry)
                else:
                    target_fp = self._file_fingerprint(target_file)
                    copied_count += 1
                    updated_entry = self._mark_entry_enabled(
                        manifest,
                        resource_id,
                        target_rel,
                        disabled_rel,
                        target_fp,
                        updated_entry,
                        now,
                    )
                    updated_files.append(updated_entry)
            else:
                missing_count += 1
                updated_entry["file_status"] = "missing"
                updated_files.append(updated_entry)

            processed_count += 1
            if processed_count % chunk_size == 0:
                _commit(files[index + 1:])
            _notify()

        if not canceled:
            skipped_count = 0
            _commit([])

        status = str(resource_record.get("status") or _current_status(updated_files))
        return {
            "success": not (canceled or conflict_count or missing_count),
            "resource_id": resource_id,
            "renamed_count": renamed_count,
            "copied_count": copied_count,
            "reused_count": reused_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count,
            "processed_count": processed_count,
            "total_count": total_count,
            "skipped_count": skipped_count,
            "canceled": canceled,
            "install_status": status,
            "conflicts": conflicts,
        }

    def _mark_entry_enabled(
        self,
        manifest: dict[str, Any],
        resource_id: str,
        target_rel: str,
        disabled_rel: str,
        target_fp: dict[str, Any],
        entry: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        file_record = manifest["file_map"].get(target_rel)
        if not isinstance(file_record, dict) or not self._same_fingerprint(file_record, target_fp):
            file_record = {"target_relative_path": target_rel, "owners": []}
        owners = [str(owner) for owner in file_record.get("owners", []) if str(owner)]
        if resource_id not in owners:
            owners.append(resource_id)
        file_record.update({
            "target_relative_path": target_rel,
            "disabled_relative_path": disabled_rel,
            "file_status": "enabled",
            "size": target_fp["size"],
            "mtime_ns": target_fp["mtime_ns"],
            "sha1": target_fp["sha1"],
            "owners": owners,
            "updated_at": now,
        })
        manifest["file_map"][target_rel] = file_record
        updated_entry = dict(entry)
        updated_entry.update({
            "disabled_relative_path": disabled_rel,
            "file_status": "enabled",
            "size": target_fp["size"],
            "mtime_ns": target_fp["mtime_ns"],
            "sha1": target_fp["sha1"],
            "managed": True,
            "conflict": False,
            "conflict_reason": "",
            "last_verified_at": now,
        })
        return updated_entry

    @_locked_manifest_write
    def uninstall_resource(self, resource_id: str, usersights_path: str | Path) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            return {"success": True, "resource_id": resource_id, "deleted_count": 0, "modified_count": 0, "missing_count": 0}

        deleted_count = 0
        modified_count = 0
        missing_count = 0
        kept_shared_count = 0
        file_locked_count = 0
        conflicts: list[dict[str, str]] = []
        for entry in list(resource_record.get("files") or []):
            if not isinstance(entry, dict):
                continue
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                continue
            file_record = manifest["file_map"].get(target_rel)
            owners = []
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners", []) if str(owner) and str(owner) != resource_id]
            if owners:
                file_record["owners"] = owners
                manifest["file_map"][target_rel] = file_record
                kept_shared_count += 1
                continue

            target_file = self._path_from_posix(usersights, target_rel)
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            baseline = file_record if isinstance(file_record, dict) else entry
            keep_file_map = False
            if target_file.exists() and disabled_file.exists():
                modified_count += 1
                conflicts.append({
                    "target_relative_path": target_rel,
                    "reason": "enabled_and_disabled_both_exist",
                    "action": "uninstall_skipped_modified",
                })
            elif target_file.exists() or disabled_file.exists():
                current_file = target_file if target_file.exists() else disabled_file
                current_fp = self._file_fingerprint(current_file)
                if self._same_fingerprint(baseline, current_fp):
                    try:
                        current_file.unlink()
                    except OSError as e:
                        if not self._is_file_locked_error(e):
                            raise
                        file_locked_count += 1
                        keep_file_map = True
                        self._record_file_locked_conflict(
                            conflicts,
                            target_rel,
                            entry,
                            action="uninstall_skipped_file_locked",
                        )
                    else:
                        deleted_count += 1
                        self._cleanup_empty_dirs(current_file.parent, usersights)
                else:
                    modified_count += 1
                    conflicts.append({
                        "target_relative_path": target_rel,
                        "reason": "fingerprint_mismatch",
                        "action": "uninstall_skipped_modified",
                    })
            else:
                missing_count += 1
            if not keep_file_map:
                manifest["file_map"].pop(target_rel, None)

        resource_record["status"] = "needs_attention" if file_locked_count else "disabled"
        resource_record["updated_at"] = self._now_iso()
        if modified_count:
            resource_record["baseline_source"] = "uninstall_skipped_modified"
        resource_record["conflict_count"] = len(conflicts)
        resource_record["conflicts"] = conflicts
        manifest["resources"][resource_id] = resource_record
        self.save_manifest(usersights, manifest)
        return {
            "success": file_locked_count == 0,
            "resource_id": resource_id,
            "deleted_count": deleted_count,
            "modified_count": modified_count,
            "missing_count": missing_count,
            "file_locked_count": file_locked_count,
            "kept_shared_count": kept_shared_count,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
        }

    @_locked_manifest_write
    def uninstall_resource_batched(
        self,
        resource_id: str,
        usersights_path: str | Path,
        should_cancel: Any = None,
        progress_callback: Any = None,
        chunk_size: int = 300,
    ) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            return {
                "success": True,
                "resource_id": resource_id,
                "deleted_count": 0,
                "modified_count": 0,
                "missing_count": 0,
                "processed_count": 0,
                "total_count": 0,
                "skipped_count": 0,
                "canceled": False,
            }

        files = [entry for entry in list(resource_record.get("files") or []) if isinstance(entry, dict)]
        total_count = len(files)
        remaining_files: list[dict[str, Any]] = []
        deleted_count = 0
        modified_count = 0
        missing_count = 0
        kept_shared_count = 0
        file_locked_count = 0
        conflicts: list[dict[str, str]] = []
        processed_count = 0
        skipped_count = 0
        canceled = False
        chunk_size = max(1, int(chunk_size or 300))

        def _commit(remaining_entries: list[dict[str, Any]]) -> None:
            entries = remaining_files + [dict(entry) for entry in remaining_entries]
            resource_record["files"] = entries
            if file_locked_count:
                resource_record["status"] = "needs_attention"
            elif entries and (deleted_count or modified_count or missing_count or kept_shared_count):
                resource_record["status"] = "partial_uninstalled"
            elif entries:
                resource_record["status"] = str(resource_record.get("status") or "enabled")
            else:
                resource_record["status"] = "disabled"
            resource_record["updated_at"] = self._now_iso()
            if modified_count:
                resource_record["baseline_source"] = "uninstall_skipped_modified"
            resource_record["conflict_count"] = len(conflicts)
            resource_record["conflicts"] = conflicts
            manifest["resources"][resource_id] = resource_record
            self.save_manifest(usersights, manifest)

        def _notify() -> None:
            if not progress_callback:
                return
            try:
                progress_callback({
                    "resource_id": resource_id,
                    "total_count": total_count,
                    "processed_count": processed_count,
                    "skipped_count": skipped_count,
                    "deleted_count": deleted_count,
                    "modified_count": modified_count,
                    "missing_count": missing_count,
                    "file_locked_count": file_locked_count,
                    "kept_shared_count": kept_shared_count,
                    "conflict_count": len(conflicts),
                    "canceled": canceled,
                })
            except Exception:
                log.debug("炮镜分批卸载进度回调失败", exc_info=True)

        for index, entry in enumerate(files):
            if should_cancel and should_cancel():
                canceled = True
                skipped_count = total_count - processed_count
                _commit(files[index:])
                _notify()
                break

            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                processed_count += 1
                _notify()
                continue

            file_record = manifest["file_map"].get(target_rel)
            owners = []
            if isinstance(file_record, dict):
                owners = [
                    str(owner)
                    for owner in file_record.get("owners", [])
                    if str(owner) and str(owner) != resource_id
                ]
            if owners:
                file_record["owners"] = owners
                manifest["file_map"][target_rel] = file_record
                kept_shared_count += 1
                processed_count += 1
                if processed_count % chunk_size == 0:
                    _commit(files[index + 1:])
                _notify()
                continue

            target_file = self._path_from_posix(usersights, target_rel)
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            baseline = file_record if isinstance(file_record, dict) else entry
            keep_file_map = False
            if target_file.exists() and disabled_file.exists():
                modified_count += 1
                conflicts.append({
                    "target_relative_path": target_rel,
                    "reason": "enabled_and_disabled_both_exist",
                    "action": "uninstall_skipped_modified",
                })
            elif target_file.exists() or disabled_file.exists():
                current_file = target_file if target_file.exists() else disabled_file
                current_fp = self._file_fingerprint(current_file)
                if self._same_fingerprint(baseline, current_fp):
                    try:
                        current_file.unlink()
                    except OSError as e:
                        if not self._is_file_locked_error(e):
                            raise
                        file_locked_count += 1
                        keep_file_map = True
                        kept_entry = dict(entry)
                        self._record_file_locked_conflict(
                            conflicts,
                            target_rel,
                            kept_entry,
                            action="uninstall_skipped_file_locked",
                        )
                        remaining_files.append(kept_entry)
                    else:
                        deleted_count += 1
                        self._cleanup_empty_dirs(current_file.parent, usersights)
                else:
                    modified_count += 1
                    conflicts.append({
                        "target_relative_path": target_rel,
                        "reason": "fingerprint_mismatch",
                        "action": "uninstall_skipped_modified",
                    })
            else:
                missing_count += 1
            if not keep_file_map:
                manifest["file_map"].pop(target_rel, None)

            processed_count += 1
            if processed_count % chunk_size == 0:
                _commit(files[index + 1:])
            _notify()

        if not canceled:
            skipped_count = 0
            _commit([])

        return {
            "success": not (canceled or file_locked_count),
            "resource_id": resource_id,
            "deleted_count": deleted_count,
            "modified_count": modified_count,
            "missing_count": missing_count,
            "file_locked_count": file_locked_count,
            "kept_shared_count": kept_shared_count,
            "conflict_count": len(conflicts),
            "processed_count": processed_count,
            "total_count": total_count,
            "skipped_count": skipped_count,
            "canceled": canceled,
            "install_status": str(resource_record.get("status") or ""),
            "conflicts": conflicts,
        }

    @_locked_manifest_write
    def clear_resource_record(self, resource_id: str, usersights_path: str | Path) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            return {"success": True, "resource_id": resource_id, "cleared_count": 0}

        cleared_count = 0
        for entry in list(resource_record.get("files") or []):
            if not isinstance(entry, dict):
                continue
            target_rel = str(entry.get("target_relative_path") or "")
            if not target_rel:
                continue
            file_record = manifest["file_map"].get(target_rel)
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners", []) if str(owner) and str(owner) != resource_id]
                if owners:
                    file_record["owners"] = owners
                    manifest["file_map"][target_rel] = file_record
                else:
                    manifest["file_map"].pop(target_rel, None)
            cleared_count += 1

        resource_record["status"] = "disabled"
        resource_record["baseline_source"] = "record_cleared_keep_files"
        resource_record["expected_file_count"] = 0
        resource_record["conflict_count"] = 0
        resource_record["conflicts"] = []
        resource_record["files"] = []
        resource_record["updated_at"] = self._now_iso()
        manifest["resources"][resource_id] = resource_record
        self.save_manifest(usersights, manifest)
        return {"success": True, "resource_id": resource_id, "cleared_count": cleared_count}

    @_locked_manifest_write
    def accept_current_state(self, resource_id: str, usersights_path: str | Path) -> dict[str, Any]:
        usersights = Path(usersights_path)
        manifest = self.load_manifest(usersights)
        resource_record = manifest["resources"].get(resource_id)
        if not isinstance(resource_record, dict):
            raise FileNotFoundError(f"安装记录不存在: {resource_id}")

        accepted_count = 0
        missing_count = 0
        conflict_count = 0
        now = self._now_iso()
        updated_files = []
        for entry in list(resource_record.get("files") or []):
            if not isinstance(entry, dict):
                continue
            target_rel = str(entry.get("target_relative_path") or "")
            disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
            target_file = self._path_from_posix(usersights, target_rel)
            disabled_file = self._path_from_posix(usersights, disabled_rel)
            if target_file.exists() and disabled_file.exists():
                conflict_count += 1
                updated_entry = dict(entry)
                updated_entry["file_status"] = "needs_attention"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "enabled_and_disabled_both_exist"
                updated_files.append(updated_entry)
                continue
            current_file = target_file if target_file.exists() else disabled_file if disabled_file.exists() else None
            current_status = "enabled" if target_file.exists() else "disabled_by_rename" if disabled_file.exists() else "missing"
            if current_file is None:
                missing_count += 1
                updated_entry = dict(entry)
                updated_entry["disabled_relative_path"] = disabled_rel
                updated_entry["file_status"] = "missing"
                updated_entry["conflict"] = True
                updated_entry["conflict_reason"] = "missing"
                updated_entry["last_verified_at"] = now
                updated_files.append(updated_entry)
                continue
            fp = self._file_fingerprint(current_file)
            file_record = manifest["file_map"].get(target_rel)
            owners = []
            if isinstance(file_record, dict):
                owners = [str(owner) for owner in file_record.get("owners", []) if str(owner)]
            if owners and resource_id not in owners:
                conflict_count += 1
                updated_files.append(entry)
                continue
            updated_entry = dict(entry)
            updated_entry.update({
                "disabled_relative_path": disabled_rel,
                "file_status": current_status,
                "size": fp["size"],
                "mtime_ns": fp["mtime_ns"],
                "sha1": fp["sha1"],
                "managed": True,
                "conflict": False,
                "conflict_reason": "",
                "last_verified_at": now,
            })
            updated_files.append(updated_entry)
            if not isinstance(file_record, dict):
                file_record = {"target_relative_path": target_rel, "owners": []}
                owners = []
            if resource_id not in owners:
                owners.append(resource_id)
            file_record.update({
                "target_relative_path": target_rel,
                "disabled_relative_path": disabled_rel,
                "file_status": current_status,
                "size": fp["size"],
                "mtime_ns": fp["mtime_ns"],
                "sha1": fp["sha1"],
                "owners": owners,
                "updated_at": now,
            })
            manifest["file_map"][target_rel] = file_record
            accepted_count += 1

        expected_count = len(updated_files)
        if missing_count and not accepted_count:
            status = "needs_attention"
        elif missing_count:
            status = "partial_enabled"
        elif conflict_count and not accepted_count:
            status = "needs_attention"
        elif conflict_count:
            status = "partial_enabled"
        elif updated_files and all(str(entry.get("file_status") or "") == "disabled_by_rename" for entry in updated_files if isinstance(entry, dict)):
            status = "disabled_by_rename"
        else:
            status = "enabled" if expected_count and accepted_count == expected_count else "partial_enabled" if accepted_count else "disabled"
        resource_record["files"] = updated_files
        resource_record["status"] = status
        resource_record["baseline_source"] = "accepted_current_state"
        resource_record["conflict_count"] = conflict_count
        resource_record["updated_at"] = now
        manifest["resources"][resource_id] = resource_record
        self.save_manifest(usersights, manifest)
        return {
            "success": True,
            "resource_id": resource_id,
            "accepted_count": accepted_count,
            "missing_count": missing_count,
            "conflict_count": conflict_count,
            "install_status": status,
        }

    def summarize_target_group(self, usersights_path: str | Path, target_group: str) -> dict[str, Any]:
        usersights = Path(usersights_path)
        group = str(target_group or "").strip().rstrip("/")
        manifest = self.load_manifest(usersights)
        expected_count = 0
        existing_count = 0
        matched_count = 0
        disabled_count = 0
        missing_count = 0
        modified_count = 0
        disabled_modified_count = 0
        conflict_count = 0
        resource_ids: list[str] = []
        resource_file_counts: dict[str, int] = {}
        resource_missing_ids: list[str] = []
        partial_statuses: list[str] = []
        baseline_source = ""
        needs_attention = False
        manifest_corrupt = bool(manifest.get("manifest_corrupt"))
        manifest_backup_paths = [
            str(path)
            for path in manifest.get("manifest_backup_paths") or []
            if str(path)
        ]
        manifest_backup_count = int(manifest.get("manifest_backup_count") or len(manifest_backup_paths))

        for resource_id, resource_record in manifest.get("resources", {}).items():
            if not isinstance(resource_record, dict):
                continue
            resource_status = str(resource_record.get("status") or "")
            if resource_status == "disabled":
                continue
            if resource_status == "needs_attention":
                needs_attention = True
            if resource_status in {"partial_enabled", "partial_disabled", "partial_uninstalled"}:
                partial_statuses.append(resource_status)
            group_files = []
            for entry in resource_record.get("files") or []:
                if not isinstance(entry, dict):
                    continue
                target_rel = str(entry.get("target_relative_path") or "")
                parts = PurePosixPath(target_rel.replace("\\", "/")).parts
                if parts and parts[0] == group:
                    group_files.append(entry)
            if not group_files:
                continue
            resource_key = str(resource_id)
            resource_ids.append(resource_key)
            resource_file_counts[resource_key] = len([
                entry
                for entry in resource_record.get("files") or []
                if isinstance(entry, dict)
            ])
            if not self.resource_exists(resource_key):
                resource_missing_ids.append(resource_key)
                needs_attention = True
            if not baseline_source:
                baseline_source = str(resource_record.get("baseline_source") or "")
            for entry in group_files:
                expected_count += 1
                target_rel = str(entry.get("target_relative_path") or "")
                disabled_rel = str(entry.get("disabled_relative_path") or self._disabled_relative_path(target_rel))
                target_file = self._path_from_posix(usersights, target_rel)
                disabled_file = self._path_from_posix(usersights, disabled_rel)
                if entry.get("conflict"):
                    conflict_count += 1
                    if target_file.exists():
                        existing_count += 1
                    elif disabled_file.exists():
                        disabled_count += 1
                    else:
                        missing_count += 1
                    continue
                if target_file.exists() and disabled_file.exists():
                    conflict_count += 1
                    needs_attention = True
                    existing_count += 1
                    disabled_count += 1
                    continue
                if target_file.exists():
                    existing_count += 1
                    current_fp = self._file_fingerprint(target_file)
                    baseline = manifest.get("file_map", {}).get(target_rel)
                    if not isinstance(baseline, dict):
                        baseline = entry
                    if self._same_fingerprint(baseline, current_fp):
                        matched_count += 1
                    else:
                        modified_count += 1
                    continue
                if disabled_file.exists():
                    current_fp = self._file_fingerprint(disabled_file)
                    baseline = manifest.get("file_map", {}).get(target_rel)
                    if not isinstance(baseline, dict):
                        baseline = entry
                    if self._same_fingerprint(baseline, current_fp):
                        disabled_count += 1
                    else:
                        modified_count += 1
                        disabled_modified_count += 1
                    continue
                if not target_file.exists():
                    missing_count += 1
                    continue

        if expected_count == 0:
            return {
                "managed_by_aimerwt": False,
                "install_status": "needs_attention" if manifest_corrupt else "external",
                "resource_ids": [],
                "resource_file_count": 0,
                "installed_file_count": 0,
                "disabled_file_count": 0,
                "expected_file_count": 0,
                "missing_count": 0,
                "modified_count": 0,
                "conflict_count": 0,
                "resource_missing_count": 0,
                "resource_missing_ids": [],
                "manifest_corrupt": manifest_corrupt,
                "manifest_error": str(manifest.get("manifest_error") or ""),
                "manifest_backup_count": manifest_backup_count,
                "manifest_backup_paths": manifest_backup_paths,
                "baseline_source": "",
            }

        if manifest_corrupt or needs_attention or conflict_count or modified_count or disabled_modified_count:
            install_status = "needs_attention"
        elif "partial_uninstalled" in partial_statuses:
            install_status = "partial_uninstalled"
        elif matched_count == expected_count:
            install_status = "enabled"
        elif disabled_count == expected_count:
            install_status = "disabled_by_rename"
        elif disabled_count:
            if "partial_enabled" in partial_statuses and "partial_disabled" not in partial_statuses:
                install_status = "partial_enabled"
            elif "partial_disabled" in partial_statuses:
                install_status = "partial_disabled"
            else:
                install_status = "partial_enabled" if matched_count else "partial_disabled"
        elif existing_count == 0:
            install_status = "disabled"
        else:
            install_status = "partial_enabled"
        return {
            "managed_by_aimerwt": True,
            "install_status": install_status,
            "resource_ids": resource_ids,
            "resource_file_count": (
                next(iter(resource_file_counts.values()), 0)
                if len(resource_file_counts) == 1
                else 0
            ),
            "installed_file_count": matched_count,
            "disabled_file_count": disabled_count,
            "expected_file_count": expected_count,
            "missing_count": missing_count,
            "modified_count": modified_count,
            "conflict_count": conflict_count + modified_count,
            "resource_missing_count": len(resource_missing_ids),
            "resource_missing_ids": resource_missing_ids,
            "manifest_corrupt": manifest_corrupt,
            "manifest_error": str(manifest.get("manifest_error") or ""),
            "manifest_backup_count": manifest_backup_count,
            "manifest_backup_paths": manifest_backup_paths,
            "baseline_source": baseline_source,
        }

    def _cleanup_empty_dirs(self, start_dir: Path, stop_dir: Path) -> None:
        stop = stop_dir.resolve(strict=False)
        current = start_dir
        while True:
            try:
                resolved = current.resolve(strict=False)
                if resolved == stop or stop not in resolved.parents:
                    return
                current.rmdir()
            except OSError:
                return
            current = current.parent
