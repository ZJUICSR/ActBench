#!/usr/bin/env python3
"""Compose the three refreshed execution-cost panels into the paper figure."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration", type=Path, required=True)
    parser.add_argument("--agent-time", type=Path, required=True)
    parser.add_argument("--model-tokens", type=Path, required=True)
    parser.add_argument("--out-pdf", type=Path, required=True)
    parser.add_argument("--out-png", type=Path)
    return parser.parse_args()


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def resize_to_width(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def main() -> int:
    args = parse_args()
    iteration = load_rgb(args.iteration)
    agent_time = load_rgb(args.agent_time)
    model_tokens = load_rgb(args.model_tokens)

    canvas_width = 3200
    gap = 40
    label_height = 56
    panel_width = (canvas_width - gap) // 2
    top_iteration = resize_to_width(iteration, panel_width)
    top_agent = resize_to_width(agent_time, panel_width)
    top_height = max(top_iteration.height, top_agent.height)
    bottom = resize_to_width(model_tokens, canvas_width)
    canvas_height = label_height + top_height + gap + label_height + bottom.height
    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(canvas)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(font_path, 40)

    draw.text((16, 6), "(a) RQ1 action cycles", fill="black", font=font)
    draw.text((panel_width + gap + 16, 6), "(b) RQ2 execution time", fill="black", font=font)
    top_y = label_height
    canvas.paste(top_iteration, (0, top_y + (top_height - top_iteration.height) // 2))
    canvas.paste(
        top_agent,
        (panel_width + gap, top_y + (top_height - top_agent.height) // 2),
    )

    bottom_label_y = label_height + top_height + gap
    draw.text((16, bottom_label_y + 6), "(c) RQ1 total token usage", fill="black", font=font)
    canvas.paste(bottom, (0, bottom_label_y + label_height))

    args.out_pdf.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.out_pdf, "PDF", resolution=450.0)
    if args.out_png is not None:
        args.out_png.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(args.out_png, "PNG")
    print(f"Wrote composite figure: {args.out_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
