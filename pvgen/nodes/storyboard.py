"""Nodes that create, validate, and normalise storyboard segments."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import List

from ..services.deepseek import DeepSeekClient
from ..types import EndAnchor, RunState, Segment
from .base import BaseNode


class DraftStoryboard(BaseNode):
    """Asks the DeepSeek client to produce a storyboard outline."""

    def __init__(self, run_id: str, logger, deepseek: DeepSeekClient) -> None:
        super().__init__(name="DraftStoryboard", run_id=run_id, logger=logger)
        self._deepseek = deepseek

    def run(self, state: RunState) -> RunState:
        """Populate the storyboard field with raw segment dicts."""
        prompt_payload = {
            "origin_prompt": state.origin_prompt,
            "description": state.description,
            "style_bible": state.style_bible,
            "target_duration_sec": state.target_duration_sec,
        }
        self.log_prompt(json.dumps(prompt_payload, ensure_ascii=False, indent=2))

        storyboard = self._deepseek.generate_storyboard(
            state.origin_prompt or "",
            state.description or "",
            state.style_bible or "",
            state.target_duration_sec or 30,
        )
        state.storyboard = storyboard
        self.log_response({"storyboard": storyboard})
        return state


class ValidateStoryboard(BaseNode):
    """Ensures storyboard segments satisfy the expected schema."""

    def __init__(self, run_id: str, logger) -> None:
        super().__init__(name="ValidateStoryboard", run_id=run_id, logger=logger)

    def run(self, state: RunState) -> RunState:
        """Validate durations, anchors, and field coverage."""
        storyboard = state.storyboard
        errors: List[str] = []

        if not isinstance(storyboard, list) or not storyboard:
            errors.append("Storyboard must contain at least one segment dictionary.")
        else:
            for segment in storyboard:
                if not isinstance(segment, dict):
                    errors.append("Storyboard entries must be dictionaries.")
                    continue
                duration = segment.get("duration_sec")
                if duration is None:
                    errors.append(f"Segment {segment.get('id')} missing duration_sec")
                    continue
                try:
                    duration_value = float(duration)
                except (TypeError, ValueError):
                    errors.append(f"Segment {segment.get('id')} duration not numeric: {duration}")
                    continue
                if not (0.5 <= duration_value <= 8):
                    errors.append(f"Segment {segment.get('id')} duration invalid: {duration}")
                anchor = segment.get("end_anchor") or {}
                if not isinstance(anchor, dict):
                    errors.append(f"Segment {segment.get('id')} end_anchor must be an object")
                    continue
                for key in ("pose", "facing", "expression"):
                    if not anchor.get(key):
                        errors.append(f"Segment {segment.get('id')} missing end_anchor.{key}")
                if not segment.get("props_bg"):
                    errors.append(f"Segment {segment.get('id')} requires props_bg entries")

        self.log_prompt("Validating storyboard against schema constraints.")

        if errors:
            self.log_response({"status": "failed", "errors": errors})
            raise ValueError("Storyboard validation failed: " + "; ".join(errors))

        self.log_response({"status": "passed", "segment_count": len(storyboard)})
        return state


class PlanSegments(BaseNode):
    """Normalises storyboard dictionaries into Segment dataclasses."""

    def __init__(self, run_id: str, logger) -> None:
        super().__init__(name="PlanSegments", run_id=run_id, logger=logger)

    def run(self, state: RunState) -> RunState:
        """Create dataclass instances and extract consistency ledger."""
        segments: List[Segment] = []
        ledger = {"flags": []}

        for raw in state.storyboard:
            end_anchor_dict = self._coerce_end_anchor(raw.get("end_anchor"))
            end_anchor = EndAnchor(
                pose=end_anchor_dict.get("pose", ""),
                facing=end_anchor_dict.get("facing", ""),
                expression=end_anchor_dict.get("expression", ""),
                prop_state=end_anchor_dict.get("prop_state"),
                position_hint_norm=end_anchor_dict.get("position_hint_norm"),
            )
            segment = Segment(
                id=int(raw.get("id", len(segments) + 1)),
                duration_sec=float(raw.get("duration_sec", 6)),
                style=raw.get("style", ""),
                shot=raw.get("shot", ""),
                camera=raw.get("camera", ""),
                story=raw.get("story", ""),
                props_bg=list(raw.get("props_bg", [])),
                end_anchor=end_anchor,
                consistency_flags=list(raw.get("consistency_flags", [])),
            )
            segments.append(segment)
            ledger["flags"].extend(segment.consistency_flags)

        state.segments = segments
        state.consistency_ledger = ledger

        self.log_prompt("Normalising storyboard into Segment dataclasses.")
        self.log_response({"segments": [asdict(seg) for seg in segments], "consistency_ledger": ledger})
        return state

    @staticmethod
    def _coerce_end_anchor(value) -> dict:
        """Attempt to normalise end_anchor into a dictionary."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = {}
            if isinstance(parsed, dict):
                return parsed
            # Best-effort parse of "key: value" or "key=value" fragments.
            candidates = {}
            normalised = text.replace("\n", ",").replace(";", ",")
            for chunk in filter(None, (part.strip() for part in normalised.split(","))):
                if ":" in chunk:
                    key, val = chunk.split(":", 1)
                elif "=" in chunk:
                    key, val = chunk.split("=", 1)
                else:
                    continue
                key = key.strip()
                if key:
                    candidates[key] = val.strip()
            return candidates
        return {}
