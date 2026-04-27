"""SVG template rewriting."""

import datetime

from lxml.etree import SubElement, _Element, _ElementTree, parse

from profilegen import config
from profilegen.formatting import format_compact_number, format_display_text

SVG_NS = "http://www.w3.org/2000/svg"

# GitHub Octicon paths (16x16 viewbox)
ICON_PATHS = {
    "commit": (
        "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32"
        "a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.25"
        "a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z"
    ),
    "pr": (
        "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0"
        "V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1"
        " 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0"
        "V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427"
        "a.25.25 0 0 1 0-.354ZM3.75 2.5a.75.75 0 1 0 0 1.5.75.75 0 0 0"
        " 0-1.5Zm0 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm8.25.75"
        "a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Z"
    ),
    "issue": (
        "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM8 0a8 8 0 1 1 0 16"
        "A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z"
    ),
    "review": (
        "M8 2c1.981 0 3.671.992 4.933 2.078 1.27 1.091 2.187 2.345 2.637"
        " 3.023a1.62 1.62 0 0 1 0 1.798c-.45.678-1.367 1.932-2.637 3.023"
        "C11.671 13.008 9.981 14 8 14s-3.671-.992-4.933-2.078C1.797 10.831"
        ".88 9.577.43 8.899a1.62 1.62 0 0 1 0-1.798c.45-.678 1.367-1.932"
        " 2.637-3.023C4.329 2.992 6.019 2 8 2ZM1.679 7.932a.12.12 0 0 0 0"
        " .136c.411.622 1.241 1.75 2.366 2.717C5.176 11.758 6.527 12.5 8"
        " 12.5s2.825-.742 3.955-1.715c1.124-.967 1.954-2.096 2.366-2.717"
        "a.12.12 0 0 0 0-.136c-.412-.621-1.242-1.75-2.366-2.717C10.824"
        " 4.242 9.473 3.5 8 3.5s-2.824.742-3.955 1.715c-1.124.967-1.954"
        " 2.096-2.366 2.717ZM8 10a2 2 0 1 1-.001-3.999A2 2 0 0 1 8 10Z"
    ),
    "repo": (
        "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5"
        "a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8"
        "a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1"
        " 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8Z"
    ),
    "star": (
        "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1"
        " .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8"
        " 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374"
        "a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"
    ),
    "follower": (
        "M10.561 8.073a6.005 6.005 0 0 1 3.432 5.142.75.75 0 1 1-1.498.07"
        " 4.5 4.5 0 0 0-8.99 0 .75.75 0 0 1-1.498-.07 6.004 6.004 0 0 1"
        " 3.431-5.142 3.999 3.999 0 1 1 5.123 0ZM10.5 5a2.5 2.5 0 1 0-5 0"
        " 2.5 2.5 0 0 0 5 0Z"
    ),
    "code": (
        "m11.28 3.22 4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.749.749 0"
        " 0 1-1.275-.326.749.749 0 0 1 .215-.734L13.94 8l-3.72-3.72a.749"
        ".749 0 0 1 .326-1.275.749.749 0 0 1 .734.215Zm-6.56 0a.751.751"
        " 0 0 1 .018 1.042L1.06 8l3.72 3.72a.749.749 0 0 1-.326 1.275"
        ".749.749 0 0 1-.734-.215l-4.25-4.25a.75.75 0 0 1 0-1.06l4.25-4.25Z"
    ),
}

# (icon_key, y_baseline) for each stat line in the GitHub sections.
ICON_LAYOUT = [
    ("commit", 550),
    ("pr", 570),
    ("issue", 590),
    ("review", 610),
    ("repo", 670),
    ("star", 690),
    ("commit", 710),
    ("follower", 730),
    ("code", 750),
    ("code", 770),
]

ICON_X = 393
ICON_SCALE = 0.875


def build_dot_string(value_text: str, length: int) -> str:
    """Build a dot-leader string to right-align a value in a fixed-width column.

    Args:
        value_text: The text being aligned.
        length: Total column width.

    Returns:
        A string of dots and spaces for visual alignment, or an empty string
        when padding is not needed.
    """
    just_len = max(0, length - len(value_text))
    if just_len <= 2:
        return {0: "", 1: " ", 2: ". "}[just_len]
    return " " + ("." * just_len) + " "


def find_and_replace(root: _Element, element_id: str, new_text: str) -> None:
    """Find an SVG element by ``id`` and replace its text content.

    Args:
        root: The root element of the SVG tree.
        element_id: The ``id`` attribute to search for.
        new_text: The replacement text.
    """
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def justify_format(
    root: _Element,
    element_id: str,
    new_text: int | str,
    length: int = 0,
) -> None:
    """Write a formatted value and its dot-leader into the SVG.

    Args:
        root: The root element of the SVG tree.
        element_id: Base ``id`` for the value element (dots element is
            ``{element_id}_dots``).
        new_text: The value to display.
        length: Column width for dot-leader calculation.
    """
    formatted = format_display_text(new_text)
    find_and_replace(root, element_id, formatted)
    find_and_replace(root, f"{element_id}_dots", build_dot_string(formatted, length))


def add_icons(root: _Element, icon_color: str) -> None:
    """Add octicon-style SVG icons to each GitHub section data line.

    Args:
        root: The root SVG element.
        icon_color: Fill colour for the icons.
    """
    for icon_key, y_baseline in ICON_LAYOUT:
        g = SubElement(
            root,
            f"{{{SVG_NS}}}g",
            attrib={"transform": f"translate({ICON_X}, {y_baseline - 12})"},
        )
        SubElement(
            g,
            f"{{{SVG_NS}}}path",
            attrib={
                "d": ICON_PATHS[icon_key],
                "fill": icon_color,
                "transform": f"scale({ICON_SCALE})",
            },
        )


def add_language_bar(
    root: _Element,
    lang_data: list[tuple[str, int, str]],
    text_color: str,
    max_display: int = 5,
) -> None:
    """Add a coloured language bar and legend below the Languages label.

    Args:
        root: The root SVG element.
        lang_data: ``(name, bytes, colour)`` tuples sorted by bytes descending.
        text_color: Fill colour for label text.
        max_display: Maximum number of languages to show individually.
    """
    if not lang_data:
        return

    bar_x = 408
    bar_y = 790
    bar_w = 582
    bar_h = 12
    bar_rx = 6
    label_y = 815

    total = sum(s for _, s, _ in lang_data)
    if total == 0:
        return

    top = lang_data[:max_display]
    other = sum(s for _, s, _ in lang_data[max_display:])
    items: list[tuple[str, int, str]] = list(top)
    if other > 0:
        items.append(("Other", other, "#858585"))

    # clipPath for rounded bar corners
    defs = root.find(f"{{{SVG_NS}}}defs")
    if defs is None:
        defs = SubElement(root, f"{{{SVG_NS}}}defs")
    clip = SubElement(defs, f"{{{SVG_NS}}}clipPath", attrib={"id": "lang-bar-clip"})
    SubElement(
        clip,
        f"{{{SVG_NS}}}rect",
        attrib={
            "x": str(bar_x),
            "y": str(bar_y),
            "width": str(bar_w),
            "height": str(bar_h),
            "rx": str(bar_rx),
        },
    )

    # Render coloured bar segments
    bar_g = SubElement(
        root, f"{{{SVG_NS}}}g", attrib={"clip-path": "url(#lang-bar-clip)"}
    )
    x = float(bar_x)
    segments: list[tuple[str, str, float]] = []
    for i, (name, size, color) in enumerate(items):
        pct = size / total
        w = bar_w - (x - bar_x) if i == len(items) - 1 else bar_w * pct
        SubElement(
            bar_g,
            f"{{{SVG_NS}}}rect",
            attrib={
                "x": f"{x:.1f}",
                "y": str(bar_y),
                "width": f"{max(1.0, w):.1f}",
                "height": str(bar_h),
                "fill": color,
            },
        )
        segments.append((name, color, pct))
        x += w

    # Legend labels with coloured dots
    text_el = SubElement(
        root,
        f"{{{SVG_NS}}}text",
        attrib={
            "x": str(bar_x),
            "y": str(label_y),
            "fill": text_color,
            "font-family": "ConsolasFallback,Consolas,monospace",
            "font-size": "13px",
        },
    )
    first = True
    for name, color, pct in segments:
        if pct < 0.01:
            continue
        if not first:
            spacer = SubElement(text_el, f"{{{SVG_NS}}}tspan")
            spacer.text = "  "
        dot = SubElement(text_el, f"{{{SVG_NS}}}tspan", attrib={"fill": color})
        dot.text = "\u25cf "
        label = SubElement(text_el, f"{{{SVG_NS}}}tspan", attrib={"fill": text_color})
        label.text = f"{name} {pct * 100:.1f}%"
        first = False


def svg_overwrite(
    filename: str,
    age_data: str,
    commit_data: int,
    star_data: int,
    repo_data: int,
    contrib_data: int,
    follower_data: int,
    loc_data: list[str],
    today_data: dict[str, int] | None = None,
    lang_data: list[tuple[str, int, str]] | None = None,
) -> None:
    """Parse an SVG file, inject statistics, and write it back.

    Args:
        filename: Path to the SVG file.
        age_data: Formatted age string.
        commit_data: Total commit count.
        star_data: Total star count.
        repo_data: Owned repository count.
        contrib_data: Contributed-to repository count.
        follower_data: Follower count.
        loc_data: List of ``[added, deleted, net]`` LOC strings.
        today_data: Today's contribution breakdown, or ``None``.
        lang_data: Language ``(name, bytes, colour)`` tuples, or ``None``.
    """
    tree: _ElementTree = parse(filename)
    root: _Element = tree.getroot()

    justify_format(root, "age_data", age_data, config.AGE_DATA_WIDTH)
    justify_format(root, "commit_data", commit_data, config.COMMIT_DATA_WIDTH)
    justify_format(root, "star_data", star_data, config.STAR_DATA_WIDTH)
    justify_format(root, "repo_data", repo_data, config.REPO_DATA_WIDTH)
    justify_format(root, "contrib_data", contrib_data)
    justify_format(root, "follower_data", follower_data, config.FOLLOWER_DATA_WIDTH)
    justify_format(root, "loc_data", loc_data[2], config.LOC_DATA_WIDTH)
    justify_format(root, "loc_add", format_compact_number(loc_data[0]))
    justify_format(root, "loc_del", format_compact_number(loc_data[1]), 5)

    if today_data is not None:
        justify_format(root, "today_commits", today_data["commits"], config.TODAY_COMMITS_WIDTH)
        justify_format(root, "today_prs", today_data["prs"], config.TODAY_PRS_WIDTH)
        justify_format(root, "today_issues", today_data["issues"], config.TODAY_ISSUES_WIDTH)
        justify_format(root, "today_reviews", today_data["reviews"], config.TODAY_REVIEWS_WIDTH)

    now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    find_and_replace(root, "last_updated", now)

    icon_color = "#ffa657" if "dark" in filename else "#953800"
    text_color = "#c9d1d9" if "dark" in filename else "#24292f"

    add_icons(root, icon_color)

    if lang_data:
        add_language_bar(root, lang_data, text_color)

    tree.write(filename, encoding="utf-8", xml_declaration=True)


def update_svg_files(
    age_data: str,
    commit_data: int,
    star_data: int,
    repo_data: int,
    contrib_data: int,
    follower_data: int,
    loc_data: list[str],
    today_data: dict[str, int] | None = None,
    lang_data: list[tuple[str, int, str]] | None = None,
) -> None:
    """Update all configured SVG files with the latest statistics.

    Args:
        age_data: Formatted age string.
        commit_data: Total commit count.
        star_data: Total star count.
        repo_data: Owned repository count.
        contrib_data: Contributed-to repository count.
        follower_data: Follower count.
        loc_data: List of ``[added, deleted, net]`` LOC strings.
        today_data: Today's contribution breakdown, or ``None``.
        lang_data: Language ``(name, bytes, colour)`` tuples, or ``None``.
    """
    for svg_file in config.SVG_FILES:
        svg_overwrite(
            svg_file,
            age_data,
            commit_data,
            star_data,
            repo_data,
            contrib_data,
            follower_data,
            loc_data,
            today_data,
            lang_data,
        )
