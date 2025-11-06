"""Node for importing raw assets into the pipeline cache."""

from __future__ import annotations

import json
from io import BytesIO
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List

try:  # pragma: no cover - optional dependency
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - optional dependency
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

    class UnidentifiedImageError(Exception):  # type: ignore[no-redef]
        """Fallback placeholder used when Pillow is unavailable."""

        pass

from ..config import PipelineConfig
from ..types import Asset, RunState
from ..utils.files import (
    atomic_write,
    b64encode,
    ensure_dir,
    guess_extension,
    read_binary,
    sha256_hex,
)
from .base import BaseNode


class IngestAssets(BaseNode):
    """Copies user supplied files into the managed asset cache."""

    _MAX_REFERENCE_DIM = 4096

    def __init__(
        self,
        run_id: str,
        logger,
        config: PipelineConfig,
        source_paths: Iterable[str],
        origin_prompt: str,
        target_duration_sec: int,
        fps: int,
    ) -> None:
        super().__init__(name="IngestAssets", run_id=run_id, logger=logger)
        self._config = config
        self._source_paths = list(source_paths)
        self._origin_prompt = origin_prompt
        self._target_duration_sec = target_duration_sec
        self._fps = fps

    def run(self, state: RunState) -> RunState:
        """Produce managed Asset records from arbitrary files."""
        ensure_dir(self._config.assets_dir)
        assets: List[Asset] = []
        asset_ids: List[str] = []

        prompt_summary = json.dumps(
            {
                "origin_prompt": self._origin_prompt,
                "target_duration_sec": self._target_duration_sec,
                "fps": self._fps,
                "source_paths": list(self._source_paths),
            },
            ensure_ascii=False,
            indent=2,
        )
        self.log_prompt(prompt_summary)

        for source in self._source_paths:
            raw_bytes = read_binary(source)
            prepared_bytes, ext, width, height = self._prepare_reference_image(source, raw_bytes)
            base64_data = b64encode(prepared_bytes)
            asset_id = sha256_hex(base64_data.encode("utf-8"))
            asset_ids.append(asset_id)
            ext = ext or guess_extension(source) or "bin"
            cached_path = Path(self._config.assets_dir) / f"{asset_id}.{ext}"
            atomic_write(cached_path, prepared_bytes)
            assets.append(
                Asset(
                    asset_id=asset_id,
                    media_type="image",
                    local_path=str(cached_path),
                    width=width,
                    height=height,
                    ext=ext,
                    sha256=asset_id,
                )
            )

        asset_hash = sha256_hex("".join(asset_ids).encode("utf-8"))
        state.assets = assets
        state.asset_hash = asset_hash
        state.origin_prompt = self._origin_prompt
        state.target_duration_sec = self._target_duration_sec
        state.fps = self._fps

        self.log_response({"asset_hash": asset_hash, "assets": [asdict(asset) for asset in assets]})
        return state

    def _prepare_reference_image(
        self, source_path: str, raw_bytes: bytes
    ) -> tuple[bytes, str | None, int | None, int | None]:
        """Convert large or exotic source files into safe reference images."""
        if Image is None:  # pragma: no cover - guard missing dependency
            raise RuntimeError(
                "Pillow is required to preprocess reference images. Install it via "
                "`pip install pillow` and rerun the pipeline."
            )

        buffer = BytesIO(raw_bytes)
        try:
            with Image.open(buffer) as image:
                if getattr(image, "n_frames", 1) > 1:
                    image.seek(0)

                image = ImageOps.exif_transpose(image)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

                if max(image.size) > self._MAX_REFERENCE_DIM:
                    image.thumbnail(
                        (self._MAX_REFERENCE_DIM, self._MAX_REFERENCE_DIM),
                        Image.LANCZOS,
                    )

                has_alpha = "A" in image.getbands()
                format_ = "PNG" if has_alpha else "JPEG"
                ext = "png" if has_alpha else "jpg"

                output = BytesIO()
                save_kwargs = {"format": format_, "optimize": True}
                if format_ == "JPEG":
                    save_kwargs["quality"] = 90

                image.save(output, **save_kwargs)
                payload = output.getvalue()
                return payload, ext, image.width, image.height
        except (UnidentifiedImageError, OSError):
            pass
        return raw_bytes, guess_extension(source_path), None, None
