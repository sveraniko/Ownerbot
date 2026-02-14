from __future__ import annotations

from pathlib import Path

import yaml

from app.templates.catalog.models import TemplateCatalog, TemplateSpec

_DEFS_DIR = Path(__file__).resolve().parents[1] / "defs"


class TemplateCatalogLoaderError(RuntimeError):
    pass


def load_template_catalog(defs_dir: Path | None = None) -> TemplateCatalog:
    source_dir = defs_dir or _DEFS_DIR
    specs: list[TemplateSpec] = []
    seen_ids: set[str] = set()

    for path in sorted(source_dir.glob("*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TemplateCatalogLoaderError(f"Template definition must be an object: {path}")
        spec = TemplateSpec.model_validate(raw)
        if spec.template_id in seen_ids:
            raise TemplateCatalogLoaderError(f"Duplicate template_id={spec.template_id}")
        seen_ids.add(spec.template_id)
        specs.append(spec)

    return TemplateCatalog(templates=specs)


_CATALOG_SINGLETON: TemplateCatalog | None = None


def get_template_catalog() -> TemplateCatalog:
    global _CATALOG_SINGLETON
    if _CATALOG_SINGLETON is None:
        _CATALOG_SINGLETON = load_template_catalog()
    return _CATALOG_SINGLETON
