"""Basic regression tests for the PetVideoGenerator pipeline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pvgen.pipeline import PetVideoGenerator


def _create_dummy_asset(directory: Path) -> Path:
    """Create a small text file that stands in for a pet image."""
    asset_path = directory / "pet.png"
    asset_path.write_text("dummy image content", encoding="utf-8")
    return asset_path


class PipelineIntegrationTest(unittest.TestCase):
    """Covers the top-level pipeline behaviour."""

    def test_pipeline_run(self) -> None:
        """Ensure the pipeline runs end-to-end with placeholder inputs."""
        with tempfile.TemporaryDirectory() as tmp:
            asset_path = _create_dummy_asset(Path(tmp))
            generator = PetVideoGenerator()

            state = generator.run(
                image_paths=[str(asset_path)],
                origin_prompt="让宠物在魔法森林完成奇幻冒险",
                target_duration_sec=30,
                fps=24,
            )

            self.assertIsNotNone(state.final_video)
            self.assertTrue(Path(state.final_video.local_path).exists())
            self.assertIsNotNone(state.report)
            self.assertTrue(state.segments, "Expected storyboard segments to be populated.")
