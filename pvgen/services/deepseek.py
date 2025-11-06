"""DeepSeek LLM client used to draft storyboard segments."""

from __future__ import annotations

import json
import math
from typing import List, Optional

from ..utils.prompts import load_prompt


class DeepSeekClient:
    """Generates storyboards using the DeepSeek API with a mock fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: str = "deepseek-chat",
        use_mock: bool = True,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url or "https://api.deepseek.com/v1"
        self._model = model
        self._use_mock = use_mock
        self._timeout = timeout
        self._client = None

    def generate_storyboard(
        self, origin_prompt: str, description: str, style_bible: str, target_duration_sec: int
    ) -> List[dict]:
        """Return a list of storyboard segments with structured fields."""
        if self._use_mock:
            return self._mock_storyboard(origin_prompt, target_duration_sec)
        if not self._api_key:
            raise ValueError("DeepSeek API key is missing; cannot call service.")

        client = self._resolve_client()
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": load_prompt("deepseek_system").strip(),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(
                        origin_prompt=origin_prompt,
                        description=description,
                        style_bible=style_bible,
                        target_duration_sec=target_duration_sec,
                    ),
                },
            ],
            temperature=0.6,
            timeout=self._timeout,
        )

        text = self._extract_text(response)
        print("DeepSeek response text:", text)
        if not text:
            raise ValueError(f"DeepSeek API response missing content: {response}")

        # sanitize common markdown/code-fence wrappers and extract JSON substring
        def _clean_json_text(s: str) -> str:
            s = s.strip()
            if s.startswith("```") and s.endswith("```"):
                lines = s.splitlines()
                if len(lines) >= 3:
                    s = "\n".join(lines[1:-1]).strip()
            # prefer array root, fallback to object root
            a_start = s.find("[")
            a_end = s.rfind("]")
            if a_start != -1 and a_end != -1 and a_end > a_start:
                return s[a_start : a_end + 1]
            o_start = s.find("{")
            o_end = s.rfind("}")
            if o_start != -1 and o_end != -1 and o_end > o_start:
                return s[o_start : o_end + 1]
            return s

        cleaned = _clean_json_text(text)
        print("DeepSeek response cleaned text:", text)
        try:
            storyboard = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to decode DeepSeek response as JSON after cleaning: {cleaned}") from exc
        if not isinstance(storyboard, list):
            raise ValueError("DeepSeek storyboard response should be a JSON array of segments.")
        return storyboard

    def _resolve_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "openai package is required for DeepSeek API calls. Install via `pip install openai`."
            ) from exc
        self._client = OpenAI(api_key=self._api_key, base_url=self._api_url)
        return self._client

    def _mock_storyboard(self, origin_prompt: str, target_duration_sec: int) -> List[dict]:
        origin = origin_prompt.strip() or "奇幻旅程"
        base_duration = max(24, target_duration_sec)
        segment_count = min(4, max(1, math.ceil(base_duration / 10)))
        per_segment = min(8.0, round(base_duration / segment_count, 2))

        segments: List[dict] = []
        for idx in range(segment_count):
            stage = idx + 1
            segments.append(
                {
                    "id": stage,
                    "duration_sec": per_segment,
                    "style": self._style_for_stage(stage),
                    "shot": self._shot_for_stage(stage, origin),
                    "camera": self._camera_for_stage(stage),
                    "props_bg": self._props_for_stage(stage),
                    "end_anchor": {
                        "pose": self._pose_for_stage(stage),
                        "facing": "右前方三分之一" if stage != segment_count else "正前方",
                        "expression": "兴奋微笑" if stage < segment_count else "温柔满足",
                        "prop_state": "围巾向后飘",
                        "position_hint_norm": {"x": 0.35 + stage * 0.1 % 0.3, "y": 0.4},
                    },
                    "consistency_flags": [
                        "围巾必须可见",
                        "毛色黄金偏暖",
                        "背景光晕保持柔和",
                    ],
                }
            )
        return segments

    def _build_prompt(
        self,
        *,
        origin_prompt: str,
        description: str,
        style_bible: str,
        target_duration_sec: int,
    ) -> str:
        return load_prompt(
            "draft_storyboard",
            {
                "origin_prompt": origin_prompt,
                "description": description,
                "style_bible": style_bible,
                "target_duration_sec": target_duration_sec,
            },
        )

    @staticmethod
    def _extract_text(response) -> str | None:
        """Extract assistant text content from OpenAI-compatible responses."""
        choices = getattr(response, "choices", None)
        if not choices and isinstance(response, dict):
            choices = response.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            message = getattr(choice, "message", None)
            if message is None and isinstance(choice, dict):
                message = choice.get("message")
            if message:
                content = getattr(message, "content", None)
                if content is None and isinstance(message, dict):
                    content = message.get("content")
                if isinstance(content, str):
                    return content
        if isinstance(response, dict):
            for key in ("output", "result"):
                value = response.get(key)
                if isinstance(value, str):
                    return value
        return None

    @staticmethod
    def _style_for_stage(stage: int) -> str:
        styles = {
            1: "whimsical calm fantasy",
            2: "midair aurora burst",
            3: "luminous chase through ruins",
            4: "crescendo of floating lights",
        }
        return styles.get(stage, "dreamy kinetic tableau")

    @staticmethod
    def _shot_for_stage(stage: int, origin_prompt: str) -> str:
        base_shots = {
            1: "宠物在晨雾草地上轻盈漫步，星屑围绕",
            2: "宠物跃上漂浮石阶，与彩色能量球互动",
            3: "穿越镜面湖泊，尾迹点亮夜空",
            4: "悬停于光之门前回眸，能量波扩散",
        }
        shot = base_shots.get(stage, "奔跑于光雾之间")
        return f"{shot}，呼应意图：{origin_prompt}"

    @staticmethod
    def _camera_for_stage(stage: int) -> str:
        cameras = {
            1: "medium shot, slow dolly-in, gentle pan",
            2: "wide shot, upward tilt following跃动",
            3: "tracking shot, glide-cam绕行",
            4: "close-up, slow orbit with rack focus",
        }
        return cameras.get(stage, "medium shot, handheld energy")

    @staticmethod
    def _props_for_stage(stage: int) -> list:
        props = {
            1: ["红色小围巾", "梦幻草浪", "晨雾光柱"],
            2: ["红色小围巾", "漂浮石阶", "极光色能量球"],
            3: ["红色小围巾", "镜面湖泊", "星辉尾迹"],
            4: ["红色小围巾", "光之门", "悬浮蒲公英"],
        }
        return props.get(stage, ["红色小围巾"])

    @staticmethod
    def _pose_for_stage(stage: int) -> str:
        poses = {
            1: "前腿轻抬，尾巴微扬",
            2: "腾跃于半空，四肢展开",
            3: "低身滑行，爪尖激起水波",
            4: "悬停凝视，前爪交叠胸前",
        }
        return poses.get(stage, "稳态站立守望远方")
