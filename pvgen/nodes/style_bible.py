"""Node generating the textual style bible based on the description."""

from __future__ import annotations

from ..services.style_bible import StyleBibleGenerator
from ..types import RunState
from ..utils.prompts import load_prompt
from .base import BaseNode


class BuildStyleBible(BaseNode):
    """Produce a natural language style bible for downstream prompts."""

    def __init__(self, run_id: str, logger, generator: StyleBibleGenerator) -> None:
        super().__init__(name="BuildStyleBible", run_id=run_id, logger=logger)
        self._generator = generator

    def run(self, state: RunState) -> RunState:
        """Derive the style bible using the provided description."""
        prompt = load_prompt(
            "build_style_bible",
            {
                "description_section": state.description or "（暂无描述）",
                "origin_prompt_section": state.origin_prompt or "（未提供）",
            },
        ).strip()
        self.log_prompt(prompt)

        style_bible = self._generator.create(state.description or "", state.origin_prompt or "")
        state.style_bible = style_bible

        self.log_response({"style_bible": style_bible})
        return state
