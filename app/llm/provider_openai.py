from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.core.settings import Settings
from app.llm.prompts import LLM_INTENT_PROMPT
from app.llm.schema import LLMIntent


class OpenAIPlanner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def plan(self, text: str) -> LLMIntent:
        if not self._settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OPENAI LLM provider")

        user_text = text.strip()[: self._settings.llm_max_input_chars]
        payload = {
            "model": self._settings.openai_llm_model,
            "store": False,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": LLM_INTENT_PROMPT}]},
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
                            "tool": {"type": ["string", "null"]},
                            "payload": {"type": "object", "additionalProperties": True},
                            "presentation": {"type": ["object", "null"], "additionalProperties": True},
                            "error_message": {"type": ["string", "null"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["tool", "payload", "presentation", "error_message", "confidence"],
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
