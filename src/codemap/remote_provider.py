from __future__ import annotations

import ipaddress
import json
import math
from dataclasses import dataclass, field
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from codemap import __version__

MAX_RESPONSE_BYTES = 1_000_000
MAX_REQUEST_BYTES = 200_000
MAX_ERROR_BYTES = 8192
_SAFE_ERROR_CODES = frozenset({
    "client_signature_blocked", "model_permission_blocked_org", "model_permission_blocked_project",
})


class RemoteHTTPError(RuntimeError):
    """Expose status and an allowlisted diagnostic, never arbitrary remote text."""

    def __init__(self, status_code: int, reason: str | None = None):
        self.status_code = status_code
        self.reason = reason if reason in _SAFE_ERROR_CODES else None
        super().__init__(f"remote provider returned HTTP {status_code}")


def _forbidden_reason(error: HTTPError) -> str | None:
    if error.code != 403:
        return None
    try:
        body = error.read(MAX_ERROR_BYTES + 1)
        if len(body) > MAX_ERROR_BYTES:
            return None
        if body.strip() == b"error code: 1010":
            return "client_signature_blocked"
        record = json.loads(body)
        code = record["error"]["code"]
        if isinstance(code, str) and code in _SAFE_ERROR_CODES - {"client_signature_blocked"}:
            return code
    except (OSError, HTTPException, ValueError, KeyError, TypeError, RecursionError):
        pass
    return None


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward repository content or credentials to another destination.
        return None


def validate_endpoint(endpoint: str) -> None:
    try:
        if any(ord(c) <= 32 or ord(c) >= 127 for c in endpoint):
            raise ValueError
        parts = urlsplit(endpoint)
        if (not parts.hostname or parts.username is not None or parts.password is not None
                or parts.fragment or parts.query or parts.port == 0):
            raise ValueError
        if parts.scheme == "https":
            return
        # Plain HTTP is limited to literal loopback addresses, without DNS resolution.
        if parts.scheme == "http" and ipaddress.ip_address(parts.hostname).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("remote endpoint must use HTTPS (HTTP allowed only on literal loopback), without credentials, query, or fragment")


@dataclass(frozen=True)
class RemoteResponse:
    data: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class RemoteClient:
    endpoint: str = field(repr=False)
    access_key: str | None = field(default=None, repr=False)

    def post_json(self, payload: dict[str, Any], *, timeout_seconds: float) -> RemoteResponse:
        validate_endpoint(self.endpoint)
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
            raise ValueError("remote timeout must be finite and between 0 and 300 seconds")
        if self.access_key and any(not 33 <= ord(c) <= 126 for c in self.access_key):
            raise ValueError("remote authentication contains invalid characters")
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("remote request exceeds size limit")
        request = Request(self.endpoint, data=body, headers=_headers(self.access_key), method="POST")
        # Ambient proxies are not additional approved recipients of the payload.
        opener = build_opener(ProxyHandler({}), _NoRedirects())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                response_body = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            code = exc.code
            try:
                reason = _forbidden_reason(exc)
            finally:
                exc.close()
            raise RemoteHTTPError(code, reason) from None
        except TimeoutError:
            raise RuntimeError("remote provider request timed out") from None
        except (URLError, OSError, HTTPException, ValueError):
            raise RuntimeError("remote provider request failed") from None
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("remote provider response exceeds size limit")
        try:
            record = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise RuntimeError("remote provider returned an invalid JSON response") from None
        if not isinstance(record, dict):
            raise RuntimeError("remote provider returned an invalid JSON object")
        if "error" in record:
            raise RuntimeError("remote provider reported an error")
        return RemoteResponse(data=record)


def _headers(access_key: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": f"codemap/{__version__}",
    }
    if access_key:
        headers["Authorization"] = f"Bearer {access_key}"
    return headers
