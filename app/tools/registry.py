from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from pydantic import BaseModel

from app.tools.contracts import ToolDefinition


@dataclass
class ToolContext:
    correlation_id: str
    session: Any
    upstream_mode: str


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, name: str, version: str, payload_model: type[BaseModel], handler: Any) -> None:
        self._tools[name] = ToolDefinition(name=name, version=version, payload_model=payload_model, handler=handler)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        return [
            {
                "name": tool.name,
                "version": tool.version,
                "payload_model": tool.payload_model.__name__,
            }
            for tool in self._tools.values()
        ]
