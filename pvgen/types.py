"""Core data models used across the PetVideoGenerator pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class Asset:
    """Represents an image or video asset referenced by the pipeline."""

    asset_id: str
    media_type: str
    local_path: str
    width: Optional[int] = None
    height: Optional[int] = None
    ext: Optional[str] = None
    sha256: Optional[str] = None


@dataclass(slots=True)
class EndAnchor:
    """Defines the pose and orientation constraints for a segment ending."""

    pose: str
    facing: str
    expression: str
    prop_state: Optional[str] = None
    position_hint_norm: Optional[Dict[str, float]] = None


@dataclass(slots=True)
class Segment:
    """Storyboard segment definition."""

    id: int
    duration_sec: float
    style: str
    shot: str
    camera: str
    story: str
    props_bg: List[str]
    end_anchor: EndAnchor
    consistency_flags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class KeyframeResult:
    """Result metadata for a generated keyframe."""

    index: int
    asset_id: str
    local_path: str
    scores: Optional[Dict[str, float]] = None


@dataclass(slots=True)
class Report:
    """Aggregated run metadata surfaced at the end of the pipeline."""

    asset_hash: str
    global_fps: int
    segments: List[Segment]
    cost_estimate: Optional[float] = None
    timings_ms: Optional[Dict[str, int]] = None


@dataclass(slots=True)
class RunState:
    """Mutable state passed between nodes."""

    assets: List[Asset] = field(default_factory=list)
    asset_hash: Optional[str] = None
    origin_prompt: Optional[str] = None
    target_duration_sec: Optional[int] = 30
    fps: int = 24
    description: Optional[str] = None
    style_bible: Optional[str] = None
    pet_style_image: Optional[Asset] = None
    storyboard: List[Dict[str, Any]] = field(default_factory=list)
    segments: List[Segment] = field(default_factory=list)
    consistency_ledger: Dict[str, List[str]] = field(default_factory=dict)
    keyframes: List[KeyframeResult] = field(default_factory=list)
    videos: List[Asset] = field(default_factory=list)
    final_video: Optional[Asset] = None
    report: Optional[Report] = None
