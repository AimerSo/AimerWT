# -*- coding: utf-8 -*-
"""AimerWT 安装实例身份和本机安装登记。"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO


REGISTRY_SCHEMA_VERSION = 1
INSTANCE_SCHEMA_VERSION = 1
INSTANCE_FILENAME = "AimerWT_Instance.json"
REGISTRY_FILENAME = "installations.json"
REGISTRY_LOCK_FILENAME = "installations.json.lock"
_registry_process_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_path(path: str | Path) -> str:
    raw = os.path.expandvars(str(path or "").strip())
    if not raw:
        return ""
    try:
        resolved = Path(raw).resolve(strict=False)
    except OSError:
        resolved = Path(raw)
    return os.path.normcase(os.path.normpath(str(resolved)))


def _path_record(
    role: str,
    path: str | Path | None,
    *,
    user_modified: bool,
    path_source: str,
    root_id: str = "",
) -> dict[str, Any]:
    path_text = str(path or "").strip()
    return {
        "path": path_text,
        "folder_name": Path(path_text).name if path_text else "",
        "user_modified": bool(user_modified),
        "path_source": str(path_source),
        "role": role,
        "root_id": str(root_id or ""),
        "exists": bool(path_text and Path(path_text).exists()),
        "previous_paths": [],
    }


def build_installation_path_snapshot(
    config: dict[str, Any],
    resource_paths: Any,
    pending_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """汇总当前安装实际使用的资源、游戏和待处理路径。"""
    from services.resource_path_manager import (
        DIR_BACKUP_ROOT_NAME,
        DIR_CUSTOM_TEXT_BACKUP_NAME,
        DIR_HANGAR_LIBRARY_NAME,
        DIR_MODEL_LIBRARY_NAME,
        DIR_PENDING,
        DIR_SIGHTS_LIBRARY_NAME,
        DIR_SOUND_BACKUP_NAME,
        DIR_TASK_LIBRARY_NAME,
        DIR_VOICE_LIBRARY_NAME,
        RESOURCE_ROOT_MARKER,
        read_resource_marker,
    )
    from utils.utils import get_app_data_dir

    clean_config = config if isinstance(config, dict) else {}
    metadata = clean_config.get("path_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    overrides = clean_config.get("resource_path_overrides")
    overrides = overrides if isinstance(overrides, dict) else {}
    resource_root = Path(resource_paths.resource_root_dir)
    marker = read_resource_marker(resource_root / RESOURCE_ROOT_MARKER) or {}
    root_id = str(marker.get("root_id") or "")

    default_paths = {
        "resource_root": resource_root,
        "voice_library": resource_root / DIR_VOICE_LIBRARY_NAME,
        "sights_library": resource_root / DIR_SIGHTS_LIBRARY_NAME,
        "task_library": resource_root / DIR_TASK_LIBRARY_NAME,
        "model_library": resource_root / DIR_MODEL_LIBRARY_NAME,
        "hangar_library": resource_root / DIR_HANGAR_LIBRARY_NAME,
        "backup_root": resource_root / DIR_BACKUP_ROOT_NAME,
        "sound_backup": resource_root / DIR_BACKUP_ROOT_NAME / DIR_SOUND_BACKUP_NAME,
        "custom_text_backup": resource_root / DIR_BACKUP_ROOT_NAME / DIR_CUSTOM_TEXT_BACKUP_NAME,
    }
    actual_paths = {
        "resource_root": resource_paths.resource_root_dir,
        "voice_library": resource_paths.voice_library_dir,
        "sights_library": resource_paths.sights_library_dir,
        "task_library": resource_paths.task_library_dir,
        "model_library": resource_paths.model_library_dir,
        "hangar_library": resource_paths.hangar_library_dir,
        "backup_root": resource_paths.backup_root_dir,
        "sound_backup": resource_paths.sound_backup_dir,
        "custom_text_backup": resource_paths.custom_text_backup_dir,
    }

    snapshot: dict[str, dict[str, Any]] = {}
    for role, actual_path in actual_paths.items():
        role_metadata = metadata.get(role) if isinstance(metadata.get(role), dict) else {}
        explicit_override = bool(str(overrides.get(role) or "").strip())
        marker_recovered = _normalize_path(actual_path) != _normalize_path(default_paths[role])
        if role == "resource_root":
            inferred_modified = bool(str(clean_config.get("resource_root_dir") or "").strip())
            inferred_source = "user_selected" if inferred_modified else "current_default"
        elif explicit_override:
            inferred_modified = True
            inferred_source = "user_selected"
        elif marker_recovered:
            inferred_modified = False
            inferred_source = "resource_marker"
        else:
            inferred_modified = False
            inferred_source = "current_default"
        snapshot[role] = _path_record(
            role,
            actual_path,
            user_modified=role_metadata.get("user_modified", inferred_modified),
            path_source=role_metadata.get("path_source", inferred_source),
            root_id=root_id,
        )

    configured_pending = str(clean_config.get("pending_dir") or "").strip()
    actual_pending = Path(pending_dir) if str(pending_dir or "").strip() else (
        Path(configured_pending) if configured_pending else get_app_data_dir() / DIR_PENDING
    )
    game_root_text = str(clean_config.get("game_path") or "").strip()
    sights_text = str(clean_config.get("sights_path") or "").strip()
    game_root = Path(game_root_text) if game_root_text else None
    game_paths = {
        "pending_dir": (
            actual_pending,
            bool(configured_pending),
            "user_selected" if configured_pending else "current_default",
        ),
        "game_root": (
            game_root,
            bool(game_root_text),
            "user_selected" if game_root_text else "unset",
        ),
        "game_usersights": (
            Path(sights_text) if sights_text else (game_root / "UserSights" if game_root else None),
            bool(sights_text),
            "user_selected" if sights_text else ("derived_from_game" if game_root else "unset"),
        ),
        "game_userskins": (
            game_root / "UserSkins" if game_root else None,
            False,
            "derived_from_game" if game_root else "unset",
        ),
    }
    for role, (actual_path, inferred_modified, inferred_source) in game_paths.items():
        role_metadata = metadata.get(role) if isinstance(metadata.get(role), dict) else {}
        snapshot[role] = _path_record(
            role,
            actual_path,
            user_modified=role_metadata.get("user_modified", inferred_modified),
            path_source=role_metadata.get("path_source", inferred_source),
        )
    return snapshot


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    verified = json.loads(temp_path.read_text(encoding="utf-8"))
    if not isinstance(verified, dict):
        raise ValueError("登记文件根内容必须是对象")
    temp_path.replace(path)


class RegistryError(RuntimeError):
    pass


class RegistrySchemaError(RegistryError):
    pass


class RegistryFutureSchemaError(RegistrySchemaError):
    pass


class RegistryConflictError(RegistryError):
    pass


class _RegistryFileLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._file: BinaryIO | None = None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        lock_file: BinaryIO | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = open(self.path, "a+b")
            if lock_file.seek(0, os.SEEK_END) == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._file = lock_file
            return True
        except OSError:
            if lock_file is not None:
                try:
                    lock_file.close()
                except Exception:
                    pass
            return False

    def release(self) -> None:
        lock_file = self._file
        self._file = None
        if lock_file is None:
            return
        try:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            lock_file.close()
        except Exception:
            pass

    def __enter__(self) -> "_RegistryFileLock":
        if not self.acquire():
            raise RegistryConflictError("installations.json 正由另一个进程保存")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def _empty_registry() -> dict[str, Any]:
    now = _now_iso()
    return {
        "app": "AimerWT",
        "schema": "installation_registry",
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "revision": 0,
        "created_at": now,
        "updated_at": now,
        "summary": {
            "total_installations": 0,
            "available_installations": 0,
            "missing_installations": 0,
            "archived_installations": 0,
        },
        "installations": [],
        "archived_installations": [],
    }


def _validate_registry(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("app") != "AimerWT" or data.get("schema") != "installation_registry":
        raise RegistrySchemaError("installations.json 不是 AimerWT 安装登记")
    version = data.get("schema_version")
    if not isinstance(version, int):
        raise RegistrySchemaError("installations.json 缺少有效格式版本")
    if version > REGISTRY_SCHEMA_VERSION:
        raise RegistryFutureSchemaError("installations.json 来自更高版本 AimerWT")
    if version < REGISTRY_SCHEMA_VERSION:
        raise RegistrySchemaError("installations.json 需要逐级升级")
    if not isinstance(data.get("installations"), list):
        raise RegistrySchemaError("installations 字段格式无效")
    if not isinstance(data.get("archived_installations"), list):
        data["archived_installations"] = []
    if not isinstance(data.get("revision"), int):
        data["revision"] = 0
    return data


def _read_registry_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RegistrySchemaError("installations.json 根内容必须是对象")
    return _validate_registry(data)


def _summary(data: dict[str, Any]) -> dict[str, int]:
    active = data.get("installations", [])
    archived = data.get("archived_installations", [])
    available = sum(1 for item in active if item.get("status") == "available")
    missing = sum(1 for item in active if item.get("status") == "missing")
    return {
        "total_installations": len(active) + len(archived),
        "available_installations": available,
        "missing_installations": missing,
        "archived_installations": len(archived),
    }


def _merge_timestamped_history(
    disk_items: list[dict[str, Any]],
    incoming_items: list[dict[str, Any]],
    key_name: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in [*disk_items, *incoming_items]:
        if not isinstance(item, dict):
            continue
        raw_key = str(item.get(key_name) or "")
        key = _normalize_path(raw_key) if key_name == "path" else raw_key
        if not key:
            continue
        if key not in merged:
            merged[key] = copy.deepcopy(item)
            order.append(key)
            continue
        current = merged[key]
        previous_first = str(current.get("first_seen_at") or "")
        previous_last = str(current.get("last_seen_at") or "")
        current.update(copy.deepcopy(item))
        first_values = [value for value in (previous_first, str(item.get("first_seen_at") or "")) if value]
        last_values = [value for value in (previous_last, str(item.get("last_seen_at") or "")) if value]
        if first_values:
            current["first_seen_at"] = min(first_values)
        if last_values:
            current["last_seen_at"] = max(last_values)
    return [merged[key] for key in order]


def _merge_installation_record(
    disk_record: dict[str, Any],
    incoming_record: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(disk_record)
    merged.update(copy.deepcopy(incoming_record))
    merged["version_history"] = _merge_timestamped_history(
        list(disk_record.get("version_history", []) or []),
        list(incoming_record.get("version_history", []) or []),
        "version",
    )
    merged["install_path_history"] = _merge_timestamped_history(
        list(disk_record.get("install_path_history", []) or []),
        list(incoming_record.get("install_path_history", []) or []),
        "path",
    )[-10:]
    disk_paths = disk_record.get("paths") if isinstance(disk_record.get("paths"), dict) else {}
    incoming_paths = incoming_record.get("paths") if isinstance(incoming_record.get("paths"), dict) else {}
    merged_paths = copy.deepcopy(disk_paths)
    for role, path_record in incoming_paths.items():
        previous = disk_paths.get(role)
        if isinstance(previous, dict) and isinstance(path_record, dict):
            merged_paths[role] = InstallationRegistry._merge_path_record(
                previous, path_record, _now_iso()
            )
        else:
            merged_paths[role] = copy.deepcopy(path_record)
    merged["paths"] = merged_paths
    return merged


def _merge_registry_for_conflict(
    disk_data: dict[str, Any],
    incoming_data: dict[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(incoming_data)
    incoming_ids = {
        str(item.get("installation_id") or "")
        for section in ("installations", "archived_installations")
        for item in result.get(section, [])
        if isinstance(item, dict)
    }
    for section in ("installations", "archived_installations"):
        disk_by_id = {
            str(item.get("installation_id") or ""): item
            for item in disk_data.get(section, [])
            if isinstance(item, dict)
        }
        merged_items = []
        for item in result.get(section, []):
            installation_id = str(item.get("installation_id") or "")
            disk_item = disk_by_id.get(installation_id)
            merged_items.append(_merge_installation_record(disk_item, item) if disk_item else item)
        merged_items.extend(
            copy.deepcopy(item)
            for item in disk_data.get(section, [])
            if str(item.get("installation_id") or "") not in incoming_ids
        )
        result[section] = merged_items
    return result


class InstallationRegistry:
    def __init__(
        self,
        config_dir: str | Path,
        install_dir: str | Path,
        executable_path: str | Path,
        app_version: str,
        build_id: str | None = None,
    ):
        self.config_dir = Path(config_dir)
        self.install_dir = Path(install_dir)
        self.executable_path = Path(executable_path)
        self.app_version = str(app_version)
        self.build_id = str(build_id or f"{self.app_version}+unknown")
        self.registry_path = self.config_dir / REGISTRY_FILENAME
        self.backup_path = self.config_dir / f"{REGISTRY_FILENAME}.bak"
        self.lock_path = self.config_dir / REGISTRY_LOCK_FILENAME
        self.instance_path = self.install_dir / INSTANCE_FILENAME

    def load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return _empty_registry()
        try:
            return _read_registry_file(self.registry_path)
        except RegistryFutureSchemaError:
            raise
        except (
            RegistrySchemaError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            OSError,
        ) as error:
            if self.backup_path.is_file():
                try:
                    return _read_registry_file(self.backup_path)
                except RegistryFutureSchemaError:
                    raise
                except (RegistrySchemaError, UnicodeDecodeError, json.JSONDecodeError, OSError):
                    pass
            raise RegistryError("installations.json 损坏且没有可用备份") from error


    def save(
        self,
        data: dict[str, Any],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        with _registry_process_lock, _RegistryFileLock(self.lock_path):
            disk_data = self.load()
            disk_revision = int(disk_data.get("revision", 0))
            if expected_revision is not None and disk_revision != int(expected_revision):
                result = _merge_registry_for_conflict(disk_data, data)
            else:
                result = copy.deepcopy(data)
            result["app"] = "AimerWT"
            result["schema"] = "installation_registry"
            result["schema_version"] = REGISTRY_SCHEMA_VERSION
            result["created_at"] = result.get("created_at") or disk_data.get("created_at") or _now_iso()
            result["updated_at"] = _now_iso()
            result["revision"] = disk_revision + 1
            result.setdefault("installations", [])
            result.setdefault("archived_installations", [])
            result["summary"] = _summary(result)
            _validate_registry(result)
            if self.registry_path.is_file():
                try:
                    _read_registry_file(self.registry_path)
                    shutil.copy2(self.registry_path, self.backup_path)
                except (RegistryError, RegistrySchemaError, UnicodeDecodeError, json.JSONDecodeError, OSError):
                    pass
            _atomic_write_json(self.registry_path, result)
            return result

    def _read_instance_marker(self) -> dict[str, Any] | None:
        if not self.instance_path.is_file():
            return None
        try:
            data = json.loads(self.instance_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RegistrySchemaError("AimerWT_Instance.json 无法读取或内容损坏") from error
        if not isinstance(data, dict):
            raise RegistrySchemaError("AimerWT_Instance.json 根内容必须是对象")
        if data.get("app") != "AimerWT" or data.get("schema") != "instance_identity":
            raise RegistrySchemaError("AimerWT_Instance.json 不属于 AimerWT 安装身份")
        version = data.get("schema_version")
        if not isinstance(version, int):
            raise RegistrySchemaError("AimerWT_Instance.json 缺少有效格式版本")
        if version > INSTANCE_SCHEMA_VERSION:
            raise RegistryFutureSchemaError(
                "AimerWT_Instance.json 来自更高版本 AimerWT，不能降级覆盖"
            )
        if version != INSTANCE_SCHEMA_VERSION:
            raise RegistrySchemaError("AimerWT_Instance.json 格式版本不受支持")
        try:
            uuid.UUID(str(data.get("installation_id") or ""))
        except ValueError as error:
            raise RegistrySchemaError("AimerWT_Instance.json 安装编号无效") from error
        return data

    def _write_instance_marker(self, installation_id: str, previous: dict[str, Any] | None = None) -> bool:
        previous = previous or {}
        data = {
            "app": "AimerWT",
            "schema": "instance_identity",
            "schema_version": INSTANCE_SCHEMA_VERSION,
            "installation_id": installation_id,
            "created_at": previous.get("created_at") or _now_iso(),
            "created_by_version": previous.get("created_by_version") or self.app_version,
        }
        try:
            _atomic_write_json(self.instance_path, data)
            return True
        except OSError:
            return False

    def _resolve_installation_id(self, data: dict[str, Any]) -> str:
        marker = self._read_instance_marker()
        marker_id = str((marker or {}).get("installation_id") or "")
        installations = data.get("installations", [])
        current_install_norm = _normalize_path(self.install_dir)

        path_match = next(
            (item for item in installations if
             _normalize_path(item.get("executable_path", "")) == _normalize_path(self.executable_path)
             and str(item.get("build_id") or "") == self.build_id),
            None,
        )
        if marker_id:
            matching = next(
                (item for item in installations if item.get("installation_id") == marker_id),
                None,
            )
            if matching:
                if path_match and path_match.get("installation_id") != marker_id:
                    stable_id = str(path_match["installation_id"])
                    self._write_instance_marker(stable_id)
                    return stable_id
                registered_dir = str(matching.get("install_dir") or "")
                registered_exe = Path(str(matching.get("executable_path") or ""))
                if _normalize_path(registered_dir) != current_install_norm and registered_exe.is_file():
                    marker_id = str(uuid.uuid4())
                    self._write_instance_marker(marker_id)
                return marker_id
            return marker_id

        if path_match:
            return str(path_match["installation_id"])

        marker_id = str(uuid.uuid4())
        self._write_instance_marker(marker_id)
        return marker_id

    @staticmethod
    def _merge_path_record(
        previous: dict[str, Any] | None,
        current: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        result = copy.deepcopy(current)
        result.setdefault("folder_name", Path(str(result.get("path") or "")).name)
        result.setdefault("user_modified", False)
        result.setdefault("path_source", "current_default")
        result.setdefault("role", "")
        result["exists"] = Path(str(result.get("path") or "")).exists()
        histories = list((previous or {}).get("previous_paths", []) or [])
        old_path = str((previous or {}).get("path") or "")
        new_path = str(result.get("path") or "")
        if old_path and _normalize_path(old_path) != _normalize_path(new_path):
            histories.insert(0, {"path": old_path, "last_seen_at": now})
        deduped = []
        seen = set()
        for item in histories:
            item_path = str((item or {}).get("path") or "")
            normalized = _normalize_path(item_path)
            if not item_path or normalized in seen or normalized == _normalize_path(new_path):
                continue
            seen.add(normalized)
            deduped.append(dict(item))
        result["previous_paths"] = deduped[:10]
        return result

    def find_current_record(self) -> dict[str, Any] | None:
        data = self.load()
        marker = self._read_instance_marker()
        marker_id = str((marker or {}).get("installation_id") or "")
        for item in data.get("installations", []):
            if (
                _normalize_path(item.get("executable_path", "")) == _normalize_path(self.executable_path)
                and str(item.get("build_id") or "") == self.build_id
            ):
                return copy.deepcopy(item)
        if marker_id:
            for item in data.get("installations", []):
                if item.get("installation_id") == marker_id:
                    return copy.deepcopy(item)
        return None

    def register_current(
        self,
        paths: dict[str, dict[str, Any]],
        migration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self.load()
        expected_revision = int(data.get("revision", 0))
        now = _now_iso()
        for item in data.get("installations", []):
            executable = Path(str(item.get("executable_path") or ""))
            item["status"] = "available" if executable.is_file() else "missing"

        installation_id = self._resolve_installation_id(data)
        current = next(
            (item for item in data["installations"] if item.get("installation_id") == installation_id),
            None,
        )
        if current is None:
            current = {
                "installation_id": installation_id,
                "first_seen_at": now,
                "version_history": [],
                "install_path_history": [],
                "paths": {},
            }
            data["installations"].append(current)

        old_install_dir = str(current.get("install_dir") or "")
        histories = list(current.get("install_path_history", []) or [])
        if not histories and old_install_dir:
            histories.append({"path": old_install_dir, "first_seen_at": current.get("first_seen_at") or now, "last_seen_at": now})
        if old_install_dir and _normalize_path(old_install_dir) != _normalize_path(self.install_dir):
            for history in histories:
                if _normalize_path(history.get("path", "")) == _normalize_path(old_install_dir):
                    history["last_seen_at"] = now
                    break
            else:
                histories.append({"path": old_install_dir, "first_seen_at": current.get("first_seen_at") or now, "last_seen_at": now})
        if not any(_normalize_path(item.get("path", "")) == _normalize_path(self.install_dir) for item in histories):
            histories.append({"path": str(self.install_dir), "first_seen_at": now, "last_seen_at": now})
        current["install_path_history"] = histories[-10:]

        versions = list(current.get("version_history", []) or [])
        if (
            isinstance(migration, dict)
            and migration.get("legacy_data_retained")
            and migration.get("same_installation_confirmed")
            and not any(str(item.get("version") or "").startswith("3.0") for item in versions)
        ):
            versions.append(
                {
                    "version": "3.0.x_unknown",
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "source": "legacy_migration",
                }
            )
        version_entry = next((item for item in versions if item.get("version") == self.app_version), None)
        if version_entry is None:
            versions.append({"version": self.app_version, "first_seen_at": now, "last_seen_at": now, "source": "current_runtime"})
        else:
            version_entry["last_seen_at"] = now
        current["version_history"] = versions
        current["current_version"] = self.app_version
        current["build_id"] = self.build_id
        current["executable_path"] = str(self.executable_path)
        current["install_dir"] = str(self.install_dir)
        current["last_seen_at"] = now
        current["status"] = "available" if self.executable_path.is_file() else "missing"
        if migration is not None:
            current["migration"] = copy.deepcopy(migration)

        previous_paths = current.get("paths", {}) if isinstance(current.get("paths"), dict) else {}
        merged_paths = {}
        for role, path_data in (paths or {}).items():
            if not isinstance(path_data, dict):
                continue
            merged_paths[str(role)] = self._merge_path_record(previous_paths.get(role), path_data, now)
        for role, path_data in previous_paths.items():
            if role not in merged_paths:
                merged_paths[role] = path_data
        current["paths"] = merged_paths

        saved = self.save(data, expected_revision=expected_revision)
        return next(item for item in saved["installations"] if item.get("installation_id") == installation_id)

    def archive(self, installation_id: str) -> bool:
        data = self.load()
        expected_revision = int(data.get("revision", 0))
        for index, item in enumerate(data["installations"]):
            if item.get("installation_id") != installation_id:
                continue
            archived = data["installations"].pop(index)
            archived["status"] = "archived"
            archived["archived_at"] = _now_iso()
            data["archived_installations"].append(archived)
            self.save(data, expected_revision=expected_revision)
            return True
        return False

    def restore(self, installation_id: str) -> bool:
        data = self.load()
        expected_revision = int(data.get("revision", 0))
        for index, item in enumerate(data["archived_installations"]):
            if item.get("installation_id") != installation_id:
                continue
            restored = data["archived_installations"].pop(index)
            restored.pop("archived_at", None)
            restored["status"] = (
                "available" if Path(str(restored.get("executable_path") or "")).is_file() else "missing"
            )
            data["installations"].append(restored)
            self.save(data, expected_revision=expected_revision)
            return True
        return False
