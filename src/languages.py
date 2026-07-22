from pathlib import Path


EXTENSION_LANGUAGES = {
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".md": "markdown",
    ".py": "python",
    ".ts": "typescript",
    ".txt": "text",
}


def language_for_path(path: Path) -> str:
    return EXTENSION_LANGUAGES.get(path.suffix.lower(), "text")
