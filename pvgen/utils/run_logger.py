"""Utilities for keeping per-run prompt and response logs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .files import ensure_dir, write_json, write_text


@dataclass(slots=True)
class StepLogPaths:
    """Convenience container with derived log file paths."""

    prompt_path: Path
    response_path: Path


class RunLogger:
    """Persists prompts and responses under ``runs/<run_id>``."""

    def __init__(self, base_dir: str | Path = "runs") -> None:
        self._base_dir = ensure_dir(base_dir)

    def step_paths(self, run_id: str, step_name: str) -> StepLogPaths:
        """Return the paths used for logging a specific step."""
        run_root = ensure_dir(self._base_dir / run_id)
        prompt_path = run_root / f"{step_name}-prompt.txt"
        response_path = run_root / f"{step_name}-response.json"
        return StepLogPaths(prompt_path=prompt_path, response_path=response_path)

    def log_prompt(self, run_id: str, step_name: str, prompt: str) -> None:
        """Persist the raw prompt text."""
        paths = self.step_paths(run_id, step_name)
        write_text(paths.prompt_path, prompt)

    def log_response(self, run_id: str, step_name: str, response: Any) -> None:
        """Persist the structured response."""
        paths = self.step_paths(run_id, step_name)
        write_json(paths.response_path, response)
