from __future__ import annotations

from app.llm.schema import AdvicePayload

_DEFAULT_EXPERIMENTS = [
    "Собрать baseline через kpi_snapshot за 7d/30d.",
    "Сравнить тренд выручки и операционные метрики до/после изменения.",
    "Запускать только dry_run/preview и переходить к commit после подтверждения.",
]


def sanitize_advice_payload(advice: AdvicePayload) -> AdvicePayload:
    updated = advice
    if not updated.title.strip():
        updated = updated.model_copy(update={"title": "Советник: гипотезы и план проверки"})
    if not updated.experiments:
        updated = updated.model_copy(update={"experiments": list(_DEFAULT_EXPERIMENTS)})
    return updated


def format_advice_text(advice: AdvicePayload, quality_header: str, warnings: list[str] | None = None) -> str:
    lines: list[str] = [quality_header, f"🧠 {advice.title}", "", "Это гипотезы. Сначала проверка данными, затем действия через preview/confirm."]
    lines.append("\n🧭 Гипотезы:")
    lines.extend(f"• {item}" for item in advice.bullets[:7])
    if advice.risks:
        lines.append("\n⚠️ Риски:")
        lines.extend(f"• {item}" for item in advice.risks[:3])
    lines.append("\n🔬 Как проверить:")
    lines.extend(f"• {item}" for item in advice.experiments[:6])
    if warnings:
        lines.append("\n⚠️ Проверка качества:")
        lines.extend(f"• {item}" for item in warnings[:3])
    return "\n".join(lines)
