"""Command-line entry point for the PetVideoGenerator pipeline."""

from __future__ import annotations

import argparse
import sys

from pvgen.pipeline import PetVideoGenerator


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate a mock pet video run.")
    parser.add_argument("origin_prompt", help="Desired storyline or theme.")
    parser.add_argument(
        "image_paths",
        nargs="+",
        help="Paths to reference pet images.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Target duration for the final video (seconds).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=24,
        help="Frame rate for the generated video segments.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``python run.py``."""
    args = parse_args(argv or sys.argv[1:])
    pipeline = PetVideoGenerator()
    state = pipeline.run(
        image_paths=args.image_paths,
        origin_prompt=args.origin_prompt,
        target_duration_sec=args.duration,
        fps=args.fps,
    )
    print("Generation completed.")
    print(f"Final video asset: {state.final_video.local_path if state.final_video else 'N/A'}")
    print(f"Report stored alongside other run logs in outputs/ and runs/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
