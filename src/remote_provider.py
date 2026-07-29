from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class RemoteResponse:
    data: dict[str, Any]


@dataclass(frozen=True)
class RemoteClient:
    endpoint: str
    access_key: str | None = None

    def post_json(
        self,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> RemoteResponse:
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=_headers(self.access_key),
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read()
        except HTTPError as exc:
            raise RuntimeError(f"remote provider returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("remote provider request failed") from exc
        except TimeoutError as exc:
            raise RuntimeError("remote provider request timed out") from exc

        try:
            record = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("remote provider returned an invalid JSON response") from exc

        if not isinstance(record, dict):
            raise RuntimeError("remote provider returned an invalid JSON object")

        return RemoteResponse(data=record)


def _headers(access_key: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    if access_key:
        headers["Authorization"] = f"Bearer {access_key}"

    return headers
