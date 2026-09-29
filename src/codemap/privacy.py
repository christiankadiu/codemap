import re
from pathlib import PurePosixPath

PRIVACY_VERSION = 4
_SENSITIVE = re.compile(
    r"^(?:\.env(?:\..*)?|(?:secrets?|credentials?|tokens?)(?:\..*)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)(?:\..*)?|PROJECT_CONTEXT\.md|"
    r".*\.(?:pem|key|p12|pfx|keystore|jks)|\.netrc|\.npmrc|\.pypirc)$", re.I
)
_KEY = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)", re.S)
_SECRET_NAME = (
    r"(?:[A-Za-z][A-Za-z0-9]*[_-])*"
    r"(?:api[_-]?key|access[_-]?key|private[_-]?key|secret(?:[_-]?key)?|"
    r"password|passwd|token|credential)"
)
_MULTILINE_SECRET = re.compile(
    r"([\"']?\b" + _SECRET_NAME + r"[\"']?\s*[:=]\s*)(\"\"\"|''')(.*?)(?:\2|\Z)",
    re.I | re.S,
)
_ASSIGNMENT = re.compile(
    r"([\"']?\b" + _SECRET_NAME + r"[\"']?\s*[:=]\s*)"
    r"([\"'])((?:\\[^\r\n]|(?!\2)[^\\\r\n])*)\2", re.I
)
_BARE_SECRET = re.compile(
    r"(\b" + _SECRET_NAME + r"\s*[:=][ \t]*)"
    r"(?![\"'\s])[^\s,;}]+", re.I | re.M
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                    r"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9_-]{20,})\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HOME = re.compile(r"(?:/(?:home|Users)/[^/\s\"']+|[A-Za-z]:\\Users\\[^\\\s\"']+)")
_URL_CREDENTIAL = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def sensitive_path(value: str) -> bool:
    return any(_SENSITIVE.fullmatch(part) for part in PurePosixPath(value).parts)


def safe_relative_path(value: str) -> bool:
    if not isinstance(value, str):
        return False
    path = PurePosixPath(value)
    return (bool(value) and value != "." and not path.is_absolute() and ".." not in path.parts
            and "\\" not in value and ":" not in value
            and not _CONTROL.search(value) and "\n" not in value and "\r" not in value)


def redact(text: str) -> str:
    # Strip invisible controls first so they cannot hide a secret from matching.
    text = _CONTROL.sub("", text)
    text = _KEY.sub(lambda m: "\n".join("[REDACTED PRIVATE KEY]" for _ in m[0].split("\n")), text)
    text = _MULTILINE_SECRET.sub(
        lambda m: m[1] + m[2] + "[REDACTED]" + "\n" * m[3].count("\n") + m[2], text
    )
    text = _ASSIGNMENT.sub(lambda m: m[1] + m[2] + "[REDACTED]" + m[2], text)
    text = _BARE_SECRET.sub(lambda m: m[1] + "[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _TOKEN.sub("[REDACTED TOKEN]", text)
    text = _EMAIL.sub("[REDACTED EMAIL]", text)
    text = _HOME.sub("[REDACTED HOME]", text)
    text = _URL_CREDENTIAL.sub(r"\1[REDACTED]@", text)
    return text
