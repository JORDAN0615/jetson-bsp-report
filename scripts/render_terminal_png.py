#!/usr/bin/env python3
"""Render terminal transcript text into a deterministic PNG evidence image."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


PROMPT_RE = re.compile(r"^(?P<user>[^@\s]+@[^:]+):(?P<path>[^$#]+)(?P<mark>[$#]) (?P<cmd>.*)$")
BLOCK_DEVICE_RE = re.compile(r"block/sd[a-z]+")


@dataclass
class Theme:
    width: int = 1420
    padding_x: int = 10
    padding_y: int = 8
    font_size: int = 25
    line_gap: int = 7
    background: str = "#0a0a0a"
    prompt: str = "#24b324"
    path: str = "#2d6ee8"
    command: str = "#d0d0d0"
    output: str = "#e84057"
    highlight: str = "#ff1f1f"


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def demo_usb3_transcript() -> str:
    commands = [
        "sudo cat /sys/bus/usb/devices/2-3.1/bMaxPacketSize0 | grep 9",
        "sudo cat /sys/bus/usb/devices/2-3.2/bMaxPacketSize0 | grep 9",
        "sudo cat /sys/bus/usb/devices/2-3.3/bMaxPacketSize0 | grep 9",
        "sudo cat /sys/bus/usb/devices/2-3.4/bMaxPacketSize0 | grep 9",
        "sudo cat /sys/bus/usb/devices/2-1.4/bMaxPacketSize0 | grep 9",
        "sudo cat /sys/bus/usb/devices/2-1.3/bMaxPacketSize0 | grep 9",
    ]
    lines: list[str] = []
    for command in commands:
        lines.append(f"mic-741@ubuntu:/$ {command}")
        lines.append("9")
    return "\n".join(lines) + "\n"


def demo_usb3_block_results(mixed: bool = False) -> list[dict[str, Any]]:
    if mixed:
        devices = [
            ("2-3.1", "/sys/bus/usb/devices/2-3.1/2-3.1:1.0/host0/target0:0:0/0:0:0:0/block/sda"),
            ("2-3.2", ""),
            ("2-3.3", "/sys/bus/usb/devices/2-3.3/2-3.3:1.0/host1/target1:0:0/1:0:0:0/block/sdb"),
            ("2-3.4", "find: '/sys/bus/usb/devices/2-3.4/': No such file or directory"),
            ("2-1.3", "/sys/bus/usb/devices/2-1.3/2-1.3:1.0/host2/target2:0:0/2:0:0:0/block/sdc"),
            ("2-1.4", ""),
        ]
    else:
        devices = [
            ("2-3.1", "/sys/bus/usb/devices/2-3.1/2-3.1:1.0/host0/target0:0:0/0:0:0:0/block/sda"),
            ("2-3.2", "/sys/bus/usb/devices/2-3.2/2-3.2:1.0/host1/target1:0:0/1:0:0:0/block/sdb"),
            ("2-3.3", "/sys/bus/usb/devices/2-3.3/2-3.3:1.0/host2/target2:0:0/2:0:0:0/block/sdc"),
            ("2-3.4", "/sys/bus/usb/devices/2-3.4/2-3.4:1.0/host3/target3:0:0/3:0:0:0/block/sdd"),
            ("2-1.3", "/sys/bus/usb/devices/2-1.3/2-1.3:1.0/host4/target4:0:0/4:0:0:0/block/sde"),
            ("2-1.4", "/sys/bus/usb/devices/2-1.4/2-1.4:1.0/host5/target5:0:0/5:0:0:0/block/sdf"),
        ]
    results: list[dict[str, Any]] = []
    for device, output in devices:
        command = f"sudo find /sys/bus/usb/devices/{device}/ | grep block/sd.$"
        results.append(
            {
                "prompt": "mic-741@ubuntu:/$",
                "command": command,
                "stdout": output,
                "stderr": "",
                "exit_code": 0 if BLOCK_DEVICE_RE.search(output) else 1,
            }
        )
    return results


def result_to_transcript(result: dict[str, Any]) -> str:
    prompt = result.get("prompt") or "mic-741@ubuntu:/$"
    command = result.get("command") or ""
    lines = [f"{prompt} {command}".rstrip()]
    for key in ("stdout", "stderr"):
        value = result.get(key) or ""
        if isinstance(value, list):
            lines.extend(str(item) for item in value)
        else:
            lines.extend(str(value).splitlines())
    return "\n".join(lines) + "\n"


def text_width(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def text_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def draw_prompt_line(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    line: str,
    theme: Theme,
) -> None:
    match = PROMPT_RE.match(line)
    if not match:
        draw.text((x, y), line, fill=theme.command, font=font)
        return

    user = match.group("user")
    path = match.group("path")
    mark = match.group("mark")
    cmd = match.group("cmd")

    segments = [
        (user + ":", theme.prompt),
        (path, theme.path),
        (mark + " ", theme.command),
        (cmd, theme.command),
    ]
    cursor = x
    for text, color in segments:
        draw.text((cursor, y), text, fill=color, font=font)
        cursor += text_width(draw, font, text)


def draw_line_with_token_highlights(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    line: str,
    theme: Theme,
    token_re: re.Pattern[str],
) -> None:
    cursor = x
    last = 0
    for match in token_re.finditer(line):
        before = line[last : match.start()]
        if before:
            draw.text((cursor, y), before, fill=theme.command, font=font)
            cursor += text_width(draw, font, before)
        token = match.group(0)
        draw.text((cursor, y), token, fill=theme.output, font=font)
        cursor += text_width(draw, font, token)
        last = match.end()
    rest = line[last:]
    if rest:
        draw.text((cursor, y), rest, fill=theme.command, font=font)


def render_terminal_png(
    transcript: str,
    output: Path,
    theme: Theme,
    highlight_regex: str,
    highlight_mode: str = "line-box",
) -> None:
    lines = transcript.splitlines()
    font = load_font(theme.font_size)
    probe = Image.new("RGB", (10, 10))
    probe_draw = ImageDraw.Draw(probe)
    line_height = text_height(probe_draw, font, "mic-741@ubuntu:/$") + theme.line_gap
    height = theme.padding_y * 2 + line_height * max(len(lines), 1)

    image = Image.new("RGB", (theme.width, height), theme.background)
    draw = ImageDraw.Draw(image)
    highlight_re = re.compile(highlight_regex)

    highlight_boxes: list[tuple[int, int, int, int]] = []
    y = theme.padding_y
    for line in lines:
        if highlight_re.search(line) and highlight_mode == "line-box":
            draw.text((theme.padding_x, y), line, fill=theme.output, font=font)
            w = text_width(draw, font, line)
            highlight_boxes.append(
                (
                    theme.padding_x - 4,
                    y - 4,
                    theme.padding_x + w + 4,
                    y + line_height - theme.line_gap + 4,
                )
            )
        elif highlight_re.search(line) and highlight_mode == "token":
            draw_line_with_token_highlights(draw, font, theme.padding_x, y, line, theme, highlight_re)
        else:
            draw_prompt_line(draw, font, theme.padding_x, y, line, theme)
        y += line_height

    if highlight_boxes and highlight_mode == "line-box":
        left = min(b[0] for b in highlight_boxes)
        top = min(b[1] for b in highlight_boxes)
        right = max(b[2] for b in highlight_boxes)
        bottom = max(b[3] for b in highlight_boxes)
        draw.rectangle((left, top, right, bottom), outline=theme.highlight, width=5)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def render_results(
    results: list[dict[str, Any]],
    output_dir: Path,
    theme: Theme,
    highlight_regex: str,
    highlight_mode: str,
    prefix: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, result in enumerate(results, start=1):
        output = output_dir / f"{prefix}_{index}.png"
        render_terminal_png(result_to_transcript(result), output, theme, highlight_regex, highlight_mode)
        paths.append(output)
    return paths


def read_transcript(args: argparse.Namespace) -> str:
    if args.demo == "usb3":
        return demo_usb3_transcript()
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    raise SystemExit("Either --demo usb3 or --input is required.")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Transcript text file.")
    parser.add_argument("--results-json", help="JSON list of command result objects.")
    parser.add_argument("--output", help="Output PNG path.")
    parser.add_argument("--output-dir", help="Output directory for multiple PNGs.")
    parser.add_argument("--prefix", default="terminal", help="Filename prefix for --output-dir mode.")
    parser.add_argument(
        "--demo",
        choices=["usb3", "usb3-block", "usb3-block-mixed"],
        help="Render built-in demo evidence. Mixed block demo is for fail-path testing only.",
    )
    parser.add_argument("--highlight-regex", default=r"^9$", help="Regex for highlighted output lines.")
    parser.add_argument("--highlight-mode", choices=["line-box", "token"], default="line-box")
    parser.add_argument("--width", type=int, default=1420)
    parser.add_argument("--font-size", type=int, default=25)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    theme = Theme(width=args.width, font_size=args.font_size)
    if args.demo in {"usb3-block", "usb3-block-mixed"}:
        if not args.output_dir:
            raise SystemExit(f"--demo {args.demo} requires --output-dir.")
        paths = render_results(
            demo_usb3_block_results(mixed=args.demo == "usb3-block-mixed"),
            Path(args.output_dir),
            theme,
            args.highlight_regex,
            args.highlight_mode,
            args.prefix,
        )
        for path in paths:
            print(path)
        return

    if args.results_json:
        if not args.output_dir:
            raise SystemExit("--results-json requires --output-dir.")
        results = json.loads(Path(args.results_json).read_text(encoding="utf-8"))
        if not isinstance(results, list):
            raise SystemExit("--results-json must contain a JSON list.")
        paths = render_results(results, Path(args.output_dir), theme, args.highlight_regex, args.highlight_mode, args.prefix)
        for path in paths:
            print(path)
        return

    if not args.output:
        raise SystemExit("--output is required for single transcript rendering.")
    transcript = read_transcript(args)
    render_terminal_png(transcript, Path(args.output), theme, args.highlight_regex, args.highlight_mode)


if __name__ == "__main__":
    main()
