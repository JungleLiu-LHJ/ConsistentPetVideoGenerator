"""即梦 API client for keyframe and video segment generation."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence
from urllib.parse import urlparse

from ..types import Asset
from ..utils.files import (
    atomic_write,
    b64decode_to_bytes,
    b64encode,
    ensure_dir,
    read_binary,
    sha256_hex,
)

try:  # pragma: no cover - optional dependency
    from volcengine.visual.VisualService import VisualService
except ImportError:  # pragma: no cover - optional dependency
    VisualService = None  # type: ignore[assignment]


JIMENG_I2V_REQ_KEY = "jimeng_i2v_first_tail_v30_1080"
JIMENG_KEYFRAME_REQ_KEY = "jimeng_i2i_v30"
# 1x1 transparent PNG base64 fallback used when no reference image is provided.
DEFAULT_SEED_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


class JimengClient:
    """Handles communication with 即梦的文/图生图与 I2V 接口。

    When ``use_mock`` is True the client falls back to deterministic text files so
    the pipeline remains testable without hitting external services.
    """

    def __init__(
        self,
        assets_dir: str | Path,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_url: Optional[str] = None,
        use_mock: bool = True,
        timeout: int = 120,
        poll_interval: float = 2.0,
        max_poll_attempts: int = 1000000,
    ) -> None:
        self._assets_dir = ensure_dir(assets_dir)
        self._api_key = api_key
        self._api_secret = api_secret or os.getenv("JIMENG_API_SECRET")
        self._api_url = api_url
        self._use_mock = use_mock
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._max_poll_attempts = max_poll_attempts
        self._visual_service = None

        if not self._api_secret and self._api_key and ":" in self._api_key:
            ak, sk = self._api_key.split(":", 1)
            self._api_key, self._api_secret = ak, sk

    def generate_keyframe(
        self,
        run_id: str,
        index: int,
        description: str,
        style_brief: str,
        segment_payload: Dict[str, Any],
        prev_image_asset_id: Optional[str] = None,
    ) -> Asset:
        """Generate a keyframe image asset either via API or local mock."""
        if self._use_mock:
            return self._generate_mock_keyframe(
                index=index,
                description=description,
                style_brief=style_brief,
                segment_payload=segment_payload,
                prev_image_asset_id=prev_image_asset_id,
            )

        form = self._build_keyframe_form(
            description=description,
            style_brief=style_brief,
            segment_payload=segment_payload,
            prev_image_asset_id=prev_image_asset_id,
        )
        response = self._call_visual_service(form)
        return self._asset_from_response(response, media_type="image", default_ext="png")

    def generate_pet_style_image(
        self,
        *,
        run_id: str,
        description: str,
        style_bible: str,
        origin_prompt: str,
        reference_assets: Sequence[Asset] | None = None,
    ) -> Asset:
        """Create a stylised character sheet of the pet for downstream references."""
        context_lines = [origin_prompt.strip(), description.strip()]
        description_context = "\n".join(filter(None, context_lines)).strip()
        style_brief = (style_bible or "")[:200]

        reference_asset_id: Optional[str] = None
        if reference_assets:
            for asset in reference_assets:
                if getattr(asset, "asset_id", None):
                    reference_asset_id = asset.asset_id
                    break

        payload: Dict[str, Any] = {
            "segment_id": "pet_style",
            "prompt": "生成宠物角色的风格化参考图，便于后续的生成保持造型一致。不用包含背景，仅宠物主体",
            "style": style_bible,
            "camera": "角色半身/全身设定稿，光线柔和，姿态稳定。",
            "props_bg": ["角色标志性配饰与可见的背景元素"],
            "consistency_flags": ["保持配饰位置与色彩", "维持毛发纹理与主副色色阶"],
            "segment_summary": origin_prompt or description or "宠物角色风格参考",
            "description": description,
            "origin_prompt": origin_prompt,
            "emphasis": "突出角色配饰、毛色与体态，作为后续关键帧参考。",
        }
        if reference_asset_id:
            payload["reference_asset_id"] = reference_asset_id

        if self._use_mock:
            return self._generate_mock_style_image(
                description=description_context,
                style_bible=style_bible,
                origin_prompt=origin_prompt,
                reference_asset_id=reference_asset_id,
            )

        form = self._build_keyframe_form(
            description=description_context or description,
            style_brief=style_brief,
            segment_payload=payload,
            prev_image_asset_id=None,
        )
        response = self._call_visual_service(form)
        return self._asset_from_response(response, media_type="image", default_ext="png")

    def generate_video_segment(
        self,
        run_id: str,
        segment_id: int,
        segment_payload: Dict[str, Any],
        first_frame_asset_id: str,
        last_frame_asset_id: str,
        fps: int,
    ) -> Asset:
        """Generate a video asset per segment via API or mock."""
        if self._use_mock:
            return self._generate_mock_video(
                segment_id=segment_id,
                segment_payload=segment_payload,
                first_frame_asset_id=first_frame_asset_id,
                last_frame_asset_id=last_frame_asset_id,
                fps=fps,
            )

        form = self._build_video_form(
            run_id=run_id,
            segment_id=segment_id,
            segment_payload=segment_payload,
            first_frame_asset_id=first_frame_asset_id,
            last_frame_asset_id=last_frame_asset_id,
            fps=fps,
        )
        response = self._call_visual_service(form)
        return self._asset_from_response(response, media_type="video", default_ext="mp4")

    def _generate_mock_style_image(
        self,
        *,
        description: str,
        style_bible: str,
        origin_prompt: str,
        reference_asset_id: Optional[str],
    ) -> Asset:
        lines = [
            "[Pet Style Image]",
            f"Origin prompt: {origin_prompt}",
            f"Description context: {description}",
            f"Style bible: {style_bible}",
        ]
        if reference_asset_id:
            lines.append(f"Reference asset: {reference_asset_id}")
        content = "\n".join(lines)
        base64_data = b64encode(content.encode("utf-8"))
        asset_id = sha256_hex(base64_data.encode("utf-8"))
        filename = f"{asset_id}.txt"
        path = self._assets_dir / filename
        atomic_write(path, content.encode("utf-8"))
        return Asset(
            asset_id=asset_id,
            media_type="image",
            local_path=str(path),
            ext="txt",
            sha256=asset_id,
        )

    def _generate_mock_keyframe(
        self,
        *,
        index: int,
        description: str,
        style_brief: str,
        segment_payload: Dict[str, Any],
        prev_image_asset_id: Optional[str],
    ) -> Asset:
        lines = [
            f"[Keyframe #{index}]",
            f"Description: {description}",
            f"Style brief: {style_brief}",
            f"Segment details: {segment_payload}",
        ]
        if prev_image_asset_id:
            lines.append(f"Prev frame anchor: {prev_image_asset_id}")
        content = "\n".join(lines)
        base64_data = b64encode(content.encode("utf-8"))
        asset_id = sha256_hex(base64_data.encode("utf-8"))
        filename = f"{asset_id}.txt"
        path = self._assets_dir / filename
        atomic_write(path, content.encode("utf-8"))
        return Asset(
            asset_id=asset_id,
            media_type="image",
            local_path=str(path),
            ext="txt",
            sha256=asset_id,
        )

    def _generate_mock_video(
        self,
        *,
        segment_id: int,
        segment_payload: Dict[str, Any],
        first_frame_asset_id: str,
        last_frame_asset_id: str,
        fps: int,
    ) -> Asset:
        content = "\n".join(
            [
                f"[Video Segment #{segment_id}]",
                f"FPS: {fps}",
                f"First frame asset: {first_frame_asset_id}",
                f"Last frame asset: {last_frame_asset_id}",
                f"Payload: {segment_payload}",
            ]
        )
        base64_data = b64encode(content.encode("utf-8"))
        asset_id = sha256_hex(base64_data.encode("utf-8"))
        filename = f"{asset_id}.txt"
        path = self._assets_dir / filename
        atomic_write(path, content.encode("utf-8"))
        return Asset(
            asset_id=asset_id,
            media_type="video",
            local_path=str(path),
            ext="txt",
            sha256=asset_id,
        )

    def _ensure_api_ready(self) -> None:
        if not self._api_key or not self._api_url:
            raise ValueError("Jimeng API key or URL is missing; cannot call real service.")

    def _resolve_endpoint(self, path: str) -> str:
        base = (self._api_url or "").rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _post_json(self, url: str, payload: dict) -> dict:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("requests package is required for real Jimeng API calls.") from exc

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _asset_from_response(self, response: dict, *, media_type: str, default_ext: str) -> Asset:
        asset_id = self._extract_string(response, ("asset_id", "id")) or ""
        base64_data = self._extract_string(
            response, ("image_base64", "video_base64", "base64", "content")
        )
        if not base64_data:
            base64_data = self._extract_base64_blob(response)

        binary: Optional[bytes] = None
        sha_source: Optional[bytes] = None
        ext = self._extract_string(response, ("ext", "format", "suffix"))

        if base64_data:
            binary = b64decode_to_bytes(base64_data)
            sha_source = base64_data.encode("utf-8")
        else:
            media_url = self._extract_media_url(response)
            if media_url:
                binary = self._download_binary(media_url)
                sha_source = binary
                if not ext:
                    ext = self._guess_ext_from_url(media_url) or None
            if not binary:
                raise ValueError(f"Jimeng API response missing payload: {response}")

        ext = ext or default_ext or ("png" if media_type == "image" else "mp4")

        if not asset_id:
            asset_id = sha256_hex(sha_source or binary)

        filename = f"{asset_id}.{ext}"
        path = self._assets_dir / filename
        atomic_write(path, binary)

        asset = Asset(
            asset_id=asset_id,
            media_type=media_type,
            local_path=str(path),
            ext=ext,
            sha256=sha256_hex(sha_source or binary),
        )
        width = self._extract_number(response, ("width", "w"))
        height = self._extract_number(response, ("height", "h"))
        if width:
            asset.width = int(width)
        if height:
            asset.height = int(height)
        return asset

    @staticmethod
    def _extract_string(response: dict, candidates: tuple[str, ...]) -> Optional[str]:
        lowered = {candidate.replace("_", "").lower() for candidate in candidates}
        for container in JimengClient._candidate_containers(response):
            for key, value in container.items():
                normalized = key.replace("_", "").lower()
                if isinstance(value, str) and value and normalized in lowered:
                    return value
        return None

    @staticmethod
    def _extract_number(response: dict, candidates: tuple[str, ...]) -> Optional[float]:
        lowered = {candidate.replace("_", "").lower() for candidate in candidates}
        for container in JimengClient._candidate_containers(response):
            for key, value in container.items():
                normalized = key.replace("_", "").lower()
                if normalized not in lowered:
                    continue
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _candidate_containers(response: dict) -> list[dict]:
        containers: list[dict] = []
        seen: set[int] = set()
        stack: list[Any] = [response]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                identifier = id(item)
                if identifier in seen:
                    continue
                seen.add(identifier)
                containers.append(item)
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        return containers

    def _resolve_cached_asset(self, asset_id: str) -> Optional[Path]:
        for file_path in self._assets_dir.glob(f"{asset_id}.*"):
            if file_path.is_file():
                return file_path
        return None

    def _build_video_form(
        self,
        *,
        run_id: str,
        segment_id: int,
        segment_payload: Dict[str, Any],
        first_frame_asset_id: str,
        last_frame_asset_id: str,
        fps: int,
    ) -> Dict[str, Any]:
        binaries: list[str] = []
        paths = [
            (first_frame_asset_id, "首帧"),
            (last_frame_asset_id, "尾帧"),
        ]
        for asset_id, label in paths:
            path = self._resolve_cached_asset(asset_id)
            if not path:
                raise FileNotFoundError(f"未找到{label}缓存资源: {asset_id}")
            binaries.append(b64encode(read_binary(path)))

        prompt = self._compose_prompt(segment_payload)

        if "frames" in segment_payload and segment_payload["frames"]:
            frames = int(segment_payload["frames"])
        else:
            duration = segment_payload.get("duration_sec") or segment_payload.get("duration")
            frames = self._select_frame_count(duration, fps)

        seed = segment_payload.get("seed", -1)
        try:
            seed = int(seed)
        except (TypeError, ValueError):  # pragma: no cover - defensive cast
            seed = -1

        form: Dict[str, Any] = {
            "req_key": JIMENG_I2V_REQ_KEY,
            "binary_data_base64": binaries,
            "prompt": prompt,
            "seed": seed,
            "frames": frames,
        }

        req_json = segment_payload.get("req_json")
        if req_json:
            form["req_json"] = req_json

        return form

    def _build_keyframe_form(
        self,
        *,
        description: str,
        style_brief: str,
        segment_payload: Dict[str, Any],
        prev_image_asset_id: Optional[str],
    ) -> Dict[str, Any]:
        reference_ids: list[str] = []
        if prev_image_asset_id:
            reference_ids.append(prev_image_asset_id)

        for key in ("reference_asset_id", "seed_image_asset_id"):
            value = segment_payload.get(key)
            if isinstance(value, str) and value:
                reference_ids.append(value)

        binary_images: list[str] = []
        for asset_id in reference_ids:
            path = self._resolve_cached_asset(asset_id)
            if path:
                binary_images.append(b64encode(read_binary(path)))
            if binary_images:
                break

        if not binary_images:
            binary_images.append(DEFAULT_SEED_IMAGE_BASE64)

        prompt = self._compose_keyframe_prompt(description, style_brief, segment_payload)

        seed = segment_payload.get("seed", -1)
        try:
            seed = int(seed)
        except (TypeError, ValueError):  # pragma: no cover - defensive cast
            seed = -1

        raw_rephraser = segment_payload.get("use_rephraser")
        if raw_rephraser is None:
            use_rephraser = True
        elif isinstance(raw_rephraser, str):
            use_rephraser = raw_rephraser.strip().lower() not in {"false", "0", "no"}
        else:
            use_rephraser = bool(raw_rephraser)

        form: Dict[str, Any] = {
            "req_key": JIMENG_KEYFRAME_REQ_KEY,
            "binary_data_base64": [binary_images[0]],
            "prompt": prompt,
            "seed": seed,
            "use_rephraser": use_rephraser,
        }

        width = segment_payload.get("width")
        height = segment_payload.get("height")
        try:
            if width:
                form["width"] = int(width)
            if height:
                form["height"] = int(height)
        except (TypeError, ValueError):  # pragma: no cover - ignore invalid overrides
            pass

        req_json = segment_payload.get("req_json")
        if req_json:
            form["req_json"] = req_json

        return form

    @staticmethod
    def _compose_prompt(segment_payload: Dict[str, Any]) -> str:
        prompt = segment_payload.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return prompt.strip()

        parts: list[str] = []

        phase = segment_payload.get("phase")
        segment_id = segment_payload.get("segment_id")
        if phase:
            if phase == "start":
                phase_label = "首帧"
                instruction = "这是这个画面的首帧，请让画面自然开启这一段情节。"
            else:
                phase_label = "尾帧"
                instruction = "下一段视频将直接使用该帧作为开场，请保持角色造型、姿态与布景连贯。"
            if segment_id is not None:
                parts.append(f"关键帧定位: 第{segment_id}段{phase_label}。{instruction}")
            else:
                parts.append(f"关键帧定位: 本段{phase_label}。{instruction}")

        fields = [
            ("style", "画面风格"),
            ("shot", "场景要点"),
            ("camera", "镜头语言"),
            ("props_bg", "道具背景"),
            ("consistency_flags", "一致性要素"),
        ]
        for key, label in fields:
            value = segment_payload.get(key)
            if not value:
                continue
            if isinstance(value, (list, tuple, set)):
                rendered = ", ".join(str(item) for item in value if item)
            else:
                rendered = str(value)
            rendered = rendered.strip()
            if rendered:
                parts.append(f"{label}: {rendered}")

        end_anchor = segment_payload.get("end_anchor")
        if end_anchor:
            parts.append(f"结尾姿态: {end_anchor}")

        description = segment_payload.get("description")
        if description:
            parts.append(str(description))

        fallback = segment_payload.get("segment_summary") or "奇幻宠物短片"
        return " | ".join(parts) if parts else str(fallback)

    @staticmethod
    def _compose_keyframe_prompt(
        description: str,
        style_brief: str,
        segment_payload: Dict[str, Any],
    ) -> str:
        parts: list[str] = []
        description_text = (description or "").strip()
        style_text = (style_brief or "").strip()
        if description_text:
            parts.append(f"角色设定: {description_text}")
        if style_text:
            parts.append(f"风格摘要: {style_text}")

        segment_prompt = JimengClient._compose_prompt(segment_payload)
        if segment_prompt:
            parts.append(segment_prompt)

        emphasis = segment_payload.get("emphasis")
        if emphasis:
            parts.append(str(emphasis))

        return "\n".join(parts) if parts else "富有情感的宠物角色特写"

    @staticmethod
    def _select_frame_count(duration: Any, fps: int) -> int:
        valid = [121, 241]
        if duration is None:
            return valid[0]
        try:
            duration_val = float(duration)
        except (TypeError, ValueError):
            return valid[0]
        approx = int(round(max(duration_val, 0) * fps)) + 1
        return min(valid, key=lambda option: abs(option - approx))

    def _call_visual_service(self, form: Dict[str, Any]) -> Dict[str, Any]:
        service = self._get_visual_service()
        submit_response = service.cv_sync2async_submit_task(form)
        print("Jimeng submit response:", submit_response)
        return self._wait_for_cv_task(
            initial_response=submit_response,
            form=form,
            poll_callable=service.cv_sync2async_get_result,
            task_action="CVSync2AsyncGetResult",
        )

    def _wait_for_cv_task(
        self,
        *,
        initial_response: Dict[str, Any],
        form: Dict[str, Any],
        poll_callable: Callable[[Dict[str, Any]], Dict[str, Any]],
        task_action: str,
    ) -> Dict[str, Any]:
        response = self._ensure_visual_success(initial_response)
        task_id = self._extract_string(response, ("task_id", "TaskId"))
        if not task_id:
            raise ValueError(f"{task_action} response missing task_id: {response}")

        query_form: Dict[str, Any] = {
            "req_key": form.get("req_key", JIMENG_I2V_REQ_KEY),
            "task_id": task_id,
        }
        if "req_json" in form:
            query_form["req_json"] = form["req_json"]

        failure_states = {"not_found", "expired", "failed", "error"}

        for _ in range(self._max_poll_attempts):
            result = self._ensure_visual_success(poll_callable(query_form))
            status = self._extract_string(result, ("status",))
            media_url = self._extract_media_url(result)
            base64_blob = self._extract_base64_blob(result)
            print(f"Jimeng {task_action} poll status: {status}, media_url: {media_url is not None}")
            if status:
                status_lower = status.lower()
                if status_lower == "done" and (media_url or base64_blob):
                    return result
                if status_lower in failure_states:
                    message = self._extract_string(result, ("message", "error_message")) or "任务失败"
                    raise RuntimeError(f"{task_action} failed with status {status}: {message}")
            if media_url or base64_blob:
                return result
            time.sleep(self._poll_interval)

        raise TimeoutError(f"{task_action} result not ready after {self._max_poll_attempts} attempts.")

    def _get_visual_service(self):
        if VisualService is None:
            raise RuntimeError(
                "volcengine SDK is required for video generation. Install via `pip install volcengine`."
            )
        if self._visual_service is None:
            service = VisualService()
            if self._api_key:
                service.set_ak(self._api_key)
            if self._api_secret:
                service.set_sk(self._api_secret)
            if self._api_url:
                parsed = urlparse(self._api_url)
                if parsed.scheme:
                    service.set_scheme(parsed.scheme)
                host = parsed.netloc or parsed.path
                if host:
                    service.set_host(host)
            if self._timeout:
                service.set_connection_timeout(self._timeout)
                service.set_socket_timeout(self._timeout)
            self._visual_service = service
        return self._visual_service

    @staticmethod
    def _ensure_visual_success(response: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(response, dict):
            code = response.get("code") or response.get("Code")
            if code is not None:
                code_str = str(code)
                if code_str not in {"0", "10000"}:
                    message = response.get("message") or response.get("Message") or "Unknown error"
                    raise RuntimeError(f"Jimeng CV service error [{code_str}]: {message}")
            status_code = response.get("status") or response.get("Status")
            if status_code is not None:
                status_str = str(status_code)
                if status_str not in {"0", "10000"}:
                    message = response.get("message") or response.get("Message") or "Unknown error"
                    raise RuntimeError(f"Jimeng CV service error [{status_str}]: {message}")

        metadata = None
        if isinstance(response, dict):
            metadata = response.get("ResponseMetadata") or response.get("response_metadata")
        if isinstance(metadata, dict):
            error = metadata.get("Error") or metadata.get("error")
            if isinstance(error, dict):
                code = str(error.get("Code") or error.get("code") or "").strip()
                if code:
                    normalized = code.lower()
                    if normalized not in {"", "0", "ok", "success"}:
                        message = error.get("Message") or error.get("message") or ""
                        raise RuntimeError(f"Jimeng CV service error [{code}]: {message}")
        return response

    @staticmethod
    def _extract_base64_blob(response: Dict[str, Any]) -> Optional[str]:
        for container in JimengClient._candidate_containers(response):
            for key, value in container.items():
                if not isinstance(value, str) or not value:
                    if isinstance(value, list) and value:
                        lowered = key.lower()
                        if "base64" in lowered or lowered.endswith("_b64"):
                            first = next((item for item in value if isinstance(item, str) and item), None)
                            if first:
                                return first
                    continue
                lowered = key.lower()
                if "base64" in lowered or lowered.endswith("_b64"):
                    return value
        return None

    @staticmethod
    def _extract_media_url(response: Dict[str, Any]) -> Optional[str]:
        for container in JimengClient._candidate_containers(response):
            for key, value in container.items():
                lowered = key.lower()
                if isinstance(value, str) and value and lowered in {"video_url", "url", "image_url"}:
                    return value
                if isinstance(value, list) and value and lowered in {"video_urls", "image_urls", "urls"}:
                    first = next((item for item in value if isinstance(item, str) and item), None)
                    if first:
                        return first
        return None

    def _download_binary(self, url: str) -> bytes:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("requests package is required to download Jimeng video results.") from exc

        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _guess_ext_from_url(url: str) -> Optional[str]:
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix
        return suffix[1:].lower() if suffix else None
