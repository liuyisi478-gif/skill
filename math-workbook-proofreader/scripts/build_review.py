#!/usr/bin/env python3
"""Validate paired-document review data and build a portable HTML package."""

from __future__ import annotations

import argparse
import base64
import copy
import json
import math
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
    if not all(math.isfinite(v) for v in (x, y, width, height)) or min(x, y, width, height) < 0 or x + width > 1.000001 or y + height > 1.000001:
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
            target_key = (document_id, page, json.dumps(target.get("bbox"), sort_keys=True))
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


def concise_answers(run) -> list[dict]:
    """Display reviewed corrections without overwriting sealed independent work."""
    independent = run.mapped("independent")
    rechecks = run.mapped("recheck")
    result = []
    for qid, question in run.questions().items():
        original = independent.get(qid, {})
        recheck = rechecks.get(qid, {})
        corrected = recheck.get("corrected_independent_answer")
        use_correction = (recheck.get("status") == "ok" and
                          recheck.get("outcome") in ("cleared", "confirmed") and
                          isinstance(corrected, list) and bool(corrected) and
                          all(isinstance(a, dict) and isinstance(a.get("value"), str) and
                              isinstance(a.get("unit"), str) for a in corrected))
        answer = corrected if use_correction else original.get("answer", [])
        reviewed = recheck.get("status") == "ok" and recheck.get("outcome") in ("cleared", "confirmed")
        pending = recheck.get("outcome") == "manual" or (original.get("status") != "ok" and not reviewed)
        result.append({"id": qid, "targets": question["targets"], "answer": answer,
                       "corrected": use_correction,
                       "status": "missing" if not answer else "pending" if pending else "ready"})
    return result


def build(work_dir: Path, review_path: Path, output: Path, skill_root: Path,
          html_file: Path | None = None) -> None:
    if html_file is not None:
        html_file = html_file.resolve()
        if html_file.suffix.lower() != ".html":
            raise ValueError("交付文件必须使用 .html 扩展名。")
    if output.resolve() == work_dir.resolve() or work_dir.resolve().is_relative_to(output.resolve()):
        raise ValueError("输出目录不能等于或包含工作目录。")
    if any(output.resolve().is_relative_to(work_dir.resolve() / name) for name in ("body", "answer", "receipts", "packets")):
        raise ValueError("输出目录不能位于原稿资源或审计记录目录内。")
    manifest = load_json(work_dir / "manifest.json")
    review = load_json(review_path)
    coverage = None
    independent = []
    concise = []
    if (work_dir / "audit-state.json").exists() or manifest.get("audit_required"):
        from audit_run import Run
        run = Run(work_dir)
        # Export is derived from receipts. A manually edited review cannot bypass the gate.
        expected = run.export(draft=bool(review.get("draft")))
        if review != expected:
            raise ValueError("review.json 与阶段记录不符，请使用 audit_run.py export 重新生成。")
        coverage = run.coverage()
        independent = run.rows("independent")
        concise = concise_answers(run)
    issues = validate(manifest, review)
    review["issues"] = issues

    for document in manifest["documents"]:
        for page in document["pages"]:
            image = work_dir / str(page.get("work_image", ""))
            if not image.is_file():
                raise ValueError(f"缺少页面图片：{image}")

    output.mkdir(parents=True, exist_ok=True)
    output_pages = output / "pages"
    if not output_pages.resolve().is_relative_to(output.resolve()) or output_pages.resolve() == output.resolve():
        raise ValueError("页面输出目录解析后超出输出根目录。")
    if output_pages.exists():
        shutil.rmtree(output_pages)
    for document in manifest["documents"]:
        shutil.copytree(
            work_dir / document["id"] / "pages",
            output_pages / document["id"],
        )

    asset_root = skill_root / "assets" / "viewer"
    for name in ("styles.css", "app.js"):
        source = asset_root / name
        if not source.is_file():
            raise ValueError(f"Skill 缺少网页资源：{source}")
        shutil.copy2(source, output / name)

    template_path = asset_root / "index.html"
    if not template_path.is_file():
        raise ValueError(f"Skill 缺少网页资源：{template_path}")
    template = template_path.read_text(encoding="utf-8")
    (output / "index-folder.html").write_text(template, encoding="utf-8")

    payload = {
        "manifest": manifest,
        "review": review,
        "coverage": coverage,
        "independent_answers": independent,
        "concise_answers": concise,
        "notice": "本校对结果由 AI 辅助生成，可能存在遗漏、误判或题答配对偏差，数学公式及结论请人工复核。",
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (output / "review-data.js").write_text(
        "window.REVIEW_DATA = " + serialized + ";\n", encoding="utf-8"
    )

    standalone_payload = copy.deepcopy(payload)
    for document in standalone_payload["manifest"]["documents"]:
        for page in document["pages"]:
            image_path = work_dir / str(page.get("work_image", ""))
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            page["image"] = f"data:image/png;base64,{encoded}"

    standalone_data = json.dumps(
        standalone_payload, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    styles = (asset_root / "styles.css").read_text(encoding="utf-8")
    app = (asset_root / "app.js").read_text(encoding="utf-8")
    standalone_html = template.replace(
        '<link rel="stylesheet" href="styles.css">',
        f"<style>\n{styles}\n</style>",
    ).replace(
        '  <script src="review-data.js"></script>\n  <script src="app.js"></script>',
        f"  <script>window.REVIEW_DATA = {standalone_data};</script>\n"
        f"  <script>\n{app}\n  </script>",
    )
    (output / "index.html").write_text(standalone_html, encoding="utf-8")
    if html_file is not None:
        html_file.parent.mkdir(parents=True, exist_ok=True)
        if html_file != (output / "index.html").resolve():
            shutil.copy2(output / "index.html", html_file)

    counts = {kind: sum(1 for item in issues if item["kind"] == kind) for kind in KINDS}
    cross_count = sum(
        1 for item in issues if len({target["document"] for target in item["targets"]}) > 1
    )
    print(f"已生成单文件校对稿：{output / 'index.html'}")
    print(f"已保留文件夹版：{output / 'index-folder.html'}")
    print(
        f"共 {len(issues)} 条：确定错误 {counts['confirmed']}，疑似问题 {counts['suspected']}，"
        f"优化建议 {counts['suggestion']}，题答关联 {cross_count}。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成正文与答案配对的静态 HTML 校对稿。")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--html-file", type=Path, help="仅将单文件 HTML 复制到用户交付位置；资源留在 --output 工作目录。")
    args = parser.parse_args()
    try:
        build(
            args.work_dir.resolve(),
            args.review.resolve(),
            args.output.resolve(),
            Path(__file__).resolve().parent.parent,
            args.html_file,
        )
    except Exception as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
