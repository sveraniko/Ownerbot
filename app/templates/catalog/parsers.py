from __future__ import annotations

import json
import re
from typing import Any

_MAX_IDS = 200


def parse_ids(text: str) -> list[str]:
    ids = [item.strip() for item in re.split(r"[\s,]+", text) if item.strip()]
    if not ids:
        raise ValueError("Нужно передать хотя бы один ID.")
    if len(ids) > _MAX_IDS:
        raise ValueError(f"Слишком много ID: максимум {_MAX_IDS}.")
    return ids


def parse_percent_1_95(text: str) -> int:
    value = int(text.strip())
    if value < 1 or value > 95:
        raise ValueError("Процент скидки должен быть от 1 до 95.")
    return value


def parse_stock_1_9999(text: str) -> int:
    value = int(text.strip())
    if value < 1 or value > 9999:
        raise ValueError("N должен быть в диапазоне 1..9999.")
    return value


def parse_json_or_kv(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise ValueError("Нужно передать хотя бы одно обновление настройки.")
    if raw.startswith("{"):
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("JSON должен быть объектом.")
        return obj

    result: dict[str, Any] = {}
    for chunk in [item.strip() for item in raw.split(",") if item.strip()]:
        if "=" not in chunk:
            raise ValueError("Формат: key=value, key2=value2")
        key, value = [part.strip() for part in chunk.split("=", 1)]
        lowered = value.lower()
        if lowered in {"true", "false"}:
            parsed: Any = lowered == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = value
        result[key] = parsed
    return result


def parse_input_value(parser_name: str, text: str) -> Any:
    if parser_name == "ids":
        return parse_ids(text)
    if parser_name == "percent_1_95":
        return parse_percent_1_95(text)
    if parser_name == "stock_1_9999":
        return parse_stock_1_9999(text)
    if parser_name == "json_or_kv":
        return parse_json_or_kv(text)
    if parser_name == "int":
        return int(text.strip())
    if parser_name == "str":
        value = text.strip()
        if not value:
            raise ValueError("Значение не может быть пустым.")
        return value
    raise ValueError(f"Unsupported parser: {parser_name}")
