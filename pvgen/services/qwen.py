"""Client wrapper for the Qwen-VL vision language model."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Iterable, Optional

from ..types import Asset
from ..utils.files import b64encode, read_binary


class QwenClient:
    """Generates pet descriptions via DashScope's Qwen-VL API with mock fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: str = "qwen-vl-plus",
        use_mock: bool = True,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url  # DashScope can auto-resolve; kept for extensibility.
        self._model = model
        self._use_mock = use_mock
        self._timeout = timeout

    def describe_pet(self, assets: Iterable[Asset], origin_prompt: str) -> str:
        """Return a compact description capturing key visual cues."""
        assets = list(assets)
        if self._use_mock:
            return self._mock_description(assets, origin_prompt)
        if not self._api_key:
            raise ValueError("Qwen API key is missing; cannot call DashScope service.")

        try:
            from dashscope import MultiModalConversation  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "DashScope SDK is required for real Qwen-VL calls. Install via `pip install dashscope`."
            ) from exc

        try:
            from dashscope.common import error as dashscope_error  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "DashScope SDK is required for real Qwen-VL calls. Install via `pip install dashscope`."
            ) from exc

        DashScopeAPIError = getattr(
            dashscope_error,
            "DashScopeAPIError",
            getattr(dashscope_error, "DashScopeException", Exception),
        )

        content_items = [
            {
                "image": self._encode_image(asset),
                "name": asset.asset_id,
            }
            for asset in assets
        ]
        content_items.append({"text": self._build_prompt(origin_prompt)})

        messages = [
            {
                "role": "user",
                "content": content_items,
            }
        ]

        try:
            response = MultiModalConversation.call(
                model=self._model,
                messages=messages,
                api_key=self._api_key,
                timeout=self._timeout,
            )
        except DashScopeAPIError as err:
            raise RuntimeError(f"DashScope Qwen-VL call failed: {err}") from err

        description = self._extract_description(response)
        if not description:
            raise ValueError(f"Qwen API response missing description field: {json.dumps(response, ensure_ascii=False)}")
        return description.strip()

    def _encode_image(self, asset: Asset) -> str:
        """Return a data URL suitable for DashScope MultiModal input."""
        binary = read_binary(asset.local_path)
        mime_type, _ = mimetypes.guess_type(asset.local_path)
        mime = mime_type or "image/png"
        encoded = b64encode(binary)
        return f"data:{mime};base64,{encoded}"

    def _mock_description(self, assets: list[Asset], origin_prompt: str) -> str:
        """Deterministic local fallback used for testing."""
        names = [Path(asset.local_path).stem for asset in assets]
        unique_names = ", ".join(sorted(set(names))) or "pet"
        color_palette = self._guess_palette(names)
        lines: list[str] = [
            f"- 宠物参考: {unique_names}",
            "- 品种体型: 中小型幻想伴侣动物，姿态灵动",
            f"- 推荐调色: {color_palette}",
            "- 显著特征: 柔软长毛、表情丰富、常戴编织颈饰",
            "- 表情暗示: 眼睛闪烁微光，动作富有节奏",
            f"- 用户意图线索: {origin_prompt.strip() or '奇幻友好场景'}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_prompt(origin_prompt: str) -> str:
        base = origin_prompt.strip() or "请描述这只宠物的视觉特征。"
        return (
            f"{base}\n"
            "输出要点：\n"
            "- 品种与体型\n"
            "- 主要/次要毛色与建议 HEX 调色（2~4 个）\n"
            "- 花纹与显著特征\n"
            "- 常驻配饰/标记物\n"
            "- 常见表情与姿态关键词\n"
            "请使用丰富中文要点回复。"
        )

    @staticmethod
    def _extract_description(response) -> str | None:
        """Extract the textual description from DashScope responses."""
        data: dict | None
        if isinstance(response, dict):
            data = response
        elif hasattr(response, "to_dict"):
            data = response.to_dict()
        else:
            data = None

        if data is None and hasattr(response, "output"):
            data = {"output": getattr(response, "output")}

        if not data:
            return None

        output = data.get("output")
        if isinstance(output, dict):
            choices = output.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("text"):
                                return str(item["text"])
        # Fallback for other response styles
        return data.get("description") or data.get("result")

    @staticmethod
    def _guess_palette(names: list[str]) -> str:
        """Derive a soft palette suggestion from filenames."""
        if not names:
            return "暖金 #D6A85E, 暗红 #8B2F39, 月白 #F1F5F9"
        joined = " ".join(names).lower()
        if "cat" in joined or "kitten" in joined:
            return "暖橘 #D99058, 奶油 #F6E7D8, 星辉蓝 #5B7FA4"
        if "dog" in joined or "pup" in joined:
            return "琥珀 #C17F2B, 雪白 #F4F0EC, 森林绿 #295943"
        return "梦幻紫 #A485E2, 极光青 #4BC6B9, 珊瑚粉 #FF6F91"
