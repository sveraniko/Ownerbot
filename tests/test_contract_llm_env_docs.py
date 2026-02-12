from __future__ import annotations

from pathlib import Path


REQUIRED_LLM_KEYS = [
    "LLM_PROVIDER",
    "OPENAI_LLM_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_INPUT_CHARS",
    "LLM_ALLOWED_ACTION_TOOLS",
]


def test_env_example_contains_llm_keys() -> None:
    source = Path("ENV.example").read_text(encoding="utf-8")
    for key in REQUIRED_LLM_KEYS:
        assert f"{key}=" in source


def test_llm_prompt_doc_exists_and_non_empty() -> None:
    prompt_doc = Path("docs/OWNERBOT_LLM_PROMPT.md")
    assert prompt_doc.exists()
    assert prompt_doc.read_text(encoding="utf-8").strip()
