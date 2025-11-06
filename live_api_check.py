#!/usr/bin/env python3
"""Run live connectivity checks against Qwen, DeepSeek, and Jimeng services."""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Iterable, List, Sequence

from pvgen.services.deepseek import DeepSeekClient
from pvgen.services.jimeng import JimengClient
from pvgen.services.qwen import QwenClient
from pvgen.types import Asset


def _load_assets(image_paths: Sequence[str]) -> List[Asset]:
    assets: List[Asset] = []
    for idx, raw_path in enumerate(image_paths):
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Qwen reference image not found: {raw_path}")
        assets.append(
            Asset(
                asset_id=f"asset_{idx}",
                media_type="image",
                local_path=str(path),
            )
        )
    return assets


def run_qwen_test(api_key: str, api_url: str | None, image_paths: Sequence[str], origin_prompt: str) -> str:
    if not image_paths:
        raise ValueError("Qwen test requires at least one reference image provided via --qwen-images.")
    client = QwenClient(api_key=api_key, api_url=api_url, use_mock=False)
    assets = _load_assets(image_paths)
    return client.describe_pet(assets, origin_prompt)


def run_deepseek_test(
    api_key: str,
    api_url: str | None,
    origin_prompt: str,
    description: str,
    style_bible: str,
    target_duration: int,
) -> list[dict]:
    client = DeepSeekClient(api_key=api_key, api_url=api_url, use_mock=False)
    return client.generate_storyboard(origin_prompt, description, style_bible, target_duration)


def run_jimeng_test(
    api_key: str,
    api_secret: str | None,
    api_url: str | None,
    assets_dir: str,
    run_id: str,
    description: str,
    style_brief: str,
    prompt: str,
) -> Asset:
    client = JimengClient(
        assets_dir=assets_dir,
        api_key=api_key,
        api_secret=api_secret,
        api_url=api_url,
        use_mock=False,
    )
    segment_payload = {
        "segment_id": "connectivity_demo",
        "prompt": prompt,
        "style": style_brief,
        "camera": "medium shot, slow dolly",
        "props_bg": ["soft rim light", "floating particles"],
        "consistency_flags": ["preserve primary pet palette"],
    }
    return client.generate_keyframe(
        run_id=run_id,
        index=0,
        description=description,
        style_brief=style_brief,
        segment_payload=segment_payload,
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Smoke-test connectivity for Qwen, DeepSeek, and Jimeng services.
            Each check only runs when the corresponding --*-key argument is supplied; otherwise it is skipped.
            """
        ),
    )

    parser.add_argument("--origin-prompt", default="A brave kitten embarks on a magical journey.", help="Shared origin prompt for Qwen and DeepSeek.")

    parser.add_argument("--qwen-key", help="Qwen DashScope API key")
    parser.add_argument("--qwen-url", help="Optional custom Qwen API URL.")
    parser.add_argument("--qwen-images", nargs="+", help="Reference images for Qwen, at least one path.")

    parser.add_argument(
        "--deepseek-key",
        help="DeepSeek API key (OpenAI-compatible).",
    )
    parser.add_argument("--deepseek-url", help="DeepSeek API base URL, defaults to https://api.deepseek.com/v1.")
    parser.add_argument(
        "--deepseek-description",
        default="- Reference: demo\n- Body: fantasy cat\n- Highlight: long fur with glowing scarf",
        help="Fallback pet description for DeepSeek; override or reuse Qwen output.",
    )
    parser.add_argument(
        "--deepseek-style",
        default="Soft volumetric light, ethereal glitter, cinematic grade.",
        help="Style bible summary passed to DeepSeek.",
    )
    parser.add_argument("--target-duration", type=int, default=30, help="DeepSeek target duration in seconds.")

    parser.add_argument("--jimeng-key", help="Jimeng API key (AK or AK:SK).")
    parser.add_argument("--jimeng-secret", help="Jimeng API secret when --jimeng-key is not AK:SK.")
    parser.add_argument("--jimeng-url", help="Jimeng API base URL.")
    parser.add_argument(
        "--jimeng-assets-dir",
        default="assets",
        help="Directory for Jimeng outputs, defaults to project assets.",
    )
    parser.add_argument(
        "--jimeng-style",
        default="Soft illustrative look with warm gold and aurora accents.",
        help="Style brief passed to Jimeng keyframe call.",
    )
    parser.add_argument(
        "--jimeng-description",
        default="The pet spins through stardust with a glowing scarf and curious expression.",
        help="Description used for Jimeng keyframe generation.",
    )
    parser.add_argument(
        "--jimeng-prompt",
        default="Generate a hero keyframe for the pet character with energetic lighting.",
        help="Prompt sent to Jimeng keyframe generation.",
    )
    parser.add_argument("--run-id", default="live_api_check", help="Run identifier used for Jimeng requests.")

    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    results: list[tuple[str, bool, str]] = []

    if args.qwen_key:
        try:
            description = run_qwen_test(args.qwen_key, args.qwen_url, args.qwen_images or [], args.origin_prompt)
            results.append(("Qwen", True, description))
        except Exception as exc:  # noqa: BLE001 - surface connectivity failures
            results.append(("Qwen", False, repr(exc)))
    else:
        results.append(("Qwen", False, "Skipped (no --qwen-key provided)"))

    if args.deepseek_key:
        description = args.deepseek_description
        if results and results[0][0] == "Qwen" and results[0][1]:
            description = results[0][2]
        try:
            storyboard = run_deepseek_test(
                args.deepseek_key,
                args.deepseek_url,
                args.origin_prompt,
                description,
                args.deepseek_style,
                args.target_duration,
            )
            detail = f"Received {len(storyboard)} storyboard segments."
            results.append(("DeepSeek", True, detail))
        except Exception as exc:  # noqa: BLE001
            results.append(("DeepSeek", False, repr(exc)))
    else:
        results.append(("DeepSeek", False, "Skipped (no --deepseek-key provided)"))

    if args.jimeng_key:
        try:
            asset = run_jimeng_test(
                args.jimeng_key,
                args.jimeng_secret,
                args.jimeng_url,
                args.jimeng_assets_dir,
                args.run_id,
                args.jimeng_description,
                args.jimeng_style,
                args.jimeng_prompt,
            )
            detail = f"Created asset {asset.asset_id} at {asset.local_path}"
            results.append(("Jimeng", True, detail))
        except Exception as exc:  # noqa: BLE001
            results.append(("Jimeng", False, repr(exc)))
    else:
        results.append(("Jimeng", False, "Skipped (no --jimeng-key provided)"))

    any_failure = False
    for name, ok, detail in results:
        status = "SUCCESS" if ok else "FAIL"
        print(f"[{name}] {status}: {detail}")
        if not ok and "Skipped" not in detail:
            any_failure = True

    return 0 if not any_failure else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
