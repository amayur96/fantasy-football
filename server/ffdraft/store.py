"""JSON persistence helpers with atomic writes and a small cache wrapper."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, TypeAdapter

log = logging.getLogger(__name__)
T = TypeVar("T")


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    if isinstance(obj, dict):
        return {str(k): _dump(v) for k, v in obj.items()}
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(_dump(obj), f, indent=2)
    os.replace(tmp, path)


def load_model(path: Path, model: type[T]) -> T | None:
    raw = read_json(path)
    if raw is None:
        return None
    return TypeAdapter(model).validate_python(raw)


def cached(path: Path, refresh: bool, loader: Callable[[], T], model: type[T]) -> tuple[T, bool]:
    """Return (value, from_cache). Loads from disk unless refresh or missing.

    If the loader fails but a stale cache exists, log the error and return the cache.
    """
    if not refresh:
        existing = load_model(path, model)
        if existing is not None:
            return existing, True
    try:
        value = loader()
    except Exception as exc:  # noqa: BLE001 - we want to fall back on any network/parse failure
        existing = load_model(path, model)
        if existing is not None:
            log.warning("Loader for %s failed (%s); using cached copy", path.name, exc)
            return existing, True
        raise
    write_json(path, value)
    return value, False
