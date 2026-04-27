"""Constants, runtime state, and environment setup."""

import datetime
import os
from pathlib import Path

from dotenv import load_dotenv

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
CACHE_DIR = Path("cache")
ARCHIVE_PATH = CACHE_DIR / "repository_archive.txt"
SVG_FILES = ("dark_mode.svg", "light_mode.svg")

COMMENT_BLOCK_SIZE = 7
BIRTHDAY = datetime.datetime(1986, 2, 5)
ARCHIVE_USER_ID = "U_kgDOC15JXw"
CACHE_COMMENT_LINE = "This line is a comment block. Write whatever you want here.\n"

AGE_DATA_WIDTH = 49
COMMIT_DATA_WIDTH = 22
LOC_DATA_WIDTH = 25
FOLLOWER_DATA_WIDTH = 10
REPO_DATA_WIDTH = 6
STAR_DATA_WIDTH = 14
STATS_SECONDARY_COLUMN_WIDTH = 34
STATS_SECONDARY_SEPARATOR = " |  "
TODAY_COMMITS_WIDTH = 18
TODAY_PRS_WIDTH = 14
TODAY_ISSUES_WIDTH = 17
TODAY_REVIEWS_WIDTH = 11

QUERY_COUNT = {
    "user_getter": 0,
    "follower_getter": 0,
    "graph_repos_stars": 0,
    "recursive_loc": 0,
    "loc_query": 0,
    "daily_contributions": 0,
}

HEADERS = {}
USER_NAME = ""
OWNER_ID = None


def require_env(name):
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def configure_environment():
    global HEADERS, USER_NAME
    load_dotenv()
    access_token = require_env("ACCESS_TOKEN")
    USER_NAME = require_env("USER_NAME")
    HEADERS = {"authorization": f"token {access_token}"}


def query_count(function_name):
    QUERY_COUNT[function_name] += 1
