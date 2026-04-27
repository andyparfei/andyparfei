"""SVG template rewriting."""

import datetime

from lxml.etree import parse

from profilegen import config
from profilegen.formatting import format_compact_number, format_display_text


def build_dot_string(value_text, length):
    just_len = max(0, length - len(value_text))
    if just_len <= 2:
        return {0: "", 1: " ", 2: ". "}[just_len]
    return " " + ("." * just_len) + " "


def find_and_replace(root, element_id, new_text):
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def justify_format(root, element_id, new_text, length=0):
    new_text = format_display_text(new_text)
    find_and_replace(root, element_id, new_text)
    find_and_replace(root, f"{element_id}_dots", build_dot_string(new_text, length))


def secondary_stat_gap(left_width, target_width=config.STATS_SECONDARY_COLUMN_WIDTH):
    return (" " * max(0, target_width - left_width)) + config.STATS_SECONDARY_SEPARATOR


def repo_stats_left_width(repo_data, contrib_data):
    repo_text = format_display_text(repo_data)
    contrib_text = format_display_text(contrib_data)
    return len(
        f". Repos:{build_dot_string(repo_text, config.REPO_DATA_WIDTH)}{repo_text}"
        f" {{Contributed: {contrib_text}}}"
    )


def commit_stats_left_width(commit_data):
    commit_text = format_display_text(commit_data)
    return len(f". Commits:{build_dot_string(commit_text, config.COMMIT_DATA_WIDTH)}{commit_text}")


def svg_overwrite(filename, age_data, commit_data, star_data, repo_data,
                  contrib_data, follower_data, loc_data, today_data=None, alltime_data=None):
    tree = parse(filename)
    root = tree.getroot()

    justify_format(root, "age_data", age_data, config.AGE_DATA_WIDTH)
    justify_format(root, "commit_data", commit_data, config.COMMIT_DATA_WIDTH)
    justify_format(root, "star_data", star_data, config.STAR_DATA_WIDTH)
    justify_format(root, "repo_data", repo_data, config.REPO_DATA_WIDTH)
    justify_format(root, "contrib_data", contrib_data)
    justify_format(root, "follower_data", follower_data, config.FOLLOWER_DATA_WIDTH)
    justify_format(root, "loc_data", loc_data[2], config.LOC_DATA_WIDTH)
    justify_format(root, "loc_add", format_compact_number(loc_data[0]))
    justify_format(root, "loc_del", format_compact_number(loc_data[1]), 5)
    find_and_replace(root, "repo_stats_gap", secondary_stat_gap(repo_stats_left_width(repo_data, contrib_data)))
    find_and_replace(root, "commit_stats_gap", secondary_stat_gap(commit_stats_left_width(commit_data)))

    if today_data is not None:
        justify_format(root, "today_commits", today_data["commits"], config.TODAY_COMMITS_WIDTH)
        justify_format(root, "today_prs", today_data["prs"], config.TODAY_PRS_WIDTH)
        justify_format(root, "today_issues", today_data["issues"])
        justify_format(root, "today_reviews", today_data["reviews"])

    if alltime_data is not None:
        justify_format(root, "commit_data", alltime_data["commits"], config.TODAY_COMMITS_WIDTH)
        justify_format(root, "alltime_prs", alltime_data["prs"], config.TODAY_PRS_WIDTH)
        justify_format(root, "alltime_issues", alltime_data["issues"])
        justify_format(root, "alltime_reviews", alltime_data["reviews"])

    # Write current UTC timestamp into the SVG.
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    find_and_replace(root, "last_updated", f"Last updated: {now}")

    tree.write(filename, encoding="utf-8", xml_declaration=True)


def update_svg_files(age_data, commit_data, star_data, repo_data,
                     contrib_data, follower_data, loc_data, today_data=None, alltime_data=None):
    for svg_file in config.SVG_FILES:
        svg_overwrite(svg_file, age_data, commit_data, star_data, repo_data,
                      contrib_data, follower_data, loc_data, today_data, alltime_data)
