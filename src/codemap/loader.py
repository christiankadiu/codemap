from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codemap.scanner import read_source_bytes


class FileLoadError(Exception):
    pass


@dataclass(frozen=True)
class TextFile:
    path: Path
    content: str
    line_count: int


def read_text_file(path: Path | str, *, max_bytes: int = 1_000_000) -> TextFile:
    file_path = Path(path)
    try:
        data = read_source_bytes(file_path, max_bytes)
    except (OSError, ValueError) as exc:
        raise FileLoadError("source file could not be read safely") from exc

    if len(data) > max_bytes:
        raise FileLoadError("source file exceeds size limit")
    if b"\x00" in data:
        raise FileLoadError("source file appears to be binary")

    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileLoadError("source file is not valid UTF-8") from None

    return TextFile(
        path=file_path,
        content=content,
        line_count=len(content.splitlines()),
    )
