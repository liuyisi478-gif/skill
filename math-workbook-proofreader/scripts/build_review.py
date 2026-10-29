#!/usr/bin/env python3
"""Validate paired-document review data and build a portable HTML package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

KINDS = {"confirmed", "suspected", "suggestion"}


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式错误：{path} 第 {exc.lineno} 行") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象：{path}")
    return value


def validate_bbox(value: object, issue_id: int, target_index: int) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"批注 {issue_id} 的第 {target_index} 个 bbox 必须是对象或 null。")
    keys = ("x", "y", "width", "height")
    if any(key not in value for key in keys):
        raise ValueError(f"批注 {issue_id} 的第 {target_index} 个 bbox 缺少字段。")
    try:
        x, y, width, height = (float(value[key]) for key in keys)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"批注 {issue_id} 的 bbox 必须是数字。") from exc
    if min(x, y, width, height) < 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError(f"批注 {issue_id} 的 bbox 必须位于页面 0-1 范围内。")
    if width == 0 or height == 0:
        raise ValueError(f"批注 {issue_id} 的 bbox 宽高必须大于 0。")


def document_index(manifest: dict) -> dict[str, dict]:
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("manifest.json 必须包含 documents 数组。")
    index = {}
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("id"), str):
            raise ValueError("manifest.json 中存在无效文档。")
        document_id = document["id"]
        if document_id in index:
            raise ValueError(f"manifest.json 文档 id 重复：{document_id}")
        page_count = document.get("page_count")
        pages = document.get("pages")
        if not isinstance(page_count, int) or page_count < 1:
            raise ValueError(f"文档 {document_id} 的 page_count 无效。")
        if not isinstance(pages, list) or len(pages) != page_count:
            raise ValueError(f"文档 {document_id} 的 pages 数量不正确。")
        index[document_id] = document
    return index


def validate(manifest: dict, review: dict) -> list[dict]:
    documents = document_index(manifest)
    issues = review.get("issues")
    if not isinstance(issues, list):
        raise ValueError("review.json 必须包含 issues 数组。")
    seen: set[int] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("issues 中的每一项都必须是对象。")
        issue_id = issue.get("id")
        if not isinstance(issue_id, int) or issue_id < 1 or issue_id in seen:
            raise ValueError(f"批注 id 无效或重复：{issue_id!r}")
        seen.add(issue_id)
        if issue.get("kind") not in KINDS:
            raise ValueError(f"批注 {issue_id} 的 kind 无效。")
        for key in ("category", "questionId", "title", "detail", "suggestion"):
            if key not in issue or not isinstance(issue[key], str):
                raise ValueError(f"批注 {issue_id} 缺少字符串字段 {key}。")
        targets = issue.get("targets")
        if not isinstance(targets, list) or not targets:
            raise ValueError(f"批注 {issue_id} 必须至少包含一个 target。")
        seen_targets: set[tuple[str, int]] = set()
        for target_index, target in enumerate(targets, start=1):
            if not isinstance(target, dict):
                raise ValueError(f"批注 {issue_id} 的 target 必须是对象。")
            document_id = target.get("document")
            page = target.get("page")
            if document_id not in documents:
                raise ValueError(f"批注 {issue_id} 引用了未知文档：{document_id}")
            if not isinstance(page, int) or not 1 <= page <= documents[document_id]["page_count"]:
                raise ValueError(f"批注 {issue_id} 在文档 {document_id} 中的页码无效。")
            target_key = (document_id, page)
            if target_key in seen_targets:
                raise ValueError(f"批注 {issue_id} 重复引用 {document_id} 第 {page} 页。")
            seen_targets.add(target_key)
            validate_bbox(target.get("bbox"), issue_id, target_index)
    return sorted(
        issues,
        key=lambda item: (
            item["targets"][0]["document"] != "body",
            item["targets"][0]["page"],
            item["id"],
        ),
    )


def build(work_dir: Path, review_path: Path, output: Path, skill_root: Path) -> None:
    manifest = load_json(work_dir / "manifest.json")
    review = load_json(review_path)
    issues = validate(manifest, review)
    review["issues"] = issues

    for document in manifest["documents"]:
        for page in document["pages"]:
            image = work_dir / str(page.get("work_image", ""))
            if not image.is_file():
                raise ValueError(f"缺少页面图片：{image}")

    output.mkdir(parents=True, exist_ok=True)
    output_pages = output / "pages"
    if output_pages.exists():
        shutil.rmtree(output_pages)
    for document in manifest["documents"]:
        shutil.copytree(
            work_dir / document["id"] / "pages",
            output_pages / document["id"],
        )

    asset_root = skill_root / "assets" / "viewer"
    for name in ("index.html", "styles.css", "app.js"):
        source = asset_root / name
        if not source.is_file():
            raise ValueError(f"Skill 缺少网页资源：{source}")
        shutil.copy2(source, output / name)

    payload = {
        "manifest": manifest,
        "review": review,
        "notice": "本校对结果由 AI 辅助生成，可能存在遗漏、误判或题答配对偏差，数学公式及结论请人工复核。",
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (output / "review-data.js").write_text(
        "window.REVIEW_DATA = " + serialized + ";\n", encoding="utf-8"
    )

    counts = {kind: sum(1 for item in issues if item["kind"] == kind) for kind in KINDS}
    cross_count = sum(
        1 for item in issues if len({target["document"] for target in item["targets"]}) > 1
    )
    print(f"已生成：{output / 'index.html'}")
    print(
        f"共 {len(issues)} 条：确定错误 {counts['confirmed']}，疑似问题 {counts['suspected']}，"
        f"优化建议 {counts['suggestion']}，题答关联 {cross_count}。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成正文与答案配对的静态 HTML 校对稿。")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        build(
            args.work_dir.resolve(),
            args.review.resolve(),
            args.output.resolve(),
            Path(__file__).resolve().parent.parent,
        )
    except Exception as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
