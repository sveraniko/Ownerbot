from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.core.settings import Settings
from app.llm.schema import LLMIntent


class OpenAIPlanner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def plan(self, text: str, prompt: str) -> LLMIntent:
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OPENAI LLM provider")

        user_text = text.strip()[: self._settings.llm_max_input_chars]
        payload = {
            "model": self._settings.openai_llm_model,
            "store": False,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_text}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "LLMIntent",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "intent_kind": {"type": "string", "enum": ["TOOL", "ADVICE", "UNKNOWN"]},
                            "tool": {"type": ["string", "null"]},
                            "payload": {"type": "object", "additionalProperties": True},
                            "presentation": {"type": ["object", "null"], "additionalProperties": True},
                            "advice": {
                                "type": ["object", "null"],
                                "additionalProperties": False,
                                "properties": {
                                    "title": {"type": "string"},
                                    "bullets": {"type": "array", "items": {"type": "string"}},
                                    "risks": {"type": "array", "items": {"type": "string"}},
                                    "experiments": {"type": "array", "items": {"type": "string"}},
                                    "suggested_tools": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "tool": {"type": "string"},
                                                "payload": {"type": "object", "additionalProperties": True}
                                            },
                                            "required": ["tool", "payload"]
                                        }
                                    },
                                    "suggested_actions": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "label": {"type": "string"},
                                                "plan_hint": {"type": ["string", "null"]},
                                                "tool": {"type": ["string", "null"]},
                                                "payload_partial": {"type": "object", "additionalProperties": True},
                                                "why": {"type": "string"}
                                            },
                                            "required": ["label", "plan_hint", "tool", "payload_partial", "why"]
                                        }
                                    }
                                },
                                "required": ["title", "bullets", "risks", "experiments", "suggested_tools", "suggested_actions"]
                            },
                            "error_message": {"type": ["string", "null"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "tool_source": {"type": ["string", "null"], "enum": ["LLM", "RULE", None]},
                            "tool_kind": {"type": ["string", "null"], "enum": ["action", "report", None]},
                        },
                        "required": ["intent_kind", "tool", "payload", "presentation", "advice", "error_message", "confidence", "tool_source", "tool_kind"],
                    },
                }
            },
        }
        base_url = self._settings.openai_base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {self._settings.openai_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(f"{base_url}/v1/responses", headers=headers, json=payload)
            response.raise_for_status()
        body = response.json()
        output_text = body.get("output_text")
        if not output_text:
            raise RuntimeError("OpenAI response missing output_text")
        try:
            data = json.loads(output_text)
            return LLMIntent.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError("Invalid OpenAI planner JSON") from exc
