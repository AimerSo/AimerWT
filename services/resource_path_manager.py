# -*- coding: utf-8 -*-
"""
AimerWT 资源库路径管理：统一解析资源库根目录、标准子库、备份目录和目录识别文件。
"""
import hashlib
import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.logger import get_logger
from utils.utils import get_app_data_dir

log = get_logger(__name__)

DIR_RESOURCE_ROOT = "AimerWT资源库"
DIR_PENDING = "待解压区"
DIR_VOICE_LIBRARY_NAME = "WT语音包库"
DIR_SIGHTS_LIBRARY_NAME = "WT炮镜库"
DIR_TASK_LIBRARY_NAME = "WT任务库"
DIR_MODEL_LIBRARY_NAME = "WT模型库"
DIR_HANGAR_LIBRARY_NAME = "WT机库"
DIR_BACKUP_ROOT_NAME = "WT备份"
DIR_SOUND_BACKUP_NAME = "Sound源文件备份"
DIR_CUSTOM_TEXT_BACKUP_NAME = "自定义文本备份"

DIR_LIBRARY = f"{DIR_RESOURCE_ROOT}/{DIR_VOICE_LIBRARY_NAME}"
DIR_SIGHTS_LIBRARY = f"{DIR_RESOURCE_ROOT}/{DIR_SIGHTS_LIBRARY_NAME}"
DIR_TASK_LIBRARY = f"{DIR_RESOURCE_ROOT}/{DIR_TASK_LIBRARY_NAME}"
DIR_MODEL_LIBRARY = f"{DIR_RESOURCE_ROOT}/{DIR_MODEL_LIBRARY_NAME}"
DIR_HANGAR_LIBRARY = f"{DIR_RESOURCE_ROOT}/{DIR_HANGAR_LIBRARY_NAME}"

RESOURCE_ROOT_MARKER = "AimerWT_ResourceRoot.json"
RESOURCE_MARKER_NOTE = "AimerWT_JSON文件说明.txt"
RESOURCE_MARKER_VERSION = 1


@dataclass(frozen=True)
class ResourcePaths:
    resource_root_dir: Path
    voice_library_dir: Path
    sights_library_dir: Path
    task_library_dir: Path
    model_library_dir: Path
    hangar_library_dir: Path
    backup_root_dir: Path
    sound_backup_dir: Path
    custom_text_backup_dir: Path


@dataclass(frozen=True)
class ResourcePathResolution:
    paths: ResourcePaths
    conflicts: dict[str, tuple[Path, ...]]
    root_id: str = ""


@dataclass(frozen=True)
class ResourceRootRecovery:
    status: str
    resource_root_dir: Path | None
    root_id: str
    candidates: tuple[Path, ...]


MARKER_DEFINITIONS: tuple[tuple[str, str, str | None], ...] = (
    (RESOURCE_ROOT_MARKER, "resource_root", None),
    (f"{DIR_VOICE_LIBRARY_NAME}/AimerWT_VoiceLibrary.json", "voice_library", "resource_root"),
    (f"{DIR_SIGHTS_LIBRARY_NAME}/AimerWT_SightsLibrary.json", "sights_library", "resource_root"),
    (f"{DIR_TASK_LIBRARY_NAME}/AimerWT_TaskLibrary.json", "task_library", "resource_root"),
    (f"{DIR_MODEL_LIBRARY_NAME}/AimerWT_ModelLibrary.json", "model_library", "resource_root"),
    (f"{DIR_HANGAR_LIBRARY_NAME}/AimerWT_HangarLibrary.json", "hangar_library", "resource_root"),
    (f"{DIR_BACKUP_ROOT_NAME}/AimerWT_BackupRoot.json", "backup_root", "resource_root"),
    (f"{DIR_BACKUP_ROOT_NAME}/{DIR_SOUND_BACKUP_NAME}/AimerWT_SoundBackup.json", "sound_backup", "backup_root"),
    (f"{DIR_BACKUP_ROOT_NAME}/{DIR_CUSTOM_TEXT_BACKUP_NAME}/AimerWT_CustomTextBackup.json", "custom_text_backup", "backup_root"),
)

ROLE_MARKER_FILENAMES = {
    "resource_root": RESOURCE_ROOT_MARKER,
    "voice_library": "AimerWT_VoiceLibrary.json",
    "sights_library": "AimerWT_SightsLibrary.json",
    "task_library": "AimerWT_TaskLibrary.json",
    "model_library": "AimerWT_ModelLibrary.json",
    "hangar_library": "AimerWT_HangarLibrary.json",
    "backup_root": "AimerWT_BackupRoot.json",
    "sound_backup": "AimerWT_SoundBackup.json",
    "custom_text_backup": "AimerWT_CustomTextBackup.json",
}

ROLE_PATH_ATTRIBUTES = {
    "resource_root": "resource_root_dir",
    "voice_library": "voice_library_dir",
    "sights_library": "sights_library_dir",
    "task_library": "task_library_dir",
    "model_library": "model_library_dir",
    "hangar_library": "hangar_library_dir",
    "backup_root": "backup_root_dir",
    "sound_backup": "sound_backup_dir",
    "custom_text_backup": "custom_text_backup_dir",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _date_part(value: Any) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else ""


def _norm_path(path: str | Path) -> str:
    try:
        resolved = Path(path).resolve(strict=False)
    except Exception:
        resolved = Path(path)
    return os.path.normcase(os.path.normpath(str(resolved)))


class ResourceCopyError(RuntimeError):
    pass


def _is_reparse_path(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _resource_tree_files(root: Path) -> list[Path]:
    if _is_reparse_path(root):
        raise ResourceCopyError(f"资源库是目录连接或符号链接：{root}")
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        for dir_name in list(dir_names):
            child = current / dir_name
            if _is_reparse_path(child):
                raise ResourceCopyError(f"资源库中包含目录连接或符号链接：{child}")
        for file_name in file_names:
            child = current / file_name
            if _is_reparse_path(child):
                raise ResourceCopyError(f"资源库中包含文件链接：{child}")
            files.append(child)
    return files


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_resource_root_transactional(
    source_root: str | Path,
    destination_root: str | Path,
    *,
    free_space_provider=None,
    minimum_free_reserve: int = 100 * 1024 * 1024,
) -> dict[str, str]:
    """复制完整资源库；校验成功前不启用目标目录，源目录始终保留。"""
    source = Path(source_root)
    destination = Path(destination_root)
    if not source.is_dir():
        raise ResourceCopyError(f"旧资源库不存在：{source}")
    if _norm_path(source) == _norm_path(destination):
        raise ResourceCopyError("旧资源库与新位置相同，无需复制")
    if destination.exists():
        if _is_reparse_path(destination):
            raise ResourceCopyError(f"新资源位置是目录连接或符号链接：{destination}")
        try:
            if any(destination.iterdir()):
                raise ResourceCopyError(f"新资源位置不是空目录：{destination}")
        except OSError as error:
            raise ResourceCopyError(f"无法检查新资源位置：{error}") from error

    source_files = _resource_tree_files(source)
    planned_bytes = sum(path.stat().st_size for path in source_files)
    destination.parent.mkdir(parents=True, exist_ok=True)
    free_bytes = int(
        free_space_provider(destination.parent)
        if free_space_provider
        else shutil.disk_usage(destination.parent).free
    )
    if free_bytes < int(planned_bytes * 1.1) + max(0, int(minimum_free_reserve)):
        raise ResourceCopyError("复制资源库所需空间不足，旧资源库保持不变")

    operation_id = uuid.uuid4().hex[:8]
    stage = destination.parent / f"{destination.name}.copy-{operation_id}"
    rollback = destination.parent / f"{destination.name}.before-copy-{operation_id}"
    try:
        shutil.copytree(source, stage, symlinks=True)
        copied_files = _resource_tree_files(stage)
        copied_by_relative = {path.relative_to(stage): path for path in copied_files}
        for source_file in source_files:
            relative = source_file.relative_to(source)
            copied_file = copied_by_relative.get(relative)
            if copied_file is None or source_file.stat().st_size != copied_file.stat().st_size:
                raise ResourceCopyError(f"资源文件复制不完整：{relative}")
            if _sha256_file(source_file) != _sha256_file(copied_file):
                raise ResourceCopyError(f"资源文件复制校验失败：{relative}")
        if destination.exists():
            destination.replace(rollback)
        try:
            stage.replace(destination)
        except OSError:
            if rollback.exists() and not destination.exists():
                rollback.replace(destination)
            raise
    except (OSError, ResourceCopyError) as error:
        raise ResourceCopyError(f"资源库复制未完成，旧资源库仍可继续使用：{error}") from error
    return {
        "source_root": str(source),
        "destination_root": str(destination),
        "retained_previous_target": str(rollback) if rollback.exists() else "",
        "stage_dir": str(stage) if stage.exists() else "",
    }


def default_resource_root_dir() -> Path:
    return get_app_data_dir() / DIR_RESOURCE_ROOT


def resolve_resource_root_dir(resource_root_dir: str | Path | None = None) -> Path:
    text = str(resource_root_dir or "").strip()
    return Path(text) if text else default_resource_root_dir()


def infer_resource_root_from_legacy_library_dir(library_dir: str | Path | None) -> Path | None:
    text = str(library_dir or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.name == DIR_VOICE_LIBRARY_NAME and path.parent.name == DIR_RESOURCE_ROOT:
        return path.parent
    return None


def _default_resource_paths(resource_root_dir: str | Path | None = None) -> ResourcePaths:
    root = resolve_resource_root_dir(resource_root_dir)
    backup_root = root / DIR_BACKUP_ROOT_NAME
    return ResourcePaths(
        resource_root_dir=root,
        voice_library_dir=root / DIR_VOICE_LIBRARY_NAME,
        sights_library_dir=root / DIR_SIGHTS_LIBRARY_NAME,
        task_library_dir=root / DIR_TASK_LIBRARY_NAME,
        model_library_dir=root / DIR_MODEL_LIBRARY_NAME,
        hangar_library_dir=root / DIR_HANGAR_LIBRARY_NAME,
        backup_root_dir=backup_root,
        sound_backup_dir=backup_root / DIR_SOUND_BACKUP_NAME,
        custom_text_backup_dir=backup_root / DIR_CUSTOM_TEXT_BACKUP_NAME,
    )


def _valid_marker(
    data: dict[str, Any] | None,
    role: str,
    root_id: str | None = None,
) -> bool:
    if not isinstance(data, dict):
        return False
    if (
        data.get("app") != "AimerWT"
        or data.get("schema") != "resource_marker"
        or data.get("version") != RESOURCE_MARKER_VERSION
        or data.get("role") != role
    ):
        return False
    marker_root_id = str(data.get("root_id") or "")
    if not marker_root_id:
        return False
    return not root_id or marker_root_id == root_id


def read_resource_marker(marker_path: str | Path) -> dict[str, Any] | None:
    return _read_marker(Path(marker_path))


def _marker_candidates(parent_dir: Path, role: str, root_id: str) -> list[Path]:
    if not parent_dir.is_dir() or parent_dir.is_symlink():
        return []
    marker_name = ROLE_MARKER_FILENAMES[role]
    candidates: list[Path] = []
    try:
        child_dirs = [item for item in parent_dir.iterdir() if item.is_dir() and not item.is_symlink()]
    except OSError:
        return []
    for child_dir in child_dirs:
        data = _read_marker(child_dir / marker_name)
        if _valid_marker(data, role, root_id):
            candidates.append(child_dir)
    return candidates


def resolve_resource_paths(
    resource_root_dir: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> ResourcePathResolution:
    defaults = _default_resource_paths(resource_root_dir)
    values = {role: getattr(defaults, attribute) for role, attribute in ROLE_PATH_ATTRIBUTES.items()}
    clean_overrides = overrides if isinstance(overrides, dict) else {}
    root_marker = _read_marker(defaults.resource_root_dir / RESOURCE_ROOT_MARKER)
    root_id = str(root_marker.get("root_id") or "") if _valid_marker(root_marker, "resource_root") else ""
    conflicts: dict[str, tuple[Path, ...]] = {}

    if root_id:
        for role in ("voice_library", "sights_library", "task_library", "model_library", "hangar_library", "backup_root"):
            override_text = str(clean_overrides.get(role) or "").strip()
            if override_text:
                values[role] = Path(override_text)
                continue
            candidates = _marker_candidates(defaults.resource_root_dir, role, root_id)
            if len(candidates) == 1:
                values[role] = candidates[0]
            elif len(candidates) > 1:
                conflicts[role] = tuple(candidates)

        backup_root = values["backup_root"]
        values["sound_backup"] = backup_root / DIR_SOUND_BACKUP_NAME
        values["custom_text_backup"] = backup_root / DIR_CUSTOM_TEXT_BACKUP_NAME
        for role in ("sound_backup", "custom_text_backup"):
            override_text = str(clean_overrides.get(role) or "").strip()
            if override_text:
                values[role] = Path(override_text)
                continue
            candidates = _marker_candidates(backup_root, role, root_id)
            if len(candidates) == 1:
                values[role] = candidates[0]
            elif len(candidates) > 1:
                conflicts[role] = tuple(candidates)
    else:
        for role in ROLE_PATH_ATTRIBUTES:
            if role == "resource_root":
                continue
            override_text = str(clean_overrides.get(role) or "").strip()
            if override_text:
                values[role] = Path(override_text)
        if str(clean_overrides.get("backup_root") or "").strip():
            backup_root = values["backup_root"]
            if not str(clean_overrides.get("sound_backup") or "").strip():
                values["sound_backup"] = backup_root / DIR_SOUND_BACKUP_NAME
            if not str(clean_overrides.get("custom_text_backup") or "").strip():
                values["custom_text_backup"] = backup_root / DIR_CUSTOM_TEXT_BACKUP_NAME

    paths = ResourcePaths(**{attribute: values[role] for role, attribute in ROLE_PATH_ATTRIBUTES.items()})
    return ResourcePathResolution(paths=paths, conflicts=conflicts, root_id=root_id)


def build_resource_paths(
    resource_root_dir: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> ResourcePaths:
    return resolve_resource_paths(resource_root_dir, overrides).paths


def recover_resource_root(
    configured_root: str | Path | None,
    default_root: str | Path | None,
    history: list[str | Path] | tuple[str | Path, ...] | None,
    expected_root_id: str | None = None,
) -> ResourceRootRecovery:
    trusted_paths = [Path(item) for item in (configured_root, default_root, *(history or [])) if str(item or "").strip()]
    candidates: list[tuple[Path, str]] = []
    seen: set[str] = set()

    def _consider(path: Path) -> None:
        normalized = _norm_path(path)
        if normalized in seen or path.is_symlink():
            return
        seen.add(normalized)
        marker = _read_marker(path / RESOURCE_ROOT_MARKER)
        if not _valid_marker(marker, "resource_root", expected_root_id):
            return
        candidates.append((path, str(marker.get("root_id") or "")))

    for trusted_path in trusted_paths:
        _consider(trusted_path)
        parent = trusted_path.parent
        if not parent.is_dir() or parent.is_symlink():
            continue
        try:
            for child in parent.iterdir():
                if child.is_dir() and not child.is_symlink():
                    _consider(child)
        except OSError:
            continue

    if not candidates:
        return ResourceRootRecovery("missing", None, str(expected_root_id or ""), ())

    grouped: dict[str, list[Path]] = {}
    for path, root_id in candidates:
        grouped.setdefault(root_id, []).append(path)
    duplicate_paths = [path for paths in grouped.values() if len(paths) > 1 for path in paths]
    if duplicate_paths:
        return ResourceRootRecovery(
            "conflict",
            None,
            str(expected_root_id or candidates[0][1]),
            tuple(duplicate_paths),
        )

    preferred: list[Path] = []
    for value in (configured_root, default_root):
        if str(value or "").strip():
            preferred.append(Path(value))
    for preferred_path in preferred:
        for candidate_path, root_id in candidates:
            if _norm_path(preferred_path) == _norm_path(candidate_path):
                return ResourceRootRecovery("current", candidate_path, root_id, tuple(path for path, _ in candidates))
    if len(candidates) == 1:
        path, root_id = candidates[0]
        return ResourceRootRecovery("recovered", path, root_id, (path,))
    return ResourceRootRecovery("conflict", None, "", tuple(path for path, _ in candidates))


def update_resource_root_history(
    history: list[str] | tuple[str, ...] | None,
    old_root: str | Path | None,
    current_root: str | Path | None = None,
    limit: int = 5,
) -> list[str]:
    old_text = str(old_root or "").strip()
    current_text = str(current_root or "").strip()
    result: list[str] = []
    seen: set[str] = set()

    def _append(path_text: str) -> None:
        if not path_text:
            return
        if current_text and _norm_path(path_text) == _norm_path(current_text):
            return
        norm = _norm_path(path_text)
        if norm in seen:
            return
        seen.add(norm)
        result.append(path_text)

    _append(old_text)
    for item in history or []:
        _append(str(item))
    return result[:limit]


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def _read_marker(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception as e:
        log.warning(f"资源库识别文件读取失败，按缺失处理: {path} ({e})")
        return None


class ResourcePathManager:
    """
    以配置字典为来源，提供 AimerWT 长期资源库的标准路径和 marker 维护能力。
    """

    def __init__(self, config: dict[str, Any] | None = None, app_version: str = "3.1"):
        self.config = config if config is not None else {}
        self.app_version = app_version

    def get_resource_root_dir(self) -> Path:
        return resolve_resource_root_dir(self.config.get("resource_root_dir", ""))

    def get_paths(self) -> ResourcePaths:
        return self.get_resolution().paths

    def get_resolution(self) -> ResourcePathResolution:
        return resolve_resource_paths(
            self.get_resource_root_dir(),
            self.config.get("resource_path_overrides", {}),
        )

    def recover_configured_root(
        self,
        default_root: str | Path | None = None,
        expected_root_id: str | None = None,
    ) -> ResourceRootRecovery:
        configured_root = self.get_resource_root_dir()
        result = recover_resource_root(
            configured_root=configured_root,
            default_root=default_root or default_resource_root_dir(),
            history=self.config.get("resource_root_history", []),
            expected_root_id=expected_root_id,
        )
        if result.status != "recovered" or result.resource_root_dir is None:
            return result

        recovered_root = str(result.resource_root_dir)
        self.config["resource_root_history"] = update_resource_root_history(
            self.config.get("resource_root_history", []),
            configured_root,
            current_root=recovered_root,
        )
        self.config["resource_root_dir"] = recovered_root
        metadata = self.config.get("path_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            self.config["path_metadata"] = metadata
        metadata["resource_root"] = {
            "user_modified": False,
            "path_source": "recovery_scan",
        }
        self.config["library_dir"] = str(self.get_paths().voice_library_dir)
        return result

    def get_resource_path_info(self) -> dict[str, Any]:
        paths = self.get_paths()
        default_paths = build_resource_paths("")
        return {
            "resource_root_dir": str(paths.resource_root_dir),
            "default_resource_root_dir": str(default_paths.resource_root_dir),
            "custom_resource_root_dir": self.config.get("resource_root_dir", ""),
            "resource_root_history": list(self.config.get("resource_root_history", []) or []),
            "voice_library_dir": str(paths.voice_library_dir),
            "sights_library_dir": str(paths.sights_library_dir),
            "task_library_dir": str(paths.task_library_dir),
            "model_library_dir": str(paths.model_library_dir),
            "hangar_library_dir": str(paths.hangar_library_dir),
            "backup_root_dir": str(paths.backup_root_dir),
            "sound_backup_dir": str(paths.sound_backup_dir),
            "custom_text_backup_dir": str(paths.custom_text_backup_dir),
        }

    def ensure_standard_dirs_and_markers(
        self,
        root_id_hint: str | None = None,
    ) -> dict[str, Any]:
        resolution = self.get_resolution()
        paths = resolution.paths
        created: list[str] = []
        marker_errors: list[str] = []

        if resolution.conflicts:
            return {
                "success": False,
                "resource_root_dir": str(paths.resource_root_dir),
                "created_dirs": [],
                "marker_errors": [
                    f"{role} 发现多个相同身份目录: {', '.join(str(path) for path in candidates)}"
                    for role, candidates in resolution.conflicts.items()
                ],
            }

        for dir_path in (
            paths.resource_root_dir,
            paths.voice_library_dir,
            paths.sights_library_dir,
            paths.task_library_dir,
            paths.model_library_dir,
            paths.hangar_library_dir,
            paths.backup_root_dir,
            paths.sound_backup_dir,
            paths.custom_text_backup_dir,
        ):
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                created.append(str(dir_path))

        root_marker = paths.resource_root_dir / RESOURCE_ROOT_MARKER
        root_data = _read_marker(root_marker) or {}
        if root_marker.exists() and not _valid_marker(root_data, "resource_root"):
            return {
                "success": False,
                "resource_root_dir": str(paths.resource_root_dir),
                "created_dirs": created,
                "marker_errors": ["资源库识别文件损坏或格式不受支持"],
            }
        existing_root_id = str(root_data.get("root_id") or "")
        if root_id_hint and existing_root_id and existing_root_id != str(root_id_hint):
            return {
                "success": False,
                "resource_root_dir": str(paths.resource_root_dir),
                "created_dirs": created,
                "marker_errors": ["资源库身份与安装登记不一致"],
            }
        root_id = existing_root_id or str(root_id_hint or uuid.uuid4())
        now = _now_iso()
        marker_paths = {
            role: getattr(paths, ROLE_PATH_ATTRIBUTES[role]) / ROLE_MARKER_FILENAMES[role]
            for role in ROLE_PATH_ATTRIBUTES
            if role != "resource_root"
        }
        marker_data: dict[str, dict[str, Any]] = {}
        for _relative_marker, role, parent_role in MARKER_DEFINITIONS[1:]:
            marker_path = marker_paths[role]
            previous = _read_marker(marker_path) or {}
            marker_data[role] = previous
            if marker_path.exists() and (
                not _valid_marker(previous, role, root_id)
                or previous.get("parent_role") != parent_role
            ):
                return {
                    "success": False,
                    "resource_root_dir": str(paths.resource_root_dir),
                    "created_dirs": created,
                    "marker_errors": [f"{role} 目录属于另一个资源库或识别文件损坏"],
                }

        try:
            self._write_marker(root_marker, "resource_root", None, root_id, root_data, now)
            for _relative_marker, role, parent_role in MARKER_DEFINITIONS[1:]:
                marker_path = marker_paths[role]
                self._write_marker(marker_path, role, parent_role, root_id, marker_data[role], now)
            self._write_marker_note(paths.resource_root_dir)
        except Exception as e:
            marker_errors.append(str(e))
            log.warning(f"资源库识别文件写入失败: {e}")

        return {
            "success": len(marker_errors) == 0,
            "resource_root_dir": str(paths.resource_root_dir),
            "created_dirs": created,
            "marker_errors": marker_errors,
        }

    def _write_marker(
        self,
        marker_path: Path,
        role: str,
        parent_role: str | None,
        root_id: str,
        previous: dict[str, Any],
        now: str,
    ) -> None:
        required_keys = {
            "app",
            "schema",
            "version",
            "role",
            "root_id",
            "parent_role",
            "created_by",
            "last_seen_by",
            "created_at",
            "last_seen_at",
        }
        if (
            marker_path.exists()
            and required_keys.issubset(previous.keys())
            and previous.get("app") == "AimerWT"
            and previous.get("schema") == "resource_marker"
            and previous.get("version") == RESOURCE_MARKER_VERSION
            and previous.get("role") == role
            and previous.get("root_id") == root_id
            and previous.get("parent_role") == parent_role
            and previous.get("last_seen_by") == self.app_version
            and _date_part(previous.get("last_seen_at")) == _date_part(now)
        ):
            return
        data = {
            "app": "AimerWT",
            "schema": "resource_marker",
            "version": RESOURCE_MARKER_VERSION,
            "role": role,
            "root_id": root_id,
            "parent_role": parent_role,
            "created_by": previous.get("created_by") or self.app_version,
            "last_seen_by": self.app_version,
            "created_at": previous.get("created_at") or now,
            "last_seen_at": now,
        }
        _atomic_write_json(marker_path, data)

    def _write_marker_note(self, root_dir: Path) -> None:
        note_path = root_dir / RESOURCE_MARKER_NOTE
        if note_path.exists():
            return
        note_path.write_text(
            "这是 AimerWT 资源库识别文件说明。\n\n"
            "AimerWT 会在资源库和各个子库中生成 AimerWT_*.json 文件，\n"
            "用于识别这个文件夹属于语音包库、炮镜库、任务库、模型库、机库或备份库。\n\n"
            "这些 JSON 文件不包含账号、密码、隐私信息。\n"
            "除非你确定这个文件夹已经彻底不用了，否则不要单独删除、移动或改名这些 JSON 文件。\n\n"
            "如果你确定整个旧资源库已经废弃，可以删除整个旧资源库文件夹。\n",
            encoding="utf-8",
        )
