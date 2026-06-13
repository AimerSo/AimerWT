import platform
import shutil
import sys
from pathlib import Path


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _bundled_candidates() -> list[Path]:
    tools_dir = _runtime_root() / "tools" / "7zip"
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        if "arm64" in machine or "aarch64" in machine:
            return [
                tools_dir / "windows" / "arm64" / "7za.exe",
                tools_dir / "windows" / "7za.exe",
            ]
        if "64" in machine:
            return [
                tools_dir / "windows" / "x64" / "7za.exe",
                tools_dir / "windows" / "7za.exe",
            ]
        return [tools_dir / "windows" / "7za.exe"]

    if system == "Darwin":
        return [tools_dir / "macos" / "7zz"]

    if "arm64" in machine or "aarch64" in machine:
        return [tools_dir / "linux-arm64" / "7zz"]
    return [tools_dir / "linux-x64" / "7zz"]


def find_7z_executable() -> str | None:
    for candidate in _bundled_candidates():
        if candidate.is_file():
            if platform.system() != "Windows":
                try:
                    candidate.chmod(candidate.stat().st_mode | 0o755)
                except OSError:
                    pass
            return str(candidate)

    return (
        shutil.which("7z")
        or shutil.which("7z.exe")
        or shutil.which("7za")
        or shutil.which("7za.exe")
        or shutil.which("7zr")
        or shutil.which("7zr.exe")
        or shutil.which("7zz")
        or shutil.which("7zzs")
    )
