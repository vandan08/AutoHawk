from __future__ import annotations

from typing import Any

import requests

USER_AGENT = "AutoHawk/0.1 (personal job-search aggregator)"
TIMEOUT = 30


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    resp = requests.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()
