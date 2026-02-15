from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InputPreset(BaseModel):
    text: str
    value: str


class InputStep(BaseModel):
    key: str
    prompt: str
    parser: Literal["ids", "int", "percent_1_95", "stock_1_9999", "json_or_kv", "str"]
    presets: list[InputPreset] | None = None
    next_step: str | None = None


class TemplateSpec(BaseModel):
    template_id: str
    category: str
    title: str
    button_text: str
    kind: Literal["REPORT", "ACTION"]
    tool_name: str
    default_payload: dict[str, object] = Field(default_factory=dict)
    presentation: dict[str, object] | None = None
    inputs: list[InputStep] = Field(default_factory=list)
    order: int = 100


class TemplateCatalog(BaseModel):
    templates: list[TemplateSpec]

    _CATEGORY_ORDER = [
        "reports",
        "orders",
        "team",
        "systems",
        "advanced",
        "forecast",
        "prices",
        "products",
        "looks",
        "discounts",
    ]

    def list_categories(self) -> list[str]:
        categories = {spec.category for spec in self.templates}
        ordered = [category for category in self._CATEGORY_ORDER if category in categories]
        extras = sorted(category for category in categories if category not in self._CATEGORY_ORDER)
        return ordered + extras

    def list_templates(self, category: str) -> list[TemplateSpec]:
        return sorted(
            [spec for spec in self.templates if spec.category == category],
            key=lambda item: (item.order, item.button_text),
        )

    def get(self, template_id: str) -> TemplateSpec:
        for spec in self.templates:
            if spec.template_id == template_id:
                return spec
        raise KeyError(f"Unknown template_id={template_id}")
