# -*- coding: utf-8 -*-
"""AimerWT 3.1 配置目录迁移与旧版设置兼容。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DATA_LAYOUT_SCHEMA_VERSION = 1
MIGRATION_STATE_SCHEMA_VERSION = 1
DEFAULT_PATH_LENGTH_LIMIT = 32760
DEFAULT_MINIMUM_FREE_RESERVE = 100 * 1024 * 1024
MAX_DIRECTORY_HISTORY = 8

IDENTITY_FILES = (
    "telemetry_device_token.json",
    "telemetry_machine_id.json",
)
CRITICAL_FILES = (
    "settings.json",
    "telemetry_device_token.json",
    "telemetry_machine_id.json",
    "telemetry_command_state.json",
    "server_cache.json",
)
OPTIONAL_DIRS = ("logs", "diagnostics")
IGNORED_NAMES = {
    ".cache",
    "cache",
    "AimerWT.single-instance.lock",
    "installations.json.lock",
}
LEGACY_COMPATIBLE_SETTINGS = {
    "game_path",
    "launch_mode",
    "theme_mode",
    "active_theme",
    "is_first_run",
    "agreement_version",
    "current_mod",
    "sound_replace_disclaimer_accepted",
    "guide_state",
    "uid_popup_state",
    "unlocked_themes",
    "sights_path",
    "pending_dir",
    "resource_root_dir",
    "resource_root_history",
    "library_dir",
    "resource_display_names",
    "telemetry_enabled",
    "autostart_enabled",
    "tray_mode",
    "close_confirm",
    "ui_language",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _is_valid_machine_scope_id(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64:
        return False
    try:
        int(normalized, 16)
    except ValueError:
        return False
    return True


def _get_machine_scope_id() -> str:
    """生成仅用于本机配置搬家核对的不可逆设备摘要。"""
    if os.name != "nt":
        return ""
    try:
        import winreg

        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access,
        ) as key:
            machine_guid, _value_type = winreg.QueryValueEx(key, "MachineGuid")
    except (ImportError, OSError, TypeError, ValueError):
        return ""
    normalized = str(machine_guid or "").strip().lower()
    if not normalized:
        return ""
    payload = f"AimerWT:migration_scope:v1:{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(_json_text(data), encoding="utf-8", newline="\n")
    parsed = json.loads(temp_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON 根内容必须是对象")
    temp_path.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _read_legacy_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "cp950", "big5"):
        try:
            data = json.loads(raw.decode(encoding))
            return data if isinstance(data, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            last_error = error
    if last_error is not None:
        raise last_error
    return None


def _settings_digest(path: Path) -> str:
    return _file_digest(path) if path.is_file() else ""


def _legacy_sync_values(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        key: settings[key]
        for key in LEGACY_COMPATIBLE_SETTINGS
        if key in settings
    }


def _update_legacy_sync_state(
    state_path: Path, settings_path: Path, action: str, settings_data: dict[str, Any]
) -> None:
    if not state_path.is_file():
        return
    state = _read_json(state_path) or {}
    state["legacy_sync"] = {
        "settings_sha256": _settings_digest(settings_path),
        "last_action": action,
        "updated_at": _now_iso(),
        "legacy_values": _legacy_sync_values(settings_data),
    }
    _atomic_write_json(state_path, state)


def sync_legacy_settings_to_current(legacy_dir: Path, target_dir: Path) -> bool:
    """旧版设置在上次同步后变化时，将旧版认识的字段导入正式设置。"""
    legacy_path = Path(legacy_dir) / "settings.json"
    target_path = Path(target_dir) / "settings.json"
    state_path = Path(target_dir) / "migration_state.json"
    if not legacy_path.is_file():
        return False
    current_digest = _settings_digest(legacy_path)
    state = _read_json(state_path) or {}
    sync_state = state.get("legacy_sync")
    if isinstance(sync_state, dict) and sync_state.get("settings_sha256") == current_digest:
        return False

    legacy = _read_legacy_json(legacy_path) or {}
    current = _read_json(target_path) or {}
    merged = dict(current)
    previous_values = sync_state.get("legacy_values") if isinstance(sync_state, dict) else None
    changed_keys: list[str] = []
    if isinstance(previous_values, dict):
        for key in LEGACY_COMPATIBLE_SETTINGS:
            if key in legacy and legacy.get(key) != previous_values.get(key):
                changed_keys.append(key)
    else:
        for key in LEGACY_COMPATIBLE_SETTINGS:
            if key in legacy and current.get(key) in (None, "", [], {}):
                changed_keys.append(key)
    for key in changed_keys:
        merged[key] = legacy[key]
    changed = merged != current
    if changed:
        _atomic_write_json(target_path, merged)
    _update_legacy_sync_state(
        state_path, legacy_path, "imported_from_legacy", legacy
    )
    return changed


def sync_current_settings_to_legacy(
    current_settings: dict[str, Any],
    legacy_dir: Path,
    target_dir: Path,
) -> bool:
    """把 3.0/3.0.1 认识的字段回写旧设置，保留旧版未知内容。"""
    legacy_dir = Path(legacy_dir)
    if not legacy_dir.exists():
        return False
    legacy_path = legacy_dir / "settings.json"
    legacy = _read_legacy_json(legacy_path) or {}
    updated = dict(legacy)
    for key in LEGACY_COMPATIBLE_SETTINGS:
        if key in current_settings:
            updated[key] = current_settings[key]
    _atomic_write_json(legacy_path, updated)
    _update_legacy_sync_state(
        Path(target_dir) / "migration_state.json",
        legacy_path,
        "exported_to_legacy",
        updated,
    )
    return True


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files_equal(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_size == right.stat().st_size and _file_digest(left) == _file_digest(right)
    except OSError:
        return False


def _default_reparse_detector(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        file_attributes = getattr(path.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(file_attributes & reparse_flag)
    except OSError:
        return False


class MigrationError(RuntimeError):
    def __init__(self, error_code: str, message: str, exit_code: int = 11):
        super().__init__(message)
        self.error_code = str(error_code)
        self.exit_code = int(exit_code)


def _state_template(
    app_version: str,
    migration_id: str,
    legacy_dir: Path,
    target_dir: Path,
    stage_dir: Path,
    machine_scope_id: str,
) -> dict[str, Any]:
    state = {
        "app": "AimerWT",
        "schema": "migration_state",
        "schema_version": MIGRATION_STATE_SCHEMA_VERSION,
        "migration_id": migration_id,
        "app_version": app_version,
        "status": "in_progress",
        "phase": "inventory",
        "source_dir": str(legacy_dir),
        "target_dir": str(target_dir),
        "stage_dir": str(stage_dir),
        "started_at": _now_iso(),
        "completed_at": None,
        "last_error_code": "",
        "items": {
            "planned": 0,
            "copied": 0,
            "verified": 0,
            "skipped_optional": 0,
            "conflicts": 0,
        },
        "rollback": {
            "available": True,
            "source_untouched": True,
            "previous_active_dir": str(legacy_dir),
        },
    }
    if _is_valid_machine_scope_id(machine_scope_id):
        state["machine_scope_id"] = machine_scope_id.lower()
    return state


def _write_state(path: Path, state: dict[str, Any], phase: str | None = None) -> None:
    if phase:
        state["phase"] = phase
    _atomic_write_json(path, state)


def _raise_with_state(
    state_path: Path,
    state: dict[str, Any],
    error_code: str,
    message: str,
    exit_code: int = 11,
) -> None:
    state["status"] = "blocked"
    state["last_error_code"] = error_code
    state["items"]["conflicts"] = int(state["items"].get("conflicts", 0)) + 1
    _write_state(state_path, state)
    raise MigrationError(error_code, message, exit_code)


def _find_reparse_points(
    root: Path,
    detector: Callable[[Path], bool],
) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        for dir_name in list(dir_names):
            child = current / dir_name
            if detector(child):
                found.append(child)
                dir_names.remove(dir_name)
        for file_name in file_names:
            child = current / file_name
            if detector(child):
                found.append(child)
    return found


def _iter_source_files(
    root: Path,
    skip_top_level: set[str] | None = None,
):
    skipped = set(skip_top_level or ())
    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        dir_names[:] = [
            name
            for name in dir_names
            if name not in IGNORED_NAMES
            and not (current == root and name in skipped)
        ]
        for file_name in file_names:
            if file_name in IGNORED_NAMES or file_name.endswith(".tmp"):
                continue
            yield current / file_name


def _has_legacy_data(legacy_dir: Path) -> bool:
    if not legacy_dir.is_dir():
        return False
    return next(_iter_source_files(legacy_dir), None) is not None


def _planned_size(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def _merge_settings(legacy_path: Path, target_path: Path) -> dict[str, Any] | None:
    legacy = _read_legacy_json(legacy_path)
    current = _read_json(target_path)
    if legacy is None and current is None:
        return None
    if current is None:
        return {key: value for key, value in (legacy or {}).items() if key in LEGACY_COMPATIBLE_SETTINGS}
    merged = dict(current)
    for key in LEGACY_COMPATIBLE_SETTINGS:
        if key not in (legacy or {}):
            continue
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = legacy[key]
    return merged


def _copy_file_with_retry(source: Path, target: Path, attempts: int = 3) -> None:
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if not _files_equal(source, target):
                raise OSError("复制后校验不一致")
            return
        except OSError as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.05 * (attempt + 1))
    raise last_error or OSError("复制失败")


def _copy_tree_with_retry(
    source: Path,
    target: Path,
    reparse_detector: Callable[[Path], bool] | None = None,
) -> None:
    detector = reparse_detector or _default_reparse_detector
    if detector(source) or _find_reparse_points(source, detector):
        raise OSError(f"目录包含符号链接或目录连接: {source}")
    last_error: OSError | None = None
    for attempt in range(3):
        try:
            if target.exists():
                shutil.rmtree(target)
            for source_file in _iter_source_files(source):
                relative = source_file.relative_to(source)
                if detector(source_file):
                    raise OSError(f"文件是符号链接或目录连接: {source_file}")
            shutil.copytree(source, target, symlinks=True)
            if detector(target) or _find_reparse_points(target, detector):
                raise OSError(f"复制结果包含符号链接或目录连接: {target}")
            for source_file in _iter_source_files(source):
                relative = source_file.relative_to(source)
                if not _files_equal(source_file, target / relative):
                    raise OSError(f"目录文件校验失败: {relative}")
            return
        except OSError as error:
            last_error = error
            if attempt + 1 < 3:
                time.sleep(0.05 * (attempt + 1))
    raise last_error or OSError("目录复制失败")


def _copy_target_snapshot(
    target_dir: Path,
    stage_dir: Path,
    detector: Callable[[Path], bool],
) -> None:
    for child in target_dir.iterdir():
        if child.name in IGNORED_NAMES or child.name.endswith(".tmp"):
            continue
        if detector(child):
            raise OSError(f"新配置中包含符号链接或目录连接: {child}")
        destination = stage_dir / child.name
        if child.is_dir():
            _copy_tree_with_retry(child, destination, detector)
        elif child.is_file():
            _copy_file_with_retry(child, destination)


def _switch_staged_directory(
    target_dir: Path,
    stage_dir: Path,
    rollback_dir: Path,
) -> None:
    if rollback_dir.exists():
        raise OSError(f"回退目录已经存在: {rollback_dir}")
    target_dir.replace(rollback_dir)
    try:
        stage_dir.replace(target_dir)
    except OSError as switch_error:
        try:
            rollback_dir.replace(target_dir)
        except OSError as rollback_error:
            raise OSError(
                f"最终切换失败且无法恢复原目标目录: {switch_error}; {rollback_error}"
            ) from rollback_error
        raise


def _rollback_staged_directory(
    target_dir: Path,
    stage_dir: Path,
    rollback_dir: Path,
) -> None:
    if stage_dir.exists():
        raise OSError(f"临时迁移目录被占用，无法回退: {stage_dir}")
    target_dir.replace(stage_dir)
    rollback_dir.replace(target_dir)


def _validate_existing_layout(target_dir: Path) -> bool:
    layout_path = target_dir / "data_layout.json"
    if not layout_path.exists():
        return False
    try:
        layout = _read_json(layout_path) or {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MigrationError("registry_corrupt", f"配置目录标识无法读取：{error}", 12) from error
    version = layout.get("schema_version")
    if not isinstance(version, int):
        raise MigrationError("registry_corrupt", "配置目录标识缺少有效版本", 12)
    if version > DATA_LAYOUT_SCHEMA_VERSION:
        raise MigrationError("registry_schema_unsupported", "该配置由更高版本 AimerWT 创建，请先更新软件", 12)
    if layout.get("app") != "AimerWT" or layout.get("schema") != "data_layout":
        raise MigrationError("registry_corrupt", "配置目录标识不属于 AimerWT", 12)
    return True


def _normalized_path(path: str | Path) -> str:
    try:
        resolved = Path(path).resolve(strict=False)
    except OSError:
        resolved = Path(path)
    return os.path.normcase(os.path.normpath(str(resolved)))


def _has_canonical_migration_names(source_dir: Path, target_dir: Path) -> bool:
    return (
        source_dir.name.casefold() == "Aimer_WT".casefold()
        and target_dir.name.casefold() == "AimerWT".casefold()
    )


def _is_completed_documents_relocation(
    state: dict[str, Any],
    legacy_dir: Path,
    target_dir: Path,
    *,
    layout_valid: bool,
    machine_scope_id: str,
) -> bool:
    if (
        not layout_valid
        or state.get("status") != "completed"
        or state.get("phase") != "completed"
    ):
        return False
    stored_scope_id = str(state.get("machine_scope_id") or "").strip().lower()
    current_scope_id = str(machine_scope_id or "").strip().lower()
    if (
        not _is_valid_machine_scope_id(stored_scope_id)
        or not _is_valid_machine_scope_id(current_scope_id)
        or stored_scope_id != current_scope_id
    ):
        return False
    history = state.get("directory_history")
    if history is not None:
        if not isinstance(history, list):
            return False
        if any(
            not isinstance(item, dict)
            or not str(item.get("source_dir") or "").strip()
            or not str(item.get("target_dir") or "").strip()
            or not str(item.get("relocated_at") or "").strip()
            for item in history
        ):
            return False

    stored_source_dir = Path(str(state["source_dir"]))
    stored_target_dir = Path(str(state["target_dir"]))
    if not _has_canonical_migration_names(stored_source_dir, stored_target_dir):
        return False
    if not _has_canonical_migration_names(legacy_dir, target_dir):
        return False
    stored_parent = stored_target_dir.parent
    current_parent = target_dir.parent
    if _normalized_path(stored_source_dir.parent) != _normalized_path(stored_parent):
        return False
    if _normalized_path(legacy_dir.parent) != _normalized_path(current_parent):
        return False
    if _normalized_path(stored_parent) == _normalized_path(current_parent):
        return False

    stage_dir = Path(str(state.get("stage_dir") or ""))
    expected_stage_name = f"AimerWT.migration-{str(state['migration_id'])[:8]}"
    return (
        stage_dir.name.casefold() == expected_stage_name.casefold()
        and _normalized_path(stage_dir.parent) == _normalized_path(stored_parent)
    )


def _relocate_completed_state_paths(
    state_path: Path,
    state: dict[str, Any],
    legacy_dir: Path,
    target_dir: Path,
) -> None:
    old_source_dir = Path(str(state["source_dir"]))
    old_target_dir = Path(str(state["target_dir"]))
    old_parent = old_target_dir.parent
    current_parent = target_dir.parent
    relocated_at = _now_iso()
    history_value = state.get("directory_history")
    history = list(history_value) if isinstance(history_value, list) else []
    history_entry = {
        "source_dir": str(old_source_dir),
        "target_dir": str(old_target_dir),
        "relocated_at": relocated_at,
    }
    if not any(
        isinstance(item, dict)
        and _normalized_path(item.get("source_dir", "")) == _normalized_path(old_source_dir)
        and _normalized_path(item.get("target_dir", "")) == _normalized_path(old_target_dir)
        for item in history
    ):
        history.append(history_entry)
    state["directory_history"] = history[-MAX_DIRECTORY_HISTORY:]
    state["source_dir"] = str(legacy_dir)
    state["target_dir"] = str(target_dir)
    state["documents_relocated_at"] = relocated_at

    stage_text = str(state.get("stage_dir") or "").strip()
    if stage_text:
        stage_dir = Path(stage_text)
        if _normalized_path(stage_dir.parent) == _normalized_path(old_parent):
            state["stage_dir"] = str(current_parent / stage_dir.name)
    rollback = state.get("rollback")
    if isinstance(rollback, dict):
        for key in ("previous_active_dir", "snapshot_dir"):
            value = str(rollback.get(key) or "").strip()
            if not value:
                continue
            candidate = Path(value)
            if _normalized_path(candidate.parent) == _normalized_path(old_parent):
                rollback[key] = str(current_parent / candidate.name)
    _write_state(state_path, state)


def _read_existing_migration_state(
    target_dir: Path,
    legacy_dir: Path,
    *,
    layout_valid: bool = False,
    machine_scope_id: str = "",
) -> dict[str, Any] | None:
    state_path = target_dir / "migration_state.json"
    if not state_path.exists():
        return None
    try:
        state = _read_json(state_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MigrationError("registry_corrupt", f"迁移状态无法读取：{error}", 12) from error
    if not isinstance(state, dict):
        raise MigrationError("registry_corrupt", "迁移状态格式无效", 12)
    version = state.get("schema_version")
    if not isinstance(version, int):
        raise MigrationError("registry_corrupt", "迁移状态缺少有效版本", 12)
    if version > MIGRATION_STATE_SCHEMA_VERSION:
        raise MigrationError("registry_schema_unsupported", "迁移状态来自更高版本 AimerWT", 12)
    required_text = ("migration_id", "source_dir", "target_dir", "status", "phase")
    if (
        state.get("app") != "AimerWT"
        or state.get("schema") != "migration_state"
        or version != MIGRATION_STATE_SCHEMA_VERSION
        or any(not str(state.get(key) or "").strip() for key in required_text)
    ):
        raise MigrationError("registry_corrupt", "迁移状态缺少必要信息", 12)
    try:
        uuid.UUID(str(state["migration_id"]))
    except ValueError as error:
        raise MigrationError("registry_corrupt", "迁移状态编号无效", 12) from error
    if (
        _normalized_path(state["source_dir"]) != _normalized_path(legacy_dir)
        or _normalized_path(state["target_dir"]) != _normalized_path(target_dir)
    ):
        if _is_completed_documents_relocation(
            state,
            legacy_dir,
            target_dir,
            layout_valid=layout_valid,
            machine_scope_id=machine_scope_id,
        ):
            _relocate_completed_state_paths(state_path, state, legacy_dir, target_dir)
        else:
            raise MigrationError(
                "registry_corrupt",
                "检测到 AimerWT 配置目录位置发生变化，但无法安全确认这是同一台电脑上的完整 Windows“文档”目录搬家。"
                "可能原因包括更换电脑、重装 Windows，或只移动了部分目录。"
                "如果仍保留 Aimer_WT，请确认它与 AimerWT 位于当前“文档”目录且名称未改。"
                "请勿删除 migration_state.json；仍无法启动时请联系支持处理。",
                12,
            )
    return state


def _write_completed_layout(target_dir: Path, app_version: str) -> None:
    layout_path = target_dir / "data_layout.json"
    existing = _read_json(layout_path) if layout_path.exists() else None
    _atomic_write_json(
        layout_path,
        {
            "app": "AimerWT",
            "schema": "data_layout",
            "schema_version": DATA_LAYOUT_SCHEMA_VERSION,
            "canonical_dir_name": "AimerWT",
            "legacy_dir_names": ["Aimer_WT"],
            "created_at": (existing or {}).get("created_at") or _now_iso(),
            "last_migrated_by": app_version,
        },
    )


def prepare_app_data_layout(
    app_version: str,
    *,
    legacy_dir: Path,
    target_dir: Path,
    free_space_provider: Callable[[Path], int] | None = None,
    minimum_free_reserve: int = DEFAULT_MINIMUM_FREE_RESERVE,
    path_length_limit: int = DEFAULT_PATH_LENGTH_LIMIT,
    reparse_detector: Callable[[Path], bool] | None = None,
) -> dict[str, Any]:
    """在应用读取配置前建立 3.1 正式目录；旧目录始终只读保留。"""
    legacy_dir = Path(legacy_dir)
    target_dir = Path(target_dir)
    detector = reparse_detector or _default_reparse_detector
    machine_scope_id = _get_machine_scope_id()
    if legacy_dir.exists() and detector(legacy_dir):
        raise MigrationError(
            "migration_source_conflict",
            "旧配置目录是目录连接或符号链接，需要用户确认后再迁移",
            11,
        )
    if target_dir.exists() and detector(target_dir):
        raise MigrationError(
            "migration_source_conflict",
            "新配置目录本身是目录连接或符号链接，需要用户确认后再迁移",
            11,
        )
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        layout_valid = _validate_existing_layout(target_dir)
        completed_state = _read_existing_migration_state(
            target_dir,
            legacy_dir,
            layout_valid=layout_valid,
            machine_scope_id=machine_scope_id,
        )
        if (
            isinstance(completed_state, dict)
            and completed_state.get("status") == "completed"
            and completed_state.get("phase") == "completed"
        ):
            if not layout_valid:
                raise MigrationError("registry_corrupt", "已完成迁移缺少配置目录标识", 12)
            legacy_sync_error = ""
            try:
                legacy_sync_applied = sync_legacy_settings_to_current(legacy_dir, target_dir)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                legacy_sync_applied = False
                legacy_sync_error = f"{type(error).__name__}: {error}"
            return {
                "status": "completed",
                "already_completed": True,
                "legacy_data_retained": _has_legacy_data(legacy_dir),
                "legacy_sync_applied": legacy_sync_applied,
                "legacy_sync_error": legacy_sync_error,
                "target_dir": str(target_dir),
            }

    migration_id = str(uuid.uuid4())
    stage_dir = target_dir.parent / f"{target_dir.name}.migration-{migration_id[:8]}"
    target_dir.mkdir(parents=True, exist_ok=True)
    state_path = target_dir / "migration_state.json"
    state = _state_template(
        app_version,
        migration_id,
        legacy_dir,
        target_dir,
        stage_dir,
        machine_scope_id,
    )
    _write_state(state_path, state)

    if not legacy_dir.exists():
        _write_completed_layout(target_dir, app_version)
        state["status"] = "completed"
        state["phase"] = "completed"
        state["completed_at"] = _now_iso()
        _write_state(state_path, state)
        return {
            "status": "completed",
            "already_completed": False,
            "legacy_data_retained": False,
            "target_dir": str(target_dir),
        }

    skipped_optional: set[str] = set()
    for reparse_path in _find_reparse_points(legacy_dir, detector):
        relative = reparse_path.relative_to(legacy_dir)
        top_name = relative.parts[0] if relative.parts else ""
        if top_name in OPTIONAL_DIRS:
            skipped_optional.add(top_name)
            continue
        _raise_with_state(
            state_path,
            state,
            "migration_source_conflict",
            "旧配置中包含目录连接或符号链接，需要用户确认后再迁移",
        )
    if _find_reparse_points(target_dir, detector):
        _raise_with_state(
            state_path,
            state,
            "migration_source_conflict",
            "新配置中包含目录连接或符号链接，未自动复制或覆盖",
        )

    state["phase"] = "preflight"
    source_files = list(_iter_source_files(legacy_dir, skipped_optional))
    for path in source_files:
        if detector(path):
            _raise_with_state(
                state_path,
                state,
                "migration_source_conflict",
                "旧配置中包含目录连接或符号链接，需要用户确认后再迁移",
            )
        relative = path.relative_to(legacy_dir)
        if len(str(path)) > path_length_limit or len(str(target_dir / relative)) > path_length_limit:
            top_name = relative.parts[0] if relative.parts else ""
            if top_name in OPTIONAL_DIRS:
                skipped_optional.add(top_name)
                continue
            _raise_with_state(
                state_path,
                state,
                "migration_path_too_long",
                "关键配置路径过长，未切换到新目录",
            )

    source_files = [
        path
        for path in source_files
        if path.relative_to(legacy_dir).parts[0] not in skipped_optional
    ]
    state["items"]["planned"] = len(source_files)
    state["items"]["skipped_optional"] = len(skipped_optional)
    _write_state(state_path, state)
    target_snapshot_files = list(_iter_source_files(target_dir))
    planned_bytes = _planned_size(source_files) + _planned_size(target_snapshot_files)
    free_bytes = (
        int(free_space_provider(target_dir.parent))
        if free_space_provider
        else int(shutil.disk_usage(target_dir.parent).free)
    )
    required_bytes = int(planned_bytes * 1.5) + max(0, int(minimum_free_reserve))
    if free_bytes < required_bytes:
        _raise_with_state(
            state_path,
            state,
            "migration_space_insufficient",
            "目标磁盘空间不足，旧配置保持不变",
        )

    for name in IDENTITY_FILES:
        legacy_path = legacy_dir / name
        target_path = target_dir / name
        if legacy_path.is_file() and target_path.is_file() and not _files_equal(legacy_path, target_path):
            _raise_with_state(
                state_path,
                state,
                "identity_conflict",
                "检测到两个不同的设备身份，未自动选择或覆盖",
                13,
            )

    rollback_dir = target_dir.parent / f"{target_dir.name}.rollback-{migration_id[:8]}"
    switched = False
    try:
        stage_dir.mkdir(parents=True, exist_ok=False)
        _copy_target_snapshot(target_dir, stage_dir, detector)
        state["phase"] = "copying_critical_data"
        _write_state(state_path, state)
        _write_state(stage_dir / "migration_state.json", state)

        merged_settings = _merge_settings(legacy_dir / "settings.json", target_dir / "settings.json")
        if merged_settings is not None:
            staged_settings = stage_dir / "settings.json"
            if staged_settings.is_file():
                shutil.copy2(staged_settings, stage_dir / "settings.json.bak")
            _atomic_write_json(stage_dir / "settings.json", merged_settings)
            state["items"]["copied"] += 1
            state["items"]["verified"] += 1

        for name in CRITICAL_FILES:
            if name == "settings.json":
                continue
            source = legacy_dir / name
            target = target_dir / name
            if not source.is_file() or target.is_file():
                continue
            _copy_file_with_retry(source, stage_dir / name)
            state["items"]["copied"] += 1
            state["items"]["verified"] += 1

        legacy_webview = legacy_dir / ".webview"
        date_suffix = datetime.now().strftime("%Y%m%d")
        staged_webview = stage_dir / ".webview"
        if legacy_webview.is_dir():
            if staged_webview.exists():
                webview_archive = (
                    stage_dir / ".webview_legacy" / f"legacy_aimer_wt_{date_suffix}"
                )
                if not webview_archive.exists():
                    _copy_tree_with_retry(legacy_webview, webview_archive, detector)
            else:
                _copy_tree_with_retry(legacy_webview, staged_webview, detector)
            state["items"]["copied"] += 1
            state["items"]["verified"] += 1

        state["phase"] = "copying_optional_data"
        _write_state(state_path, state)
        _write_state(stage_dir / "migration_state.json", state)
        for optional_name in OPTIONAL_DIRS:
            if optional_name in skipped_optional:
                continue
            source_dir = legacy_dir / optional_name
            if not source_dir.is_dir():
                continue
            archive_dir = stage_dir / optional_name / f"legacy_aimer_wt_{date_suffix}"
            if archive_dir.exists():
                continue
            try:
                _copy_tree_with_retry(source_dir, archive_dir, detector)
            except OSError:
                state["items"]["skipped_optional"] += 1

        state["phase"] = "verifying"
        _write_state(state_path, state)
        _write_state(stage_dir / "migration_state.json", state)
        state["phase"] = "switching"
        state["rollback"]["snapshot_dir"] = str(rollback_dir)
        _write_state(state_path, state)
        _write_state(stage_dir / "migration_state.json", state)

        _switch_staged_directory(target_dir, stage_dir, rollback_dir)
        switched = True
        _write_completed_layout(target_dir, app_version)
        legacy_settings_path = legacy_dir / "settings.json"
        if legacy_settings_path.is_file():
            legacy_settings = _read_legacy_json(legacy_settings_path) or {}
            state["legacy_sync"] = {
                "settings_sha256": _settings_digest(legacy_settings_path),
                "last_action": "initial_migration",
                "updated_at": _now_iso(),
                "legacy_values": _legacy_sync_values(legacy_settings),
            }
        state["status"] = "completed"
        state["phase"] = "completed"
        state["completed_at"] = _now_iso()
        _write_state(state_path, state)
        if rollback_dir.exists() and not stage_dir.exists():
            rollback_dir.replace(stage_dir)
    except MigrationError:
        raise
    except OSError as error:
        rollback_error: OSError | None = None
        if switched and rollback_dir.exists():
            try:
                _rollback_staged_directory(target_dir, stage_dir, rollback_dir)
                switched = False
            except OSError as caught_rollback_error:
                rollback_error = caught_rollback_error
        state["status"] = "blocked"
        state["phase"] = "switch_failed"
        state["last_error_code"] = "migration_switch_failed"
        for candidate_state_path in (
            target_dir / "migration_state.json",
            stage_dir / "migration_state.json",
            rollback_dir / "migration_state.json",
        ):
            if candidate_state_path.parent.is_dir():
                try:
                    _write_state(candidate_state_path, state)
                except OSError:
                    pass
        detail = str(error)
        if rollback_error is not None:
            detail = f"{detail}；回退也失败：{rollback_error}"
        raise MigrationError(
            "migration_switch_failed",
            f"新配置目录切换失败，旧目录仍然保留：{detail}",
            11,
        ) from error
    return {
        "status": "completed",
        "already_completed": False,
        "legacy_data_retained": _has_legacy_data(legacy_dir),
        "target_dir": str(target_dir),
        "migration_id": migration_id,
        "items": dict(state["items"]),
    }
