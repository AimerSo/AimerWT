# -*- coding: utf-8 -*-
"""
远程素材离线缓存管理器

功能定位:
    联网时将服务端下发的远程图片（广告轮播、信息库广告）下载到本地隐藏缓存目录，
    离线启动时将缓存图片转为 base64 Data URI 注入前端，实现无感知离线展示。

    注: Edge WebView2 的 file:// 页面无法通过 file:/// URI 加载外部目录图片，
    因此使用 Data URI（data:image/...;base64,...）作为图片源。

缓存目录:
    ~/Documents/Aimer_WT/.cache/remote_assets/
        ├── ad_carousel/
        └── knowledge_ads/

文件命名:
    {asset_id}_{url_md5_前8位}.{ext}
"""

import base64
import hashlib
import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter

log = logging.getLogger(__name__)

# 允许缓存的图片扩展名白名单
_ALLOWED_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp"}

# 扩展名 → MIME 类型映射
_EXT_MIME = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
}

# 单文件大小上限（8MB，对齐后台广告上传上限）
_MAX_FILE_SIZE = 8 * 1024 * 1024

# 下载超时（秒）
_DOWNLOAD_TIMEOUT = 10

# 下载失败后的重试间隔，避免心跳期间反复请求同一失败素材
_FAILED_RETRY_SECONDS = 10 * 60


class _PinnedHTTPSAdapter(HTTPAdapter):
    """将 HTTPS 连接固定到已验证 IP，同时保留原域名 TLS 身份。"""

    def __init__(self, pinned_ip: str, tls_hostname: str):
        self._pinned_ip = pinned_ip
        self._tls_hostname = tls_hostname
        super().__init__()

    def get_connection_with_tls_context(
        self, request, verify, proxies=None, cert=None
    ):
        host_params, pool_kwargs = self.build_connection_pool_key_attributes(
            request, verify, cert
        )
        host_params["host"] = self._pinned_ip
        pool_kwargs["server_hostname"] = self._tls_hostname
        pool_kwargs["assert_hostname"] = self._tls_hostname
        return self.poolmanager.connection_from_host(
            **host_params,
            pool_kwargs=pool_kwargs,
        )


class RemoteAssetCache:
    """远程素材离线缓存管理器"""

    def __init__(self, cache_root: Path, trusted_origin: str = ""):
        self._root = cache_root
        self._trusted_origin = self._parse_https_origin(trusted_origin)

    def is_allowed_remote_url(self, url: str) -> bool:
        """判断远程地址是否与可信 HTTPS 来源完全同源。"""
        if self._trusted_origin is None:
            return False
        return self._parse_https_origin(url) == self._trusted_origin

    @staticmethod
    def _parse_https_origin(url: str) -> tuple[str, str, int] | None:
        if not isinstance(url, str) or not url:
            return None
        try:
            parsed = urlparse(url)
            if (
                parsed.scheme.lower() != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                return None
            port = parsed.port
            if port is not None and not 1 <= port <= 65535:
                return None
            return (
                "https",
                parsed.hostname.lower(),
                443 if port is None else port,
            )
        except ValueError:
            return None

    @staticmethod
    def _resolve_public_addresses(url: str) -> tuple[str, ...]:
        try:
            parsed = urlparse(url)
            results = socket.getaddrinfo(
                parsed.hostname,
                443 if parsed.port is None else parsed.port,
                type=socket.SOCK_STREAM,
            )
            addresses = tuple(
                ipaddress.ip_address(result[4][0])
                for result in results
            )
        except (OSError, ValueError):
            return ()
        if not addresses or not all(
            address.is_global
            and not address.is_private
            and not address.is_loopback
            and not address.is_link_local
            and not address.is_reserved
            and not address.is_multicast
            and not address.is_unspecified
            for address in addresses
        ):
            return ()
        return tuple(str(address) for address in addresses)

    def cache_image(self, url: str, category: str, asset_id: str) -> str | None:
        """
        下载远程图片到本地缓存，并返回 base64 Data URI 供前端直接使用。

        输入:
            url: 远程图片 URL（https://...）
            category: 分类子目录（"ad_carousel" / "knowledge_ads"）
            asset_id: 资产标识符（如 "ad_slide_1"、"kb_ad_2_avatar"）
        输出:
            data:image/...;base64,... 格式的 Data URI，失败返回 None，由调用方拒绝或清空图片值
        """
        if not self.is_allowed_remote_url(url):
            return None

        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        ext = self._guess_extension(url)
        safe_id = _sanitize_id(asset_id)
        filename = f"{safe_id}_{url_hash}{ext}"
        category_dir = self._root / category
        local_path = category_dir / filename

        # 缓存命中：文件存在且非空 → 直接转 Data URI
        if local_path.exists() and local_path.stat().st_size > 0:
            return self._file_to_data_uri(local_path)

        # 按前缀搜索（扩展名可能因 Content-Type 不同）
        existing = self._find_cached_file(category_dir, safe_id, url_hash)
        if existing:
            return self._file_to_data_uri(existing)

        if self._has_recent_failure(local_path) or self._find_recent_failure(category_dir, safe_id, url_hash):
            return None

        resolved_addresses = self._resolve_public_addresses(url)
        if not resolved_addresses:
            return None

        tmp: Path | None = None
        # 下载
        try:
            import requests
            category_dir.mkdir(parents=True, exist_ok=True)

            parsed = urlparse(url)
            session = requests.Session()
            try:
                session.trust_env = False
                session.mount(
                    "https://",
                    _PinnedHTTPSAdapter(
                        resolved_addresses[0],
                        parsed.hostname,
                    ),
                )
                resp = session.get(
                    url,
                    timeout=_DOWNLOAD_TIMEOUT,
                    stream=True,
                    allow_redirects=False,
                    headers={"Host": parsed.netloc},
                )
                try:
                    if 300 <= resp.status_code < 400:
                        return None
                    resp.raise_for_status()

                    # 推断实际扩展名（优先使用 Content-Type）
                    content_type = resp.headers.get("Content-Type", "")
                    ct_ext = _ext_from_content_type(content_type)
                    if ct_ext and ct_ext != ext:
                        filename = f"{safe_id}_{url_hash}{ct_ext}"
                        local_path = category_dir / filename

                    tmp = local_path.with_suffix(".tmp")
                    written = 0
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                            written += len(chunk)
                            if written > _MAX_FILE_SIZE:
                                tmp.unlink(missing_ok=True)
                                self._mark_failure(local_path, "too_large")
                                log.warning(f"[素材缓存] 文件过大，跳过: {url}")
                                return None
                    tmp.replace(local_path)
                    self._clear_failure(local_path)
                    log.debug(f"[素材缓存] 已缓存: {url} -> {local_path.name}")
                    return self._file_to_data_uri(local_path)
                finally:
                    resp.close()
            finally:
                session.close()

        except Exception as e:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                self._mark_failure(local_path, type(e).__name__)
            except Exception:
                pass
            log.debug(f"[素材缓存] 下载失败: {url} ({e})")
            return None

    def load_cached_data_uri(self, url: str, category: str, asset_id: str) -> str | None:
        """
        仅从本地缓存加载 Data URI，不触发下载。用于离线启动时恢复。

        输出:
            缓存命中返回 data:image/... Data URI，否则返回 None
        """
        if not url or not isinstance(url, str):
            return None
        if not self.is_allowed_remote_url(url):
            return None
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        safe_id = _sanitize_id(asset_id)
        category_dir = self._root / category

        # 精确匹配
        for ext in _ALLOWED_EXTENSIONS:
            candidate = category_dir / f"{safe_id}_{url_hash}{ext}"
            if candidate.exists() and candidate.stat().st_size > 0:
                return self._file_to_data_uri(candidate)

        # 前缀搜索
        existing = self._find_cached_file(category_dir, safe_id, url_hash)
        if existing:
            return self._file_to_data_uri(existing)
        return None

    def has_cached_image(self, url: str, category: str, asset_id: str) -> bool:
        """
        判断素材是否已具备本地缓存。用于决定是否向服务端声明缓存命中。
        """
        if not url or not isinstance(url, str):
            return True
        if url.startswith("data:"):
            return True
        if not url.startswith(("http://", "https://")):
            return True

        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        safe_id = _sanitize_id(asset_id)
        category_dir = self._root / category
        for ext in _ALLOWED_EXTENSIONS:
            candidate = category_dir / f"{safe_id}_{url_hash}{ext}"
            if candidate.exists() and candidate.stat().st_size > 0:
                return True
        return self._find_cached_file(category_dir, safe_id, url_hash) is not None

    def cleanup_stale(self, category: str, active_asset_ids: list[str]):
        """
        清理不再使用的缓存文件（按 asset_id 前缀匹配）。

        输入:
            category: 分类子目录
            active_asset_ids: 当前仍在使用的 asset_id 列表
        """
        category_dir = self._root / category
        if not category_dir.exists():
            return
        active_prefixes = {_sanitize_id(aid) for aid in active_asset_ids}
        for f in category_dir.iterdir():
            if not f.is_file():
                continue
            name = f.stem
            parts = name.rsplit("_", 1)
            prefix = parts[0] if len(parts) == 2 else name
            if prefix not in active_prefixes:
                try:
                    f.unlink()
                    log.debug(f"[素材缓存] 清理过期文件: {f.name}")
                except Exception:
                    pass

    # ---- 内部方法 ----

    @staticmethod
    def _file_to_data_uri(path: Path) -> str | None:
        """将本地图片文件转为 base64 Data URI"""
        try:
            mime = _EXT_MIME.get(path.suffix.lower(), "image/webp")
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return None

    @staticmethod
    def _guess_extension(url: str) -> str:
        """从 URL 路径推断文件扩展名，默认 .webp"""
        try:
            path = urlparse(url).path
            suffix = Path(path).suffix.lower()
            if suffix in _ALLOWED_EXTENSIONS:
                return suffix
        except Exception:
            pass
        return ".webp"

    @staticmethod
    def _find_cached_file(category_dir: Path, safe_id: str, url_hash: str) -> Path | None:
        """在缓存目录中按前缀搜索匹配文件"""
        if not category_dir.exists():
            return None
        prefix = f"{safe_id}_{url_hash}"
        for f in category_dir.iterdir():
            if f.name.startswith(prefix) and f.suffix in _ALLOWED_EXTENSIONS:
                if f.stat().st_size > 0:
                    return f
        return None

    @staticmethod
    def _failure_marker(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".fail")

    def _has_recent_failure(self, path: Path) -> bool:
        marker = self._failure_marker(path)
        if not marker.exists():
            return False
        try:
            import time
            age = time.time() - marker.stat().st_mtime
            if age <= _FAILED_RETRY_SECONDS:
                return True
            marker.unlink(missing_ok=True)
        except Exception:
            return False
        return False

    def _find_recent_failure(self, category_dir: Path, safe_id: str, url_hash: str) -> bool:
        if not category_dir.exists():
            return False
        prefix = f"{safe_id}_{url_hash}"
        for marker in category_dir.iterdir():
            if marker.name.startswith(prefix) and marker.name.endswith(".fail"):
                if self._has_recent_failure(marker.with_suffix("")):
                    return True
        return False

    def _mark_failure(self, path: Path, reason: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._failure_marker(path).write_text(str(reason or "failed"), encoding="utf-8")

    def _clear_failure(self, path: Path):
        self._failure_marker(path).unlink(missing_ok=True)


def _ext_from_content_type(content_type: str) -> str | None:
    """从 HTTP Content-Type 推断扩展名"""
    ct = content_type.lower().split(";")[0].strip()
    mapping = {
        "image/webp": ".webp",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
    }
    return mapping.get(ct)


def _sanitize_id(asset_id: str) -> str:
    """清理 asset_id，仅保留安全字符"""
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(asset_id or "unknown"))[:48]
