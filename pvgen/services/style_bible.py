"""Utility to craft a simple style bible from the pet description."""

from __future__ import annotations

from textwrap import dedent


class StyleBibleGenerator:
    """Transforms feature highlights into a structured natural-language brief."""

    def create(self, description: str, origin_prompt: str) -> str:
        """Return a multi-paragraph style bible description."""
        prompt_reference = origin_prompt.strip() or "奇幻宠物短片"
        return dedent(
            f"""
            角色与性格：活泼而好奇的幻想伴侣，始终佩戴编织围巾，眼神清澈灵动。
            色彩与光照：主色调保持暖金与奶油白，辅以星辉蓝点缀高光，常见柔和逆光。
            画风与镜头：平滑赛璐珞上色搭配干净线稿，镜头偏向 dolly-in 与柔和摇摄。
            背景与道具：漂浮石阶、镜面湖泊与星屑植物贯穿始终，围巾与能量球作为主要道具。
            负面约束：避免现代城市元素，禁止夸张机械装甲或写实血腥氛围。
            描述参考：{description}
            用户意图：{prompt_reference}
            """
        ).strip()
