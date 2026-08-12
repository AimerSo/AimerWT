# -*- coding: utf-8 -*-
"""
配置管理模组：维护应用配置的内存表示，并提供按键读写与持久化保存能力。

功能特性:
- 跨平台配置文件存储路径支援 (Windows/Linux/macOS)
- 自动编码回退策略读取 JSON
- 配置项的安全读写与验证
"""
import json
import os
import platform
import copy
import re
from pathlib import Path
from typing import Callable
import sys
from utils.logger import get_logger
from utils.utils import get_docs_data_dir, get_legacy_docs_data_dir
from services.app_data_migration import sync_current_settings_to_legacy
from services.resource_path_manager import (
    build_resource_paths,
    infer_resource_root_from_legacy_library_dir,
    update_resource_root_history,
)

log = get_logger(__name__)


class ConfigError(Exception):
    """配置相关错误的基类。"""
    pass


class ConfigLoadError(ConfigError):
    """配置加载失败。"""
    pass


class ConfigSaveError(ConfigError):
    """配置保存失败。"""
    pass


def _get_config_dir():
    """获取配置文件目录。"""
    return get_docs_data_dir()


DOCS_DIR = _get_config_dir()
CONFIG_FILE = DOCS_DIR / "settings.json"
REMOTE_THEME_FILENAME_RE = re.compile(r"^remote_[a-z0-9_]+\.json$")


class ConfigManager:
    """
    维护应用配置的内存表示，并提供按键读写与落盘保存能力。
    
    属性:
        config_dir: 配置文件目录
        config_file: 配置文件路径
        config: 配置字典
    """

    # 默认配置模板
    DEFAULT_CONFIG = {
        "game_path": "",
        "launch_mode": "launcher",
        "theme_mode": "Light",
        "active_theme": "default.json",
        "is_first_run": True,
        "agreement_version": "",
        "current_mod": "",
        "sound_replace_disclaimer_accepted": False,
        "guide_state": {
            "completed": False,
            "firstOpenHandled": False
        },
        "uid_popup_state": {
            "shown_seq_ids": []
        },
        "unlocked_themes": [],
        "sights_path": "",
        "pending_dir": "",
        "resource_root_dir": "",
        "resource_root_history": [],
        "resource_path_overrides": {},
        "path_metadata": {},
        "library_dir": "",
        "resource_display_names": {},
        "telemetry_enabled": True,
        "autostart_enabled": False,
        "tray_mode": False,
        "close_confirm": True,
        "ui_language": "",
        "remote_themes_cache": {}
    }

    def __init__(
        self,
        config_dir: str | Path | None = None,
        legacy_config_dir: str | Path | None = None,
        sync_legacy: bool = True,
        save_callback: Callable[[dict], bool | None] | None = None,
    ):
        """初始化配置管理器，加载或创建配置文件。"""
        self.config_dir = Path(config_dir) if config_dir is not None else get_docs_data_dir()
        self.config_file = self.config_dir / "settings.json"
        self.legacy_config_dir = (
            Path(legacy_config_dir) if legacy_config_dir is not None else get_legacy_docs_data_dir()
        )
        self.sync_legacy = bool(sync_legacy)
        self._save_callback = save_callback
        # 初始化默认配置并尝试从 settings.json 加载覆盖
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        self.load_error_code = ""
        self.loaded_from_disk = self.load_config()
        self._last_saved_config = copy.deepcopy(self.config)

    def set_save_callback(self, callback: Callable[[dict], bool | None] | None) -> None:
        self._save_callback = callback

    def _restore_after_save_failure(
        self,
        previous_bytes: bytes | None,
        previous_config: dict | None,
        *,
        restore_disk: bool,
    ) -> bool:
        disk_restored = True
        if restore_disk:
            try:
                if previous_bytes is None:
                    if self.config_file.exists():
                        self.config_file.unlink()
                else:
                    rollback_file = self.config_file.with_suffix('.rollback.tmp')
                    rollback_file.write_bytes(previous_bytes)
                    rollback_file.replace(self.config_file)
            except OSError as rollback_error:
                disk_restored = False
                log.error(f"配置文件回退失败，内存设置仍会恢复: {rollback_error}")
        restored = copy.deepcopy(self.DEFAULT_CONFIG)
        if isinstance(previous_config, dict):
            for key in self.DEFAULT_CONFIG:
                if key in previous_config:
                    restored[key] = previous_config[key]
        self.config.clear()
        self.config.update(restored)
        self._last_saved_config = copy.deepcopy(restored)
        return disk_restored

    def _load_json_with_fallback(self, file_path: Path) -> dict | None:
        """严格按无 BOM UTF-8 读取正式配置。"""
        try:
            text = file_path.read_text(encoding="utf-8")
            if text.startswith("\ufeff"):
                raise UnicodeError("正式配置不允许 UTF-8 BOM")
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            log.error(f"无法读取正式配置文件 {file_path}: {error}")
            return None

    def _config_types_are_valid(self, data: dict) -> bool:
        for key, default_value in self.DEFAULT_CONFIG.items():
            if key not in data:
                continue
            value = data[key]
            if isinstance(default_value, bool):
                valid = isinstance(value, bool)
            else:
                valid = isinstance(value, type(default_value))
            if not valid:
                log.error(f"配置字段类型无效: {key}")
                return False
        return True

    def load_config(self) -> bool:
        """
        从 settings.json 加载配置并合併到当前配置字典。
        
        Returns:
            bool: 是否成功加载
        """
        if not self.config_file.exists():
            log.info("配置文件不存在，使用默认配置")
            return False

        try:
            data = self._load_json_with_fallback(self.config_file)
            if isinstance(data, dict) and self._config_types_are_valid(data):
                # 只更新已知的配置项，忽略未知项
                for key in self.DEFAULT_CONFIG:
                    if key in data:
                        self.config[key] = data[key]
                self._migrate_resource_root_config()
                log.debug(f"已加载配置文件: {self.config_file}")
                return True
            else:
                self.load_error_code = "settings_corrupt"
                log.warning("配置文件格式无效，停止自动覆盖")
                return False
        except Exception as e:
            self.load_error_code = "settings_corrupt"
            log.error(f"加载配置文件失败: {type(e).__name__}: {e}")
            return False

    def save_config(self) -> bool:
        """
        将当前配置字典写入 settings.json。
        
        Returns:
            bool: 是否成功保存
            
        Raises:
            ConfigSaveError: 保存失败时（仅在严重错误时）
        """
        previous_config = copy.deepcopy(self._last_saved_config)
        previous_bytes: bytes | None = None
        disk_replaced = False
        try:
            if not self.config_dir.exists():
                self.config_dir.mkdir(parents=True, exist_ok=True)

            previous_bytes = self.config_file.read_bytes() if self.config_file.is_file() else None
            temp_file = self.config_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            temp_file.replace(self.config_file)
            disk_replaced = True

            try:
                if self._save_callback is not None:
                    callback_result = self._save_callback(copy.deepcopy(self.config))
                    if callback_result is False:
                        raise ConfigSaveError("安装登记未能同步保存")
            except Exception as callback_error:
                self._restore_after_save_failure(
                    previous_bytes,
                    previous_config,
                    restore_disk=disk_replaced,
                )
                log.error(f"配置与安装登记同步失败，已恢复旧设置: {callback_error}")
                return False

            if self.sync_legacy:
                try:
                    sync_current_settings_to_legacy(
                        self.config,
                        self.legacy_config_dir,
                        self.config_dir,
                    )
                except Exception as sync_error:
                    log.warning(f"旧版兼容配置同步失败: {sync_error}")
            log.debug(f"配置已保存: {self.config_file}")
            self._last_saved_config = copy.deepcopy(self.config)
            return True

        except PermissionError as e:
            self._restore_after_save_failure(
                previous_bytes, previous_config, restore_disk=disk_replaced
            )
            log.error(f"保存配置文件失败（权限不足）: {e}")
            return False
        except OSError as e:
            self._restore_after_save_failure(
                previous_bytes, previous_config, restore_disk=disk_replaced
            )
            log.error(f"保存配置文件失败（系统错误）: {e}")
            return False
        except Exception as e:
            self._restore_after_save_failure(
                previous_bytes, previous_config, restore_disk=disk_replaced
            )
            log.error(f"保存配置文件失败: {type(e).__name__}: {e}")
            return False

    def _record_path_choice(self, role: str, path: str) -> None:
        metadata = self.config.get("path_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            self.config["path_metadata"] = metadata
        has_path = bool(str(path or "").strip())
        metadata[str(role)] = {
            "user_modified": has_path,
            "path_source": "user_selected" if has_path else "current_default",
        }

    def get_game_path(self) -> str:
        """读取当前配置中的游戏根目录路径。"""
        return self.config.get("game_path", "")

    def set_game_path(self, path: str) -> bool:
        """
        更新游戏根目录路径并写入 settings.json。
        
        Args:
            path: 游戏路径
            
        Returns:
            bool: 是否成功保存
        """
        self.config["game_path"] = str(path) if path else ""
        self._record_path_choice("game_root", self.config["game_path"])
        return self.save_config()

    def get_sights_path(self) -> str:
        """读取当前配置中的 UserSights 目录路径。"""
        return self.config.get("sights_path", "")

    def set_sights_path(self, path: str) -> bool:
        """
        更新 UserSights 目录路径并写入 settings.json。
        
        Args:
            path: UserSights 路径
            
        Returns:
            bool: 是否成功保存
        """
        self.config["sights_path"] = str(path) if path else ""
        self._record_path_choice("game_usersights", self.config["sights_path"])
        return self.save_config()

    def get_theme_mode(self) -> str:
        """读取当前主题模式（Light/Dark）。"""
        return self.config.get("theme_mode", "Light")

    def set_theme_mode(self, mode: str) -> bool:
        """
        更新主题模式并写入 settings.json。
        
        Args:
            mode: 主题模式 ("Light" 或 "Dark")
            
        Returns:
            bool: 是否成功保存
        """
        if mode not in ("Light", "Dark"):
            log.warning(f"无效的主题模式: {mode}，使用 Light")
            mode = "Light"
        self.config["theme_mode"] = mode
        return self.save_config()

    def get_ui_language(self) -> str:
        """读取当前界面语言。"""
        val = self.config.get("ui_language", "")
        return val if val in ("zh_cn", "zh_tw", "en_us", "ru_ru", "de_de") else ""

    def set_ui_language(self, lang: str) -> bool:
        """
        更新界面语言并写入 settings.json。

        Args:
            lang: 界面语言 ("zh_cn" / "zh_tw" / "en_us" / "ru_ru" / "de_de")

        Returns:
            bool: 是否成功保存
        """
        if lang not in ("zh_cn", "zh_tw", "en_us", "ru_ru", "de_de"):
            log.warning(f"无效的界面语言: {lang}，使用 zh_cn")
            lang = "zh_cn"
        self.config["ui_language"] = lang
        return self.save_config()

    def get_launch_mode(self) -> str:
        """读取启动方式（launcher/steam/aces）。"""
        return self.config.get("launch_mode", "launcher")

    def set_launch_mode(self, mode: str) -> bool:
        """
        更新启动方式并写入 settings.json。
        
        Args:
            mode: 启动方式 ("launcher" / "steam" / "aces")
            
        Returns:
            bool: 是否成功保存
        """
        if mode not in ("launcher", "steam", "aces"):
            log.warning(f"无效的启动方式: {mode}，使用 launcher")
            mode = "launcher"
        self.config["launch_mode"] = mode
        return self.save_config()

    def get_active_theme(self) -> str:
        """读取当前选择的主题文件名（自定义主题的配置项）。"""
        return self.config.get("active_theme", "default.json")

    def set_active_theme(self, filename: str) -> bool:
        """
        更新当前选择的主题文件名并写入 settings.json。
        
        Args:
            filename: 主题文件名
            
        Returns:
            bool: 是否成功保存
        """
        self.config["active_theme"] = str(filename) if filename else "default.json"
        return self.save_config()

    def get_current_mod(self) -> str:
        """读取当前记录的已安装/已生效语音包标识。"""
        return self.config.get("current_mod", "")

    def set_current_mod(self, mod_id: str) -> bool:
        """
        更新当前已生效语音包标识并写入 settings.json。
        
        Args:
            mod_id: 语音包标识
            
        Returns:
            bool: 是否成功保存
        """
        self.config["current_mod"] = str(mod_id) if mod_id else ""
        return self.save_config()

    def get_is_first_run(self) -> bool:
        """读取是否为首次运行的标誌位。"""
        return bool(self.config.get("is_first_run", True))

    def set_is_first_run(self, is_first_run: bool) -> bool:
        """
        更新首次运行标誌位并写入 settings.json。
        
        Args:
            is_first_run: 是否首次运行
            
        Returns:
            bool: 是否成功保存
        """
        self.config["is_first_run"] = bool(is_first_run)
        return self.save_config()

    def get_agreement_version(self) -> str:
        """读取用户已确认的协议版本号。"""
        return self.config.get("agreement_version", "")

    def set_agreement_version(self, version: str) -> bool:
        """
        更新用户已确认的协议版本号并写入 settings.json。
        
        Args:
            version: 协议版本号
            
        Returns:
            bool: 是否成功保存
        """
        self.config["agreement_version"] = str(version) if version else ""
        return self.save_config()

    def get_sound_replace_disclaimer_accepted(self) -> bool:
        """读取 Sound 源文件替换风险提示的确认状态。"""
        return bool(self.config.get("sound_replace_disclaimer_accepted", False))

    def set_sound_replace_disclaimer_accepted(self, accepted: bool) -> bool:
        """更新 Sound 源文件替换风险提示的确认状态并写入 settings.json。"""
        self.config["sound_replace_disclaimer_accepted"] = bool(accepted)
        return self.save_config()

    def get_guide_state(self) -> dict:
        """读取新手引导状态。"""
        fallback = {"completed": False, "firstOpenHandled": False}
        raw = self.config.get("guide_state", {})
        if not isinstance(raw, dict):
            return fallback
        return {
            "completed": bool(raw.get("completed", False)),
            "firstOpenHandled": bool(raw.get("firstOpenHandled", False)),
        }

    def set_guide_state(self, guide_state: dict) -> bool:
        """
        更新新手引导状态并写入 settings.json。

        Args:
            guide_state: 引导状态字典，支持 completed / firstOpenHandled

        Returns:
            bool: 是否成功保存
        """
        current = self.get_guide_state()
        if isinstance(guide_state, dict):
            current["completed"] = bool(guide_state.get("completed", current["completed"]))
            current["firstOpenHandled"] = bool(
                guide_state.get("firstOpenHandled", current["firstOpenHandled"])
            )
        self.config["guide_state"] = current
        return self.save_config()

    def _normalize_uid_popup_seq_id(self, seq_id) -> str:
        """规范化用户 UID 弹窗记录编号。"""
        try:
            value = int(str(seq_id or "").strip())
        except (TypeError, ValueError):
            return ""
        return str(value) if value > 0 else ""

    def get_uid_popup_state(self) -> dict:
        """读取 UID 欢迎弹窗主动展示状态。"""
        raw = self.config.get("uid_popup_state", {})
        if not isinstance(raw, dict):
            return {"shown_seq_ids": []}

        shown_ids = []
        for item in raw.get("shown_seq_ids", []):
            normalized = self._normalize_uid_popup_seq_id(item)
            if normalized and normalized not in shown_ids:
                shown_ids.append(normalized)
        return {"shown_seq_ids": shown_ids}

    def has_uid_popup_shown(self, seq_id) -> bool:
        """判断指定 UID 是否已经主动展示过欢迎弹窗。"""
        normalized = self._normalize_uid_popup_seq_id(seq_id)
        if not normalized:
            return False
        return normalized in self.get_uid_popup_state().get("shown_seq_ids", [])

    def _migrate_resource_root_config(self) -> None:
        """将旧版语音包库路径兼容为资源库根目录或明确的语音库路径。"""
        resource_root_dir = str(self.config.get("resource_root_dir") or "").strip()
        legacy_library_dir = str(self.config.get("library_dir") or "").strip()
        overrides = self.config.get("resource_path_overrides")
        if not isinstance(overrides, dict):
            overrides = {}
            self.config["resource_path_overrides"] = overrides

        if not resource_root_dir and legacy_library_dir:
            inferred = infer_resource_root_from_legacy_library_dir(legacy_library_dir)
            if inferred is not None:
                self.config["resource_root_dir"] = str(inferred)
                resource_root_dir = str(inferred)
            else:
                overrides["voice_library"] = legacy_library_dir
                metadata = self.config.get("path_metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    self.config["path_metadata"] = metadata
                metadata["voice_library"] = {
                    "user_modified": True,
                    "path_source": "legacy_setting",
                }

        if resource_root_dir:
            self.config["library_dir"] = str(
                build_resource_paths(resource_root_dir, overrides).voice_library_dir
            )
        elif str(overrides.get("voice_library") or "").strip():
            self.config["library_dir"] = str(overrides["voice_library"])

    def mark_uid_popup_shown(self, seq_id) -> bool:
        """记录指定 UID 已经主动展示过欢迎弹窗。"""
        normalized = self._normalize_uid_popup_seq_id(seq_id)
        if not normalized:
            return False
        state = self.get_uid_popup_state()
        shown_ids = state.get("shown_seq_ids", [])
        if normalized not in shown_ids:
            shown_ids.append(normalized)
        self.config["uid_popup_state"] = {"shown_seq_ids": shown_ids}
        return self.save_config()

    def get_config_dir(self) -> str:
        """读取当前配置文件所在目录路径。"""
        return str(self.config_dir)

    def get_unlocked_themes(self) -> list[str]:
        """读取已解锁的隐藏主题文件名列表。"""
        raw = self.config.get("unlocked_themes", [])
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw if item]

    def set_unlocked_themes(self, filenames: list[str]) -> bool:
        """更新已解锁的隐藏主题列表并写入 settings.json。"""
        cleaned = []
        seen = set()
        for item in filenames or []:
            name = str(item or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            cleaned.append(name)
        self.config["unlocked_themes"] = cleaned
        return self.save_config()

    def get_remote_themes_cache(self) -> dict:
        """读取远程主题元数据缓存。"""
        raw = self.config.get("remote_themes_cache", {})
        if not isinstance(raw, dict):
            return {}
        return copy.deepcopy(raw)

    def set_remote_themes_cache(self, themes_cache: dict) -> bool:
        """更新远程主题元数据缓存并写入 settings.json。"""
        cleaned = {}
        if isinstance(themes_cache, dict):
            for filename, meta in themes_cache.items():
                name = str(filename or "").strip()
                if not REMOTE_THEME_FILENAME_RE.match(name) or not isinstance(meta, dict):
                    continue
                try:
                    sort_order = int(meta.get("sort_order") or 100)
                except (TypeError, ValueError):
                    sort_order = 100
                try:
                    file_size = int(meta.get("file_size") or 0)
                except (TypeError, ValueError):
                    file_size = 0
                cleaned[name] = {
                    "filename": name,
                    "name": str(meta.get("name") or name),
                    "author": str(meta.get("author") or ""),
                    "version": str(meta.get("version") or ""),
                    "visibility": str(meta.get("visibility") or "public"),
                    "status": str(meta.get("status") or "active"),
                    "sort_order": sort_order,
                    "checksum": str(meta.get("checksum") or ""),
                    "file_size": file_size,
                    "description": str(meta.get("description") or ""),
                    "updated_at": str(meta.get("updated_at") or ""),
                }
        self.config["remote_themes_cache"] = cleaned
        return self.save_config()

    def get_config_file_path(self) -> str:
        """读取当前 settings.json 的完整路径。"""
        return str(self.config_file)

    def get_pending_dir(self) -> str:
        """读取自定义的待解压区目录路径。"""
        return self.config.get("pending_dir", "")

    def set_pending_dir(self, path: str) -> bool:
        """
        更新待解压区目录路径并写入 settings.json。
        
        Args:
            path: 待解压区路径
            
        Returns:
            bool: 是否成功保存
        """
        self.config["pending_dir"] = str(path) if path else ""
        self._record_path_choice("pending_dir", self.config["pending_dir"])
        return self.save_config()

    def get_library_dir(self) -> str:
        """读取自定义的语音包库目录路径。"""
        return self.config.get("library_dir", "")

    def set_library_dir(self, path: str) -> bool:
        """兼容旧版语音包库路径；任意目录作为明确覆盖保留。"""
        path_text = str(path) if path else ""
        old_root = self.config.get("resource_root_dir", "")
        overrides = self.config.get("resource_path_overrides")
        if not isinstance(overrides, dict):
            overrides = {}
            self.config["resource_path_overrides"] = overrides

        if not path_text:
            overrides.pop("voice_library", None)
            self.config["library_dir"] = (
                str(build_resource_paths(old_root, overrides).voice_library_dir) if old_root else ""
            )
            self._record_path_choice("voice_library", "")
            return self.save_config()

        inferred = infer_resource_root_from_legacy_library_dir(path_text)
        if inferred is not None:
            new_root = str(inferred)
            overrides.pop("voice_library", None)
            self.config["resource_root_dir"] = new_root
            self.config["resource_root_history"] = update_resource_root_history(
                self.config.get("resource_root_history", []), old_root, current_root=new_root
            )
        else:
            overrides["voice_library"] = path_text
        self.config["library_dir"] = path_text
        self._record_path_choice("voice_library", path_text)
        return self.save_config()

    def get_resource_root_dir(self) -> str:
        """读取 AimerWT 资源库根目录路径。"""
        return self.config.get("resource_root_dir", "")

    def set_resource_root_dir(self, path: str) -> bool:
        """
        更新 AimerWT 资源库根目录路径并写入 settings.json。
        """
        old_root = self.config.get("resource_root_dir", "")
        self.config["resource_root_dir"] = str(path) if path else ""
        self._record_path_choice("resource_root", self.config["resource_root_dir"])
        self.config["library_dir"] = (
            str(build_resource_paths(path, self.config.get("resource_path_overrides", {})).voice_library_dir)
            if path
            else str((self.config.get("resource_path_overrides") or {}).get("voice_library") or "")
        )
        self.config["resource_root_history"] = update_resource_root_history(
            self.config.get("resource_root_history", []),
            old_root,
            current_root=self.config["resource_root_dir"],
        )
        return self.save_config()

    def get_resource_root_history(self) -> list[str]:
        """读取最近使用过的资源库根目录历史。"""
        history = self.config.get("resource_root_history", [])
        return list(history) if isinstance(history, list) else []

    def get_telemetry_enabled(self):
        """
        功能定位:
        - 读取遥测功能开启状态。
        输入输出:
        - 参数: 无
        - 返回: bool，默认 True。
        """
        return bool(self.config.get("telemetry_enabled", True))

    def set_telemetry_enabled(self, enabled):
        """
        功能定位:
        - 更新遥测功能开启状态。
        输入输出:
        - 参数:
          - enabled: bool，是否开启。
        """
        self.config["telemetry_enabled"] = bool(enabled)
        self.save_config()

    def get_autostart_enabled(self):
        """
        功能定位:
        - 读取开机自启动状态。
        输入输出:
        - 参数: 无
        - 返回: bool，默认 False。
        """
        return bool(self.config.get("autostart_enabled", False))

    def set_autostart_enabled(self, enabled):
        """
        功能定位:
        - 更新开机自启动状态。
        输入输出:
        - 参数:
          - enabled: bool，是否开启。
        """
        self.config["autostart_enabled"] = bool(enabled)
        self.save_config()

    def get_tray_mode(self):
        """
        功能定位:
        - 读取托盘模式状态（关闭时最小化到托盘）。
        输入输出:
        - 参数: 无
        - 返回: bool，默认 False。
        """
        return bool(self.config.get("tray_mode", False))

    def set_tray_mode(self, enabled):
        """
        功能定位:
        - 更新托盘模式状态。
        输入输出:
        - 参数:
          - enabled: bool，是否开启。
        """
        self.config["tray_mode"] = bool(enabled)
        self.save_config()

    def get_close_confirm(self):
        """
        功能定位:
        - 读取关闭确认提示状态。
        输入输出:
        - 参数: 无
        - 返回: bool，默认 True。
        """
        return bool(self.config.get("close_confirm", True))

    def set_close_confirm(self, enabled):
        """
        功能定位:
        - 更新关闭确认提示状态。
        输入输出:
        - 参数:
          - enabled: bool，是否开启。
        """
        self.config["close_confirm"] = bool(enabled)
        self.save_config()
