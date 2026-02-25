from app.advice.sanitizer import sanitize_advice_payload
from app.llm.schema import AdvicePayload


def test_sanitizer_ensures_experiments_present() -> None:
    payload = AdvicePayload(title="", bullets=["Гипотеза"], experiments=[])
    sanitized = sanitize_advice_payload(payload)
    assert sanitized.title
    assert sanitized.experiments
