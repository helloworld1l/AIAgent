from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


SUPPORTED_DOC_TYPES = {
    ".md": "markdown",
    ".txt": "text",
}

DEFAULT_DOCS_DIR = Path(__file__).resolve().parent / "docs"


def load_file_documents(
    docs_dir: str | Path | None = None,
    start_id: int = 1_000_000,
    chunk_size: int = 480,
    chunk_overlap: int = 80,
) -> List[Dict[str, Any]]:
    root = Path(docs_dir) if docs_dir is not None else DEFAULT_DOCS_DIR
    if not root.exists() or not root.is_dir():
        return []

    documents: List[Dict[str, Any]] = []
    next_id = start_id
    for path in sorted(_iter_supported_files(root), key=lambda item: item.as_posix().lower()):
        content = _read_text_file(path)
        if not content.strip():
            continue

        title = _extract_title(path, content)
        doc_type = SUPPORTED_DOC_TYPES[path.suffix.lower()]
        source_file = _to_display_path(root, path)
        chunks = _chunk_text(content, max_chars=chunk_size, overlap_chars=chunk_overlap)
        for chunk_index, chunk in enumerate(chunks, start=1):
            documents.append(
                {
                    "id": next_id,
                    "text": f"title: {title}; source: {source_file}; content: {chunk}",
                    "payload": {
                        "type": "document",
                        "doc_type": doc_type,
                        "title": title,
                        "source_file": source_file,
                        "chunk_index": chunk_index,
                    },
                }
            )
            next_id += 1
    return documents


def _iter_supported_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_DOC_TYPES:
            yield path


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_title(path: Path, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
        if len(stripped) <= 80:
            return stripped
        break
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def _chunk_text(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
    if not paragraphs:
        return [normalized[:max_chars]]

    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)
    return chunks


def _split_long_text(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    parts: List[str] = []
    start = 0
    safe_overlap = max(0, min(overlap_chars, max_chars // 2))
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            parts.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - safe_overlap)
    return parts


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cleaned_lines = []
    for line in text.split("\n"):
        stripped = line.strip().lstrip("\ufeff")
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        cleaned_lines.append(stripped)
    normalized = "\n".join(cleaned_lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip()


def _to_display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root.parent.parent).as_posix()
    except Exception:
        try:
            return path.relative_to(root).as_posix()
        except Exception:
            return path.as_posix()
