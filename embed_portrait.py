"""Optimize asciify.svg, embed in profile SVGs, render full-card animated APNGs.

Strategy for APNG: render the static stats panel once, then composite
animated portrait frames on top so the wave effect only touches the portrait.
"""

import io
import math
import re
from collections import defaultdict
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image

# --- Configuration ---
SOURCE_SVG = Path("asciify.svg")
TARGET_SVGS = ("dark_mode.svg", "light_mode.svg")
APNG_DARK = Path("dark_mode.apng")
APNG_LIGHT = Path("light_mode.apng")

# Portrait placement in the profile SVG
PORTRAIT_X = 15
PORTRAIT_Y = 25
PORTRAIT_MAX_W = 365
PORTRAIT_MAX_H = 420

# Subsampling
TARGET_COLS = 80

# Animation
WAVE_DURATION = 6  # seconds for full wave cycle
WAVE_ROWS = 8  # how many row-groups for staggered animation
APNG_FRAMES = 20
APNG_FRAME_DELAY_MS = 150

# Original asciify.svg cell spacing
ORIG_X_STEP = 6
ORIG_Y_STEP = 12

# Font metrics for ConsolasFallback (size-adjust: 109%)
CHAR_W_RATIO = 0.6 * 1.09  # ~0.654
LINE_H_RATIO = 1.2

# Render dimensions
RENDER_W = 1024
RENDER_H = 920


def parse_asciify_svg(path: Path) -> tuple[list[list[tuple[int, int, str, str]]], int, int]:
    """Parse asciify.svg into a grid of (x, y, color, char) tuples."""
    with open(path) as f:
        content = f.read()

    elements = re.findall(
        r'<text x="(\d+)" y="(\d+)" fill="([^"]+)" text-anchor="middle">([^<]+)</text>',
        content,
    )
    rows: dict[int, list[tuple[int, int, str, str]]] = defaultdict(list)
    for x_s, y_s, color, char in elements:
        rows[int(y_s)].append((int(x_s), int(y_s), color, char))

    sorted_rows = [rows[y] for y in sorted(rows.keys())]
    for row in sorted_rows:
        row.sort(key=lambda e: e[0])

    xs = sorted({e[0] for row in sorted_rows for e in row})
    return sorted_rows, len(xs), len(sorted_rows)


def parse_rgb(color_str: str) -> tuple[int, int, int]:
    """Parse 'rgb(r,g,b)' string to integer tuple."""
    m = re.match(r"rgb\(([^,]+),([^,]+),([^)]+)\)", color_str)
    if m:
        return (
            min(255, max(0, round(float(m.group(1))))),
            min(255, max(0, round(float(m.group(2))))),
            min(255, max(0, round(float(m.group(3))))),
        )
    return (0, 0, 0)


def subsample_grid(
    rows: list[list[tuple[int, int, str, str]]],
    orig_cols: int,
    orig_rows: int,
    target_cols: int,
) -> list[list[tuple[tuple[int, int, int], str]]]:
    """Subsample the grid, preserving the original image aspect ratio."""
    img_w = orig_cols * ORIG_X_STEP
    img_h = orig_rows * ORIG_Y_STEP

    target_rows = round(target_cols * CHAR_W_RATIO * img_h / (LINE_H_RATIO * img_w))
    target_rows = max(1, min(target_rows, orig_rows))

    result = []
    for ri in range(target_rows):
        src_ri = round(ri * (orig_rows - 1) / (target_rows - 1)) if target_rows > 1 else 0
        if src_ri >= len(rows):
            break
        row = rows[src_ri]
        sampled_row = []
        for ci in range(target_cols):
            src_ci = round(ci * (orig_cols - 1) / (target_cols - 1)) if target_cols > 1 else 0
            if src_ci < len(row):
                _, _, color, char = row[src_ci]
                sampled_row.append((parse_rgb(color), char))
            else:
                sampled_row.append(((0, 0, 0), " "))
        result.append(sampled_row)
    return result


def trim_background(
    grid: list[list[tuple[tuple[int, int, int], str]]],
    bg_threshold: int = 15,
) -> list[list[tuple[tuple[int, int, int], str]]]:
    """Remove trailing near-black cells from each row."""
    trimmed = []
    for row in grid:
        last_visible = -1
        for i, (rgb, _) in enumerate(row):
            if sum(rgb) > bg_threshold:
                last_visible = i
        trimmed.append(row[: last_visible + 1] if last_visible >= 0 else [])
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    return trimmed


def quantize_colors(
    grid: list[list[tuple[tuple[int, int, int], str]]],
) -> tuple[list[list[tuple[int, str]]], list[tuple[int, int, int]]]:
    """Quantize colors using fine uniform binning (16 levels per channel)."""
    all_colors = []
    for row in grid:
        for rgb, _ in row:
            all_colors.append(rgb)
    arr = np.array(all_colors, dtype=np.float32)

    levels = 16
    quantized = np.round(arr / 255 * (levels - 1)) * (255 / (levels - 1))
    quantized = np.clip(quantized, 0, 255).astype(np.uint8)

    unique_map: dict[tuple[int, int, int], int] = {}
    palette: list[tuple[int, int, int]] = []
    indices = []
    for rgb in quantized:
        key = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if key not in unique_map:
            unique_map[key] = len(palette)
            palette.append(key)
        indices.append(unique_map[key])

    idx = 0
    result = []
    for row in grid:
        result_row = []
        for _, char in row:
            result_row.append((indices[idx], char))
            idx += 1
        result.append(result_row)

    return result, palette


def generate_portrait_svg_snippet(
    grid: list[list[tuple[int, str]]],
    palette: list[tuple[int, int, int]],
    x_offset: int,
    y_offset: int,
    max_w: int,
    max_h: int,
    wave_duration: float,
    wave_rows: int,
) -> tuple[str, str]:
    """Generate SVG markup for the optimized portrait with wave animation."""
    n_rows = len(grid)
    n_cols = max(len(r) for r in grid) if grid else 0

    font_by_w = max_w / (n_cols * CHAR_W_RATIO)
    font_by_h = max_h / (n_rows * LINE_H_RATIO)
    font_size = min(font_by_w, font_by_h)
    line_height = font_size * LINE_H_RATIO

    lines = []
    lines.append("/* Portrait palette */")
    for i, (r, g, b) in enumerate(palette):
        lines.append(f".p{i} {{fill:#{r:02x}{g:02x}{b:02x};}}")

    lines.append(f"""
@keyframes wave {{
  0%, 100% {{ opacity: 1; }}
  50% {{ opacity: 0.6; }}
}}""")

    for i in range(wave_rows):
        delay = (wave_duration / wave_rows) * i
        lines.append(
            f".w{i} {{animation: wave {wave_duration}s ease-in-out {delay:.2f}s infinite;}}"
        )

    css = "\n".join(lines)

    text_lines = []
    for ri, row in enumerate(grid):
        y = y_offset + ri * line_height + line_height
        wave_class = f"w{ri % wave_rows}"

        groups: list[tuple[int, str]] = []
        for palette_idx, char in row:
            if groups and groups[-1][0] == palette_idx:
                groups[-1] = (palette_idx, groups[-1][1] + char)
            else:
                groups.append((palette_idx, char))

        spans = []
        for palette_idx, text in groups:
            spans.append(f'<tspan class="p{palette_idx}">{text}</tspan>')

        text_lines.append(
            f'<text x="{x_offset}" y="{y:.1f}" font-size="{font_size:.2f}px" '
            f'class="{wave_class}">{"".join(spans)}</text>'
        )

    return css, "\n".join(text_lines)


def embed_in_profile_svg(
    svg_path: str,
    portrait_css: str,
    portrait_markup: str,
) -> None:
    """Replace the ASCII banner in a profile SVG with the portrait."""
    with open(svg_path) as f:
        content = f.read()

    content = re.sub(
        r'<text x="15" y="25"[^>]*class="ascii"[^>]*>.*?</text>\s*',
        "",
        content,
        flags=re.DOTALL,
    )

    content = content.replace(
        "text, tspan {white-space: pre;}",
        f"text, tspan {{white-space: pre;}}\n{portrait_css}",
    )

    content = content.replace(
        '<text x="390"',
        f'{portrait_markup}\n<text x="390"',
        1,
    )

    with open(svg_path, "w") as f:
        f.write(content)


def _svg_to_pil(svg_content: str, width: int, height: int) -> Image.Image:
    """Render SVG string to a Pillow RGB image."""
    png_bytes = cairosvg.svg2png(
        bytestring=svg_content.encode("utf-8"),
        output_width=width,
        output_height=height,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def render_svg_to_apng(
    svg_path: str,
    output_path: Path,
    n_frames: int,
    frame_delay_ms: int,
    wave_duration: float,
    wave_rows: int,
) -> None:
    """Render the full profile SVG to animated APNG.

    The stats panel is rendered once as a static layer. The portrait is
    rendered per-frame with varying opacity, then composited on top.
    Only the portrait area animates; everything else stays crisp.
    """
    with open(svg_path) as f:
        svg_content = f.read()

    # --- 1. Render static base: SVG with portrait at full opacity, no animation ---
    static_svg = svg_content
    for i in range(wave_rows):
        delay = (wave_duration / wave_rows) * i
        old_rule = (
            f".w{i} {{animation: wave {wave_duration}s "
            f"ease-in-out {delay:.2f}s infinite;}}"
        )
        static_svg = static_svg.replace(old_rule, f".w{i} {{opacity: 1;}}")
    base_img = _svg_to_pil(static_svg, RENDER_W, RENDER_H)

    # --- 2. Render a version with portrait hidden (opacity 0) for the static layer ---
    no_portrait_svg = svg_content
    for i in range(wave_rows):
        delay = (wave_duration / wave_rows) * i
        old_rule = (
            f".w{i} {{animation: wave {wave_duration}s "
            f"ease-in-out {delay:.2f}s infinite;}}"
        )
        no_portrait_svg = no_portrait_svg.replace(old_rule, f".w{i} {{opacity: 0;}}")
    static_layer = _svg_to_pil(no_portrait_svg, RENDER_W, RENDER_H)

    # --- 3. For each frame, render portrait at its wave opacity and composite ---
    frames: list[Image.Image] = []

    for frame_i in range(n_frames):
        t = frame_i / n_frames * wave_duration

        frame_svg = svg_content
        for i in range(wave_rows):
            delay = (wave_duration / wave_rows) * i
            elapsed = t - delay
            phase = (elapsed % wave_duration) / wave_duration
            opacity = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * phase))

            old_rule = (
                f".w{i} {{animation: wave {wave_duration}s "
                f"ease-in-out {delay:.2f}s infinite;}}"
            )
            frame_svg = frame_svg.replace(old_rule, f".w{i} {{opacity: {opacity:.3f};}}")

        portrait_frame = _svg_to_pil(frame_svg, RENDER_W, RENDER_H)

        # Composite: start with static layer (portrait hidden), paste portrait frame on top
        # The static layer has full stats but no portrait; the portrait frame has both.
        # We use the static layer as base and only take the portrait region from the frame.
        composite = static_layer.copy()
        # Portrait region: left side of the card (x=0..385, y=0..RENDER_H)
        portrait_box = (0, 0, 385, RENDER_H)
        portrait_region = portrait_frame.crop(portrait_box)
        composite.paste(portrait_region, portrait_box)

        frames.append(composite.convert("RGB"))

    # Save as APNG (full quality, no palette reduction)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=frame_delay_ms,
        loop=0,
    )


def main() -> None:
    print("Parsing asciify.svg...")
    rows, n_cols, n_rows = parse_asciify_svg(SOURCE_SVG)
    print(f"  Grid: {n_cols}x{n_rows} = {n_cols * n_rows} cells")

    print(f"Subsampling to ~{TARGET_COLS} columns (aspect-corrected)...")
    grid = subsample_grid(rows, n_cols, n_rows, TARGET_COLS)
    actual_cols = max(len(r) for r in grid)
    print(f"  Result: {actual_cols}x{len(grid)}")

    print("Trimming background cells...")
    grid = trim_background(grid)
    actual_cols = max(len(r) for r in grid) if grid else 0
    print(f"  After trim: {actual_cols}x{len(grid)}")

    print("Quantizing colors...")
    indexed_grid, palette = quantize_colors(grid)
    print(f"  Palette: {len(palette)} colors")

    print("Generating portrait SVG snippet...")
    portrait_css, portrait_markup = generate_portrait_svg_snippet(
        indexed_grid,
        palette,
        PORTRAIT_X,
        PORTRAIT_Y,
        PORTRAIT_MAX_W,
        PORTRAIT_MAX_H,
        WAVE_DURATION,
        WAVE_ROWS,
    )
    print(f"  CSS: {len(portrait_css)} chars, Markup: {len(portrait_markup)} chars")

    for svg_file in TARGET_SVGS:
        print(f"Embedding in {svg_file}...")
        embed_in_profile_svg(svg_file, portrait_css, portrait_markup)
        size = Path(svg_file).stat().st_size
        print(f"  {svg_file}: {size / 1024:.1f} KB")

    print("Rendering full-card APNGs (portrait animated, stats static)...")
    for svg_file, apng_path in [
        ("dark_mode.svg", APNG_DARK),
        ("light_mode.svg", APNG_LIGHT),
    ]:
        render_svg_to_apng(
            svg_file,
            apng_path,
            APNG_FRAMES,
            APNG_FRAME_DELAY_MS,
            WAVE_DURATION,
            WAVE_ROWS,
        )
        size = apng_path.stat().st_size
        print(f"  {apng_path}: {size / 1024:.1f} KB")

    print("Done!")


if __name__ == "__main__":
    main()
