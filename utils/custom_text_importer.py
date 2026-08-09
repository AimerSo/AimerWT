import re
import zipfile
import shutil
import csv
import os
import tempfile
from pathlib import Path
from typing import Optional


def extract_csv_references_from_blk(blk_content: str) -> list[str]:
    """
    从 blk 文件内容中提取 CSV 文件引用
    例如：%lang/custom_menu.csv -> custom_menu.csv
    """
    pattern = r'%lang/([^"\s]+\.csv)'
    matches = re.findall(pattern, blk_content, re.IGNORECASE)
    return list(set(matches))


def detect_import_mode(import_path: Path) -> tuple[str, dict]:
    """
    检测导入模式
    返回: (mode, info)
    mode: "standard" | "custom_blk" | "unknown"
    info: 包含检测到的文件信息
    """
    csv_files = []
    blk_files = []

    for file in import_path.iterdir():
        if file.is_file():
            if file.suffix.lower() == '.csv':
                csv_files.append(file.name)
            elif file.suffix.lower() == '.blk':
                blk_files.append(file.name)

    info = {
        "csv_files": csv_files,
        "blk_files": blk_files,
        "csv_references": []
    }

    # 如果有 blk 文件，解析它
    if blk_files:
        for blk_file in blk_files:
            try:
                with open(import_path / blk_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    refs = extract_csv_references_from_blk(content)
                    info["csv_references"].extend(refs)
            except Exception:
                pass

        info["csv_references"] = list(set(info["csv_references"]))

        if info["csv_references"]:
            return "custom_blk", info

    # 检查是否是标准命名
    if csv_files:
        return "standard", info

    return "unknown", info


def match_csv_to_standard(csv_name: str, standard_names: list[str]) -> Optional[str]:
    """
    尝试将自定义 CSV 名称映射到标准名称
    """
    csv_lower = csv_name.lower()

    # 直接匹配
    if csv_name in standard_names:
        return csv_name

    # 模糊匹配
    for std_name in standard_names:
        std_lower = std_name.lower()
        # 如果自定义名称包含标准名称（去掉.csv）
        if std_lower.replace('.csv', '') in csv_lower:
            return std_name

    # 特殊规则：menu 相关的都映射到 menu.csv
    if 'menu' in csv_lower:
        if 'menu.csv' in standard_names:
            return 'menu.csv'

    return None


def _normalize_csv_header(value: str) -> str:
    return str(value or "").strip().strip('"').strip().strip("<>").strip().lower()


def _find_csv_id_index(header: list[str]) -> int:
    for index, value in enumerate(header):
        normalized = _normalize_csv_header(value)
        if normalized == "id" or "readonly" in normalized:
            return index
    return -1


def _load_csv_rows(csv_path: Path) -> tuple[list[list[str]], str]:
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb18030", "cp1252", "latin-1"]
    last_error = None
    for encoding in encodings:
        try:
            with open(csv_path, "r", encoding=encoding, newline="") as file_obj:
                rows = list(csv.reader(file_obj, delimiter=";", quotechar='"', strict=True))
            return rows, encoding
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"读取 CSV 失败: {last_error}")


def validate_csv_file(csv_path: Path) -> tuple[bool, str, list[list[str]], str]:
    try:
        rows, encoding = _load_csv_rows(csv_path)
    except Exception as exc:
        return False, str(exc), [], ""

    if len(rows) < 2 or len(rows[0]) < 2:
        return False, "CSV 文件缺少表头或数据行", [], ""

    header = rows[0]
    id_index = _find_csv_id_index(header)
    if id_index < 0:
        return False, "CSV 文件缺少 ID 列", [], ""

    seen_ids = set()
    data_count = 0
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or not any(str(value).strip() for value in row):
            continue
        if id_index >= len(row):
            return False, f"CSV 第 {row_number} 行缺少 ID", [], ""
        text_id = str(row[id_index]).strip()
        if not text_id:
            return False, f"CSV 第 {row_number} 行 ID 为空", [], ""
        normalized_id = text_id.casefold()
        if normalized_id in seen_ids:
            return False, f"CSV 包含重复 ID: {text_id}", [], ""
        seen_ids.add(normalized_id)
        data_count += 1

    if data_count == 0:
        return False, "CSV 文件没有有效数据行", [], ""

    return True, "CSV 校验通过", rows, encoding


def write_csv_rows_atomic(output_csv_path: Path, rows: list[list[str]], encoding: str) -> None:
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="",
            delete=False,
            dir=str(output_csv_path.parent),
            prefix=f".{output_csv_path.name}.",
            suffix=".tmp",
        ) as file_obj:
            temp_path = Path(file_obj.name)
            writer = csv.writer(
                file_obj,
                delimiter=";",
                quotechar='"',
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
            )
            writer.writerows(rows)
        os.replace(temp_path, output_csv_path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def merge_csv_files(original_csv_path: Path, mod_csv_path: Path, output_csv_path: Path, encoding: str = "utf-8-sig") -> tuple[bool, str, dict]:
    """
    以当前有效 CSV 为基线，按表头名称合并模组 CSV，保留模组未提供的列和行。
    """
    try:
        original_ok, original_message, original_rows, original_encoding = validate_csv_file(original_csv_path)
        if not original_ok:
            return False, f"原始 {original_message}", {}

        mod_ok, mod_message, mod_rows, _mod_encoding = validate_csv_file(mod_csv_path)
        if not mod_ok:
            return False, f"模组 {mod_message}", {}

        original_header = original_rows[0]
        mod_header = mod_rows[0]
        original_id_index = _find_csv_id_index(original_header)
        mod_id_index = _find_csv_id_index(mod_header)
        original_columns = {
            _normalize_csv_header(value): index
            for index, value in enumerate(original_header)
            if _normalize_csv_header(value)
        }
        mod_columns = {
            _normalize_csv_header(value): index
            for index, value in enumerate(mod_header)
            if _normalize_csv_header(value)
        }

        original_data = {}
        for row_index, row in enumerate(original_rows[1:], start=1):
            if original_id_index >= len(row):
                continue
            text_id = str(row[original_id_index]).strip()
            if text_id:
                original_data[text_id.casefold()] = row_index

        stats = {"added": 0, "modified": 0, "total": 0}
        for mod_row in mod_rows[1:]:
            if mod_id_index >= len(mod_row):
                continue
            text_id = str(mod_row[mod_id_index]).strip()
            if not text_id:
                continue

            lookup_id = text_id.casefold()
            existing_index = original_data.get(lookup_id)
            if existing_index is None:
                merged_row = [""] * len(original_header)
            else:
                merged_row = list(original_rows[existing_index])
                if len(merged_row) < len(original_header):
                    merged_row.extend([""] * (len(original_header) - len(merged_row)))
                merged_row = merged_row[:len(original_header)]

            for column_name, mod_index in mod_columns.items():
                target_index = original_columns.get(column_name)
                if target_index is None:
                    continue
                merged_row[target_index] = str(mod_row[mod_index]) if mod_index < len(mod_row) else ""

            merged_row[original_id_index] = text_id
            if existing_index is None:
                original_rows.append(merged_row)
                original_data[lookup_id] = len(original_rows) - 1
                stats["added"] += 1
            elif original_rows[existing_index] != merged_row:
                original_rows[existing_index] = merged_row
                stats["modified"] += 1

        stats["total"] = len(original_rows) - 1
        write_csv_rows_atomic(output_csv_path, original_rows, original_encoding or encoding)
        return True, "合并成功", stats
    except Exception as exc:
        return False, f"合并失败: {exc}", {}


def extract_archive(archive_path: Path, extract_to: Path) -> tuple[bool, str]:
    """
    解压 ZIP 压缩包
    """
    try:
        extract_to.mkdir(parents=True, exist_ok=True)

        if archive_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            return True, "解压成功"
        else:
            return False, f"不支持的压缩格式: {archive_path.suffix}"

    except Exception as e:
        return False, f"解压失败: {e}"


def find_csv_files_recursive(directory: Path) -> list[Path]:
    """
    递归查找目录中的所有 CSV 文件
    """
    csv_files = []
    for item in directory.rglob("*.csv"):
        if item.is_file():
            csv_files.append(item)
    return csv_files


def find_blk_files_recursive(directory: Path) -> list[Path]:
    """
    递归查找目录中的所有 BLK 文件
    """
    blk_files = []
    for item in directory.rglob("*.blk"):
        if item.is_file():
            blk_files.append(item)
    return blk_files

