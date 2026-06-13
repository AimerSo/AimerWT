# -*- coding: utf-8 -*-
"""
涂装资源管理模组：负责 UserSkins 的扫描、导入、重命名与封面处理。

功能定位:
- 扫描游戏目录下的 UserSkins 文件夹，生成前端展示数据。
- 支援从 ZIP/RAR/7Z 导入涂装，包含文件类型校验与磁盘空间检查。
- 提供涂装重命名与封面更新功能。

输入输出:
- 输入: 游戏路径、涂装压缩包路径、封面图片数据、重命名参数。
- 输出: 涂装列表字典、导入结果字典、对 UserSkins 目录结构的写入副作用。

错误处理策略:
- 文件操作使用具体的异常类型（PermissionError、FileNotFoundError 等）
- 压缩包解压支援路径安全校验和文件类型白名单
- 所有操作记录完整的错误上下文
"""
import base64
import hashlib
import os
import platform
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Callable, Any

from services.resource_index_cache import ResourceIndexCache
from utils.logger import get_logger
from utils.sevenzip import find_7z_executable

try:
    import winreg
except ImportError:
    winreg = None

log = get_logger(__name__)


class SkinsManagerError(Exception):
    """涂装管理器相关错误的基类。"""
    pass


class SkinsImportError(SkinsManagerError):
    """涂装导入过程错误。"""
    pass


class DiskSpaceError(SkinsManagerError):
    """磁盘空间不足错误。"""
    pass


class SkinsManager:
    """
    UserSkins 目录的资源管理器，封装扫描、导入与文件操作能力。
    
    属性:
        _cache: 扫描结果缓存
    """
    supported_archive_extensions = (".zip", ".rar", ".7z")
    allowed_skin_extensions = {".dds", ".blk", ".tga"}
    disabled_suffix = ".AimerWT_BAN"
    
    def __init__(self, cache_dir: str | Path | None = None):
        """
        初始化 SkinsManager。
        """
        self._cache: dict | None = None
        self._cache_signature = None
        self._index_cache = ResourceIndexCache("skins_library", cache_dir=cache_dir)

    def _clear_cache(self) -> None:
        self._cache = None
        self._cache_signature = None
        self._index_cache.clear()

    def get_userskins_dir(self, game_path: str | Path) -> Path:
        """
        计算指定游戏目录下 UserSkins 的绝对路径。
        
        Args:
            game_path: 游戏安装路径
            
        Returns:
            UserSkins 目录路径
        """
        return Path(str(game_path)) / "UserSkins"

    def discover_userskins_locations(
        self,
        configured_game_path: str | Path | None = None,
        extra_game_paths: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        """
        查找本机可能存在的 War Thunder UserSkins 目录，用于识别 Steam/官方客户端之间的涂装目录差异。
        """
        candidates = self._collect_userskins_game_candidates(configured_game_path, extra_game_paths)
        current_key = self._path_key(configured_game_path) if configured_game_path else ""
        folders = []

        for game_path in candidates:
            userskins_dir = self.get_userskins_dir(game_path)
            valid_game = self._check_is_wt_dir(game_path)
            if not valid_game and not userskins_dir.exists():
                continue

            summary = self._summarize_userskins_dir(userskins_dir)
            install_type = self._classify_game_path(game_path)
            folders.append({
                "id": self._location_id(userskins_dir),
                "install_type": install_type,
                "install_label": self._install_type_label(install_type),
                "game_path": str(game_path),
                "userskins_path": str(userskins_dir),
                "exists": userskins_dir.exists(),
                "valid_game": valid_game,
                "is_current": self._path_key(game_path) == current_key if current_key else False,
                **summary,
            })

        folders.sort(key=lambda item: (
            not bool(item.get("is_current")),
            str(item.get("install_type") or "unknown"),
            str(item.get("userskins_path") or "").lower(),
        ))
        return {
            "success": True,
            "current_game_path": str(configured_game_path or ""),
            "folders": folders,
        }

    def migrate_userskins_items(
        self,
        source_userskins_path: str | Path,
        target_userskins_path: str | Path,
    ) -> dict[str, Any]:
        """
        将来源 UserSkins 下的涂装文件夹复制到目标 UserSkins；同名文件夹默认跳过，不覆盖、不删除来源。
        """
        source_dir = Path(source_userskins_path).expanduser().resolve()
        target_dir = Path(target_userskins_path).expanduser().resolve()
        self._validate_userskins_migration_paths(source_dir, target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = []
        skipped = []
        failed = []

        entries = sorted((entry for entry in source_dir.iterdir() if entry.is_dir()), key=lambda p: p.name.lower())
        for entry in entries:
            target_entry = target_dir / entry.name
            if target_entry.exists():
                skipped.append(entry.name)
                continue
            try:
                shutil.copytree(entry, target_entry)
                copied.append(entry.name)
            except Exception as exc:
                failed.append({"name": entry.name, "error": str(exc)})

        if copied:
            self._clear_cache()

        return {
            "success": len(failed) == 0,
            "source_path": str(source_dir),
            "target_path": str(target_dir),
            "copied": copied,
            "skipped": skipped,
            "failed": failed,
            "copied_count": len(copied),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
        }

    def _collect_userskins_game_candidates(
        self,
        configured_game_path: str | Path | None = None,
        extra_game_paths: list[str | Path] | None = None,
    ) -> list[Path]:
        candidates: list[Path] = []

        def add_candidate(path_value: str | Path | None) -> None:
            if not path_value:
                return
            try:
                path = Path(path_value).expanduser()
            except Exception:
                return
            key = self._path_key(path)
            if not key:
                return
            if any(self._path_key(existing) == key for existing in candidates):
                return
            candidates.append(path)

        add_candidate(configured_game_path)
        for path in extra_game_paths or []:
            add_candidate(path)

        for path in self._steam_warthunder_candidates():
            add_candidate(path)
        for path in self._official_warthunder_candidates():
            add_candidate(path)

        return candidates

    def _steam_warthunder_candidates(self) -> list[Path]:
        candidates = []
        for library_root in self._steam_library_roots():
            candidates.append(library_root / "steamapps" / "common" / "War Thunder")
        return candidates

    def _steam_library_roots(self) -> list[Path]:
        roots: list[Path] = []

        def add_root(path_value: str | Path | None) -> None:
            if not path_value:
                return
            try:
                path = Path(path_value).expanduser()
            except Exception:
                return
            key = self._path_key(path)
            if key and not any(self._path_key(root) == key for root in roots):
                roots.append(path)

        if winreg:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
                steam_path_str, _ = winreg.QueryValueEx(key, "SteamPath")
                winreg.CloseKey(key)
                add_root(steam_path_str)
            except Exception:
                pass

        for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env_name)
            if base:
                add_root(Path(base) / "Steam")

        if platform.system() == "Windows":
            for drive in "CDEFGHIJK":
                drive_root = Path(f"{drive}:\\")
                add_root(drive_root / "Steam")
                add_root(drive_root / "SteamLibrary")
        else:
            home = Path.home()
            add_root(home / ".local/share/Steam")
            add_root(home / ".steam/steam")

        parsed_roots = list(roots)
        for root in parsed_roots:
            library_vdf = root / "steamapps" / "libraryfolders.vdf"
            for parsed in self._parse_steam_libraryfolders(library_vdf):
                add_root(parsed)

        return roots

    def _parse_steam_libraryfolders(self, library_vdf: Path) -> list[Path]:
        if not library_vdf.exists():
            return []
        try:
            text = library_vdf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        paths = []
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            raw = match.group(1).replace("\\\\", "\\")
            paths.append(Path(raw))
        return paths

    def _official_warthunder_candidates(self) -> list[Path]:
        candidates = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "WarThunder")

        for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env_name)
            if base:
                candidates.append(Path(base) / "WarThunder")
                candidates.append(Path(base) / "War Thunder")

        if platform.system() == "Windows":
            for drive in "CDEFGHIJK":
                drive_root = Path(f"{drive}:\\")
                candidates.extend([
                    drive_root / "WarThunder",
                    drive_root / "War Thunder",
                    drive_root / "Games" / "War Thunder",
                ])
        else:
            home = Path.home()
            candidates.extend([
                home / "WarThunder",
                home / "War Thunder",
                home / ".local/share/WarThunder",
            ])
        return candidates

    def _summarize_userskins_dir(self, userskins_dir: Path) -> dict[str, Any]:
        if not userskins_dir.exists() or not userskins_dir.is_dir():
            return {
                "item_count": 0,
                "file_count": 0,
                "total_size_bytes": 0,
                "mtime": 0,
                "truncated": False,
            }

        total_size = 0
        file_count = 0
        mtime = 0
        try:
            mtime = userskins_dir.stat().st_mtime
            entries = sorted([entry for entry in userskins_dir.iterdir() if entry.is_dir()], key=lambda p: p.name.lower())
            for entry in entries[:500]:
                try:
                    mtime = max(mtime, entry.stat().st_mtime)
                except Exception:
                    pass
                size_bytes, count = self._get_dir_size_and_count_fast(entry)
                total_size += size_bytes
                file_count += count
            return {
                "item_count": len(entries),
                "file_count": file_count,
                "total_size_bytes": total_size,
                "mtime": mtime,
                "truncated": len(entries) > 500,
            }
        except Exception as exc:
            log.warning(f"统计 UserSkins 目录失败: {userskins_dir} - {exc}")
            return {
                "item_count": 0,
                "file_count": 0,
                "total_size_bytes": 0,
                "mtime": mtime,
                "truncated": False,
            }

    def _classify_game_path(self, game_path: str | Path) -> str:
        normalized = str(game_path).replace("\\", "/").lower()
        name_key = Path(game_path).name.lower().replace(" ", "")
        if "/steamapps/common/war thunder" in normalized:
            return "steam"
        if name_key == "warthunder":
            return "official"
        return "unknown"

    def _install_type_label(self, install_type: str) -> str:
        if install_type == "steam":
            return "Steam 版"
        if install_type == "official":
            return "官方客户端"
        return "未知来源"

    def _check_is_wt_dir(self, path: str | Path) -> bool:
        try:
            game_path = Path(path)
            if not game_path.exists() or not game_path.is_dir():
                return False
            valid_markers = ["config.blk", "beac_wt_mlauncher.exe", "gaijin_downloader.exe", "launcher.exe", "aces.exe"]
            return any((game_path / marker).exists() for marker in valid_markers)
        except Exception:
            return False

    def _validate_userskins_migration_paths(self, source_dir: Path, target_dir: Path) -> None:
        if source_dir.name.lower() != "userskins" or target_dir.name.lower() != "userskins":
            raise ValueError("只能迁移 UserSkins 目录")
        if not source_dir.exists() or not source_dir.is_dir():
            raise FileNotFoundError(f"来源 UserSkins 不存在: {source_dir}")
        if self._path_key(source_dir) == self._path_key(target_dir):
            raise ValueError("来源和目标 UserSkins 不能相同")
        source_text = str(source_dir)
        target_text = str(target_dir)
        try:
            common_path = os.path.commonpath([source_text, target_text])
        except ValueError:
            common_path = ""
        except Exception:
            common_path = ""
        if common_path in (source_text, target_text):
            raise ValueError("来源和目标 UserSkins 不能互相嵌套")

    def _path_key(self, path_value: str | Path | None) -> str:
        if not path_value:
            return ""
        try:
            return os.path.normcase(str(Path(path_value).expanduser().resolve(strict=False)))
        except Exception:
            return os.path.normcase(str(path_value))

    def _location_id(self, path_value: str | Path) -> str:
        key = self._path_key(path_value)
        return hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:12]

    def scan_userskins(
        self, 
        game_path: str | Path, 
        default_cover_path: Path | None = None, 
        force_refresh: bool = False,
        skip_covers: bool = False
    ) -> dict[str, Any]:
        """
        扫描 UserSkins 目录下的涂装文件夹，并生成前端展示用的列表数据。
        skip_covers: 如果为 True，则不生成 base64 的 cover_url，仅返回 preview_path。
        """
        userskins_dir = self.get_userskins_dir(game_path)
        
        if not userskins_dir.exists():
            self._clear_cache()
            return {"exists": False, "path": str(userskins_dir), "items": [], "valid": True}

        try:
            current_mtime = userskins_dir.stat().st_mtime
        except Exception:
            current_mtime = 0

        root_signature = self._index_cache.build_root_signature(userskins_dir)

        if not skip_covers and not force_refresh and self._cache is not None:
            if (self._cache.get("path") == str(userskins_dir) and
                self._cache_signature == root_signature):
                # 如果缓存中有完整数据，直接返回即可
                return self._cache

        items = []
        cached_records = {} if skip_covers else self._index_cache.load_records(userskins_dir)
        next_records: dict[str, dict] = {}
        try:
            entries = sorted([e for e in userskins_dir.iterdir() if e.is_dir()], key=lambda p: p.name.lower())
            
            for entry in entries:
                entry_mtime = entry.stat().st_mtime
                preview_path = self._find_preview_image(entry)
                cover_path = preview_path
                if not cover_path and default_cover_path and default_cover_path.exists():
                    cover_path = default_cover_path

                signature = self._index_cache.build_item_signature(entry, cover_path)
                item = None if skip_covers else self._index_cache.get_cached_item(cached_records, entry.name, signature)

                is_disabled = entry.name.endswith(self.disabled_suffix)
                enabled_name = entry.name[:-len(self.disabled_suffix)] if is_disabled else entry.name

                if item is None:
                    size_bytes, file_count = self._get_dir_size_and_count_fast(entry)
                    cover_url = ""
                    cover_is_default = False

                    if not skip_covers:
                        if preview_path:
                            cover_url = self._to_data_url(preview_path)
                        elif default_cover_path and default_cover_path.exists():
                            cover_url = self._to_data_url(default_cover_path)
                            cover_is_default = True

                    item = {
                        "name": entry.name,
                        "enabled_name": enabled_name,
                        "disabled": is_disabled,
                        "path": str(entry),
                        "size_bytes": size_bytes,
                        "file_count": file_count,
                        "preview_path": str(preview_path) if preview_path else "",
                        "cover_url": cover_url,
                        "cover_is_default": cover_is_default,
                        "mtime": entry_mtime,
                    }
                else:
                    item["name"] = entry.name
                    item["enabled_name"] = enabled_name
                    item["disabled"] = is_disabled
                    item["path"] = str(entry)
                    item["preview_path"] = str(preview_path) if preview_path else ""
                    item["mtime"] = entry_mtime

                items.append(item)
                if not skip_covers:
                    next_records[entry.name] = self._index_cache.make_record(signature, item)
        except Exception as e:
            log.error(f"扫描涂装失败: {e}")

        result = {
            "exists": True, 
            "path": str(userskins_dir), 
            "mtime": current_mtime, 
            "items": items, 
            "valid": True
        }
        if not skip_covers:
            self._cache = result
            self._cache_signature = root_signature
            self._index_cache.save_records(userskins_dir, next_records)
        return result

    def _get_dir_size_and_count_fast(self, dir_path: Path) -> tuple[int, int]:
        """优化版统计：限制遍历文件数量，防止异常庞大的项目造成挂起。"""
        total = 0
        count = 0
        try:
            for entry in dir_path.rglob("*"):
                if count > 200: # 单个涂装文件夹如果超过200个文件，停止统计详细信息以保性能
                    break
                if entry.is_file():
                    total += entry.stat().st_size
                    count += 1
        except Exception:
            pass
        return total, count

    def import_skin_zip(
        self,
        zip_path: str | Path,
        game_path: str | Path,
        progress_callback: Callable[[int, str], None] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """
        将涂装压缩包解压导入到 UserSkins，并整理为目标目录结构。
        
        Args:
            zip_path: ZIP/RAR/7Z 文件路径
            game_path: 游戏安装路径
            progress_callback: 进度回调函数 (percentage, message)
            overwrite: 是否复盖同名文件夹
            
        Returns:
            包含 ok 和 target_dir 的字典
            
        Raises:
            ValueError: 文件无效或包含非法文件类型
            FileExistsError: 目标文件夹已存在且未允许复盖
            DiskSpaceError: 磁盘空间不足
            SkinsImportError: 导入过程失败
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise ValueError(f"压缩包文件不存在: {zip_path}")
        archive_ext = zip_path.suffix.lower()
        if archive_ext not in self.supported_archive_extensions:
            raise ValueError("请选择有效的 .zip/.rar/.7z 文件")

        # 仅允许导入涂装相关文件扩展名
        invalid_files = []
        
        if archive_ext == ".zip":
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for member in zf.infolist():
                        if member.is_dir():
                            continue
                        filename = member.filename
                        if '__MACOSX' in filename or 'desktop.ini' in filename.lower():
                            continue

                        ext = Path(filename).suffix.lower()
                        if ext and ext not in self.allowed_skin_extensions:
                            invalid_files.append(filename)
            except zipfile.BadZipFile as e:
                raise ValueError(f"无效的 ZIP 文件: {e}")
        
        if invalid_files:
            file_list = '\n'.join(f'  • {f}' for f in invalid_files[:10])
            if len(invalid_files) > 10:
                file_list += f'\n  ... 还有 {len(invalid_files) - 10} 个文件'
            
            raise ValueError(
                f"❌ 检测到不允许的文件类型！\n\n"
                f"涂装包只允许包含以下文件类型：\n"
                f"  ✓ .dds (纹理文件)\n"
                f"  ✓ .blk (配置文件)\n"
                f"  ✓ .tga (纹理文件)\n\n"
                f"但在压缩包中发现了以下非法文件：\n{file_list}\n\n"
                f"💡 提示：请检查压缩包内容，确保只包含涂装相关文件。"
            )

        userskins_dir = self.get_userskins_dir(game_path)
        try:
            userskins_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise SkinsImportError(f"无法创建 UserSkins 目录（权限不足）: {e}")
        except OSError as e:
            raise SkinsImportError(f"无法创建 UserSkins 目录: {e}")

        target_name = zip_path.stem
        target_dir = userskins_dir / target_name
        if target_dir.exists():
            if not overwrite:
                raise FileExistsError(f"已存在同名涂装文件夹: {target_name}")
            try:
                shutil.rmtree(target_dir)
            except PermissionError as e:
                raise SkinsImportError(f"无法移除现有文件夹（权限不足）: {e}")
            except OSError as e:
                raise SkinsImportError(f"无法移除现有文件夹: {e}")

        self._check_disk_space(zip_path, userskins_dir)

        tmp_dir = userskins_dir / f".__tmp_extract__{target_name}"
        if tmp_dir.exists():
            try:
                shutil.rmtree(tmp_dir)
            except OSError as e:
                log.error(f"清理临时目录失败: {e}")
        
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise SkinsImportError(f"无法创建临时目录: {e}")

        try:
            if progress_callback:
                progress_callback(1, f"准备解压到 UserSkins: {zip_path.name}")

            self._extract_archive_safely(
                zip_path, tmp_dir, 
                progress_callback=progress_callback, 
                base_progress=2, share_progress=85
            )
            self._validate_extracted_skin_files(tmp_dir)

            top_level = [
                p for p in tmp_dir.iterdir() 
                if p.name not in ("__MACOSX",) and p.name != "desktop.ini"
            ]
            
            if len(top_level) == 1 and top_level[0].is_dir():
                inner_dir = top_level[0]
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    self._move_tree(inner_dir, target_dir)
                except OSError as e:
                    raise SkinsImportError(f"整理文件失败: {e}")
            else:
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for child in top_level:
                        self._move_tree(child, target_dir / child.name)
                except OSError as e:
                    raise SkinsImportError(f"整理文件失败: {e}")

            if progress_callback:
                progress_callback(98, "完成整理")
        finally:
            # 清理临时目录
            try:
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
            except OSError as e:
                log.error(f"清理临时目录失败: {e}")

        if progress_callback:
            progress_callback(100, "导入完成")

        self._clear_cache()
        log.info(f"涂装导入成功: {target_dir}")
        return {"ok": True, "target_dir": str(target_dir)}

    def rename_skin(self, game_path: str | Path, old_name: str, new_name: str) -> bool:
        """
        在 UserSkins 目录内安全重命名涂装文件夹。
        
        Args:
            game_path: 游戏安装路径
            old_name: 原文件夹名称
            new_name: 新文件夹名称
            
        Returns:
            是否重命名成功
            
        Raises:
            FileNotFoundError: 源文件夹不存在
            ValueError: 名称不合法
            FileExistsError: 目标名称已存在
            OSError: 重命名操作失败
        """
        userskins_dir = self.get_userskins_dir(game_path)
        old_dir = userskins_dir / old_name
        new_dir = userskins_dir / new_name

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
            self._clear_cache()
            log.info(f"已重命名涂装: {old_name} -> {new_name}")
            return True
        except PermissionError as e:
            raise OSError(f"重命名失败（权限不足）: {e}")
        except OSError as e:
            raise OSError(f"重命名失败: {e}")

    def _resolve_skin_dir(self, game_path: str | Path, skin_name: str) -> Path:
        name = str(skin_name or "").strip()
        if not name or name != Path(name).name:
            raise ValueError("涂装文件夹名称不合法")
        skin_dir = self.get_userskins_dir(game_path) / name
        if not skin_dir.exists() or not skin_dir.is_dir():
            raise FileNotFoundError(f"涂装文件夹不存在: {name}")
        return skin_dir

    def open_skin_folder(self, game_path: str | Path, skin_name: str) -> bool:
        """打开指定涂装文件夹。"""
        skin_dir = self._resolve_skin_dir(game_path, skin_name)
        system = platform.system()
        if system == "Windows":
            os.startfile(str(skin_dir))
        elif system == "Darwin":
            subprocess.run(["open", str(skin_dir)], check=True)
        else:
            subprocess.run(["xdg-open", str(skin_dir)], check=True)
        return True

    def disable_skin(self, game_path: str | Path, skin_name: str) -> dict[str, Any]:
        """将涂装文件夹改名为禁用状态。"""
        skin_dir = self._resolve_skin_dir(game_path, skin_name)
        if skin_dir.name.endswith(self.disabled_suffix):
            return {"success": True, "name": skin_dir.name, "disabled": True}
        target_dir = skin_dir.with_name(f"{skin_dir.name}{self.disabled_suffix}")
        if target_dir.exists():
            raise FileExistsError(f"已存在禁用状态文件夹: {target_dir.name}")
        skin_dir.rename(target_dir)
        self._clear_cache()
        return {"success": True, "name": target_dir.name, "disabled": True}

    def enable_skin(self, game_path: str | Path, skin_name: str) -> dict[str, Any]:
        """将涂装文件夹恢复为启用状态。"""
        skin_dir = self._resolve_skin_dir(game_path, skin_name)
        if not skin_dir.name.endswith(self.disabled_suffix):
            return {"success": True, "name": skin_dir.name, "disabled": False}
        enabled_name = skin_dir.name[:-len(self.disabled_suffix)]
        if not enabled_name:
            raise ValueError("启用后的涂装文件夹名称不合法")
        target_dir = skin_dir.with_name(enabled_name)
        if target_dir.exists():
            raise FileExistsError(f"已存在启用状态文件夹: {target_dir.name}")
        skin_dir.rename(target_dir)
        self._clear_cache()
        return {"success": True, "name": target_dir.name, "disabled": False}

    def delete_skin(self, game_path: str | Path, skin_name: str) -> dict[str, Any]:
        """删除指定涂装文件夹。"""
        skin_dir = self._resolve_skin_dir(game_path, skin_name)
        shutil.rmtree(skin_dir)
        self._clear_cache()
        return {"success": True, "name": skin_dir.name}

    def update_skin_cover(self, game_path: str | Path, skin_name: str, img_path: str) -> bool:
        """
        将指定图片複製为涂装目录的标准封面文件 preview.png。
        
        Args:
            game_path: 游戏安装路径
            skin_name: 涂装文件夹名称
            img_path: 来源图片路径
            
        Returns:
            是否更新成功
            
        Raises:
            FileNotFoundError: 涂装文件夹或图片文件不存在
            SkinsManagerError: 封面更新失败
        """
        userskins_dir = self.get_userskins_dir(game_path)
        skin_dir = userskins_dir / skin_name
        
        if not skin_dir.exists():
            raise FileNotFoundError("涂装文件夹不存在")
            
        if not os.path.exists(img_path):
            raise FileNotFoundError("图片文件不存在")
        
        # 统一封面文件名为 preview.png
        dst = skin_dir / "preview.png"
        
        try:
            shutil.copy2(img_path, dst)
            self._clear_cache()
            log.info(f"已更新涂装封面: {skin_name}")
            return True
        except PermissionError as e:
            raise SkinsManagerError(f"封面更新失败（权限不足）: {e}")
        except OSError as e:
            raise SkinsManagerError(f"封面更新失败: {e}")

    def update_skin_cover_data(self, game_path: str | Path, skin_name: str, data_url: str) -> bool:
        """
        将前端传入的 base64 图片数据写入为 preview.png，作为涂装封面。
        
        Args:
            game_path: 游戏安装路径
            skin_name: 涂装文件夹名称
            data_url: base64 编码的图片数据 URL
            
        Returns:
            是否更新成功
            
        Raises:
            FileNotFoundError: 涂装文件夹不存在
            ValueError: 数据格式错误
            SkinsManagerError: 封面更新失败
        """
        userskins_dir = self.get_userskins_dir(game_path)
        skin_dir = userskins_dir / skin_name

        if not skin_dir.exists():
            raise FileNotFoundError("涂装文件夹不存在")

        data_url = str(data_url or "")
        if ";base64," not in data_url:
            raise ValueError("图片数据格式错误")

        _prefix, b64 = data_url.split(";base64,", 1)
        try:
            raw = base64.b64decode(b64)
        except (ValueError, TypeError) as e:
            raise ValueError(f"图片数据解析失败: {e}")

        dst = skin_dir / "preview.png"
        try:
            with open(dst, "wb") as f:
                f.write(raw)
            self._clear_cache()
            log.info(f"已更新涂装封面: {skin_name}")
            return True
        except PermissionError as e:
            raise SkinsManagerError(f"封面更新失败（权限不足）: {e}")
        except OSError as e:
            raise SkinsManagerError(f"封面更新失败: {e}")


    def _get_dir_size_and_count(self, dir_path: Path) -> tuple[int, int]:
        """
        统计目录内所有文件的总大小与文件数量。
        
        Args:
            dir_path: 目录路径
            
        Returns:
            (总大小字节数, 文件数量)
        """
        total = 0
        count = 0
        try:
            for root, _dirs, files in os.walk(dir_path):
                for f in files:
                    fp = Path(root) / f
                    try:
                        total += fp.stat().st_size
                    except (OSError, PermissionError):
                        pass
                    count += 1
        except (OSError, PermissionError) as e:
            log.warning(f"统计目录大小失败 {dir_path}: {e}")
        return total, count

    def _find_preview_image(self, dir_path: Path) -> Path | None:
        """
        在涂装目录中查找可用的预览图文件。
        
        Args:
            dir_path: 涂装目录路径
            
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
            log.error(f"读取图片失败 {file_path}: {e}")
            return ""

    def _check_disk_space(self, zip_path: Path, target_dir: Path) -> None:
        """
        基于 ZIP 文件大小估算解压所需空间，并与目标盘剩余空间进行比较。
        
        Args:
            zip_path: ZIP 文件路径
            target_dir: 目标目录路径
            
        Raises:
            DiskSpaceError: 磁盘空间不足
        """
        try:
            zip_size = zip_path.stat().st_size
            estimated = zip_size * 3
            required = estimated * 2

            drive = Path(target_dir).anchor
            if not drive:
                drive = str(target_dir)

            total, used, free = shutil.disk_usage(drive)
            if free < required:
                free_mb = free / (1024 * 1024)
                req_mb = required / (1024 * 1024)
                raise DiskSpaceError(f"磁盘空间不足 (可用 {free_mb:.0f}MB, 需要 {req_mb:.0f}MB)")
        except DiskSpaceError:
            raise
        except OSError as e:
            log.warning(f"磁盘空间检查失败（已跳过）: {e}")

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
            raise SkinsImportError(output.strip() or "7z 解压超时") from e
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        return result.returncode, output.strip()

    def _is_archive_member_path_safe(self, filename: str) -> bool:
        normalized = str(filename or "").replace("\\", "/").strip()
        if not normalized:
            return False
        if re.match(r"^[a-zA-Z]:", normalized) or normalized.startswith("/"):
            return False
        parts = [part for part in normalized.split("/") if part]
        return ".." not in parts

    def _validate_7z_archive_entries(self, seven_zip: str, archive_path: Path) -> None:
        code, output = self._run_7z([seven_zip, "l", "-slt", "-p", str(archive_path)])
        if code != 0:
            raise SkinsImportError(output or "无法读取压缩包目录")

        in_entries = False
        invalid_files: list[str] = []
        unsafe_files: list[str] = []
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
            if ext and ext not in self.allowed_skin_extensions:
                invalid_files.append(filename)

        if unsafe_files:
            file_list = "\n".join(f"  - {f}" for f in unsafe_files[:10])
            raise SkinsImportError(f"压缩包路径不安全，已拒绝导入:\n{file_list}")
        if invalid_files:
            file_list = "\n".join(f"  • {f}" for f in invalid_files[:10])
            if len(invalid_files) > 10:
                file_list += f"\n  ... 还有 {len(invalid_files) - 10} 个文件"
            raise ValueError(
                f"❌ 检测到不允许的文件类型！\n\n"
                f"涂装包只允许包含以下文件类型：\n"
                f"  ✓ .dds (纹理文件)\n"
                f"  ✓ .blk (配置文件)\n"
                f"  ✓ .tga (纹理文件)\n\n"
                f"但在压缩包中发现了以下非法文件：\n{file_list}\n\n"
                f"💡 提示：请检查压缩包内容，确保只包含涂装相关文件。"
            )

    def _extract_with_7z(
        self,
        archive_path: Path,
        target_dir: Path,
        progress_callback: Callable[[int, str], None] | None = None,
        base_progress: int = 0,
        share_progress: int = 100,
    ) -> None:
        seven_zip = self._find_7z()
        if not seven_zip:
            raise SkinsImportError("未检测到 7z 解压组件，RAR/7Z 导入需要安装 7-Zip")

        self._validate_7z_archive_entries(seven_zip, archive_path)
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
                raise SkinsImportError("压缩包需要密码，当前涂装导入暂不支持加密压缩包")
            raise SkinsImportError(output or "解压失败")

        if progress_callback:
            progress_callback(base_progress + share_progress, f"解压完成: {archive_path.name}")

    def _extract_archive_safely(
        self,
        archive_path: Path,
        target_dir: Path,
        progress_callback: Callable[[int, str], None] | None = None,
        base_progress: int = 0,
        share_progress: int = 100,
    ) -> None:
        suffix = archive_path.suffix.lower()
        if suffix == ".zip":
            self._extract_zip_safely(
                archive_path,
                target_dir,
                progress_callback=progress_callback,
                base_progress=base_progress,
                share_progress=share_progress,
            )
            return
        if suffix in (".rar", ".7z"):
            self._extract_with_7z(
                archive_path,
                target_dir,
                progress_callback=progress_callback,
                base_progress=base_progress,
                share_progress=share_progress,
            )
            return
        raise SkinsImportError(f"不支持的压缩格式: {archive_path.suffix}")

    def _validate_extracted_skin_files(self, base_dir: Path) -> None:
        invalid_files = []
        for file_path in base_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(base_dir))
            if "__MACOSX" in rel_path or "desktop.ini" in rel_path.lower():
                continue
            ext = file_path.suffix.lower()
            if ext and ext not in self.allowed_skin_extensions:
                invalid_files.append(rel_path)

        if not invalid_files:
            return

        file_list = "\n".join(f"  • {f}" for f in invalid_files[:10])
        if len(invalid_files) > 10:
            file_list += f"\n  ... 还有 {len(invalid_files) - 10} 个文件"
        raise ValueError(
            f"❌ 检测到不允许的文件类型！\n\n"
            f"涂装包只允许包含以下文件类型：\n"
            f"  ✓ .dds (纹理文件)\n"
            f"  ✓ .blk (配置文件)\n"
            f"  ✓ .tga (纹理文件)\n\n"
            f"但在压缩包中发现了以下非法文件：\n{file_list}\n\n"
            f"💡 提示：请检查压缩包内容，确保只包含涂装相关文件。"
        )

    def _extract_zip_safely(
        self, 
        zip_path: Path, 
        target_dir: Path, 
        progress_callback: Callable[[int, str], None] | None = None, 
        base_progress: int = 0, 
        share_progress: int = 100
    ) -> None:
        """
        将 ZIP 内容解压到临时目录，并执行路径边界校验与进度回调更新。
        
        Args:
            zip_path: ZIP 文件路径
            target_dir: 目标目录
            progress_callback: 进度回调函数
            base_progress: 基础进度百分比
            share_progress: 分配的进度百分比范围
            
        Raises:
            SkinsImportError: 解压过程失败
        """
        target_root = Path(target_dir).resolve()
        
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                file_list = zf.infolist()
                total_files = len(file_list)
                last_update = 0.0
                extracted_bytes = 0
                total_bytes = 0

                if total_files > 0:
                    for m in file_list:
                        if m.is_dir():
                            continue
                        name = m.filename
                        if "__MACOSX" in name or "desktop.ini" in name:
                            continue
                        try:
                            total_bytes += int(getattr(m, "file_size", 0) or 0)
                        except (ValueError, TypeError):
                            pass

                for idx, member in enumerate(file_list):
                    if idx % 50 == 0:
                        time.sleep(0.001)

                    # 处理文件名编码
                    try:
                        filename = member.filename.encode("cp437").decode("utf-8")
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        try:
                            filename = member.filename.encode("cp437").decode("gbk")
                        except (UnicodeDecodeError, UnicodeEncodeError):
                            filename = member.filename

                    if "__MACOSX" in filename or "desktop.ini" in filename:
                        continue

                    # 更新进度
                    now = time.monotonic()
                    should_push = (idx == 0) or (idx % 10 == 0) or (idx == total_files - 1)
                    if progress_callback and total_files > 0 and should_push and (now - last_update) >= 0.05:
                        ratio = idx / total_files
                        current_percent = base_progress + ratio * share_progress
                        fname = filename
                        if len(fname) > 25:
                            fname = "..." + fname[-25:]
                        try:
                            progress_callback(int(current_percent), f"解压中: {fname}")
                        except Exception:
                            pass
                        last_update = now

                    # 路径安全校验
                    full_target_path = (target_dir / filename).resolve()
                    try:
                        is_inside = os.path.commonpath([str(full_target_path), str(target_root)]) == str(target_root)
                    except ValueError:
                        is_inside = False
                    if not is_inside:
                        log.warning(f"拦截恶意路径穿越文件: {filename}")
                        continue

                    target_path = target_dir / filename
                    if member.is_dir():
                        try:
                            target_path.mkdir(parents=True, exist_ok=True)
                        except OSError as e:
                            log.warning(f"创建目录失败 {filename}: {e}")
                        continue

                    try:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as source, open(target_path, "wb") as target:
                            while True:
                                chunk = source.read(8192)
                                if not chunk:
                                    break
                                target.write(chunk)
                                if total_bytes > 0:
                                    extracted_bytes += len(chunk)

                                now = time.monotonic()
                                if progress_callback and total_files > 0 and (now - last_update) >= 0.2:
                                    if total_bytes > 0:
                                        ratio = extracted_bytes / total_bytes
                                    else:
                                        ratio = idx / total_files
                                    current_percent = base_progress + ratio * share_progress
                                    fname = filename
                                    if len(fname) > 25:
                                        fname = "..." + fname[-25:]
                                    try:
                                        progress_callback(int(current_percent), f"解压中: {fname}")
                                    except Exception:
                                        pass
                                    last_update = now
                    except PermissionError as e:
                        raise SkinsImportError(f"解压文件失败（权限不足）: {filename}: {e}")
                    except OSError as e:
                        raise SkinsImportError(f"解压文件失败: {filename}: {e}")
                        
        except zipfile.BadZipFile as e:
            raise SkinsImportError(f"无效的 ZIP 文件: {e}")
        except zipfile.LargeZipFile as e:
            raise SkinsImportError(f"ZIP 文件过大: {e}")

    def _move_tree(self, src: Path, dst: Path) -> None:
        """
        将文件或目录从 src 移动到 dst，并在目标已存在时做合併式移动。
        
        Args:
            src: 源路径
            dst: 目标路径
        """
        if src.is_dir():
            if dst.exists():
                for child in src.iterdir():
                    self._move_tree(child, dst / child.name)
                try:
                    src.rmdir()
                except OSError:
                    pass
                return

            try:
                shutil.move(str(src), str(dst))
            except OSError as e:
                log.error(f"移动目录失败 {src}: {e}")
            return

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                try:
                    dst.unlink()
                except OSError:
                    pass
            shutil.move(str(src), str(dst))
        except OSError as e:
            log.error(f"移动文件失败 {src}: {e}")
