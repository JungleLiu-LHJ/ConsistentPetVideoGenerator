"""Utilities for loading reusable prompt templates."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, MutableMapping

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def load_prompt(name: str, variables: Mapping[str, object] | None = None) -> str:
    """Return the rendered prompt text for ``name`` using optional placeholders."""
    path = PROMPTS_DIR / f"{name}.txt"
    template = path.read_text(encoding="utf-8")
    if not variables:
        return template

    # Allow mapping-like inputs (including dataclasses via asdict) while keeping defaults.
    if not isinstance(variables, Mapping):
        raise TypeError("variables must be a mapping of placeholder -> value")

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            return match.group(0)
        value = variables[key]
        return "" if value is None else str(value)

    return _PLACEHOLDER_PATTERN.sub(_replace, template)


__all__ = ["load_prompt", "PROMPTS_DIR"]
