"""Nodes around keyframe generation and selection."""

from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from ..services.jimeng import JimengClient
from ..types import KeyframeResult, RunState, Segment
from .base import BaseNode


class GenKeyframe(BaseNode):
    """Generates n+1 keyframes to anchor every storyboard segment."""

    def __init__(self, run_id: str, logger, jimeng: JimengClient) -> None:
        super().__init__(name="GenKeyframe", run_id=run_id, logger=logger)
        self._jimeng = jimeng

    def run(self, state: RunState) -> RunState:
        """Populate ``state.keyframes`` with generated assets."""
        keyframes: List[KeyframeResult] = []
        description_context = self._compose_description_context(
            origin_prompt=state.origin_prompt,
            description=state.description,
        )
        style_brief = (state.style_bible or "")[:160]

        pet_style_image = state.pet_style_image
        if pet_style_image is None:
            pet_style_image = self._jimeng.generate_pet_style_image(
                run_id=self.run_id,
                description=state.description or "",
                style_bible=state.style_bible or "",
                origin_prompt=state.origin_prompt or "",
                reference_assets=state.assets,
            )
            state.pet_style_image = pet_style_image
        style_reference_id: Optional[str] = getattr(pet_style_image, "asset_id", None)

        for idx, segment in enumerate(state.segments):
            if idx == 0:
                asset = self._jimeng.generate_keyframe(
                    self.run_id,
                    index=len(keyframes) + 1,
                    description=description_context,
                    style_brief=style_brief,
                    segment_payload=self._segment_payload(
                        segment,
                        phase="start",
                        style_reference_id=style_reference_id,
                        origin_prompt=state.origin_prompt,
                    ),
                    prev_image_asset_id=None,
                )
                keyframes.append(
                    self._asset_to_result(
                        asset=asset,
                        index=len(keyframes) + 1,
                    )
                )

            prev_asset_id = keyframes[-1].asset_id if keyframes else style_reference_id
            asset = self._jimeng.generate_keyframe(
                self.run_id,
                index=len(keyframes) + 1,
                description=description_context,
                style_brief=style_brief,
                segment_payload=self._segment_payload(
                    segment,
                    phase="end",
                    style_reference_id=style_reference_id,
                    origin_prompt=state.origin_prompt,
                ),
                prev_image_asset_id=prev_asset_id,
            )
            keyframes.append(
                self._asset_to_result(
                    asset=asset,
                    index=len(keyframes) + 1,
                )
            )

        state.keyframes = keyframes
        self.log_prompt("Generating stylised pet reference and keyframes for storyboard segments.")
        response_payload = {
            "pet_style_image": asdict(state.pet_style_image) if state.pet_style_image else None,
            "keyframes": [asdict(kf) for kf in keyframes],
        }
        self.log_response(response_payload)
        return state

    @staticmethod
    def _asset_to_result(*, asset, index: int) -> KeyframeResult:
        """Convert an asset into the keyframe result structure."""
        return KeyframeResult(index=index, asset_id=asset.asset_id, local_path=asset.local_path)

    @staticmethod
    def _segment_payload(
        segment: Segment,
        phase: str,
        *,
        style_reference_id: Optional[str],
        origin_prompt: Optional[str],
    ) -> dict:
        """Create a concise payload describing the segment."""
        payload = {
            "segment_id": segment.id,
            "phase": phase,
            "style": segment.style,
            "shot": segment.shot,
            "camera": segment.camera,
            "story": segment.story,
            "duration_sec": segment.duration_sec,
            "props_bg": segment.props_bg,
            "consistency_flags": segment.consistency_flags,
            "end_anchor": {
                "pose": segment.end_anchor.pose,
                "facing": segment.end_anchor.facing,
                "expression": segment.end_anchor.expression,
                "prop_state": segment.end_anchor.prop_state,
                "position_hint_norm": segment.end_anchor.position_hint_norm,
            },
        }
        if style_reference_id:
            payload["reference_asset_id"] = style_reference_id
        if origin_prompt:
            payload["origin_prompt"] = origin_prompt
            payload.setdefault("segment_summary", origin_prompt)
        return payload

    @staticmethod
    def _compose_description_context(
        *,
        origin_prompt: Optional[str],
        description: Optional[str],
    ) -> str:
        """Merge origin prompt and description for richer keyframe context."""
        parts: List[str] = []
        if origin_prompt and origin_prompt.strip():
            parts.append(f"用户原始意图: {origin_prompt.strip()}")
        if description and description.strip():
            parts.append(description.strip())
        return "\n".join(parts)


class PickKeyframe(BaseNode):
    """Placeholder selector that keeps the generated keyframes as-is."""

    def __init__(self, run_id: str, logger) -> None:
        super().__init__(name="PickKeyframe", run_id=run_id, logger=logger)

    def run(self, state: RunState) -> RunState:
        """Act as a no-op, while still emitting log artifacts."""
        self.log_prompt("Selecting best keyframes (mock keeps originals).")
        self.log_response({"selected_keyframes": [kf.asset_id for kf in state.keyframes]})
        return state
