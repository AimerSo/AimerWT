# -*- coding: utf-8 -*-
"""真实炮镜 BLK 尾部 AimerWT V2 元数据的字节级读写。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


EMBEDDED_META_START = b"\n/* AIMERWT_SIGHT_EMBED_V2\n"
EMBEDDED_META_END = b"\nAIMERWT_SIGHT_EMBED_END */"
MAX_EMBEDDED_META_BYTES = 1024 * 1024
_TAIL_READ_BYTES = MAX_EMBEDDED_META_BYTES + len(EMBEDDED_META_START) + len(EMBEDDED_META_END) + 4096
_TRAILING_WHITESPACE = b" \t\r\n"


class SightEmbeddedMetadataError(ValueError):
    """内嵌元数据结构不完整或不符合 V2 协议。"""


class SightEmbeddedMetadataConflict(SightEmbeddedMetadataError):
    """目标真实炮镜主体已被外部修改。"""


def _empty_result() -> dict[str, Any]:
    return {
        "parsed": False,
        "meta": None,
        "error": "",
        "warnings": [],
        "block_start": -1,
        "block_end": -1,
    }


def _trimmed_end(raw: bytes) -> int:
    index = len(raw)
    while index > 0 and raw[index - 1] in _TRAILING_WHITESPACE:
        index -= 1
    return index


def parse_embedded_metadata_bytes(raw: bytes) -> dict[str, Any]:
    """从真实 BLK 的限定尾部读取一个完整 V2 注释块。"""
    if not isinstance(raw, bytes):
        raise TypeError("raw 必须是 bytes")

    trimmed_end = _trimmed_end(raw)
    tail_start = max(0, trimmed_end - _TAIL_READ_BYTES)
    tail = raw[tail_start:trimmed_end]
    start_count = tail.count(EMBEDDED_META_START)
    end_count = tail.count(EMBEDDED_META_END)
    if start_count == 0 and end_count == 0:
        return _empty_result()
    if start_count != 1 or end_count != 1:
        raise SightEmbeddedMetadataError("AimerWT V2 元数据标记不完整或重复")

    relative_start = tail.find(EMBEDDED_META_START)
    payload_start = relative_start + len(EMBEDDED_META_START)
    relative_end = tail.find(EMBEDDED_META_END, payload_start)
    if relative_start < 0 or relative_end < payload_start:
        raise SightEmbeddedMetadataError("AimerWT V2 元数据标记顺序无效")
    if relative_end + len(EMBEDDED_META_END) != len(tail):
        raise SightEmbeddedMetadataError("AimerWT V2 元数据必须位于真实 BLK 末尾")

    payload = tail[payload_start:relative_end]
    if not payload or len(payload) > MAX_EMBEDDED_META_BYTES:
        raise SightEmbeddedMetadataError("AimerWT V2 元数据为空或超过大小限制")
    try:
        meta = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SightEmbeddedMetadataError("AimerWT V2 元数据 JSON 无法解析") from exc
    if not isinstance(meta, dict) or meta.get("meta_version") != 2:
        raise SightEmbeddedMetadataError("AimerWT V2 元数据版本无效")

    return {
        "parsed": True,
        "meta": meta,
        "error": "",
        "warnings": [],
        "block_start": tail_start + relative_start,
        "block_end": trimmed_end,
    }


def strip_embedded_metadata_bytes(raw: bytes) -> bytes:
    """移除真实 BLK 末尾已有的完整 V2 注释块。"""
    parsed = parse_embedded_metadata_bytes(raw)
    if not parsed["parsed"]:
        return raw
    return raw[: int(parsed["block_start"])]


def _serialize_meta(meta: dict[str, Any]) -> bytes:
    if not isinstance(meta, dict) or meta.get("meta_version") != 2:
        raise SightEmbeddedMetadataError("写入内容必须是 meta_version=2 的对象")
    text = json.dumps(
        meta,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).replace("/", "\\/")
    payload = text.encode("ascii")
    if len(payload) > MAX_EMBEDDED_META_BYTES:
        raise SightEmbeddedMetadataError("AimerWT V2 元数据超过大小限制")
    return payload


def replace_embedded_metadata_bytes(raw: bytes, meta: dict[str, Any]) -> bytes:
    """保留真实炮镜主体字节，并幂等替换末尾 V2 注释块。"""
    body = strip_embedded_metadata_bytes(raw)
    payload = _serialize_meta(meta)
    return body + EMBEDDED_META_START + payload + EMBEDDED_META_END + b"\n"


def body_sha256(raw: bytes) -> str:
    """计算不包含 AimerWT V2 注释块的真实炮镜主体摘要。"""
    return hashlib.sha256(strip_embedded_metadata_bytes(raw)).hexdigest()


def parse_embedded_metadata_file(path: str | Path) -> dict[str, Any]:
    """只读取文件尾部并解析 V2 元数据。"""
    file_path = Path(path)
    size = file_path.stat().st_size
    tail_start = max(0, size - _TAIL_READ_BYTES)
    with file_path.open("rb") as handle:
        handle.seek(tail_start)
        tail = handle.read(_TAIL_READ_BYTES)
    parsed = parse_embedded_metadata_bytes(tail)
    if parsed["parsed"]:
        parsed["block_start"] = tail_start + int(parsed["block_start"])
        parsed["block_end"] = tail_start + int(parsed["block_end"])
    return parsed


def write_embedded_metadata_file(
    source: str | Path,
    meta: dict[str, Any],
    *,
    destination: str | Path | None = None,
    expected_body_sha256: str = "",
) -> dict[str, Any]:
    """把 V2 元数据写入来源或另存目标，并在替换前完成回读校验。"""
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve() if destination is not None else source_path
    if not source_path.is_file():
        raise FileNotFoundError(f"真实炮镜不存在: {source_path}")
    if not destination_path.parent.is_dir():
        raise FileNotFoundError(f"目标目录不存在: {destination_path.parent}")

    source_raw = source_path.read_bytes()
    source_body_sha256 = body_sha256(source_raw)
    expected = str(expected_body_sha256 or "").strip().lower()
    if expected and source_body_sha256.lower() != expected:
        raise SightEmbeddedMetadataConflict("真实炮镜主体已被外部修改")

    output_raw = replace_embedded_metadata_bytes(source_raw, meta)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            dir=destination_path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(output_raw)
            handle.flush()
            os.fsync(handle.fileno())

        parsed = parse_embedded_metadata_file(temp_path)
        if not parsed["parsed"] or parsed["meta"] != meta:
            raise SightEmbeddedMetadataError("写入后的 AimerWT V2 元数据回读不一致")
        os.replace(str(temp_path), str(destination_path))
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()

    return {
        "path": str(destination_path),
        "body_sha256": source_body_sha256,
        "size": destination_path.stat().st_size,
        "meta": meta,
    }
