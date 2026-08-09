# -*- coding: utf-8 -*-
"""
炮镜发布包的无状态路径与归档规则。

功能定位:
- 为主程序导入预检、真实安装和作者端兼容报告提供同一套目标推导答案。
- 只处理字符串和相对路径，不读取 UserSights、不创建目录、不执行安装。
- 保留 SightsManager 现有四种目标模式及错误文案。
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from services.sight_vehicle_catalog import normalize_vehicle_id


BLOCKED_ARCHIVE_EXTENSIONS = frozenset({
    ".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar", ".msi", ".com",
})
PREVIEW_ASSET_NAMES = frozenset({
    "preview.png", "preview.jpg", "preview.jpeg", "preview.webp",
})
PACKAGE_COVER_ASSET_NAMES = frozenset({
    *PREVIEW_ASSET_NAMES,
    "icon.png", "icon.jpg", "icon.jpeg", "icon.webp",
})
WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})
VEHICLE_SIGHT_PREFIXES = (
    "germ_", "ussr_", "us_", "uk_", "jp_", "cn_", "fr_", "it_", "sw_", "il_",
)
TARGET_DIR_UNSET = object()


def is_unsafe_windows_path_part(part: str) -> bool:
    """判断单个路径段是否命中 Windows 保留名或危险首尾字符。"""
    text = str(part or "")
    base_name = text.split(".", 1)[0].upper()
    return (
        text != text.strip()
        or text.endswith(".")
        or text.endswith(" ")
        or base_name in WINDOWS_RESERVED_NAMES
    )


def is_archive_member_path_safe(filename: str) -> bool:
    """保持主程序现有语义，校验归档成员是否为安全相对路径。"""
    raw_filename = str(filename or "")
    normalized = raw_filename.replace("\\", "/").strip()
    if not normalized or raw_filename != raw_filename.strip():
        return False
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return False
    parts = [part for part in normalized.split("/") if part]
    return ".." not in parts and not any(is_unsafe_windows_path_part(part) for part in parts)


def normalize_safe_relative_path(value: Any) -> str:
    """将作者输入归一化为 ZIP 使用的安全 POSIX 相对路径。"""
    raw_text = str(value or "")
    text = raw_text.strip().replace("\\", "/")
    if not text or raw_text != raw_text.strip():
        raise ValueError("路径不能为空或包含非法首尾字符")
    if text.startswith("/") or re.match(r"^[A-Za-z]:/", text):
        raise ValueError("路径必须是相对路径")

    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("路径包含不安全的上级目录")
    if any(is_unsafe_windows_path_part(part) for part in parts):
        raise ValueError("路径包含 Windows 非法名称")
    if any(re.search(r'[<>:"|?*\x00-\x1f]', part) for part in parts):
        raise ValueError("路径包含 Windows 非法字符")
    return str(PurePosixPath(*parts))


def normalize_sight_target_dir(target_dir: Any = None) -> str:
    """归一化主程序指定目录模式使用的单层 UserSights 目录名。"""
    raw_text = str(target_dir or "")
    text = raw_text.strip()
    if not text:
        return "all_tanks"
    if raw_text != text:
        raise ValueError("炮镜目标目录包含非法首尾字符")
    if text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError("炮镜目标目录只能是单层目录名")
    if re.search(r'[<>:"|?*\x00-\x1f]', text):
        raise ValueError("炮镜目标目录包含非法字符")
    if is_unsafe_windows_path_part(text):
        raise ValueError("炮镜目标目录使用了 Windows 非法名称")
    if Path(text).name != text:
        raise ValueError("炮镜目标目录只能是单层目录名")
    return text


def build_vehicle_sight_target(vehicle_id: Any, source_relative_path: Any) -> str:
    """为指定车辆或 all_tanks 生成安全的单层炮镜目标路径。"""
    raw_target_dir = str(vehicle_id or "").strip().lower()
    target_dir = "all_tanks" if raw_target_dir == "all_tanks" else normalize_vehicle_id(raw_target_dir)
    source_path = normalize_safe_relative_path(source_relative_path)
    source_name = PurePosixPath(source_path).name
    if PurePosixPath(source_name).suffix.lower() != ".blk":
        raise ValueError("炮镜源文件必须以 .blk 结尾")
    return normalize_safe_relative_path(str(PurePosixPath(target_dir) / source_name))

def looks_like_vehicle_sight_dir(name: str) -> bool:
    """判断顶层目录是否属于主程序可直接保留的载具目录。"""
    lower = str(name or "").lower()
    if lower == "all_tanks":
        return True
    return any(lower.startswith(prefix) for prefix in VEHICLE_SIGHT_PREFIXES)


def _normalize_real_paths(real_paths: Iterable[str | PurePosixPath]) -> list[PurePosixPath]:
    paths: list[PurePosixPath] = []
    for raw_path in real_paths:
        text = str(raw_path or "").replace("\\", "/").strip()
        if not text:
            continue
        paths.append(PurePosixPath(text))
    return paths


def infer_archive_target(
    real_paths: Iterable[str | PurePosixPath],
    archive_stem: str,
    requested_target_dir: Any = TARGET_DIR_UNSET,
) -> tuple[str, str]:
    """按主程序现行优先级推导归档目标模式和目录名。"""
    if requested_target_dir is not TARGET_DIR_UNSET:
        return "specified_dir", normalize_sight_target_dir(requested_target_dir)

    paths = _normalize_real_paths(real_paths)
    top_names = {path.parts[0] for path in paths if path.parts}
    all_under_top_dirs = bool(paths) and all(len(path.parts) > 1 for path in paths)
    if all_under_top_dirs and top_names and all(looks_like_vehicle_sight_dir(name) for name in top_names):
        return "usersights_structure", ""
    if all_under_top_dirs and len(top_names) == 1:
        return "single_folder", next(iter(top_names))
    return "archive_folder", str(archive_stem or "").strip()


def map_archive_member_to_target(
    member_path: str | PurePosixPath,
    target_mode: str,
    target_dir_name: str,
    archive_stem: str,
) -> str:
    """把 ZIP 内真实 BLK 路径映射为 UserSights 下的相对路径。"""
    source_rel = PurePosixPath(str(member_path).replace("\\", "/"))
    if target_mode == "specified_dir":
        target_rel = PurePosixPath(target_dir_name) / source_rel.name
    elif target_mode in {"usersights_structure", "single_folder"}:
        target_rel = source_rel
    else:
        target_rel = PurePosixPath(target_dir_name or archive_stem) / source_rel
    return str(target_rel)


def build_archive_install_mapping(
    real_paths: Iterable[str | PurePosixPath],
    archive_stem: str,
    requested_target_dir: Any = TARGET_DIR_UNSET,
) -> dict[str, Any]:
    """一次性返回目标模式和全部源到目标映射。"""
    paths = _normalize_real_paths(real_paths)
    target_mode, target_dir_name = infer_archive_target(
        paths,
        archive_stem,
        requested_target_dir=requested_target_dir,
    )
    entries = [
        {
            "source_relative_path": str(source_rel),
            "target_relative_path": map_archive_member_to_target(
                source_rel,
                target_mode,
                target_dir_name,
                archive_stem,
            ),
        }
        for source_rel in paths
    ]
    return {
        "target_mode": target_mode,
        "target_dir": target_dir_name,
        "entries": entries,
    }


def is_preview_asset_name(member_path: str | PurePosixPath) -> bool:
    """判断导入预检当前会计数的根目录无关 preview 文件名。"""
    return PurePosixPath(str(member_path).replace("\\", "/")).name.lower() in PREVIEW_ASSET_NAMES


def is_package_cover_asset_name(member_path: str | PurePosixPath) -> bool:
    """判断资源包封面读取链路支持的 preview/icon 文件名。"""
    return PurePosixPath(str(member_path).replace("\\", "/")).name.lower() in PACKAGE_COVER_ASSET_NAMES
