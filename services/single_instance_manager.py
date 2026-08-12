# -*- coding: utf-8 -*-
"""AimerWT 跨版本单实例保护。"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import BinaryIO


class _FileLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._file: BinaryIO | None = None
        self.error_code = ""

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        lock_file: BinaryIO | None = None
        self.error_code = ""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = open(self.path, "a+b")
            if lock_file.seek(0, os.SEEK_END) == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._file = lock_file
            return True
        except OSError:
            self.error_code = (
                "another_instance_running" if lock_file is not None else "config_dir_unavailable"
            )
            if lock_file is not None:
                try:
                    lock_file.close()
                except Exception:
                    pass
            return False

    def release(self) -> None:
        lock_file = self._file
        self._file = None
        if lock_file is None:
            return
        try:
            lock_file.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            lock_file.close()
        except Exception:
            pass


class _WindowsUserMutex:
    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name: str):
        self.name = str(name)
        self._handle = None
        self._kernel32 = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        if self._handle:
            return True
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_mutex = kernel32.CreateMutexW
            create_mutex.restype = ctypes.c_void_p
            ctypes.set_last_error(0)
            handle = create_mutex(None, False, self.name)
            if not handle:
                return False
            if ctypes.get_last_error() == self.ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            self._kernel32 = kernel32
            return True
        except Exception:
            return False

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        kernel32 = self._kernel32
        self._kernel32 = None
        if not handle or sys.platform != "win32":
            return
        try:
            if kernel32 is None:
                import ctypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle(handle)
        except Exception:
            pass


def default_user_mutex_name(user_scope: str | Path) -> str:
    normalized = os.path.normcase(os.path.abspath(str(user_scope)))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"Local\\AimerWT.SingleInstance.{digest}"


class MultiVersionInstanceGuard:
    """依次持有旧版文件锁、新版文件锁和 Windows 用户级互斥对象。"""

    def __init__(
        self,
        legacy_lock_path: Path,
        current_lock_path: Path,
        mutex_name: str | None = None,
    ):
        self.legacy_lock_path = Path(legacy_lock_path)
        self.current_lock_path = Path(current_lock_path)
        self._legacy_lock = _FileLock(self.legacy_lock_path)
        self._current_lock = _FileLock(self.current_lock_path)
        self._mutex = _WindowsUserMutex(
            mutex_name or default_user_mutex_name(self.current_lock_path.parent.parent)
        )
        self._acquired = False
        self.error_code = ""

    def acquire(self) -> bool:
        if self._acquired:
            return True
        self.error_code = ""
        if not self._legacy_lock.acquire():
            self.error_code = self._legacy_lock.error_code or "another_instance_running"
            return False
        if not self._current_lock.acquire():
            self.error_code = self._current_lock.error_code or "another_instance_running"
            self._legacy_lock.release()
            return False
        if not self._mutex.acquire():
            self.error_code = "another_instance_running"
            self._current_lock.release()
            self._legacy_lock.release()
            return False
        self._acquired = True
        return True

    def suspend_current_lock(self) -> None:
        """目录切换期间仅放开新目录文件锁，旧锁和用户互斥量继续生效。"""
        if self._acquired:
            self._current_lock.release()

    def resume_current_lock(self) -> bool:
        if not self._acquired:
            return False
        if self._current_lock.acquire():
            return True
        self.error_code = self._current_lock.error_code or "config_dir_unavailable"
        return False

    def release(self) -> None:
        self._acquired = False
        self._mutex.release()
        self._current_lock.release()
        self._legacy_lock.release()

    def __enter__(self) -> "MultiVersionInstanceGuard":
        if not self.acquire():
            raise RuntimeError("another_instance_running")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
