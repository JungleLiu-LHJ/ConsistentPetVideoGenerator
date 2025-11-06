"""Node responsible for calling Qwen-VL to describe the pet."""

from __future__ import annotations

from ..services.qwen import QwenClient
from ..types import RunState
from ..utils.prompts import load_prompt
from .base import BaseNode


class DescribePet(BaseNode):
    """Wraps the Qwen client to obtain a detailed pet description."""

    def __init__(self, run_id: str, logger, qwen: QwenClient) -> None:
        super().__init__(name="DescribePet", run_id=run_id, logger=logger)
        self._qwen = qwen

    def run(self, state: RunState) -> RunState:
        """Populate the run state with a descriptive paragraph."""
        origin_prompt_line = (
            f"额外用户意图提示：{state.origin_prompt.strip()}" if state.origin_prompt else ""
        )
        prompt = load_prompt("describe_pet", {"origin_prompt_line": origin_prompt_line}).strip()
        self.log_prompt(prompt)

        description = self._qwen.describe_pet(state.assets, state.origin_prompt or "")
        state.description = description

        self.log_response({"description": description})
        return state
