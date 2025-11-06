"""Node abstractions shared by concrete pipeline steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..types import RunState
from ..utils.run_logger import RunLogger


class Node(Protocol):
    """A unit of work that mutates the shared run state."""

    name: str

    def run(self, state: RunState) -> RunState:
        ...


@dataclass(slots=True)
class BaseNode:
    """Convenience base for nodes needing logging support."""

    name: str
    run_id: str
    logger: RunLogger

    def log_prompt(self, prompt: str) -> None:
        """Persist the prompt."""
        self.logger.log_prompt(self.run_id, self.name, prompt)

    def log_response(self, response: object) -> None:
        """Persist the response."""
        self.logger.log_response(self.run_id, self.name, response)
