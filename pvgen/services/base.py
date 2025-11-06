"""Base service abstractions and mock implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LanguageModel(Protocol):
    """Protocol for text-only generation services."""

    def generate(self, prompt: str) -> str:
        ...


class VisionLanguageModel(Protocol):
    """Protocol for multi-modal generation services."""

    def generate(self, prompt: str, image_paths: list[str]) -> str:
        ...


@dataclass(slots=True)
class MockResponseConfig:
    """Controls trivial variations in the mock LLM responses."""

    prefix: str = ""
    suffix: str = ""
