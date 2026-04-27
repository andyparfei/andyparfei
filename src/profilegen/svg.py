"""SVG template rewriting."""

import datetime

from lxml.etree import _Element, _ElementTree, parse

from profilegen import config
from profilegen.formatting import format_compact_number, format_display_text


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


def secondary_stat_gap(
    left_width: int, target_width: int = config.STATS_SECONDARY_COLUMN_WIDTH
) -> str:
    """Compute the spacing string between two stat columns.

    Args:
        left_width: Character count of the left column.
        target_width: Target column width before the separator.

    Returns:
        A spacing string followed by the column separator.
    """
    return (" " * max(0, target_width - left_width)) + config.STATS_SECONDARY_SEPARATOR


def repo_stats_left_width(repo_data: int | str, contrib_data: int | str) -> int:
    """Calculate the character width of the repo stats left column.

    Args:
        repo_data: Repository count value.
        contrib_data: Contributed-to repository count value.

    Returns:
        The character length of the formatted left column.
    """
    repo_text = format_display_text(repo_data)
    contrib_text = format_display_text(contrib_data)
    return len(
        f". Repos:{build_dot_string(repo_text, config.REPO_DATA_WIDTH)}{repo_text}"
        f" {{Contributed: {contrib_text}}}"
    )


def commit_stats_left_width(commit_data: int | str) -> int:
    """Calculate the character width of the commit stats left column.

    Args:
        commit_data: Commit count value.

    Returns:
        The character length of the formatted left column.
    """
    commit_text = format_display_text(commit_data)
    return len(f". Commits:{build_dot_string(commit_text, config.COMMIT_DATA_WIDTH)}{commit_text}")


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
    find_and_replace(
        root, "repo_stats_gap", secondary_stat_gap(repo_stats_left_width(repo_data, contrib_data))
    )
    find_and_replace(
        root, "commit_stats_gap", secondary_stat_gap(commit_stats_left_width(commit_data))
    )

    if today_data is not None:
        justify_format(root, "today_commits", today_data["commits"], config.TODAY_COMMITS_WIDTH)
        justify_format(root, "today_prs", today_data["prs"], config.TODAY_PRS_WIDTH)
        justify_format(root, "today_issues", today_data["issues"], config.TODAY_ISSUES_WIDTH)
        justify_format(root, "today_reviews", today_data["reviews"], config.TODAY_REVIEWS_WIDTH)

    now = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    find_and_replace(root, "last_updated", now)

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
        )
