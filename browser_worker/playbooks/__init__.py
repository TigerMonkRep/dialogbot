"""Deterministic playbooks, one module per booking engine. `get(engine)` returns the module or None."""
from __future__ import annotations

from importlib import import_module

# engine key -> module name. Add engine no. 2 here (see browser_worker/README.md).
REGISTRY = {"onlinebooq": "onlinebooq"}


def get(engine: str):
    mod = REGISTRY.get(engine)
    return import_module(f"{__name__}.{mod}") if mod else None


def engines() -> list[str]:
    return sorted(REGISTRY)
