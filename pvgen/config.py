"""Configuration containers for the PetVideoGenerator pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar


@dataclass(slots=True)
class PipelineConfig:
    """Static configuration applied to every pipeline run."""

    env_prefix: ClassVar[str] = "PVGEN_"

    assets_dir: str = "assets"
    runs_dir: str = "runs"
    enable_mock_generation: bool = True
    qwen_api_key: str | None = None
    qwen_api_url: str | None = None
    deepseek_api_key: str | None = None
    deepseek_api_url: str | None = None
    jimeng_api_key: str | None = None
    jimeng_api_url: str | None = None

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """Create a config object populated from environment variables."""
        prefix = cls.env_prefix
        return cls(
            assets_dir=os.getenv(f"{prefix}ASSETS_DIR", "assets"),
            runs_dir=os.getenv(f"{prefix}RUNS_DIR", "runs"),
            enable_mock_generation=os.getenv(f"{prefix}ENABLE_MOCKS", "true").lower() == "true",
            qwen_api_key=os.getenv("QWEN_API_KEY"),
            qwen_api_url=os.getenv("QWEN_API_URL"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_api_url=os.getenv("DEEPSEEK_API_URL"),
            jimeng_api_key=os.getenv("JIMENG_API_KEY"),
            jimeng_api_url=os.getenv("JIMENG_API_URL"),
        )
