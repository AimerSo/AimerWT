# -*- coding: utf-8 -*-
"""整理跨平台构建产物，生成可直接上传到 Release 的文件。"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build import EXE_DISPLAY_NAME

SUPPORTED_PLATFORMS = ("Windows", "Linux", "macOS")
RELEASE_NAME = EXE_DISPLAY_NAME.replace(" ", "_")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_existing(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _archive_macos_app(source: Path, target: Path) -> None:
    """使用 macOS 原生 ditto 保留 app bundle 内的资源和权限。"""
    _remove_existing(target)
    try:
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(source),
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("macOS 构建环境缺少 ditto 命令") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"压缩 macOS app 失败: {detail}") from exc


def _write_checksum(target: Path, output_dir: Path, platform: str, arch: str) -> Path:
    checksum_path = output_dir / f"checksum_{platform}_{arch}.txt"
    checksum_path.write_text(
        "\n".join(
            (
                f"File: {target.name}",
                f"SHA256: {_sha256(target)}",
                f"Date: {datetime.now(timezone.utc).isoformat()}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return checksum_path


def prepare_release_asset(
    platform: str,
    arch: str,
    *,
    dist_dir: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    """整理一个矩阵 job 的产物并返回二进制和 checksum 路径。"""
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"不支持的平台: {platform}")
    if not arch or any(char.isspace() for char in arch):
        raise ValueError(f"架构名称无效: {arch!r}")

    dist_dir = dist_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if platform == "Windows":
        source = dist_dir / f"{EXE_DISPLAY_NAME}.exe"
        target = output_dir / f"{RELEASE_NAME}_{platform}_{arch}.exe"
        if not source.is_file():
            raise FileNotFoundError(f"未找到 Windows 构建产物: {source}")
        _remove_existing(target)
        shutil.copy2(source, target)
    elif platform == "Linux":
        source = dist_dir / EXE_DISPLAY_NAME
        target = output_dir / f"{RELEASE_NAME}_{platform}_{arch}"
        if not source.is_file():
            raise FileNotFoundError(f"未找到 Linux 构建产物: {source}")
        _remove_existing(target)
        shutil.copy2(source, target)
    else:
        source = dist_dir / f"{EXE_DISPLAY_NAME}.app"
        target = output_dir / f"{RELEASE_NAME}_{platform}_{arch}.zip"
        if not source.is_dir():
            raise FileNotFoundError(f"未找到 macOS app 产物: {source}")
        _archive_macos_app(source, target)

    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError(f"发布文件为空或未生成: {target}")

    checksum = _write_checksum(target, output_dir, platform, arch)
    return target, checksum


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="整理 Aimer WT Release 构建产物")
    parser.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--dist-dir", type=Path, default=PROJECT_ROOT / "dist")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "release-assets")
    args = parser.parse_args(argv)

    try:
        target, checksum = prepare_release_asset(
            args.platform,
            args.arch,
            dist_dir=args.dist_dir,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"Release asset: {target}")
    print(f"Checksum: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
