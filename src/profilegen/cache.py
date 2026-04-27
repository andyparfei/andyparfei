"""File-based LOC cache management."""

import hashlib
import re
from pathlib import Path
from typing import Any

from profilegen import config


def cache_file_path() -> Path:
    """Return the cache file path derived from the hashed username.

    Returns:
        Path to the user-specific cache file inside the cache directory.
    """
    hashed_user = hashlib.sha256(config.USER_NAME.encode("utf-8")).hexdigest()
    return config.CACHE_DIR / f"{hashed_user}.txt"


def comment_block_lines(comment_size: int) -> list[str]:
    """Generate a list of comment placeholder lines.

    Args:
        comment_size: Number of comment lines to produce.

    Returns:
        A list of identical comment strings.
    """
    return [config.CACHE_COMMENT_LINE for _ in range(comment_size)]


def cache_builder(
    edges: list[dict[str, Any]],
    comment_size: int,
    force_cache: bool,
    loc_fetcher: Any,
    loc_add: int = 0,
    loc_del: int = 0,
) -> list[Any]:
    """Build or update the LOC cache file and return aggregated statistics.

    Args:
        edges: Repository edge nodes from the GitHub GraphQL API.
        comment_size: Number of leading comment lines in the cache file.
        force_cache: If ``True``, flush and rebuild the cache unconditionally.
        loc_fetcher: Callable that fetches LOC data for a single repository.
        loc_add: Running total of added lines (used for accumulation).
        loc_del: Running total of deleted lines (used for accumulation).

    Returns:
        A list of ``[additions, deletions, net_loc, cached_flag]``.
    """
    cached = True
    filename = cache_file_path()

    try:
        with filename.open("r") as handle:
            data = handle.readlines()
    except FileNotFoundError:
        data = comment_block_lines(comment_size)
        with filename.open("w") as handle:
            handle.writelines(data)

    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with filename.open("r") as handle:
            data = handle.readlines()

    cache_header = data[:comment_size]
    cache_rows = data[comment_size:]

    for index, edge in enumerate(edges):
        repository_name: str = edge["node"]["nameWithOwner"]
        expected_hash = hashlib.sha256(repository_name.encode("utf-8")).hexdigest()
        stored_hash, stored_commit_count, *_ = cache_rows[index].split()

        if stored_hash != expected_hash:
            cache_rows[index] = f"{expected_hash} 0 0 0 0\n"
            stored_hash = expected_hash
            stored_commit_count = "0"

        branch = edge["node"].get("defaultBranchRef")
        history = None if branch is None else branch["target"]["history"]
        current_commit_count: int = 0 if history is None else history["totalCount"]

        if int(stored_commit_count) != current_commit_count:
            cached = False
            if current_commit_count == 0:
                cache_rows[index] = f"{stored_hash} 0 0 0 0\n"
                continue

            owner, repo_name = repository_name.split("/", 1)
            additions, deletions, my_commits = loc_fetcher(
                owner,
                repo_name,
                cache_rows,
                cache_header,
            )
            cache_rows[index] = (
                f"{stored_hash} {current_commit_count} {my_commits} {additions} {deletions}\n"
            )

    with filename.open("w") as handle:
        handle.writelines(cache_header)
        handle.writelines(cache_rows)

    for line in cache_rows:
        _, _, _, added_lines, deleted_lines = line.split()
        loc_add += int(added_lines)
        loc_del += int(deleted_lines)

    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges: list[dict[str, Any]], filename: Path, comment_size: int) -> None:
    """Overwrite the cache file with zeroed entries for every repository.

    Args:
        edges: Repository edge nodes from the GitHub GraphQL API.
        filename: Path to the cache file.
        comment_size: Number of leading comment lines to preserve.
    """
    try:
        with filename.open("r") as handle:
            cache_header = handle.readlines()[:comment_size]
    except FileNotFoundError:
        cache_header = []

    if len(cache_header) < comment_size:
        cache_header.extend(comment_block_lines(comment_size - len(cache_header)))

    with filename.open("w") as handle:
        handle.writelines(cache_header[:comment_size])
        for edge in edges:
            repository_name: str = edge["node"]["nameWithOwner"]
            repository_hash = hashlib.sha256(repository_name.encode("utf-8")).hexdigest()
            handle.write(f"{repository_hash} 0 0 0 0\n")


def force_close_file(cache_rows: list[str], cache_header: list[str]) -> None:
    """Write partial cache data to disk as an emergency save.

    Args:
        cache_rows: The data rows of the cache.
        cache_header: The comment header lines of the cache.
    """
    filename = cache_file_path()
    with filename.open("w") as handle:
        handle.writelines(cache_header)
        handle.writelines(cache_rows)
    print(f"Saved partial cache data to {filename}.")


def commit_counter(comment_size: int) -> int:
    """Sum the commit counts stored in the cache file.

    Args:
        comment_size: Number of leading comment lines to skip.

    Returns:
        Total number of commits across all cached repositories.
    """
    total_commits = 0
    filename = cache_file_path()
    with filename.open("r") as handle:
        data = handle.readlines()
    for line in data[comment_size:]:
        total_commits += int(line.split()[2])
    return total_commits


def add_archive() -> list[int]:
    """Load archived repository data and return aggregated statistics.

    Returns:
        A list of ``[added_loc, deleted_loc, net_loc, archived_commits,
        contributed_repos]``, or all zeros if the archive file is missing.
    """
    if not config.ARCHIVE_PATH.exists():
        return [0, 0, 0, 0, 0]

    with config.ARCHIVE_PATH.open("r") as handle:
        lines = handle.readlines()

    added_loc = 0
    deleted_loc = 0
    saved_commits = 0
    contributed_repos = 0

    for line in lines:
        parts = line.split()
        if len(parts) != 5 or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None:
            continue
        contributed_repos += 1
        added_loc += int(parts[3])
        deleted_loc += int(parts[4])
        if parts[2].isdigit():
            saved_commits += int(parts[2])

    proof_match = re.search(r"total was (\d+)\.", "".join(lines))
    archived_commits = saved_commits
    if proof_match is not None:
        archived_commits = max(saved_commits, int(proof_match.group(1)))

    return [added_loc, deleted_loc, added_loc - deleted_loc, archived_commits, contributed_repos]
