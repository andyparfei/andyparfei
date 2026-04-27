"""Entry point for the GitHub profile stats generator."""

import sys
from pathlib import Path

# Add src/ to the Python path so profilegen package is importable.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from profilegen import config
from profilegen.cache import add_archive, commit_counter
from profilegen.formatting import format_age, perf_counter, print_duration
from profilegen.github_api import (
    alltime_contributions,
    daily_contributions,
    follower_getter,
    graph_repos_stars,
    loc_query,
    user_getter,
)
from profilegen.svg import update_svg_files


def main():
    config.configure_environment()

    print("Calculation times:")

    config.OWNER_ID, user_time = perf_counter(user_getter, config.USER_NAME)
    print(config.OWNER_ID)
    print_duration("account data", user_time)

    age_data, age_time = perf_counter(format_age, config.BIRTHDAY)
    print_duration("age calculation", age_time)

    total_loc, loc_time = perf_counter(
        loc_query,
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"],
        config.COMMENT_BLOCK_SIZE,
    )
    print_duration("LOC (cached)" if total_loc[-1] else "LOC (no cache)", loc_time)

    commit_data, commit_time = perf_counter(commit_counter, config.COMMENT_BLOCK_SIZE)
    print_duration("commit count", commit_time)

    star_data, star_time = perf_counter(graph_repos_stars, "stars", ["OWNER"])
    print_duration("stars", star_time)

    repo_data, repo_time = perf_counter(graph_repos_stars, "repos", ["OWNER"])
    print_duration("repos", repo_time)

    contrib_data, contrib_time = perf_counter(
        graph_repos_stars,
        "repos",
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"],
    )
    print_duration("contributed repos", contrib_time)

    follower_data, follower_time = perf_counter(follower_getter, config.USER_NAME)
    print_duration("followers", follower_time)

    today_data, today_time = perf_counter(daily_contributions, config.USER_NAME)
    print_duration("daily stats", today_time)

    alltime_data, alltime_time = perf_counter(alltime_contributions, config.USER_NAME)
    print_duration("alltime stats", alltime_time)

    if config.OWNER_ID == config.ARCHIVE_USER_ID:
        archived_data = add_archive()
        for index in range(len(total_loc) - 1):
            total_loc[index] += archived_data[index]
        contrib_data += archived_data[-1]
        commit_data += archived_data[-2]

    total_loc[:-1] = [f"{value:,}" for value in total_loc[:-1]]

    update_svg_files(
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data,
        total_loc[:-1],
        today_data,
        alltime_data,
    )

    total_runtime = (
        user_time
        + age_time
        + loc_time
        + commit_time
        + star_time
        + repo_time
        + contrib_time
        + follower_time
        + today_time
        + alltime_time
    )
    print(f"{'Total function time:':<21} {total_runtime:>11.4f} s")
    print(f"Total GitHub GraphQL API calls: {sum(config.QUERY_COUNT.values()):>3}")
    for function_name, count in config.QUERY_COUNT.items():
        print(f"   {function_name + ':':<25} {count:>6}")


if __name__ == "__main__":
    main()
