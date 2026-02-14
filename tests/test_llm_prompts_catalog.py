from app.llm.prompts import build_llm_intent_prompt
from app.tools.registry_setup import build_registry


def test_llm_prompt_includes_key_tools_from_registry() -> None:
    prompt = build_llm_intent_prompt(build_registry())

    assert "sis_fx_reprice" in prompt
    assert "sis_products_publish" in prompt
    assert "sis_looks_publish" in prompt
    assert "sis_discounts_set" in prompt
    assert "sis_discounts_clear" in prompt
    assert "notify_team" in prompt
    assert "flag_order" in prompt
