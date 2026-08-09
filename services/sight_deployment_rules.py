# -*- coding: utf-8 -*-
"""炮镜部署预检的无状态规则；只生成目标映射，不修改文件系统。"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable

from services.sight_meta_parser import SightMetaParser
from services.sight_package_rules import build_vehicle_sight_target, normalize_safe_relative_path
from services.sight_vehicle_catalog import SightVehicleCatalog, normalize_vehicle_id


_DEPLOYMENT_MODES = {"author_recommended", "all_tanks", "custom_vehicles"}
_MATCH_EXP_CLASS_STATUSES = (
    "present_with_entries",
    "present_empty",
    "missing",
    "unknown_unreadable",
)


def build_sight_deployment_preview(
    resource_files: Iterable[dict[str, Any] | str],
    public_meta: dict[str, Any] | None,
    deployment_request: dict[str, Any] | None,
    vehicle_catalog: SightVehicleCatalog | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """返回确定的部署目标、警告和阻断错误，不执行文件写入。"""
    meta = public_meta if isinstance(public_meta, dict) else {}
    request = deployment_request if isinstance(deployment_request, dict) else {}
    mode = str(request.get("mode") or "").strip().lower()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if mode not in _DEPLOYMENT_MODES:
        errors.append(_issue("invalid_deployment_mode", "不支持的炮镜部署模式。", mode=mode))

    normalized_files = _normalize_resource_files(resource_files, errors)
    known_vehicle_ids = _known_vehicle_ids(vehicle_catalog)
    warned_unknown_ids: set[str] = set()
    parser = SightMetaParser()
    file_meta_by_path = _file_meta_by_path(meta)
    group_meta_by_path = _group_meta_by_path(meta)

    custom_vehicle_ids: list[str] = []
    if mode == "custom_vehicles":
        custom_vehicle_ids = _normalize_vehicle_ids(
            request.get("selected_vehicle_ids"),
            errors,
            scope="custom",
        )
        if not custom_vehicle_ids and not any(item["code"] == "invalid_vehicle_id" for item in errors):
            errors.append(_issue(
                "vehicle_selection_required",
                "自定义车辆模式至少需要选择一辆车。",
            ))

    candidates: list[dict[str, Any]] = []
    fallback_all_tanks_count = 0
    author_recommended_file_count = 0
    for resource_file in normalized_files:
        source_path = resource_file["source_relative_path"]
        source_key = source_path.lower()
        file_meta = file_meta_by_path.get(source_key)
        group_meta = group_meta_by_path.get(source_key)
        recommendation = parser.resolve_recommendation(meta, group_meta, file_meta)
        target_vehicle_ids: list[str] = []
        recommendation_source = "user"

        if mode == "all_tanks":
            target_vehicle_ids = ["all_tanks"]
        elif mode == "custom_vehicles":
            target_vehicle_ids = list(custom_vehicle_ids)
        elif mode == "author_recommended":
            recommendation_source = recommendation.get("source_level") or "fallback"
            if recommendation.get("recommended_apply_mode") == "all_tanks":
                target_vehicle_ids = ["all_tanks"]
                author_recommended_file_count += 1
            elif recommendation.get("recommended_apply_mode") == "vehicles":
                target_vehicle_ids = _normalize_vehicle_ids(
                    [
                        recommendation.get("primary_vehicle_id"),
                        *(recommendation.get("compatible_vehicle_ids") or []),
                    ],
                    warnings,
                    scope="author",
                    invalid_code="invalid_author_vehicle_id",
                )
                if target_vehicle_ids:
                    author_recommended_file_count += 1
            if not target_vehicle_ids:
                target_vehicle_ids = ["all_tanks"]
                recommendation_source = "fallback"
                fallback_all_tanks_count += 1
                warnings.append(_issue(
                    "author_recommendation_missing_fallback",
                    "该文件没有有效作者推荐，已在预览中回退到 all_tanks。",
                    source_relative_path=source_path,
                ))

        for vehicle_id in target_vehicle_ids:
            if vehicle_id != "all_tanks" and vehicle_id not in known_vehicle_ids and vehicle_id not in warned_unknown_ids:
                warned_unknown_ids.add(vehicle_id)
                warnings.append(_issue(
                    "unverified_vehicle_id",
                    "车辆 ID 格式安全，但当前静态目录尚未收录；应用前需由用户确认。",
                    vehicle_id=vehicle_id,
                ))
            try:
                target_path = build_vehicle_sight_target(vehicle_id, source_path)
            except ValueError as exc:
                errors.append(_issue(
                    "invalid_deployment_target",
                    str(exc),
                    source_relative_path=source_path,
                    vehicle_id=vehicle_id,
                ))
                continue
            candidates.append({
                "source_relative_path": source_path,
                "source_storage_relative_path": resource_file["source_storage_relative_path"],
                "target_relative_path": target_path,
                "target_vehicle_id": vehicle_id,
                "recommendation_source": recommendation_source,
                "match_exp_class_status": resource_file["match_exp_class_status"],
            })

    file_targets, collision_count = _remove_filename_collisions(candidates, errors)
    match_status_counts = {status: 0 for status in _MATCH_EXP_CLASS_STATUSES}
    warned_match_sources: set[tuple[str, str]] = set()
    for target in file_targets:
        if target["target_vehicle_id"] != "all_tanks":
            continue
        status = target["match_exp_class_status"]
        match_status_counts[status] += 1
        if status == "present_with_entries":
            continue
        warning_key = (target["source_relative_path"].lower(), status)
        if warning_key in warned_match_sources:
            continue
        warned_match_sources.add(warning_key)
        warnings.append(_issue(
            f"all_tanks_match_exp_class_{status}",
            _match_exp_class_warning_message(status),
            source_relative_path=target["source_relative_path"],
            match_exp_class_status=status,
        ))

    selected_vehicle_ids = []
    seen_selected_ids: set[str] = set()
    for target in file_targets:
        vehicle_id = target["target_vehicle_id"]
        if vehicle_id in seen_selected_ids:
            continue
        seen_selected_ids.add(vehicle_id)
        selected_vehicle_ids.append(vehicle_id)

    return {
        "success": not errors,
        "mode": mode,
        "selected_vehicle_ids": selected_vehicle_ids,
        "file_targets": file_targets,
        "warnings": _deduplicate_issues(warnings),
        "errors": _deduplicate_issues(errors),
        "summary": {
            "resource_file_count": len(normalized_files),
            "target_count": len(file_targets),
            "author_recommended_file_count": author_recommended_file_count,
            "fallback_all_tanks_count": fallback_all_tanks_count,
            "filename_collision_count": collision_count,
            "match_exp_class_status_counts": match_status_counts,
        },
    }


def _normalize_resource_files(
    resource_files: Iterable[dict[str, Any] | str],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in resource_files or []:
        item = raw if isinstance(raw, dict) else {"source_relative_path": raw}
        source_value = (
            item.get("source_relative_path")
            or item.get("output_path")
            or item.get("path")
        )
        try:
            source_path = normalize_safe_relative_path(source_value)
        except ValueError as exc:
            errors.append(_issue("invalid_source_relative_path", str(exc), value=str(source_value or "")))
            continue
        if PurePosixPath(source_path).suffix.lower() != ".blk":
            errors.append(_issue(
                "invalid_source_relative_path",
                "部署源文件必须以 .blk 结尾。",
                value=source_path,
            ))
            continue
        key = source_path.lower()
        if key in seen:
            continue
        seen.add(key)
        storage_value = item.get("source_storage_relative_path") or source_path
        try:
            source_storage_path = normalize_safe_relative_path(storage_value)
        except ValueError as exc:
            errors.append(_issue(
                "invalid_source_storage_path",
                str(exc),
                value=str(storage_value or ""),
            ))
            continue
        status = str(item.get("match_exp_class_status") or "unknown_unreadable")
        if status not in _MATCH_EXP_CLASS_STATUSES:
            status = "unknown_unreadable"
        normalized.append({
            "source_relative_path": source_path,
            "source_storage_relative_path": source_storage_path,
            "match_exp_class_status": status,
        })
    return normalized


def _normalize_vehicle_ids(
    values: Any,
    issues: list[dict[str, Any]],
    scope: str,
    invalid_code: str = "invalid_vehicle_id",
) -> list[str]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, (list, tuple)):
        source = list(values)
    else:
        source = []
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in source:
        if not str(raw_value or "").strip():
            continue
        try:
            vehicle_id = normalize_vehicle_id(raw_value)
        except ValueError:
            issues.append(_issue(
                invalid_code,
                "车辆 ID 不符合安全内部 ID 规则。",
                scope=scope,
                value=str(raw_value or ""),
            ))
            continue
        if vehicle_id in seen:
            continue
        seen.add(vehicle_id)
        result.append(vehicle_id)
    return result


def _file_meta_by_path(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in meta.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/").strip()
        if path:
            result[path.lower()] = item
    return result


def _group_meta_by_path(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    groups = [item for item in meta.get("groups") or [] if isinstance(item, dict)]
    groups.sort(key=lambda item: int(item.get("sort_order") or 0))
    for group in groups:
        for raw_path in group.get("files") or []:
            path = str(raw_path or "").replace("\\", "/").strip().lower()
            if path and path not in result:
                result[path] = group
    return result


def _known_vehicle_ids(
    vehicle_catalog: SightVehicleCatalog | list[dict[str, Any]] | None,
) -> set[str]:
    if isinstance(vehicle_catalog, SightVehicleCatalog):
        rows = vehicle_catalog.list_vehicles()
    elif isinstance(vehicle_catalog, list):
        rows = vehicle_catalog
    else:
        rows = SightVehicleCatalog().list_vehicles()
    return {
        str(item.get("vehicle_id") or "").strip().lower()
        for item in rows
        if isinstance(item, dict) and str(item.get("vehicle_id") or "").strip()
    }


def _remove_filename_collisions(
    candidates: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    by_target: dict[str, list[dict[str, Any]]] = {}
    deduplicated: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in candidates:
        pair = (
            item["source_relative_path"].lower(),
            item["target_relative_path"].lower(),
        )
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        deduplicated.append(item)
        by_target.setdefault(item["target_relative_path"].lower(), []).append(item)

    collided_targets: set[str] = set()
    for target_key, rows in by_target.items():
        source_paths = sorted({row["source_relative_path"] for row in rows})
        if len(source_paths) < 2:
            continue
        collided_targets.add(target_key)
        errors.append(_issue(
            "filename_collision",
            "多个炮镜源文件会写入同一目标文件；自动改名尚未经过游戏实机验证，已阻断这些目标。",
            target_relative_path=rows[0]["target_relative_path"],
            source_relative_paths=source_paths,
        ))
    return (
        [item for item in deduplicated if item["target_relative_path"].lower() not in collided_targets],
        len(collided_targets),
    )


def _match_exp_class_warning_message(status: str) -> str:
    return {
        "present_empty": "matchExpClass 块为空，应用到 all_tanks 可能无法按预期匹配车辆。",
        "missing": "未检测到 matchExpClass；请参考战争雷霆自定义炮镜规则确认全车兼容性。",
        "unknown_unreadable": "无法确认 matchExpClass 兼容性；文件可能不可读或不是可靠文本。",
    }.get(status, "无法确认 all_tanks 兼容性。")


def _issue(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **context}


def _deduplicate_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = repr(sorted(item.items(), key=lambda pair: pair[0]))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result