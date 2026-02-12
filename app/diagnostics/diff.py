from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Number
from typing import Any

IGNORED_KEYS = {"as_of", "filters_hash"}


@dataclass(frozen=True)
class DiffItem:
    key: str
    demo: Any
    sis: Any


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in IGNORED_KEYS:
                continue
            normalized[str(key)] = _normalize(value[key])
        return normalized

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized_list = [_normalize(item) for item in value]
        if all(isinstance(item, Mapping) and "id" in item for item in normalized_list):
            return sorted(normalized_list, key=lambda item: str(item.get("id")))
        return normalized_list

    if isinstance(value, Number) and not isinstance(value, bool):
        return round(float(value), 2)

    return value


def normalize_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return _normalize(dict(payload or {}))


def _flatten(value: Any, *, path: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            flattened.update(_flatten(item, path=child_path))
        return flattened

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        flattened: dict[str, Any] = {}
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            flattened.update(_flatten(item, path=child_path))
        return flattened

    return {path: value}


def collect_differences(demo_payload: Mapping[str, Any], sis_payload: Mapping[str, Any], *, limit: int = 5) -> list[DiffItem]:
    demo_flat = _flatten(normalize_payload(demo_payload))
    sis_flat = _flatten(normalize_payload(sis_payload))

    keys = sorted(set(demo_flat) | set(sis_flat))
    differences: list[DiffItem] = []
    for key in keys:
        demo_value = demo_flat.get(key)
        sis_value = sis_flat.get(key)
        if demo_value != sis_value:
            differences.append(DiffItem(key=key, demo=demo_value, sis=sis_value))
            if len(differences) >= limit:
                break
    return differences
