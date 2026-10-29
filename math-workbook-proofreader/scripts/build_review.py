#!/usr/bin/env python3
"""Validate review data and build a portable static HTML proofing package."""

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


def validate_bbox(value: object, issue_id: int) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"批注 {issue_id} 的 bbox 必须是对象或 null。")
    keys = ("x", "y", "width", "height")
    if any(key not in value for key in keys):
        raise ValueError(f"批注 {issue_id} 的 bbox 缺少字段。")
    try:
        x, y, width, height = (float(value[key]) for key in keys)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"批注 {issue_id} 的 bbox 必须是数字。") from exc
    if min(x, y, width, height) < 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError(f"批注 {issue_id} 的 bbox 必须位于页面 0-1 范围内。")
    if width == 0 or height == 0:
        raise ValueError(f"批注 {issue_id} 的 bbox 宽高必须大于 0。")


def validate(manifest: dict, review: dict) -> list[dict]:
    page_count = manifest.get("page_count")
    if not isinstance(page_count, int) or page_count < 1:
        raise ValueError("manifest.json 中的 page_count 无效。")
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
        page = issue.get("page")
        if not isinstance(page, int) or not 1 <= page <= page_count:
            raise ValueError(f"批注 {issue_id} 的页码超出范围。")
        if issue.get("kind") not in KINDS:
            raise ValueError(f"批注 {issue_id} 的 kind 必须是 confirmed、suspected 或 suggestion。")
        for key in ("category", "title", "detail", "suggestion"):
            if key not in issue or not isinstance(issue[key], str):
                raise ValueError(f"批注 {issue_id} 缺少字符串字段 {key}。")
        validate_bbox(issue.get("bbox"), issue_id)
    return sorted(issues, key=lambda item: (item["page"], item["id"]))


def build(work_dir: Path, review_path: Path, output: Path, skill_root: Path) -> None:
    manifest = load_json(work_dir / "manifest.json")
    review = load_json(review_path)
    issues = validate(manifest, review)
    review["issues"] = issues

    page_entries = manifest.get("pages")
    if not isinstance(page_entries, list) or len(page_entries) != manifest["page_count"]:
        raise ValueError("manifest.json 的 pages 数量与 page_count 不一致。")
    for page in page_entries:
        image = work_dir / str(page.get("image", ""))
        if not image.is_file():
            raise ValueError(f"缺少页面图片：{image}")

    output.mkdir(parents=True, exist_ok=True)
    output_pages = output / "pages"
    if output_pages.exists():
        shutil.rmtree(output_pages)
    shutil.copytree(work_dir / "pages", output_pages)

    asset_root = skill_root / "assets" / "viewer"
    for name in ("index.html", "styles.css", "app.js"):
        source = asset_root / name
        if not source.is_file():
            raise ValueError(f"Skill 缺少网页资源：{source}")
        shutil.copy2(source, output / name)

    payload = {
        "manifest": manifest,
        "review": review,
        "notice": "本校对结果由 AI 辅助生成，可能存在遗漏或误判，数学公式及结论请人工复核。",
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (output / "review-data.js").write_text(
        "window.REVIEW_DATA = " + serialized + ";\n", encoding="utf-8"
    )

    counts = {kind: sum(1 for item in issues if item["kind"] == kind) for kind in KINDS}
    print(f"已生成：{output / 'index.html'}")
    print(
        f"共 {len(issues)} 条：确定错误 {counts['confirmed']}，"
        f"疑似问题 {counts['suspected']}，优化建议 {counts['suggestion']}。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成数学教辅静态 HTML 校对稿。")
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
