from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.models.domain import MaterialSource, StudyGraph

IGNORED_DIRS = frozenset({
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
    "vendor",
})

TEXT_EXTENSIONS = frozenset({
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp",
    ".go", ".rs", ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".kts", ".scala", ".swift", ".rb", ".php", ".cs",
    ".sh", ".bash", ".zsh", ".fish", ".ps1",
    ".sql", ".proto", ".graphql", ".gql", ".thrift",
    ".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env.example",
    ".xml", ".html", ".htm", ".css", ".scss", ".less",
    ".cmake", ".mk", ".gradle", ".dockerfile",
})

TEXT_FILENAMES = frozenset({
    "README", "LICENSE", "Makefile", "Dockerfile", "CMakeLists.txt",
    "go.mod", "go.sum", "Cargo.toml", "pyproject.toml", "package.json",
})

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB for text/code files
MAX_PDF_BYTES = 40 * 1024 * 1024  # 40 MiB for PDF files
MAX_LIST_ENTRIES = 200
MAX_SEARCH_MATCHES = 40
MAX_SLICE_LINES = 240
MAX_PDF_PAGES_PER_READ = 6


class MaterialError(ValueError):
    pass


def _is_supported_text_file(path: Path) -> bool:
    if path.name in TEXT_FILENAMES:
        return True
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    return False


def _is_pdf_file(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def _resolve_root(source: MaterialSource) -> Path:
    root = Path(source.path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise MaterialError(f"Material folder does not exist or is not a directory: {source.label} ({source.path})")
    return root


def _resolve_confined_path(root: Path, relative_path: str) -> Path:
    cleaned = relative_path.strip().lstrip("/")
    if not cleaned:
        return root
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise MaterialError("Requested path escapes the bound material folder.") from exc
    return candidate


def _find_source(graph: StudyGraph, source_id: str | None) -> list[MaterialSource]:
    if not graph.material_sources:
        raise MaterialError("This graph has no bound local material folders.")
    if source_id is None:
        return list(graph.material_sources)
    match = next((s for s in graph.material_sources if s.id == source_id), None)
    if match is None:
        raise MaterialError(f"Material source not found: {source_id}")
    return [match]


def _extract_pdf_pages(path: Path) -> list[str]:
    if path.stat().st_size > MAX_PDF_BYTES:
        raise MaterialError(f"PDF file exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB limit.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise MaterialError("PDF reading requires pypdf to be installed in the Clew backend environment.") from exc
    try:
        reader = PdfReader(str(path))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise MaterialError(f"Could not read PDF file {path.name}: {exc}") from exc


class MaterialService:
    """Strictly read-only, root-confined reader for bound local repos, docs, and PDFs."""

    def validate_folder_path(self, raw_path: str) -> Path:
        cleaned = raw_path.strip()
        if not cleaned:
            raise MaterialError("Material folder path is required.")
        resolved = Path(cleaned).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise MaterialError(f"Folder not found: {cleaned}")
        return resolved

    def list_files(
        self,
        graph: StudyGraph,
        *,
        source_id: str | None = None,
        subpath: str = "",
        max_depth: int = 3,
        limit: int = MAX_LIST_ENTRIES,
    ) -> dict[str, Any]:
        sources = _find_source(graph, source_id)
        bounded_depth = max(1, min(max_depth, 6))
        bounded_limit = max(1, min(limit, MAX_LIST_ENTRIES))
        entries: list[dict[str, Any]] = []
        truncated = False

        for source in sources:
            root = _resolve_root(source)
            start = _resolve_confined_path(root, subpath) if subpath else root
            if not start.exists():
                if source_id is not None:
                    raise MaterialError(f"Subpath not found in {source.label}: {subpath}")
                continue
            if start.is_file():
                entries.append({
                    "source_id": source.id,
                    "source_label": source.label,
                    "path": start.relative_to(root).as_posix(),
                    "kind": "pdf" if _is_pdf_file(start) else "file",
                    "size_bytes": start.stat().st_size,
                })
                continue

            start_depth = len(start.parts)
            for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
                current = Path(dirpath)
                depth = len(current.parts) - start_depth
                dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.startswith("."))
                if depth >= bounded_depth:
                    dirnames[:] = []
                for filename in sorted(filenames):
                    if filename.startswith("."):
                        continue
                    file_path = current / filename
                    if file_path.is_symlink():
                        try:
                            file_path.resolve().relative_to(root)
                        except ValueError:
                            continue
                    if not (_is_supported_text_file(file_path) or _is_pdf_file(file_path)):
                        continue
                    rel = file_path.relative_to(root).as_posix()
                    entries.append({
                        "source_id": source.id,
                        "source_label": source.label,
                        "path": rel,
                        "kind": "pdf" if _is_pdf_file(file_path) else "file",
                        "size_bytes": file_path.stat().st_size,
                    })
                    if len(entries) >= bounded_limit:
                        truncated = True
                        break
                if truncated:
                    break
            if truncated:
                break

        return {
            "sources": [{"id": s.id, "label": s.label, "path": s.path} for s in sources],
            "entries": entries,
            "truncated": truncated,
        }

    def search_text(
        self,
        graph: StudyGraph,
        query: str,
        *,
        source_id: str | None = None,
        subpath: str = "",
        limit: int = MAX_SEARCH_MATCHES,
    ) -> dict[str, Any]:
        needle = query.strip()
        if not needle:
            raise MaterialError("Search query cannot be empty.")
        needle_lower = needle.lower()
        sources = _find_source(graph, source_id)
        bounded_limit = max(1, min(limit, MAX_SEARCH_MATCHES))
        matches: list[dict[str, Any]] = []
        truncated = False

        for source in sources:
            root = _resolve_root(source)
            start = _resolve_confined_path(root, subpath) if subpath else root
            if not start.exists():
                continue
            files_to_scan: list[Path] = []
            if start.is_file():
                files_to_scan.append(start)
            else:
                for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
                    dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.startswith("."))
                    current = Path(dirpath)
                    for filename in sorted(filenames):
                        if filename.startswith("."):
                            continue
                        file_path = current / filename
                        if file_path.is_symlink():
                            try:
                                file_path.resolve().relative_to(root)
                            except ValueError:
                                continue
                        if _is_supported_text_file(file_path) or _is_pdf_file(file_path):
                            files_to_scan.append(file_path)

            for file_path in files_to_scan:
                rel = file_path.relative_to(root).as_posix()
                if _is_pdf_file(file_path):
                    try:
                        pages = _extract_pdf_pages(file_path)
                    except MaterialError:
                        continue
                    for page_num, text in enumerate(pages, start=1):
                        if needle_lower in text.lower():
                            snippet_lines = [line.strip() for line in text.splitlines() if needle_lower in line.lower()]
                            snippet = snippet_lines[0][:240] if snippet_lines else text.strip()[:240]
                            matches.append({
                                "source_id": source.id,
                                "source_label": source.label,
                                "path": rel,
                                "page": page_num,
                                "snippet": snippet,
                            })
                            if len(matches) >= bounded_limit:
                                truncated = True
                                break
                else:
                    try:
                        if file_path.stat().st_size > MAX_FILE_BYTES:
                            continue
                        raw = file_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    for line_no, line in enumerate(raw.splitlines(), start=1):
                        if needle_lower in line.lower():
                            matches.append({
                                "source_id": source.id,
                                "source_label": source.label,
                                "path": rel,
                                "line": line_no,
                                "snippet": line.strip()[:240],
                            })
                            if len(matches) >= bounded_limit:
                                truncated = True
                                break
                if truncated:
                    break
            if truncated:
                break

        return {"query": needle, "matches": matches, "truncated": truncated}

    def read_slice(
        self,
        graph: StudyGraph,
        *,
        source_id: str | None,
        path: str,
        start: int = 1,
        end: int | None = None,
    ) -> dict[str, Any]:
        sources = _find_source(graph, source_id)
        resolved_source: MaterialSource | None = None
        target: Path | None = None
        target_root: Path | None = None
        for source in sources:
            root = _resolve_root(source)
            candidate = _resolve_confined_path(root, path)
            if candidate.exists() and candidate.is_file():
                resolved_source = source
                target = candidate
                target_root = root
                break
        if resolved_source is None or target is None or target_root is None:
            raise MaterialError(f"File not found in bound material folders: {path}")

        rel = target.relative_to(target_root).as_posix()
        if _is_pdf_file(target):
            pages = _extract_pdf_pages(target)
            total_pages = len(pages)
            start_page = max(1, start)
            end_page = min(total_pages, end if end is not None else start_page + MAX_PDF_PAGES_PER_READ - 1)
            end_page = min(end_page, start_page + MAX_PDF_PAGES_PER_READ - 1)
            selected = [
                {"page": p, "text": pages[p - 1][:8000]}
                for p in range(start_page, end_page + 1)
                if 1 <= p <= total_pages
            ]
            return {
                "source_id": resolved_source.id,
                "source_label": resolved_source.label,
                "path": rel,
                "kind": "pdf",
                "total_pages": total_pages,
                "start_page": start_page,
                "end_page": end_page,
                "pages": selected,
            }

        if not _is_supported_text_file(target):
            raise MaterialError(f"Unsupported binary or non-text file: {rel}")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise MaterialError(f"File exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB text limit: {rel}")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        start_line = max(1, start)
        end_line = min(total_lines, end if end is not None else start_line + MAX_SLICE_LINES - 1)
        end_line = min(end_line, start_line + MAX_SLICE_LINES - 1)
        numbered = "\n".join(f"{idx}: {lines[idx - 1]}" for idx in range(start_line, end_line + 1) if 1 <= idx <= total_lines)
        return {
            "source_id": resolved_source.id,
            "source_label": resolved_source.label,
            "path": rel,
            "kind": "text",
            "total_lines": total_lines,
            "start_line": start_line,
            "end_line": end_line,
            "content": numbered,
        }
