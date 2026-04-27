"""Optimize asciify.svg and embed it into profile SVG templates."""

import re
import struct
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from lxml.etree import _Element, _ElementTree, parse, SubElement, tostring

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

# Subsampling: target columns (rows derived from aspect ratio)
TARGET_COLS = 80

# Color quantization
NUM_COLORS = 256

# Animation
WAVE_DURATION = 6  # seconds for full wave cycle
WAVE_ROWS = 8  # how many row-groups for staggered animation
APNG_FRAMES = 30
APNG_FRAME_DELAY_MS = 100


def parse_asciify_svg(path: Path) -> tuple[list[list[tuple[int, int, str, str]]], int, int]:
    """Parse asciify.svg into a grid of (x, y, color, char) tuples.

    Returns:
        (elements_by_row, n_cols, n_rows)
    """
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
    ys = sorted(rows.keys())
    return sorted_rows, len(xs), len(ys)


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
    rows: list[list[tuple[int, int, str, str]]], orig_cols: int, orig_rows: int, target_cols: int
) -> list[list[tuple[tuple[int, int, int], str]]]:
    """Subsample the grid to target_cols, preserving aspect ratio.

    Returns list of rows, each row is list of (rgb, char).
    """
    col_step = max(1, orig_cols // target_cols)
    row_step = col_step  # keep square pixels
    target_rows = orig_rows // row_step

    result = []
    for ri in range(0, orig_rows, row_step):
        if ri >= len(rows):
            break
        row = rows[ri]
        sampled_row = []
        for ci in range(0, orig_cols, col_step):
            if ci < len(row):
                _, _, color, char = row[ci]
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
    # Also trim trailing empty rows
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    return trimmed


def quantize_colors(
    grid: list[list[tuple[tuple[int, int, int], str]]], n_colors: int
) -> tuple[list[list[tuple[int, str]]], list[tuple[int, int, int]]]:
    """Quantize colors using fine uniform binning.

    Returns (grid_with_indices, palette).
    """
    all_colors = []
    for row in grid:
        for rgb, _ in row:
            all_colors.append(rgb)
    arr = np.array(all_colors, dtype=np.float32)

    # Use 16 levels per channel for much better color fidelity
    levels = 16
    quantized = np.round(arr / 255 * (levels - 1)) * (255 / (levels - 1))
    quantized = np.clip(quantized, 0, 255).astype(np.uint8)

    # Build palette from unique quantized colors
    unique_map: dict[tuple[int, int, int], int] = {}
    palette: list[tuple[int, int, int]] = []
    indices = []
    for rgb in quantized:
        key = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if key not in unique_map:
            unique_map[key] = len(palette)
            palette.append(key)
        indices.append(unique_map[key])

    # Rebuild grid with palette indices
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
) -> str:
    """Generate SVG markup for the optimized portrait with wave animation.

    Returns SVG string to embed.
    """
    n_rows = len(grid)
    n_cols = max(len(r) for r in grid) if grid else 0

    # Monospace fonts: Consolas character cell is ~0.6em wide, ~1.2em tall
    # ConsolasFallback uses size-adjust: 109%, so effective width = 0.6 * 1.09
    char_w_ratio = 0.6 * 1.09  # ~0.654
    font_by_w = max_w / (n_cols * char_w_ratio)
    font_by_h = max_h / (n_rows * 1.2)
    font_size = min(font_by_w, font_by_h)
    line_height = font_size * 1.2

    lines = []

    # CSS classes for palette colors
    lines.append("/* Portrait palette */")
    for i, (r, g, b) in enumerate(palette):
        lines.append(f".p{i} {{fill:#{r:02x}{g:02x}{b:02x};}}")

    # Wave animation
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

    # Build text elements row by row
    text_lines = []
    for ri, row in enumerate(grid):
        y = y_offset + ri * line_height + line_height
        wave_class = f"w{ri % wave_rows}"

        # Group consecutive same-palette chars
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

    # Remove the old ASCII banner text block (the <text> with class="ascii")
    content = re.sub(
        r'<text x="15" y="25"[^>]*class="ascii"[^>]*>.*?</text>\s*',
        "",
        content,
        flags=re.DOTALL,
    )

    # Inject portrait CSS into existing <style> block
    content = content.replace(
        "text, tspan {white-space: pre;}",
        f"text, tspan {{white-space: pre;}}\n{portrait_css}",
    )

    # Inject portrait markup before the profile text block
    content = content.replace(
        '<text x="390"',
        f'{portrait_markup}\n<text x="390"',
        1,
    )

    with open(svg_path, "w") as f:
        f.write(content)


def make_apng(
    grid: list[list[tuple[int, str]]],
    palette: list[tuple[int, int, int]],
    bg_color: tuple[int, int, int],
    output_path: Path,
    n_frames: int,
    frame_delay_ms: int,
    wave_duration: float,
    wave_rows: int,
) -> None:
    """Render animated APNG of the portrait with wave effect."""
    n_grid_rows = len(grid)
    n_cols = max(len(r) for r in grid) if grid else 0

    # Scale: each cell = 4x4 pixels for a reasonable APNG size
    scale = 4
    img_w = n_cols * scale
    img_h = n_grid_rows * scale

    br, bg_, bb = bg_color
    frames_data = []

    for frame_i in range(n_frames):
        t = frame_i / n_frames  # 0..1 through the wave cycle

        # Build raw RGBA pixel data, pre-fill with background
        pixels = bytearray(img_w * img_h * 4)
        for i in range(img_w * img_h):
            pixels[i * 4] = br
            pixels[i * 4 + 1] = bg_
            pixels[i * 4 + 2] = bb
            pixels[i * 4 + 3] = 255

        for ri, row in enumerate(grid):
            wave_group = ri % wave_rows
            phase = (t - wave_group / wave_rows) % 1.0
            # Sine wave opacity: 0.6 to 1.0
            opacity = 0.6 + 0.4 * (0.5 + 0.5 * np.sin(2 * np.pi * phase))

            for ci, (palette_idx, _) in enumerate(row):
                r, g, b = palette[palette_idx]
                fr = int(r * opacity + br * (1 - opacity))
                fg = int(g * opacity + bg_ * (1 - opacity))
                fb = int(b * opacity + bb * (1 - opacity))

                for dy in range(scale):
                    for dx in range(scale):
                        px = ci * scale + dx
                        py = ri * scale + dy
                        if px < img_w and py < img_h:
                            offset = (py * img_w + px) * 4
                            pixels[offset] = fr
                            pixels[offset + 1] = fg
                            pixels[offset + 2] = fb

        frames_data.append((img_w, img_h, bytes(pixels)))

    _write_apng(frames_data, output_path, frame_delay_ms)


def _write_apng(
    frames: list[tuple[int, int, bytes]],
    output: Path,
    delay_ms: int,
) -> None:
    """Write frames as APNG file."""
    if not frames:
        return

    w, h, _ = frames[0]
    n_frames = len(frames)

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk + crc

    def compress_image_data(raw_rgba: bytes, width: int, height: int) -> bytes:
        """Apply PNG filtering (none filter) and deflate."""
        filtered = bytearray()
        row_len = width * 4
        for y in range(height):
            filtered.append(0)  # filter type: None
            filtered.extend(raw_rgba[y * row_len : (y + 1) * row_len])
        return zlib.compress(bytes(filtered), 9)

    out = bytearray()

    # PNG signature
    out.extend(b"\x89PNG\r\n\x1a\n")

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    out.extend(make_chunk(b"IHDR", ihdr_data))

    # acTL (animation control)
    actl_data = struct.pack(">II", n_frames, 0)  # num_frames, num_plays (0=infinite)
    out.extend(make_chunk(b"acTL", actl_data))

    seq_num = 0

    # First frame: fcTL + IDAT
    fctl_data = struct.pack(
        ">IIIIIHHBB",
        seq_num, w, h, 0, 0, delay_ms, 1000, 0, 0,
    )
    out.extend(make_chunk(b"fcTL", fctl_data))
    seq_num += 1

    compressed = compress_image_data(frames[0][2], w, h)
    out.extend(make_chunk(b"IDAT", compressed))

    # Subsequent frames: fcTL + fdAT
    for i in range(1, n_frames):
        fctl_data = struct.pack(
            ">IIIIIHHBB",
            seq_num, w, h, 0, 0, delay_ms, 1000, 0, 0,
        )
        out.extend(make_chunk(b"fcTL", fctl_data))
        seq_num += 1

        compressed = compress_image_data(frames[i][2], w, h)
        fdat_data = struct.pack(">I", seq_num) + compressed
        out.extend(make_chunk(b"fdAT", fdat_data))
        seq_num += 1

    # IEND
    out.extend(make_chunk(b"IEND", b""))

    output.write_bytes(bytes(out))


def main() -> None:
    print("Parsing asciify.svg...")
    rows, n_cols, n_rows = parse_asciify_svg(SOURCE_SVG)
    print(f"  Grid: {n_cols}x{n_rows} = {n_cols * n_rows} cells")

    print(f"Subsampling to ~{TARGET_COLS} columns...")
    grid = subsample_grid(rows, n_cols, n_rows, TARGET_COLS)
    actual_cols = max(len(r) for r in grid)
    print(f"  Result: {actual_cols}x{len(grid)}")

    print("Trimming background cells...")
    grid = trim_background(grid)
    actual_cols = max(len(r) for r in grid) if grid else 0
    print(f"  After trim: {actual_cols}x{len(grid)}")

    print(f"Quantizing to {NUM_COLORS} colors...")
    indexed_grid, palette = quantize_colors(grid, NUM_COLORS)
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

    # File size check
    for svg_file in TARGET_SVGS:
        size = Path(svg_file).stat().st_size
        print(f"  {svg_file}: {size / 1024:.1f} KB")

    print("Generating APNGs...")
    for apng_path, bg, label in [
        (APNG_DARK, (22, 27, 34), "dark"),    # #161b22
        (APNG_LIGHT, (246, 248, 250), "light"),  # #f6f8fa
    ]:
        make_apng(
            indexed_grid,
            palette,
            bg,
            apng_path,
            APNG_FRAMES,
            APNG_FRAME_DELAY_MS,
            WAVE_DURATION,
            WAVE_ROWS,
        )
        size = apng_path.stat().st_size
        print(f"  {apng_path} ({label}): {size / 1024:.1f} KB")

    print("Done!")


if __name__ == "__main__":
    main()
