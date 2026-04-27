"""GitHub GraphQL API queries."""

import datetime
from typing import Any

import requests

from profilegen import config
from profilegen.cache import cache_builder, force_close_file


def _raise_request_error(operation_name: str, response: requests.Response) -> None:
    """Raise a descriptive ``RuntimeError`` for a failed HTTP response.

    Args:
        operation_name: Label used in the error message.
        response: The failed HTTP response.

    Raises:
        RuntimeError: Always raised with status and body details.
    """
    if response.status_code == 403:
        raise RuntimeError("Too many requests in a short amount of time. GitHub returned 403.")
    raise RuntimeError(
        f"{operation_name} failed with status {response.status_code}: "
        f"{response.text}. Query counts: {config.QUERY_COUNT}"
    )


def graphql_request(
    operation_name: str,
    query: str,
    variables: dict[str, Any],
    partial_cache: tuple[list[str], list[str]] | None = None,
) -> dict[str, Any]:
    """Execute a GitHub GraphQL request and return the ``data`` payload.

    Args:
        operation_name: Human-readable label for error messages.
        query: The GraphQL query string.
        variables: Variables passed alongside the query.
        partial_cache: Optional ``(cache_rows, cache_header)`` tuple; if
            provided the cache is flushed to disk on failure.

    Returns:
        The ``data`` key of the parsed JSON response.

    Raises:
        RuntimeError: On HTTP errors, invalid JSON, or GraphQL-level errors.
    """
    try:
        response = requests.post(
            config.GITHUB_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=config.HEADERS,
            timeout=30,
        )
    except requests.RequestException as error:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(f"{operation_name} request failed: {error}") from error

    if response.status_code != 200:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        _raise_request_error(operation_name, response)

    try:
        payload: dict[str, Any] = response.json()
    except ValueError as error:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(f"{operation_name} returned invalid JSON: {response.text}") from error

    if payload.get("errors"):
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(f"{operation_name} returned GraphQL errors: {payload['errors']}")

    return payload["data"]


def user_getter(username: str) -> str:
    """Fetch the GitHub node ID for a user.

    Args:
        username: GitHub login name.

    Returns:
        The user's node ID string.
    """
    config.query_count("user_getter")
    query = """
    query($login: String!){
        user(login: $login) { id }
    }"""
    data = graphql_request("user_getter", query, {"login": username})
    return data["user"]["id"]


def follower_getter(username: str) -> int:
    """Fetch the follower count for a user.

    Args:
        username: GitHub login name.

    Returns:
        Number of followers.
    """
    config.query_count("follower_getter")
    query = """
    query($login: String!){
        user(login: $login) { followers { totalCount } }
    }"""
    data = graphql_request("follower_getter", query, {"login": username})
    return int(data["user"]["followers"]["totalCount"])


def daily_contributions(username: str) -> dict[str, int]:
    """Fetch today's contribution counts for a user.

    Args:
        username: GitHub login name.

    Returns:
        A dict with keys ``commits``, ``prs``, ``issues``, ``reviews``.
    """
    config.query_count("daily_contributions")
    today = datetime.datetime.now(tz=datetime.timezone.utc).date()
    from_date = f"{today}T00:00:00Z"
    to_date = f"{today}T23:59:59Z"
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
                totalCommitContributions
                totalPullRequestContributions
                totalIssueContributions
                totalPullRequestReviewContributions
            }
        }
    }"""
    data = graphql_request(
        "daily_contributions", query, {"login": username, "from": from_date, "to": to_date}
    )
    c = data["user"]["contributionsCollection"]
    return {
        "commits": c["totalCommitContributions"],
        "prs": c["totalPullRequestContributions"],
        "issues": c["totalIssueContributions"],
        "reviews": c["totalPullRequestReviewContributions"],
    }


def alltime_contributions(username: str) -> dict[str, int]:
    """Fetch all-time contribution counts for a user.

    Args:
        username: GitHub login name.

    Returns:
        A dict with keys ``commits``, ``prs``, ``issues``, ``reviews``.
    """
    config.query_count("daily_contributions")
    query = """
    query($login: String!) {
        user(login: $login) {
            contributionsCollection {
                totalCommitContributions
                totalPullRequestContributions
                totalIssueContributions
                totalPullRequestReviewContributions
            }
        }
    }"""
    data = graphql_request("alltime_contributions", query, {"login": username})
    c = data["user"]["contributionsCollection"]
    return {
        "commits": c["totalCommitContributions"],
        "prs": c["totalPullRequestContributions"],
        "issues": c["totalIssueContributions"],
        "reviews": c["totalPullRequestReviewContributions"],
    }


def languages_query(owner_affiliation: list[str]) -> list[tuple[str, int, str]]:
    """Fetch language byte counts and colors across all user repositories.

    Args:
        owner_affiliation: List of affiliation filters for the query.

    Returns:
        A list of ``(name, bytes, color)`` tuples sorted by bytes descending.
    """
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                                edges {
                                    node { name color }
                                    size
                                }
                            }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }"""

    cursor: str | None = None
    lang_totals: dict[str, tuple[int, str]] = {}

    while True:
        config.query_count("languages_query")
        variables: dict[str, Any] = {
            "owner_affiliation": owner_affiliation,
            "login": config.USER_NAME,
            "cursor": cursor,
        }
        data = graphql_request("languages_query", query, variables)
        repos = data["user"]["repositories"]

        for edge in repos["edges"]:
            for lang_edge in edge["node"]["languages"]["edges"]:
                name = lang_edge["node"]["name"]
                color = lang_edge["node"]["color"] or "#858585"
                size = lang_edge["size"]
                if name in lang_totals:
                    prev_size, prev_color = lang_totals[name]
                    lang_totals[name] = (prev_size + size, prev_color)
                else:
                    lang_totals[name] = (size, color)

        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    result = [(name, size, color) for name, (size, color) in lang_totals.items()]
    result.sort(key=lambda x: x[1], reverse=True)
    return result


def _stars_counter(edges: list[dict[str, Any]]) -> int:
    """Sum the stargazer counts across a list of repository edges.

    Args:
        edges: Repository edge nodes from the GraphQL response.

    Returns:
        Total star count.
    """
    return sum(e["node"]["stargazers"]["totalCount"] for e in edges)


def graph_repos_stars(count_type: str, owner_affiliation: list[str]) -> int:
    """Paginate through a user's repositories and return a total count.

    Args:
        count_type: ``"stars"`` to count stargazers, ``"repos"`` to count
            repositories.
        owner_affiliation: List of affiliation filters (e.g.
            ``["OWNER", "COLLABORATOR"]``).

    Returns:
        The total star count or repository count depending on *count_type*.
    """
    total_repositories = 0
    total_stars = 0
    cursor: str | None = None

    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges { node { ... on Repository { stargazers { totalCount } } } }
                pageInfo { endCursor hasNextPage }
            }
        }
    }"""

    while True:
        config.query_count("graph_repos_stars")
        variables: dict[str, Any] = {
            "owner_affiliation": owner_affiliation,
            "login": config.USER_NAME,
            "cursor": cursor,
        }
        data = graphql_request("graph_repos_stars", query, variables)
        repositories = data["user"]["repositories"]
        total_repositories = repositories["totalCount"]
        total_stars += _stars_counter(repositories["edges"])
        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    if count_type == "repos":
        return total_repositories
    if count_type == "stars":
        return total_stars
    return 0


def recursive_loc(
    owner: str,
    repo_name: str,
    cache_rows: list[str],
    cache_header: list[str],
    addition_total: int = 0,
    deletion_total: int = 0,
    my_commits: int = 0,
    cursor: str | None = None,
) -> tuple[int, int, int]:
    """Recursively paginate commit history to count LOC contributed by the user.

    Args:
        owner: Repository owner login.
        repo_name: Repository name.
        cache_rows: Current cache data rows (for emergency save).
        cache_header: Current cache header lines (for emergency save).
        addition_total: Running additions accumulator.
        deletion_total: Running deletions accumulator.
        my_commits: Running commit count accumulator.
        cursor: GraphQL pagination cursor.

    Returns:
        A tuple of ``(additions, deletions, my_commits)``.
    """
    config.query_count("recursive_loc")
    query = """
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            edges {
                                node {
                                    ... on Commit {
                                        author { user { id } }
                                        deletions
                                        additions
                                    }
                                }
                            }
                            pageInfo { endCursor hasNextPage }
                        }
                    }
                }
            }
        }
    }"""
    variables: dict[str, Any] = {"repo_name": repo_name, "owner": owner, "cursor": cursor}
    data = graphql_request(
        "recursive_loc", query, variables, partial_cache=(cache_rows, cache_header)
    )
    branch = data["repository"]["defaultBranchRef"]

    if branch is None:
        return 0, 0, 0

    history = branch["target"]["history"]
    for edge in history["edges"]:
        author = edge["node"].get("author") or {}
        user = author.get("user") or {}
        if user.get("id") == config.OWNER_ID:
            my_commits += 1
            addition_total += edge["node"]["additions"]
            deletion_total += edge["node"]["deletions"]

    if not history["pageInfo"]["hasNextPage"]:
        return addition_total, deletion_total, my_commits

    return recursive_loc(
        owner,
        repo_name,
        cache_rows,
        cache_header,
        addition_total,
        deletion_total,
        my_commits,
        history["pageInfo"]["endCursor"],
    )


def loc_query(
    owner_affiliation: list[str],
    comment_size: int = 0,
    force_cache: bool = False,
) -> list[Any]:
    """Query all repositories for the authenticated user and build the LOC cache.

    Args:
        owner_affiliation: List of affiliation filters for the query.
        comment_size: Number of comment lines at the top of the cache file.
        force_cache: If ``True``, rebuild the cache from scratch.

    Returns:
        A list of ``[additions, deletions, net_loc, cached_flag]``.
    """
    query = """
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            defaultBranchRef { target { ... on Commit { history { totalCount } } } }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }"""

    cursor: str | None = None
    edges: list[dict[str, Any]] = []
    while True:
        config.query_count("loc_query")
        variables: dict[str, Any] = {
            "owner_affiliation": owner_affiliation,
            "login": config.USER_NAME,
            "cursor": cursor,
        }
        data = graphql_request("loc_query", query, variables)
        repositories = data["user"]["repositories"]
        edges.extend(repositories["edges"])
        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    return cache_builder(edges, comment_size, force_cache, recursive_loc)
