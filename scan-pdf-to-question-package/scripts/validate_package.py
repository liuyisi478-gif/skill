#!/usr/bin/env python3
"""Validate an Olympiad question package ZIP without importing it."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 5000
MAX_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 10 * 1024 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DIFFICULTIES = {"", "基础", "进阶", "高阶"}


def safe_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and "." not in path.parts and ".." not in path.parts


def knowledge_catalog() -> set[tuple[str, str, str]]:
    path = Path(__file__).resolve().parent.parent / "references" / "knowledge_points.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(x["level_1"], x["level_2"], x["level_3"]) for x in data["entries"]}


def add_unknown(obj: dict, allowed: set[str], label: str, errors: list[str]) -> None:
    unknown = set(obj) - allowed
    if unknown:
        errors.append(f"{label}包含未知字段：{', '.join(sorted(unknown))}")


def validate_manifest(data: object, names: set[str], errors: list[str], warnings: list[str]) -> tuple[int, int]:
    if not isinstance(data, dict):
        errors.append("manifest.json 顶层必须是对象。")
        return 0, 0
    add_unknown(data, {"schema_version", "sources", "questions"}, "顶层", errors)
    if data.get("schema_version") != "1.0":
        errors.append("schema_version 必须为 1.0。")
    sources = data.get("sources")
    questions = data.get("questions")
    if not isinstance(sources, list) or not sources:
        errors.append("sources 必须是非空数组。")
        sources = []
    if not isinstance(questions, list) or not questions:
        errors.append("questions 必须是非空数组。")
        questions = []

    source_ids: set[str] = set()
    source_metadata: dict[str, tuple[str, str]] = {}
    for index, source in enumerate(sources, 1):
        label = f"题源[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label}必须是对象。")
            continue
        add_unknown(source, {"source_id", "name", "school_name", "original_file"}, label, errors)
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
            errors.append(f"{label}.source_id 格式无效。")
        elif source_id in source_ids:
            errors.append(f"题源编号重复：{source_id}")
        else:
            source_ids.add(source_id)
        if not isinstance(source.get("name"), str) or not source["name"].strip():
            errors.append(f"{label}.name 不能为空。")
        school_name = source.get("school_name", "")
        if not isinstance(school_name, str):
            errors.append(f"{label}.school_name 必须是字符串；无法确认时填写空字符串。")
            school_name = ""
        if isinstance(source_id, str):
            source_metadata[source_id] = (source.get("name", ""), school_name)
        original = source.get("original_file")
        if original is not None:
            if not safe_path(original):
                errors.append(f"{label}.original_file 路径不安全。")
            elif original not in names:
                errors.append(f"{label}.original_file 在 ZIP 中不存在：{original}")
            elif Path(original).suffix.lower() != ".pdf":
                errors.append(f"{label}.original_file 必须是 PDF。")

    catalog = knowledge_catalog()
    question_ids: set[str] = set()
    allowed_question = {
        "question_id", "source_id", "original_number", "question_type", "stem",
        "source_name", "school_name", "answer", "analysis", "knowledge_points", "difficulty", "source_pages", "images",
    }
    for index, question in enumerate(questions, 1):
        label = f"题目[{index}]"
        if not isinstance(question, dict):
            errors.append(f"{label}必须是对象。")
            continue
        add_unknown(question, allowed_question, label, errors)
        question_id = question.get("question_id")
        if not isinstance(question_id, str) or not ID_RE.fullmatch(question_id):
            errors.append(f"{label}.question_id 格式无效。")
        elif question_id in question_ids:
            errors.append(f"题目编号重复：{question_id}")
        else:
            question_ids.add(question_id)
        if question.get("source_id") not in source_ids:
            errors.append(f"{label}.source_id 没有对应题源：{question.get('source_id')}")
        if "source_name" in question or "school_name" in question:
            expected_name, expected_school = source_metadata.get(question.get("source_id"), ("", ""))
            if question.get("source_name") != expected_name:
                errors.append(f"{label}.source_name 必须与对应题源的 name 完全一致：{expected_name}")
            if not isinstance(question.get("school_name"), str):
                errors.append(f"{label}.school_name 必须是字符串；无法确认时填写空字符串。")
            elif question.get("school_name") != expected_school:
                errors.append(f"{label}.school_name 必须与对应题源的 school_name 完全一致：{expected_school}")
        if not isinstance(question.get("original_number"), str) or not question["original_number"].strip():
            errors.append(f"{label}.original_number 不能为空。")
        stem = question.get("stem", "")
        images = question.get("images", [])
        if not isinstance(stem, str):
            errors.append(f"{label}.stem 必须是字符串。")
            stem = ""
        if not isinstance(images, list):
            errors.append(f"{label}.images 必须是数组。")
            images = []
        if not stem.strip():
            errors.append(f"{label}.stem 不能为空；图片不能代替题干文字。")
        for image in images:
            if not safe_path(image):
                errors.append(f"{label}图片路径不安全：{image}")
            elif image not in names:
                errors.append(f"{label}图片在 ZIP 中不存在：{image}")
            elif Path(image).suffix.lower() not in IMAGE_EXTENSIONS:
                errors.append(f"{label}图片格式不支持：{image}")
        for field in ("question_type", "answer", "analysis"):
            if field in question and not isinstance(question[field], str):
                errors.append(f"{label}.{field} 必须是字符串。")
        if question.get("difficulty", "") not in DIFFICULTIES:
            errors.append(f"{label}.difficulty 只能是基础、进阶、高阶或空。")
        pages = question.get("source_pages", [])
        if not isinstance(pages, list) or any(not isinstance(x, int) or isinstance(x, bool) or x < 1 for x in pages):
            errors.append(f"{label}.source_pages 必须是正整数数组。")
        points = question.get("knowledge_points", [])
        if not isinstance(points, list):
            errors.append(f"{label}.knowledge_points 必须是数组。")
            points = []
        seen: set[tuple[str, str, str]] = set()
        for point_index, point in enumerate(points, 1):
            if not isinstance(point, dict) or set(point) != {"level_1", "level_2", "level_3"}:
                errors.append(f"{label}知识点[{point_index}]必须完整包含三级路径。")
                continue
            path = (point["level_1"], point["level_2"], point["level_3"])
            if not all(isinstance(x, str) and x.strip() for x in path):
                errors.append(f"{label}知识点[{point_index}]路径不能为空。")
            elif path not in catalog:
                errors.append(f"{label}包含目录中不存在的知识点：{' > '.join(path)}")
            elif path in seen:
                warnings.append(f"{label}重复标注知识点：{' > '.join(path)}")
            seen.add(path)
    return len(sources), len(questions)


def validate(zip_path: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    source_count = question_count = 0
    if not zip_path.is_file():
        return {"valid": False, "errors": [f"文件不存在：{zip_path}"], "warnings": []}
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                errors.append(f"压缩包文件数量超过上限 {MAX_FILES}。")
            if sum(item.file_size for item in infos) > MAX_BYTES:
                errors.append("压缩包解压后总大小超过 2 GB。")
            names = {item.filename for item in infos if not item.is_dir()}
            for name in names:
                if not safe_path(name):
                    errors.append(f"压缩包包含不安全路径：{name}")
            if "manifest.json" not in names:
                errors.append("ZIP 根目录缺少 manifest.json。")
            else:
                info = archive.getinfo("manifest.json")
                if info.file_size > MAX_MANIFEST_BYTES:
                    errors.append("manifest.json 超过 10 MB。")
                else:
                    try:
                        manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
                        source_count, question_count = validate_manifest(manifest, names, errors, warnings)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        errors.append(f"manifest.json 不是有效 UTF-8 JSON：{exc}")
    except (zipfile.BadZipFile, OSError) as exc:
        errors.append(f"文件不是有效 ZIP：{exc}")
    return {
        "valid": not errors,
        "source_count": source_count,
        "question_count": question_count,
        "errors": errors,
        "warnings": warnings,
        "sha256": digest,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python validate_package.py <题库包.zip>")
        return 2
    report = validate(Path(sys.argv[1]).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
