"""Deterministic file classification and language detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileClassification:
    pipeline: str
    language: str
    mime: str
    is_supported_text: bool = True


PIPELINES_BY_EXT: dict[str, FileClassification] = {
    ".java": FileClassification("java", "java", "text/x-java"),
    ".md": FileClassification("markdown", "markdown", "text/markdown"),
    ".markdown": FileClassification("markdown", "markdown", "text/markdown"),
    ".html": FileClassification("html", "html", "text/html"),
    ".htm": FileClassification("html", "html", "text/html"),
    ".json": FileClassification("json", "json", "application/json"),
    ".yml": FileClassification("yaml", "yaml", "application/yaml"),
    ".yaml": FileClassification("yaml", "yaml", "application/yaml"),
    ".txt": FileClassification("text", "text", "text/plain"),
    ".rst": FileClassification("text", "rst", "text/plain"),
    ".py": FileClassification("code_generic", "python", "text/x-python"),
    ".js": FileClassification("code_generic", "javascript", "text/javascript"),
    ".ts": FileClassification("code_generic", "typescript", "text/typescript"),
    ".tsx": FileClassification("code_generic", "typescript", "text/typescript"),
    ".go": FileClassification("code_generic", "go", "text/x-go"),
    ".rs": FileClassification("code_generic", "rust", "text/x-rust"),
    ".c": FileClassification("code_generic", "c", "text/x-c"),
    ".cpp": FileClassification("code_generic", "cpp", "text/x-c++"),
    ".h": FileClassification("code_generic", "c", "text/x-c"),
    ".cs": FileClassification("code_generic", "csharp", "text/x-csharp"),
    ".kt": FileClassification("code_generic", "kotlin", "text/x-kotlin"),
}


def classify_file(path: Path, content: str) -> FileClassification:
    ext = path.suffix.lower()
    known = PIPELINES_BY_EXT.get(ext)
    if known is not None:
        return known

    head = content.lstrip()[:128]
    if head.startswith("#!"):
        if "python" in head:
            return FileClassification("code_generic", "python", "text/x-python")
        if "bash" in head or "sh" in head:
            return FileClassification("text", "shell", "text/x-shellscript")

    if "\x00" in content:
        return FileClassification(
            pipeline="binary_unsupported",
            language="binary",
            mime="application/octet-stream",
            is_supported_text=False,
        )

    return FileClassification("text", "text", "text/plain")

