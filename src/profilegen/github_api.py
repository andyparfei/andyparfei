"""GitHub GraphQL API queries."""

import datetime

import requests

from profilegen import config
from profilegen.cache import cache_builder, force_close_file


def _raise_request_error(operation_name, response):
    if response.status_code == 403:
        raise RuntimeError("Too many requests in a short amount of time. GitHub returned 403.")
    raise RuntimeError(
        f"{operation_name} failed with status {response.status_code}: "
        f"{response.text}. Query counts: {config.QUERY_COUNT}"
    )


def graphql_request(operation_name, query, variables, partial_cache=None):
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
        payload = response.json()
    except ValueError as error:
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(f"{operation_name} returned invalid JSON: {response.text}") from error

    if payload.get("errors"):
        if partial_cache is not None:
            force_close_file(*partial_cache)
        raise RuntimeError(f"{operation_name} returned GraphQL errors: {payload['errors']}")

    return payload["data"]


def user_getter(username):
    config.query_count("user_getter")
    query = """
    query($login: String!){
        user(login: $login) { id }
    }"""
    data = graphql_request("user_getter", query, {"login": username})
    return data["user"]["id"]


def follower_getter(username):
    config.query_count("follower_getter")
    query = """
    query($login: String!){
        user(login: $login) { followers { totalCount } }
    }"""
    data = graphql_request("follower_getter", query, {"login": username})
    return int(data["user"]["followers"]["totalCount"])


def daily_contributions(username):
    config.query_count("daily_contributions")
    today = datetime.datetime.utcnow().date()
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
    data = graphql_request("daily_contributions", query, {"login": username, "from": from_date, "to": to_date})
    c = data["user"]["contributionsCollection"]
    return {
        "commits": c["totalCommitContributions"],
        "prs": c["totalPullRequestContributions"],
        "issues": c["totalIssueContributions"],
        "reviews": c["totalPullRequestReviewContributions"],
    }


def alltime_contributions(username):
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


def _stars_counter(edges):
    return sum(e["node"]["stargazers"]["totalCount"] for e in edges)


def graph_repos_stars(count_type, owner_affiliation):
    total_repositories = 0
    total_stars = 0
    cursor = None

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
        variables = {"owner_affiliation": owner_affiliation, "login": config.USER_NAME, "cursor": cursor}
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


def recursive_loc(owner, repo_name, cache_rows, cache_header,
                  addition_total=0, deletion_total=0, my_commits=0, cursor=None):
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
    variables = {"repo_name": repo_name, "owner": owner, "cursor": cursor}
    data = graphql_request("recursive_loc", query, variables, partial_cache=(cache_rows, cache_header))
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
        owner, repo_name, cache_rows, cache_header,
        addition_total, deletion_total, my_commits, history["pageInfo"]["endCursor"],
    )


def loc_query(owner_affiliation, comment_size=0, force_cache=False):
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

    cursor = None
    edges = []
    while True:
        config.query_count("loc_query")
        variables = {"owner_affiliation": owner_affiliation, "login": config.USER_NAME, "cursor": cursor}
        data = graphql_request("loc_query", query, variables)
        repositories = data["user"]["repositories"]
        edges.extend(repositories["edges"])
        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    return cache_builder(edges, comment_size, force_cache, recursive_loc)
