# -*- coding: utf-8 -*-
import os
import shutil
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger

log = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXE_DISPLAY_NAME = "AimerWT V3.1 Beta"
APP_VERSION = "3.1.0"
APP_VERSION_TUPLE = (3, 1, 0, 0)


REQUIRED_BUILD_ENV_VARS = (
    "REPORT_URL",
    "TELEMETRY_CLIENT_SECRET",
    "TELEMETRY_SALT",
)

REQUIRED_UNTRACKED_THEME_FILES = (
    "bi_an.json",
    "beiku.json",
    "lianying.json",
    "chifeng.json",
    "wuye_fuyin.json",
    "zqrx_mifuyu.json",
    "supporter.json",
)

REQUIRED_UNTRACKED_WEB_FILES = (
    "components/ResourceLibraryLoading.js",
)


def calculate_checksum(file_path, algorithm='sha256'):
    """计算文件的校验和"""
    hash_func = getattr(hashlib, algorithm)()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def clean_build_artifacts():
    """清理构建临时文件"""
    log.info("🧹 正在清理临时文件...")

    # 删除 build 文件夹
    build_dir = PROJECT_ROOT / "build"
    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
            log.info("   - 已删除 build 文件夹")
        except Exception as e:
            log.warning(f"   ! 删除 build 文件夹失败: {e}")

    # 删除 spec 文件
    for spec_name in ('WT_Aimer_Voice.spec', 'AimerWT V3 Beta.spec', 'AimerWT V3.1 Beta.spec'):
        spec_path = PROJECT_ROOT / spec_name
        if spec_path.exists():
            try:
                spec_path.unlink()
                log.info(f'   - 已删除 spec 文件: {spec_name}')
            except Exception as e:
                log.warning(f'   ! 删除 spec 文件失败: {e}')


def load_dotenv(path=".env"):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        except Exception as e:
            print(f"   ! 加载 .env 失败: {e}")


def copy_tracked_web_files(target_dir: Path) -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "web"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_files = [item for item in result.stdout.split("\0") if item]
    if not tracked_files:
        raise RuntimeError("未找到 Git 跟踪的 web 文件")

    copied = 0
    for rel_path in tracked_files:
        source = PROJECT_ROOT / rel_path
        if not source.is_file():
            continue
        web_rel_path = Path(rel_path).relative_to("web")
        destination = target_dir / web_rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
    return copied


def _copy_untracked_build_assets(web_pack_dir: Path) -> int:
    """复制被 .gitignore 排除但分发版必需的 web 文件。"""
    themes_src = PROJECT_ROOT / "web" / "themes"
    themes_dst = web_pack_dir / "themes"
    themes_dst.mkdir(parents=True, exist_ok=True)

    copied = 0
    for relative_path in REQUIRED_UNTRACKED_WEB_FILES:
        source = PROJECT_ROOT / "web" / relative_path
        if not source.is_file():
            log.warning(f"   - 分发版必需文件缺失: {relative_path}")
            continue
        destination = web_pack_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
            copied += 1

    for filename in REQUIRED_UNTRACKED_THEME_FILES:
        source = themes_src / filename
        if not source.is_file():
            log.warning(f"   - 分发版隐藏主题缺失: {filename}")
            continue
        dst = themes_dst / filename
        if not dst.exists():
            shutil.copy2(source, dst)
            copied += 1
    return copied


def write_version_info(version_file: Path) -> None:
    version_file.write_text(
        f"""# UTF-8
# PyInstaller Windows 版本资源文件
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={APP_VERSION_TUPLE},
    prodvers={APP_VERSION_TUPLE},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'080404B0',
          [
            StringStruct(u'CompanyName', u'Aimer'),
            StringStruct(u'FileDescription', u'{EXE_DISPLAY_NAME}'),
            StringStruct(u'FileVersion', u'{APP_VERSION}'),
            StringStruct(u'InternalName', u'{EXE_DISPLAY_NAME}'),
            StringStruct(u'LegalCopyright', u'Copyright (c) 2026 Aimer. All rights reserved.'),
            StringStruct(u'OriginalFilename', u'{EXE_DISPLAY_NAME}.exe'),
            StringStruct(u'ProductName', u'{EXE_DISPLAY_NAME}'),
            StringStruct(u'ProductVersion', u'{APP_VERSION}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [0x0804, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def require_build_env() -> dict[str, str]:
    """校验生产打包所需的关键环境变量。"""
    missing = []
    values: dict[str, str] = {}
    for key in REQUIRED_BUILD_ENV_VARS:
        value = os.environ.get(key, "").strip()
        if not value:
            missing.append(key)
            continue
        values[key] = value

    if missing:
        raise RuntimeError(
            "缺少必填环境变量: " + ", ".join(missing)
        )
    return values


def build_exe():
    """执行打包任务"""
    log.info("🚀 开始打包程序...")

    # 确保 dist 目录存在 (PyInstaller 会自动创建，但为了保险)
    dist_dir = PROJECT_ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)

    load_dotenv(PROJECT_ROOT / ".env")

    try:
        build_env = require_build_env()
    except RuntimeError as exc:
        log.error(f"[X] 打包终止: {exc}")
        sys.exit(1)

    # 在打包前，从打包环境的环境变量中读取遥测配置。
    salt = build_env["TELEMETRY_SALT"]
    url = build_env["REPORT_URL"]
    client_secret = build_env["TELEMETRY_CLIENT_SECRET"]

    # 生成临时的 app_secrets.py 供编译使用
    # 注意：该文件已被加入 .gitignore，不会被上传到 GitHub
    secrets_file = PROJECT_ROOT / "app_secrets.py"
    with open(secrets_file, "w", encoding="utf-8") as f:
        f.write("# 由 build.py 自动生成 - 不要把它提交到github\n")
        f.write(f"TELEMETRY_SALT = {repr(salt)}\n")
        f.write(f"REPORT_URL = {repr(url)}\n")
        f.write(f"TELEMETRY_CLIENT_SECRET = {repr(client_secret)}\n")

    # Os specific separator
    sep = ';' if os.name == 'nt' else ':'

    with tempfile.TemporaryDirectory(prefix="aimerwt_web_pack_") as tmp_dir:
        web_pack_dir = Path(tmp_dir) / "web"
        copied_web_files = copy_tracked_web_files(web_pack_dir)
        log.info(f"   - 已准备 web 打包文件: {copied_web_files} 个")

        # 补充复制被 .gitignore 排除但分发版必需的文件
        extra_count = _copy_untracked_build_assets(web_pack_dir)
        if extra_count:
            log.info(f"   - 已补充非 Git 跟踪文件: {extra_count} 个")
        version_file = Path(tmp_dir) / "version_info.txt"
        write_version_info(version_file)

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconsole",
            "--onefile",
            "--add-data", f"{web_pack_dir}{sep}web",
            "--name", EXE_DISPLAY_NAME,
            "--clean",
            # hidden imports：确保 pywebview 各后端、pystray、pythonnet 均被打包
            "--hidden-import", "webview.platforms.winforms",
            "--hidden-import", "webview.platforms.cef",
            "--hidden-import", "webview.platforms.gtk",
            "--hidden-import", "clr",
            "--hidden-import", "clr_loader",
            "--hidden-import", "pystray._win32",
            "--hidden-import", "PIL._imaging",
            "--hidden-import", "PIL.Image",
            "--hidden-import", "PIL.IcoImagePlugin",
            "--hidden-import", "requests",
            "--hidden-import", "certifi",
            "--hidden-import", "charset_normalizer",
            "--hidden-import", "bottle",
            "--hidden-import", "services.theme_unlock",
            "--hidden-import", "services.theme_unlock.service",
            "--collect-all", "webview",
            "--collect-all", "pystray",
            "main.py"
        ]

        # 可选打包 tools 目录（例如 vgmstream-cli 及其依赖）
        tools_dir = PROJECT_ROOT / "tools"
        if tools_dir.is_dir():
            cmd.extend(["--add-data", f"{tools_dir}{sep}tools"])
        else:
            log.warning("未发现 tools 目录，跳过工具文件打包")

        if os.name == 'nt':
            cmd.extend(["--icon", str(PROJECT_ROOT / "web" / "assets" / "app_icon.ico")])
            cmd.extend(["--version-file", str(version_file)])
            log.info(f"已生成版本资源文件: {version_file}")
        else:
            cmd.append("--strip")

        log.info(f"执行命令: {' '.join(cmd)}")

        try:
            # shell=False ensures arguments are passed correctly on Linux without manual escaping
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
            if result.stdout:
                log.debug(result.stdout)
            if result.stderr:
                log.debug(result.stderr)
        except subprocess.CalledProcessError as e:
            log.error(f"[X] 打包失败！错误: {e}", exc_info=True)
            log.error("--- PyInstaller stdout ---")
            if e.stdout:
                log.error(e.stdout)
            log.error("--- PyInstaller stderr ---")
            if e.stderr:
                log.error(e.stderr)
            sys.exit(1)
        except Exception as e:
            log.exception(f"[X] 打包失败！错误: {e}")
            sys.exit(1)
        else:
            exe_name = f"{EXE_DISPLAY_NAME}.exe" if os.name == 'nt' else EXE_DISPLAY_NAME
            exe_path = dist_dir / exe_name
            log.info("[OK] 打包成功！")
            log.info(f"输出文件: {exe_path}")
            return True


def main():
    # 1. 执行打包
    if not build_exe():
        return

    # 2. 生成校验文件
    exe_name = f"{EXE_DISPLAY_NAME}.exe" if os.name == 'nt' else EXE_DISPLAY_NAME
    dist_dir = PROJECT_ROOT / "dist"
    exe_path = dist_dir / exe_name

    if not exe_path.exists():
        log.error(f"❌ 未找到生成的 exe 文件！: {exe_path}")
        return

    log.info("🔐 正在生成校验文件...")
    checksum = calculate_checksum(exe_path, 'sha256')
    checksum_file = dist_dir / Path("checksum.txt")

    with open(checksum_file, 'w', encoding='utf-8') as f:
        f.write(f"File: {exe_path.name}\n")
        f.write(f"SHA256: {checksum}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    log.info(f"✅ 校验文件已生成: {checksum_file}")
    log.info(f"   SHA256: {checksum}")

    # 3. 清理临时文件
    clean_build_artifacts()

    log.info("\n🎉 所有任务完成！可执行文件位于 dist 目录。")


if __name__ == "__main__":
    main()
