#!/usr/bin/env python3
"""Create a standard question package ZIP and validate it."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from validate_package import safe_path, validate


def package_folder(source: Path, output: Path) -> dict:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"包目录不存在：{source}")
    if output.suffix.lower() != ".zip":
        raise ValueError("输出文件扩展名必须是 .zip。")
    if source in output.parents:
        raise ValueError("输出 ZIP 不能放在待打包目录内部。")
    if not (source / "manifest.json").is_file():
        raise ValueError("包目录根部缺少 manifest.json。")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    for path in files:
        if path.is_symlink():
            raise ValueError(f"不允许打包符号链接：{path}")
        relative = path.relative_to(source).as_posix()
        if not safe_path(relative):
            raise ValueError(f"不安全的包内路径：{relative}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"输出文件已存在，请换一个名称：{output}")
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, path.relative_to(source).as_posix())
        report = validate(output)
        if not report["valid"]:
            output.unlink(missing_ok=True)
        return report
    except Exception:
        output.unlink(missing_ok=True)
        raise


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: python package_folder.py <包目录> <输出.zip>")
        return 2
    try:
        report = package_folder(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
