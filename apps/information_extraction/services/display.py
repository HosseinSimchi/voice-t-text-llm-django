"""Schema-driven flattening of validated extraction results for e-mail and UI."""

from __future__ import annotations

from typing import Any


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _inline(value: Any, schema: dict[str, Any]) -> str:
    if isinstance(value, dict):
        props = schema.get("properties", {})
        parts = []
        for i, key in enumerate([k for k in props if k in value] + [k for k in value if k not in props]):
            if _empty(value[key]):
                continue
            text = _inline(value[key], props.get(key, {}))
            parts.append(text if i == 0 else f"{props.get(key, {}).get('title') or key}: {text}")
        return " — ".join(parts)
    if isinstance(value, list):
        return "، ".join(_inline(v, schema.get("items", {}) or {}) for v in value)
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    return str(value)


def flatten(data: dict[str, Any] | None, schema: dict[str, Any], fields: list[str] | str = "*",
            labels: dict[str, dict] | None = None, lang: str = "fa") -> list[dict[str, Any]]:
    """Return [{"key", "label", "items": [str, ...]}] for non-empty fields in schema order."""
    if not data:
        return []
    props = schema.get("properties", {})
    keys = list(props) if fields == "*" else list(fields)
    out = []
    for key in keys:
        value = data.get(key)
        if _empty(value):
            continue
        prop = props.get(key, {})
        label = (labels or {}).get(key, {}).get(lang) if labels and key in labels else None
        label = label or prop.get("title") or key.replace("_", " ").capitalize()
        if isinstance(value, list):
            items = [_inline(v, prop.get("items", {}) or {}) for v in value]
        else:
            items = [_inline(value, prop)]
        out.append({"key": key, "label": label, "items": items})
    return out
