"""Nodes handling video segment generation, QC, and assembly."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import List

from ..services.jimeng import JimengClient
from ..types import Asset, Report, RunState, Segment
from ..utils.files import ensure_dir, write_text
from .base import BaseNode


class GenVideoSegment(BaseNode):
    """Generates a video asset per storyboard segment."""

    def __init__(self, run_id: str, logger, jimeng: JimengClient) -> None:
        super().__init__(name="GenVideoSegment", run_id=run_id, logger=logger)
        self._jimeng = jimeng

    def run(self, state: RunState) -> RunState:
        """Populate the state with generated video segments."""
        videos: List[Asset] = []
        for idx, segment in enumerate(state.segments):
            first = state.keyframes[idx]
            last = state.keyframes[idx + 1]
            payload = {
                "shot": segment.shot,
                "camera": segment.camera,
                "story": segment.story,
                "style": segment.style,
                "props_bg": segment.props_bg,
                "consistency_flags": segment.consistency_flags,
                "duration_sec": segment.duration_sec,
            }
            asset = self._jimeng.generate_video_segment(
                run_id=self.run_id,
                segment_id=segment.id,
                segment_payload=payload,
                first_frame_asset_id=first.asset_id,
                last_frame_asset_id=last.asset_id,
                fps=state.fps,
            )
            videos.append(asset)

        state.videos = videos
        self.log_prompt("Generating video segments via 即梦 I2V.")
        self.log_response({"videos": [asdict(video) for video in videos]})
        return state


class QCVideoSegment(BaseNode):
    """Performs lightweight validation on generated video segments."""

    def __init__(self, run_id: str, logger) -> None:
        super().__init__(name="QCVideoSegment", run_id=run_id, logger=logger)

    def run(self, state: RunState) -> RunState:
        """Check that each segment has matching frame anchors."""
        inconsistencies = []
        for idx, segment in enumerate(state.segments):
            first = state.keyframes[idx].asset_id
            last = state.keyframes[idx + 1].asset_id
            video = state.videos[idx]
            video_path = Path(video.local_path)
            try:
                content = video_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Binary outputs from real API calls cannot be inspected cheaply.
                continue
            if first not in content or last not in content:
                inconsistencies.append(segment.id)

        self.log_prompt("Verifying video segment frame anchors.")
        self.log_response({"inconsistencies": inconsistencies})

        if inconsistencies:
            raise ValueError(f"Video QC failed for segments: {inconsistencies}")
        return state


class AssembleVideo(BaseNode):
    """Writes a manifest representing the concatenated final video."""

    def __init__(self, run_id: str, logger, output_dir: str | Path) -> None:
        super().__init__(name="AssembleVideo", run_id=run_id, logger=logger)
        self._output_dir = ensure_dir(output_dir)

    def run(self, state: RunState) -> RunState:
        """Concatenate segment videos into a single deliverable asset."""
        if not state.videos:
            raise ValueError("No video segments available for assembly.")

        video_paths = [Path(video.local_path) for video in state.videos]
        binary_segments = [path for path in video_paths if path.suffix.lower() not in {".txt", ".json"}]

        if binary_segments:
            output_path = self._output_dir / f"{self.run_id}-final.mp4"
            self._concat_videos(binary_segments, output_path)
            final_ext = "mp4"
        else:
            # Mock mode: concatenate textual stand-ins to keep pipeline observable.
            output_path = self._output_dir / f"{self.run_id}-final.txt"
            combined = []
            for path in video_paths:
                combined.append(path.read_text(encoding="utf-8"))
            write_text(output_path, "\n\n".join(combined))
            final_ext = "txt"

        final_asset = Asset(
            asset_id=f"final-{self.run_id}",
            media_type="video",
            local_path=str(output_path),
            ext=final_ext,
        )
        state.final_video = final_asset

        self.log_prompt("Concatenating segment videos into final deliverable.")
        self.log_response({"final_video": asdict(final_asset)})
        return state

    def _concat_videos(self, sources: List[Path], output_path: Path) -> None:
        """Concatenate binary video segments using ffmpeg."""
        resolved_sources: list[Path] = []
        missing_sources: list[str] = []
        for original in sources:
            expanded = original.expanduser()
            try:
                resolved = expanded.resolve(strict=True)
            except FileNotFoundError:
                missing_sources.append(str(expanded))
                continue
            resolved_sources.append(resolved)

        if missing_sources or not resolved_sources:
            missing = ", ".join(missing_sources) if missing_sources else "unknown sources"
            raise FileNotFoundError(f"Video segments missing for concat: {missing}")

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as manifest:
            manifest_path = Path(manifest.name)
            for path in resolved_sources:
                line_path = str(path).replace("'", r"'\''")
                manifest.write(f"file '{line_path}'\n")

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest_path),
                "-c",
                "copy",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    "ffmpeg concat failed: "
                    f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
                )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffmpeg is required to assemble video segments. Please install ffmpeg and retry."
            ) from exc
        finally:
            manifest_path.unlink(missing_ok=True)


class ReportNode(BaseNode):
    """Aggregates and writes the final run report."""

    def __init__(self, run_id: str, logger, output_dir: str | Path) -> None:
        super().__init__(name="Report", run_id=run_id, logger=logger)
        self._output_dir = ensure_dir(output_dir)

    def run(self, state: RunState) -> RunState:
        """Generate a lightweight report based on the run state."""
        report = Report(
            asset_hash=state.asset_hash or "",
            global_fps=state.fps,
            segments=state.segments,
            cost_estimate=0.0,
            timings_ms=None,
        )
        state.report = report
        report_path = self._output_dir / f"{self.run_id}-report.txt"
        write_text(
            report_path,
            "\n".join(
                [
                    f"asset_hash: {report.asset_hash}",
                    f"global_fps: {report.global_fps}",
                    f"segment_count: {len(report.segments)}",
                    f"final_video: {state.final_video.local_path if state.final_video else 'N/A'}",
                ]
            ),
        )

        self.log_prompt("Generating final report.")
        self.log_response({"report_path": str(report_path)})
        return state
