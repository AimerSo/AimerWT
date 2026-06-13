# -*- coding: utf-8 -*-
"""
炮镜资源管理模组：负责 UserSights 的路径设置、扫描、导入、重命名与封面处理。

功能定位:
- 管理用户指定的 UserSights 目录，并扫描其中的炮镜文件夹以生成前端展示数据。
- 将用户提供的炮镜 ZIP/RAR/7Z 解压导入到 UserSights，支援覆盖导入与进度回调。
- 提供炮镜文件夹重命名与封面（preview.png）更新能力。
- 自动搜索 War Thunder 的 UserSights 路径，支援多 UID 选择。

输入输出:
- 输入: UserSights 路径、炮镜压缩包路径、封面 base64 数据、重命名参数、进度回调。
- 输出: 炮镜列表字典、导入结果字典、对 UserSights 目录结构与 preview.png 的写入副作用。
- 外部资源/依赖:
  - 目录: UserSights（读写）
  - 文件: 炮镜目录内的 .blk 文件（扫描计数）、preview.png（写入）
  - 系统能力: zipfile/7z 解压、文件系统读写、os.startfile

错误处理策略:
- 文件操作使用具体的异常类型（PermissionError、FileNotFoundError 等）
- 压缩包解压支援路径安全校验
- 所有操作记录完整的错误上下文
"""
import base64
import os
import platform
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable, Any
from utils.logger import get_logger
from utils.sevenzip import find_7z_executable
from services.resource_index_cache import ResourceIndexCache

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
    
    def __init__(self, cache_dir: str | Path | None = None):
        """
        初始化 SightsManager。
        """
        self._usersights_path: Path | None = None
        self._cache: dict | None = None
        self._cache_signature = None
        self._index_cache = ResourceIndexCache("sights_library", cache_dir=cache_dir)

    def _clear_sights_cache(self) -> None:
        self._cache = None
        self._cache_signature = None
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
        sight_dir = usersights_dir / folder_name
        if not sight_dir.exists() or not sight_dir.is_dir():
            raise FileNotFoundError(f"炮镜文件夹不存在: {folder_name}")
        return sight_dir

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
    
    def scan_sights(self, force_refresh: bool = False, 
                    default_cover_path: Path | None = None) -> dict[str, Any]:
        """
        扫描 UserSights 目录下的炮镜文件夹并生成前端展示用列表数据。
        
        Args:
            force_refresh: 是否强制刷新缓存
            default_cover_path: 默认封面路径
            
        Returns:
            包含 exists, path, items 的字典
        """
        if not self._usersights_path or not self._usersights_path.exists():
            return {'exists': False, 'path': '', 'items': []}

        root_signature = self._index_cache.build_root_signature(self._usersights_path)
        if (
            not force_refresh
            and self._cache is not None
            and self._cache_signature == root_signature
            and self._cache.get("path") == str(self._usersights_path)
        ):
            return self._cache

        sights = []
        cached_records = self._index_cache.load_records(self._usersights_path)
        next_records: dict[str, dict] = {}
        try:
            for item in self._usersights_path.iterdir():
                if not item.is_dir():
                    continue

                item_mtime = item.stat().st_mtime
                preview_path = self._find_preview_image(item)
                cover_path = preview_path
                if not cover_path and default_cover_path and default_cover_path.exists():
                    cover_path = default_cover_path

                signature = self._index_cache.build_item_signature(item, cover_path)
                sight = self._index_cache.get_cached_item(cached_records, item.name, signature)

                if sight is None:
                    blk_files = []
                    try:
                        for fp in item.rglob('*'):
                            if fp.is_file() and fp.suffix.lower() == '.blk':
                                blk_files.append(fp)
                    except PermissionError:
                        log.warning(f"无法访问目录 {item.name}（权限不足）")
                        continue

                    cover_url = ""
                    cover_is_default = False
                    if preview_path:
                        cover_url = self._to_data_url(preview_path)
                    elif default_cover_path and default_cover_path.exists():
                        cover_url = self._to_data_url(default_cover_path)
                        cover_is_default = True

                    sight = {
                        'name': item.name,
                        'path': str(item),
                        'disabled': item.name.endswith(self.disabled_suffix),
                        'enabled_name': item.name[:-len(self.disabled_suffix)] if item.name.endswith(self.disabled_suffix) else item.name,
                        'file_count': len(blk_files),
                        'cover_url': cover_url,
                        'cover_is_default': cover_is_default,
                        'mtime': item_mtime,
                    }
                else:
                    sight['name'] = item.name
                    sight['path'] = str(item)
                    sight['disabled'] = item.name.endswith(self.disabled_suffix)
                    sight['enabled_name'] = item.name[:-len(self.disabled_suffix)] if item.name.endswith(self.disabled_suffix) else item.name
                    sight['mtime'] = item_mtime

                sights.append(sight)
                next_records[item.name] = self._index_cache.make_record(signature, sight)
        except PermissionError as e:
            log.error(f"扫描炮镜失败（权限不足）: {e}")
        except OSError as e:
            log.error(f"扫描炮镜失败（系统错误）: {e}")
        
        result = {
            'exists': True,
            'path': str(self._usersights_path),
            'items': sorted(sights, key=lambda x: x['name'].lower())
        }
        self._cache = result
        self._cache_signature = root_signature
        self._index_cache.save_records(self._usersights_path, next_records)
        return result

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
        import re
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")

        old_dir = usersights_dir / old_name
        new_dir = usersights_dir / new_name

        if not old_dir.exists():
            raise FileNotFoundError(f"找不到源文件夹: {old_name}")

        if not new_name or len(new_name) > 255:
            raise ValueError("名称长度不合法")

        if re.search(r'[<>:"/\\|?*]', new_name):
            raise ValueError('名称包含非法字符 (不能包含 < > : " / \\ | ? *)')

        if new_dir.exists():
            raise FileExistsError(f"目标名称已存在: {new_name}")

        try:
            old_dir.rename(new_dir)
            self._cache = None
            self._cache_signature = None
            self._index_cache.clear()
            log.info(f"已重命名炮镜: {old_name} -> {new_name}")
            return True
        except PermissionError as e:
            raise OSError(f"重命名失败（权限不足）: {e}")
        except OSError as e:
            raise OSError(f"重命名失败: {e}")

    def disable_sight(self, name: str) -> dict[str, Any]:
        sight_dir = self._resolve_sight_dir(name)
        if sight_dir.name.endswith(self.disabled_suffix):
            return {"success": True, "name": sight_dir.name, "disabled": True}
        target_dir = sight_dir.with_name(f"{sight_dir.name}{self.disabled_suffix}")
        if target_dir.exists():
            raise FileExistsError(f"已存在禁用状态文件夹: {target_dir.name}")
        sight_dir.rename(target_dir)
        self._clear_sights_cache()
        return {"success": True, "name": target_dir.name, "disabled": True}

    def enable_sight(self, name: str) -> dict[str, Any]:
        sight_dir = self._resolve_sight_dir(name)
        if not sight_dir.name.endswith(self.disabled_suffix):
            return {"success": True, "name": sight_dir.name, "disabled": False}
        enabled_name = sight_dir.name[:-len(self.disabled_suffix)]
        if not enabled_name:
            raise ValueError("启用后的炮镜文件夹名称不合法")
        target_dir = sight_dir.with_name(enabled_name)
        if target_dir.exists():
            raise FileExistsError(f"已存在启用状态文件夹: {target_dir.name}")
        sight_dir.rename(target_dir)
        self._clear_sights_cache()
        return {"success": True, "name": target_dir.name, "disabled": False}

    def delete_sight(self, name: str) -> dict[str, Any]:
        sight_dir = self._resolve_sight_dir(name)
        shutil.rmtree(sight_dir)
        self._clear_sights_cache()
        return {"success": True, "name": sight_dir.name}

    def open_sight_folder(self, name: str) -> bool:
        sight_dir = self._resolve_sight_dir(name)
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
        将前端传入的 base64 图片数据写入为 preview.png，作为炮镜封面。
        
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
        usersights_dir = self._usersights_path
        if not usersights_dir or not usersights_dir.exists():
            raise ValueError("UserSights 路径未设置或不存在")

        sight_dir = usersights_dir / sight_name
        if not sight_dir.exists():
            raise FileNotFoundError("炮镜文件夹不存在")

        data_url = str(data_url or "")
        if ";base64," not in data_url:
            raise ValueError("图片数据格式错误")

        _prefix, b64 = data_url.split(";base64,", 1)
        try:
            raw = base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise ValueError(f"图片数据解析失败: {e}")

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
        normalized = str(filename or "").replace("\\", "/").strip()
        if not normalized:
            return False
        if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
            return False
        parts = [part for part in normalized.split("/") if part]
        return ".." not in parts

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
        text = str(target_dir or "").strip()
        if not text:
            return "all_tanks"
        if text in {".", ".."} or "/" in text or "\\" in text:
            raise ValueError("炮镜目标目录只能是单层目录名")
        if re.search(r'[<>:"|?*\x00-\x1f]', text):
            raise ValueError('炮镜目标目录包含非法字符')
        if Path(text).name != text:
            raise ValueError("炮镜目标目录只能是单层目录名")
        return text

    def _looks_like_vehicle_sight_dir(self, name: str) -> bool:
        lower = str(name or "").lower()
        if lower == "all_tanks":
            return True
        vehicle_prefixes = ("germ_", "ussr_", "us_", "uk_", "jp_", "cn_", "fr_", "it_", "sw_", "il_")
        return any(lower.startswith(prefix) for prefix in vehicle_prefixes)

    def _merge_directory_contents(self, source_dir: Path, target_dir: Path) -> tuple[int, int]:
        installed_count = 0
        backup_count = 0
        target_dir.mkdir(parents=True, exist_ok=True)
        for child in source_dir.iterdir():
            target_path = target_dir / child.name
            if child.is_dir():
                child_installed, child_backups = self._merge_directory_contents(child, target_path)
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
        return installed_count, backup_count

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
            return {
                "success": True,
                "file_path": str(source_path),
                "file_name": source_path.name,
                "file_type": ext.lstrip("."),
                "detected_type": "archive_package",
                "target_root": str(self._usersights_path),
                "install_entries": [],
                "blk_count": 0,
                "conflict_count": 0,
                "warnings": ["压缩包将导入到 UserSights，安装后需要在游戏内选择并保存炮镜"],
            }
        return {"success": False, "error_code": "unsupported_file_type", "msg": "仅支持 .blk/.zip/.rar/.7z 炮镜文件"}

    def _preview_blk_import(self, source_path: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
        target_dir = self._normalize_sight_target_dir((options or {}).get("target_dir"))
        target_path = self._usersights_path / target_dir / source_path.name
        if target_dir == "all_tanks":
            warnings = ["将安装为全载具可选炮镜，安装后需要在游戏内选择并保存炮镜"]
        else:
            warnings = [f"将安装到特定载具目录 {target_dir}，安装后需要在该载具的 Sight Settings 中选择并保存"]
        if not self._looks_like_blk_sight(source_path):
            warnings.insert(0, "该文件内容不像标准炮镜配置，请确认文件是否正确")

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
            return self._import_blk_file(source_path, target_dir=target_dir, progress_callback=progress_callback)
        if ext in self.supported_archive_extensions:
            target_dir = options.get("target_dir") if "target_dir" in options else None
            result = self.import_sights_zip(
                source_path,
                progress_callback=progress_callback,
                overwrite=False,
                target_dir=target_dir,
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
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        if not self._usersights_path or not self._usersights_path.exists():
            raise ValueError("请先设置有效的 UserSights 路径")
        if not source_path.exists():
            raise ValueError(f"炮镜文件不存在: {source_path}")
        if source_path.suffix.lower() != ".blk":
            raise ValueError("请选择有效的 .blk 炮镜文件")

        target_dir_name = self._normalize_sight_target_dir(target_dir)
        target_dir_path = self._usersights_path / target_dir_name
        target_path = target_dir_path / source_path.name
        if progress_callback:
            progress_callback(5, f"准备安装炮镜: {source_path.name}")
        try:
            target_dir_path.mkdir(parents=True, exist_ok=True)
            backup_path = self._backup_existing_file(target_path)
            shutil.copy2(source_path, target_path)
        except PermissionError as e:
            raise SightsImportError(f"安装炮镜失败（权限不足）: {e}") from e
        except OSError as e:
            raise SightsImportError(f"安装炮镜失败: {e}") from e

        self._clear_sights_cache()
        if progress_callback:
            progress_callback(100, "炮镜安装完成")

        warnings = []
        if not self._looks_like_blk_sight(source_path):
            warnings.append("该文件内容不像标准炮镜配置，请确认文件是否正确")
        return {
            "success": True,
            "installed_count": 1,
            "backup_count": 1 if backup_path else 0,
            "target_root": str(self._usersights_path),
            "installed_dirs": [target_dir_name],
            "target_path": str(target_path),
            "backup_path": str(backup_path) if backup_path else "",
            "warnings": warnings,
            "message": f"已安装炮镜文件: {source_path.name}",
        }

    def import_sights_zip(
        self,
        zip_path: str | Path,
        progress_callback: Callable[[int, str], None] | None = None,
        overwrite: bool = False,
        target_dir: Any = None,
    ) -> dict[str, Any]:
        """
        将炮镜压缩包解压导入到 UserSights，并根据压缩包结构决定目标目录命名策略。
        
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

        blocked_ext = {
            ".exe", ".dll", ".bat", ".cmd", ".ps1", 
            ".vbs", ".js", ".jar", ".msi", ".com",
        }

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

        def _is_within(base_dir: Path, target: Path) -> bool:
            """判断目标路径是否位于指定基准目录内部。"""
            try:
                base = base_dir.resolve()
                t = target.resolve()
                return base == t or str(t).startswith(str(base) + os.sep)
            except (OSError, ValueError):
                return False

        requested_target_dir = target_dir
        target_dir: Path | None = None
        
        try:
            if progress_callback:
                progress_callback(1, f"准备解压到 UserSights: {zip_path.name}")

            if archive_ext == ".zip":
                try:
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        members = [m for m in zf.infolist() if not m.is_dir()]
                        total = max(len(members), 1)
                        extracted = 0

                        for m in members:
                            filename = m.filename
                            if not filename or "__MACOSX" in filename or "desktop.ini" in filename.lower():
                                continue
                            if filename.endswith("/"):
                                continue

                            ext = Path(filename).suffix.lower()
                            if ext in blocked_ext:
                                raise SightsImportError(f"检测到不允许的文件类型: {filename}")

                            target_path = tmp_dir / filename
                            if not _is_within(tmp_dir, target_path):
                                raise SightsImportError(f"压缩包路径不安全（路径遍历）: {filename}")

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

            top_level = [
                p
                for p in tmp_dir.iterdir()
                if p.name not in ("__MACOSX",) and p.name.lower() != "desktop.ini"
            ]

            if requested_target_dir is not None:
                target_dir_name = self._normalize_sight_target_dir(requested_target_dir)
                target_dir_path = usersights_dir / target_dir_name
                blk_files = sorted(
                    [
                        p for p in tmp_dir.rglob("*.blk")
                        if p.is_file()
                        and "__MACOSX" not in str(p.relative_to(tmp_dir))
                        and "desktop.ini" not in p.name.lower()
                    ],
                    key=lambda p: str(p.relative_to(tmp_dir)).lower(),
                )
                if not blk_files:
                    raise SightsImportError("压缩包内未找到 .blk 炮镜文件")
                installed_count = 0
                backup_count = 0
                target_dir_path.mkdir(parents=True, exist_ok=True)
                for blk_file in blk_files:
                    target_path = target_dir_path / blk_file.name
                    backup_path = self._backup_existing_file(target_path)
                    if backup_path:
                        backup_count += 1
                    shutil.move(str(blk_file), str(target_path))
                    installed_count += 1
                target_dir = target_dir_path
                log.info(
                    "炮镜压缩包按指定目录安装: target=%s files=%s backups=%s",
                    target_dir_name,
                    installed_count,
                    backup_count,
                )
                if progress_callback:
                    progress_callback(98, "完成整理")
                    progress_callback(100, "导入完成")
                self._clear_sights_cache()
                return {
                    "ok": True,
                    "target_dir": str(target_dir),
                    "installed_count": installed_count,
                    "backup_count": backup_count,
                }

            root_sight_dirs = [
                p for p in top_level
                if p.is_dir() and self._looks_like_vehicle_sight_dir(p.name)
            ]
            if root_sight_dirs and len(root_sight_dirs) == len(top_level):
                installed_count = 0
                backup_count = 0
                installed_dirs = []
                for source_dir in root_sight_dirs:
                    target_item_dir = usersights_dir / source_dir.name
                    item_count, item_backups = self._merge_directory_contents(source_dir, target_item_dir)
                    installed_count += item_count
                    backup_count += item_backups
                    installed_dirs.append(source_dir.name)
                target_dir = usersights_dir
                log.info(
                    "炮镜压缩包按 UserSights 目录结构合并: dirs=%s files=%s backups=%s",
                    installed_dirs,
                    installed_count,
                    backup_count,
                )
            elif len(top_level) == 1 and top_level[0].is_dir():
                inner_dir = top_level[0]
                target_dir = usersights_dir / inner_dir.name
                if target_dir.exists():
                    if not overwrite:
                        raise FileExistsError(f"已存在同名炮镜文件夹: {inner_dir.name}")
                    try:
                        shutil.rmtree(target_dir)
                    except OSError as e:
                        raise SightsImportError(f"无法移除现有文件夹: {e}")
                try:
                    shutil.move(str(inner_dir), str(target_dir))
                except OSError as e:
                    raise SightsImportError(f"移动文件夹失败: {e}")
            else:
                target_dir = usersights_dir / zip_path.stem
                if target_dir.exists():
                    if not overwrite:
                        raise FileExistsError(f"已存在同名炮镜文件夹: {zip_path.stem}")
                    try:
                        shutil.rmtree(target_dir)
                    except OSError as e:
                        raise SightsImportError(f"无法移除现有文件夹: {e}")
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for child in top_level:
                        shutil.move(str(child), str(target_dir / child.name))
                except OSError as e:
                    raise SightsImportError(f"整理文件失败: {e}")

            if progress_callback:
                progress_callback(98, "完成整理")
                
        finally:
            # 清理临时目录
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
            except OSError as e:
                log.warning(f"清理临时目录失败: {e}")

        if progress_callback:
            progress_callback(100, "导入完成")

        self._clear_sights_cache()
        log.info(f"炮镜导入成功: {target_dir}")
        return {"ok": True, "target_dir": str(target_dir)}
