from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class FileLoadError(Exception):
    pass


@dataclass(frozen=True)
class TextFile:
    path: Path
    content: str
    line_count: int


def read_text_file(path: Path | str, *, max_bytes: int = 1_000_000) -> TextFile:
    file_path = Path(path)
    data = file_path.read_bytes()

    if len(data) > max_bytes:
        raise FileLoadError(f"File exceeds size limit: {file_path}")
    if b"\x00" in data:
        raise FileLoadError(f"File appears to be binary: {file_path}")

    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileLoadError(f"File is not valid UTF-8: {file_path}") from exc

    return TextFile(
        path=file_path,
        content=content,
        line_count=len(content.splitlines()),
    )
