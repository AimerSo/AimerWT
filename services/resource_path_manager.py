# -*- coding: utf-8 -*-
"""
AimerWT 资源库路径管理：统一解析资源库根目录、标准子库、备份目录和目录识别文件。
"""
import json
import os
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


def build_resource_paths(resource_root_dir: str | Path | None = None) -> ResourcePaths:
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
        return build_resource_paths(self.get_resource_root_dir())

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

    def ensure_standard_dirs_and_markers(self) -> dict[str, Any]:
        paths = self.get_paths()
        created: list[str] = []
        marker_errors: list[str] = []

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
        root_id = str(root_data.get("root_id") or uuid.uuid4())
        now = _now_iso()

        try:
            self._write_marker(root_marker, "resource_root", None, root_id, root_data, now)
            for relative_marker, role, parent_role in MARKER_DEFINITIONS[1:]:
                marker_path = paths.resource_root_dir / relative_marker
                previous = _read_marker(marker_path) or {}
                self._write_marker(marker_path, role, parent_role, root_id, previous, now)
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
