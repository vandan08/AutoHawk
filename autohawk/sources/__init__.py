from __future__ import annotations

from typing import Any, Callable

from ..models import Job
from . import adzuna, greenhouse, lever, remoteok, remotive

# name -> fetch(source_config) -> list[Job]
REGISTRY: dict[str, Callable[[Any], list[Job]]] = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "remoteok": remoteok.fetch,
    "remotive": remotive.fetch,
    "adzuna": adzuna.fetch,
}


def fetch_all(sources_config: dict[str, Any]) -> dict[str, list[Job] | Exception]:
    """Fetch every configured source; a failing source never blocks the others."""
    results: dict[str, list[Job] | Exception] = {}
    for name, cfg in sources_config.items():
        fetcher = REGISTRY.get(name)
        if fetcher is None:
            results[name] = ValueError(f"unknown source '{name}'")
            continue
        try:
            results[name] = fetcher(cfg)
        except Exception as exc:  # network errors, schema drift, bad slugs
            results[name] = exc
    return results
