# -*- coding: utf-8 -*-
"""AimerWT 启动前的跨版本锁和配置目录迁移编排。"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import os
import sys
from pathlib import Path
from typing import Any, Callable

from services.app_data_migration import MigrationError, prepare_app_data_layout
from services.installation_registry import (
    InstallationRegistry,
    RegistryConflictError,
    RegistryError,
    build_installation_path_snapshot,
)
from services.resource_path_manager import (
    DIR_RESOURCE_ROOT,
    RESOURCE_MARKER_NOTE,
    ROLE_MARKER_FILENAMES,
    ResourceCopyError,
    copy_resource_root_transactional,
)
from services.single_instance_manager import MultiVersionInstanceGuard


class StartupRegistrationError(RuntimeError):
    def __init__(self, error_code: str, message: str, exit_code: int):
        super().__init__(message)
        self.error_code = str(error_code)
        self.exit_code = int(exit_code)


@dataclass(frozen=True)
class StartupRegistration:
    registry: InstallationRegistry
    current: dict[str, Any]
    resource_recovery: Any
    marker_result: dict[str, Any]


@dataclass(frozen=True)
class StartupBootstrapResult:
    success: bool
    exit_code: int
    error_code: str
    message: str
    migration: dict[str, Any] | None
    guard: Any | None


def bootstrap_startup_data(
    app_version: str,
    *,
    legacy_dir: str | Path,
    target_dir: str | Path,
    guard_factory: Callable[..., Any] = MultiVersionInstanceGuard,
    migration_runner: Callable[..., dict[str, Any]] = prepare_app_data_layout,
) -> StartupBootstrapResult:
    legacy_dir = Path(legacy_dir)
    target_dir = Path(target_dir)
    try:
        guard = guard_factory(
            legacy_dir / "AimerWT.single-instance.lock",
            target_dir / "AimerWT.single-instance.lock",
        )
    except OSError as error:
        return StartupBootstrapResult(
            False,
            14,
            "config_dir_unavailable",
            f"无法准备 AimerWT 配置目录：{error}",
            None,
            None,
        )

    if not guard.acquire():
        error_code = str(getattr(guard, "error_code", "") or "another_instance_running")
        if error_code == "config_dir_unavailable":
            return StartupBootstrapResult(
                False,
                14,
                error_code,
                "无法访问 AimerWT 配置目录，请检查文档目录权限。",
                None,
                None,
            )
        return StartupBootstrapResult(
            False,
            10,
            "another_instance_running",
            "已有一个 AimerWT 正在运行，请先关闭后再启动。",
            None,
            None,
        )

    current_lock_suspended = False
    suspend_current_lock = getattr(guard, "suspend_current_lock", None)
    if callable(suspend_current_lock):
        try:
            suspend_current_lock()
            current_lock_suspended = True
        except OSError as error:
            guard.release()
            return StartupBootstrapResult(
                False,
                14,
                "config_dir_unavailable",
                f"无法准备配置目录切换：{error}",
                None,
                None,
            )

    try:
        migration = migration_runner(
            str(app_version),
            legacy_dir=legacy_dir,
            target_dir=target_dir,
        )
    except MigrationError as error:
        guard.release()
        return StartupBootstrapResult(
            False,
            error.exit_code,
            error.error_code,
            str(error),
            None,
            None,
        )
    except OSError as error:
        guard.release()
        return StartupBootstrapResult(
            False,
            14,
            "config_dir_unavailable",
            f"无法访问 AimerWT 配置目录：{error}",
            None,
            None,
        )
    except Exception as error:
        guard.release()
        return StartupBootstrapResult(
            False,
            11,
            "migration_switch_failed",
            f"配置迁移未完成，旧数据保持不变：{error}",
            None,
            None,
        )

    if current_lock_suspended:
        resume_current_lock = getattr(guard, "resume_current_lock", None)
        if not callable(resume_current_lock) or not resume_current_lock():
            error_code = str(getattr(guard, "error_code", "") or "config_dir_unavailable")
            guard.release()
            exit_code = 10 if error_code == "another_instance_running" else 14
            message = (
                "已有另一个 AimerWT 正在运行，请先关闭后再启动。"
                if exit_code == 10
                else "迁移已完成，但无法重新占用新配置目录锁。"
            )
            return StartupBootstrapResult(
                False,
                exit_code,
                error_code,
                message,
                migration,
                None,
            )

    return StartupBootstrapResult(True, 0, "", "", migration, guard)


def _path_is_within(path: str | Path, parent: str | Path) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(Path(parent).resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _restore_paths_from_registry(config_manager: Any, record: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(record, dict):
        return False, ""
    paths = record.get("paths")
    if not isinstance(paths, dict):
        return False, ""
    root_record = paths.get("resource_root")
    if not isinstance(root_record, dict) or not str(root_record.get("path") or "").strip():
        return False, ""

    config = config_manager.config
    root_path = str(root_record["path"])
    root_id = str(root_record.get("root_id") or "")
    if bool(getattr(config_manager, "loaded_from_disk", False)):
        return False, root_id
    config["resource_root_dir"] = root_path
    history = []
    for item in root_record.get("previous_paths", []) or []:
        item_path = str((item or {}).get("path") or "").strip()
        if item_path and item_path not in history:
            history.append(item_path)
    config["resource_root_history"] = history[:5]

    metadata = config.get("path_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        config["path_metadata"] = metadata
    overrides = config.get("resource_path_overrides")
    if not isinstance(overrides, dict):
        overrides = {}
        config["resource_path_overrides"] = overrides

    resource_roles = (
        "voice_library",
        "sights_library",
        "task_library",
        "model_library",
        "hangar_library",
        "backup_root",
        "sound_backup",
        "custom_text_backup",
    )
    for role in ("resource_root", *resource_roles, "pending_dir", "game_root", "game_usersights"):
        path_record = paths.get(role)
        if not isinstance(path_record, dict):
            continue
        metadata[role] = {
            "user_modified": bool(path_record.get("user_modified", False)),
            "path_source": "recovery_scan",
        }
    for role in resource_roles:
        path_record = paths.get(role)
        path_text = str((path_record or {}).get("path") or "").strip()
        if path_text and Path(path_text).exists() and not _path_is_within(path_text, root_path):
            overrides[role] = path_text

    voice_record = paths.get("voice_library") or {}
    config["library_dir"] = str(voice_record.get("path") or "")
    pending_record = paths.get("pending_dir") or {}
    game_record = paths.get("game_root") or {}
    sights_record = paths.get("game_usersights") or {}
    config["pending_dir"] = str(pending_record.get("path") or "")
    config["game_path"] = str(game_record.get("path") or "")
    config["sights_path"] = str(sights_record.get("path") or "")
    return True, root_id


RESOURCE_MIGRATION_CHOICES = {"use_existing", "copy_to_current", "use_empty"}


def _resource_root_is_empty(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    try:
        marker_names = set(ROLE_MARKER_FILENAMES.values())
        for candidate in path.rglob("*"):
            if candidate.is_symlink():
                return False
            if candidate.is_dir():
                continue
            if candidate.name == RESOURCE_MARKER_NOTE or candidate.name in marker_names:
                continue
            return False
        return True
    except OSError:
        return False


def _apply_legacy_resource_choice(
    config_manager: Any,
    resource_manager: Any,
    *,
    install_dir: Path,
    migration: dict[str, Any] | None,
    previous_record: dict[str, Any] | None,
    choice_provider: Callable[[Path, Path], str] | None,
    copy_runner: Callable[..., dict[str, str]],
) -> tuple[str, dict[str, str] | None]:
    migration_data = migration if isinstance(migration, dict) else {}
    configured_text = str(config_manager.config.get("resource_root_dir") or "").strip()
    if (
        not migration_data.get("legacy_data_retained")
        or previous_record is not None
        or not configured_text
    ):
        return "", None

    candidate = Path(configured_text)
    current_default = install_dir / DIR_RESOURCE_ROOT
    try:
        same_path = candidate.resolve(strict=False) == current_default.resolve(strict=False)
    except OSError:
        same_path = os.path.normcase(str(candidate)) == os.path.normcase(str(current_default))
    if same_path or not candidate.is_dir() or not _resource_root_is_empty(current_default):
        return "", None
    if not callable(choice_provider):
        raise StartupRegistrationError(
            "resource_migration_choice_required",
            "发现旧资源库和新的空资源位置，需要先选择继续使用、复制或使用新空库。",
            11,
        )
    try:
        choice = str(choice_provider(candidate, current_default) or "")
    except Exception as error:
        raise StartupRegistrationError(
            "resource_migration_choice_required",
            f"无法显示资源库迁移选择：{error}",
            11,
        ) from error
    if choice not in RESOURCE_MIGRATION_CHOICES:
        raise StartupRegistrationError(
            "resource_migration_choice_required",
            "尚未选择如何处理旧资源库，未继续启动。",
            11,
        )

    copy_result = None
    metadata = config_manager.config.get("path_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        config_manager.config["path_metadata"] = metadata
    if choice == "copy_to_current":
        try:
            copy_result = copy_runner(candidate, current_default)
        except (OSError, ResourceCopyError) as error:
            raise StartupRegistrationError("migration_switch_failed", str(error), 11) from error
        config_manager.config["resource_root_dir"] = str(current_default)
        metadata["resource_root"] = {"user_modified": False, "path_source": "migration_copied"}
    elif choice == "use_empty":
        config_manager.config["resource_root_dir"] = str(current_default)
        metadata["resource_root"] = {"user_modified": False, "path_source": "migration_new_default"}
    else:
        metadata["resource_root"] = {"user_modified": False, "path_source": "legacy_setting"}
    config_manager.config["library_dir"] = str(resource_manager.get_paths().voice_library_dir)
    if not config_manager.save_config():
        raise StartupRegistrationError("config_dir_unavailable", "无法保存资源库迁移选择。", 14)
    return choice, copy_result


def register_startup_installation(
    config_manager: Any,
    resource_manager: Any,
    *,
    app_version: str,
    migration: dict[str, Any] | None,
    install_dir: str | Path | None = None,
    executable_path: str | Path | None = None,
    build_id: str | None = None,
    registry_factory: Callable[..., InstallationRegistry] = InstallationRegistry,
    resource_migration_choice_provider: Callable[[Path, Path], str] | None = None,
    resource_copy_runner: Callable[..., dict[str, str]] = copy_resource_root_transactional,
) -> StartupRegistration:
    """恢复资源位置、登记当前安装，并绑定后续配置保存回调。"""
    if getattr(config_manager, "load_error_code", ""):
        raise StartupRegistrationError(
            "registry_corrupt",
            "新的 AimerWT 设置文件无法读取，已保留原文件且未继续启动。",
            12,
        )
    if executable_path is None:
        executable_path = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent / "main.py"
    executable_path = Path(executable_path)
    if install_dir is None:
        install_dir = executable_path.parent
    try:
        registry = registry_factory(
            config_manager.config_dir,
            Path(install_dir),
            executable_path,
            str(app_version),
            build_id or os.environ.get("AIMERWT_BUILD_ID") or None,
        )
        previous_record = registry.find_current_record()
    except OSError as error:
        raise StartupRegistrationError("config_dir_unavailable", str(error), 14) from error
    except RegistryConflictError as error:
        raise StartupRegistrationError(
            "registry_busy",
            "另一个 AimerWT 正在保存安装登记，请稍后重试。",
            14,
        ) from error
    except RegistryError as error:
        raise StartupRegistrationError("registry_corrupt", str(error), 12) from error

    restored_from_registry, expected_root_id = _restore_paths_from_registry(
        config_manager,
        previous_record,
    )
    try:
        recovery = resource_manager.recover_configured_root(expected_root_id=expected_root_id or None)
    except OSError as error:
        raise StartupRegistrationError("config_dir_unavailable", str(error), 14) from error
    if recovery.status == "conflict":
        candidates = "、".join(str(path) for path in recovery.candidates)
        raise StartupRegistrationError(
            "migration_source_conflict",
            f"发现多个身份相同的 AimerWT 资源库，未自动选择：{candidates}",
            11,
        )
    if expected_root_id and recovery.status == "missing":
        raise StartupRegistrationError(
            "migration_source_conflict",
            "原资源库已经不在登记位置，请重新选择原资源库后再继续。",
            11,
        )
    if (restored_from_registry or recovery.status == "recovered") and not config_manager.save_config():
        raise StartupRegistrationError(
            "config_dir_unavailable",
            "已找到原有路径，但无法恢复到新的设置文件。",
            14,
        )

    try:
        config_before_resource_choice = copy.deepcopy(config_manager.config)
        settings_path = Path(config_manager.config_file)
        settings_before_resource_choice = (
            settings_path.read_bytes() if settings_path.is_file() else None
        )
    except OSError as error:
        raise StartupRegistrationError("config_dir_unavailable", str(error), 14) from error

    migration_for_registry = dict(migration or {})
    resource_choice, copy_result = _apply_legacy_resource_choice(
        config_manager,
        resource_manager,
        install_dir=Path(install_dir),
        migration=migration,
        previous_record=previous_record,
        choice_provider=resource_migration_choice_provider,
        copy_runner=resource_copy_runner,
    )
    if resource_choice:
        migration_for_registry["resource_migration_choice"] = resource_choice
    if copy_result is not None:
        migration_for_registry["resource_copy"] = copy_result

    def _rollback_resource_choice() -> None:
        if not resource_choice:
            return
        restore = getattr(config_manager, "_restore_after_save_failure", None)
        if not callable(restore) or not restore(
            settings_before_resource_choice,
            config_before_resource_choice,
            restore_disk=True,
        ):
            raise StartupRegistrationError(
                "config_dir_unavailable",
                "安装登记失败，且资源库选择未能恢复到保存前状态。",
                14,
            )

    try:
        marker_result = resource_manager.ensure_standard_dirs_and_markers(expected_root_id or None)
    except OSError as error:
        _rollback_resource_choice()
        raise StartupRegistrationError("config_dir_unavailable", str(error), 14) from error
    if not marker_result.get("success"):
        _rollback_resource_choice()
        raise StartupRegistrationError(
            "migration_source_conflict",
            "资源库身份存在冲突，未继续启动："
            + "；".join(marker_result.get("marker_errors", [])),
            11,
        )

    def _refresh_registry(_saved_config: dict[str, Any]) -> bool:
        refreshed_markers = resource_manager.ensure_standard_dirs_and_markers()
        if not refreshed_markers.get("success"):
            return False
        snapshot = build_installation_path_snapshot(
            config_manager.config,
            resource_manager.get_paths(),
        )
        try:
            registry.register_current(snapshot, migration=migration_for_registry)
            return True
        except (RegistryError, OSError):
            return False

    snapshot = build_installation_path_snapshot(
        config_manager.config,
        resource_manager.get_paths(),
    )
    try:
        current = registry.register_current(snapshot, migration=migration_for_registry)
    except RegistryConflictError as error:
        _rollback_resource_choice()
        raise StartupRegistrationError(
            "registry_busy",
            "另一个 AimerWT 正在保存安装登记，请稍后重试。",
            14,
        ) from error
    except OSError as error:
        _rollback_resource_choice()
        raise StartupRegistrationError("config_dir_unavailable", str(error), 14) from error
    except RegistryError as error:
        _rollback_resource_choice()
        raise StartupRegistrationError("registry_corrupt", str(error), 12) from error
    config_manager.set_save_callback(_refresh_registry)
    return StartupRegistration(registry, current, recovery, marker_result)
