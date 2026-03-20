"""Count lines of code for the current project.

Examples:
    python tools/count_loc.py
    python tools/count_loc.py --include-generated
    python tools/count_loc.py --extensions .py,.ps1,.html
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CODE_EXTENSIONS = (
    ".py",
    ".ps1",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".bat",
)

COMMON_EXCLUDED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}

GENERATED_DIRS = {
    "generated_builds",
    "generated_models",
}


@dataclass(frozen=True)
class FileStat:
    path: Path
    total_lines: int
    non_empty_lines: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计当前项目代码行数")
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="项目根目录，默认自动定位到当前仓库根目录",
    )
    parser.add_argument(
        "--extensions",
        default=",".join(DEFAULT_CODE_EXTENSIONS),
        help="要统计的扩展名，逗号分隔，例如 .py,.ps1,.html",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="是否包含 generated_builds、generated_models 等生成目录",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="显示非空行数最多的前 N 个文件，默认 20",
    )
    return parser.parse_args()


def normalize_extensions(raw_extensions: str) -> tuple[str, ...]:
    extensions: list[str] = []
    for item in raw_extensions.split(","):
        extension = item.strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        extensions.append(extension)
    return tuple(dict.fromkeys(extensions))


def should_skip_file(path: Path, root: Path, excluded_dirs: set[str]) -> bool:
    relative_parts = path.relative_to(root).parts[:-1]
    return any(part in excluded_dirs for part in relative_parts)


def count_file_lines(path: Path) -> FileStat:
    total_lines = 0
    non_empty_lines = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            total_lines += 1
            if line.strip():
                non_empty_lines += 1
    return FileStat(path=path, total_lines=total_lines, non_empty_lines=non_empty_lines)


def collect_file_stats(root: Path, extensions: Iterable[str], include_generated: bool) -> list[FileStat]:
    extension_set = {extension.lower() for extension in extensions}
    excluded_dirs = set(COMMON_EXCLUDED_DIRS)
    if not include_generated:
        excluded_dirs.update(GENERATED_DIRS)

    file_stats: list[FileStat] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extension_set:
            continue
        if should_skip_file(path, root, excluded_dirs):
            continue
        file_stats.append(count_file_lines(path))
    return file_stats


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def format_row(row: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

    separator = "  ".join("-" * width for width in widths)
    content = [format_row(headers), separator]
    content.extend(format_row(row) for row in rows)
    return "\n".join(content)


def print_report(root: Path, file_stats: list[FileStat], extensions: tuple[str, ...], include_generated: bool, top: int) -> None:
    total_lines = sum(item.total_lines for item in file_stats)
    non_empty_lines = sum(item.non_empty_lines for item in file_stats)

    by_extension: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "total": 0, "non_empty": 0})
    for item in file_stats:
        current = by_extension[item.path.suffix.lower()]
        current["files"] += 1
        current["total"] += item.total_lines
        current["non_empty"] += item.non_empty_lines

    extension_rows = [
        [
            extension,
            str(values["files"]),
            str(values["total"]),
            str(values["non_empty"]),
        ]
        for extension, values in sorted(by_extension.items(), key=lambda item: (-item[1]["non_empty"], item[0]))
    ]

    top_rows = [
        [
            str(item.non_empty_lines),
            str(item.total_lines),
            item.path.relative_to(root).as_posix(),
        ]
        for item in sorted(file_stats, key=lambda current: (-current.non_empty_lines, str(current.path)))[:top]
    ]

    excluded_dirs = sorted(COMMON_EXCLUDED_DIRS if include_generated else COMMON_EXCLUDED_DIRS | GENERATED_DIRS)

    print(f"项目根目录: {root}")
    print(f"统计扩展名: {', '.join(extensions)}")
    print(f"排除目录: {', '.join(excluded_dirs)}")
    print(f"扫描文件数: {len(file_stats)}")
    print()
    print("汇总:")
    print(f"- 总行数: {total_lines}")
    print(f"- 非空行数: {non_empty_lines}")

    if extension_rows:
        print()
        print("按扩展名统计:")
        print(format_table(["扩展名", "文件数", "总行数", "非空行数"], extension_rows))

    if top_rows:
        print()
        print(f"非空行数 Top {min(top, len(top_rows))} 文件:")
        print(format_table(["非空行", "总行数", "文件"], top_rows))


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    extensions = normalize_extensions(args.extensions)

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"无效项目目录: {root}")
    if not extensions:
        raise SystemExit("至少需要提供一个扩展名")

    file_stats = collect_file_stats(root=root, extensions=extensions, include_generated=args.include_generated)
    print_report(
        root=root,
        file_stats=file_stats,
        extensions=extensions,
        include_generated=args.include_generated,
        top=max(args.top, 0),
    )


if __name__ == "__main__":
    main()
