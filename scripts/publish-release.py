#!/usr/bin/env python3
"""Publish the checked-out VERSION using the repository's Actions token."""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = (root / "VERSION").read_text().strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit("VERSION must contain a semantic version, for example 0.1.0")
tag = "v" + version
repo = os.environ["GITHUB_REPOSITORY"]
commit = os.environ["GITHUB_SHA"]
base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
headers = {
    "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
    "Accept": "application/vnd.github+json",
    "User-Agent": "School-Agent-release",
}


def request(path, data=None):
    encoded = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        base + "/repos/" + repo + path, data=encoded, headers=headers
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


try:
    release = request("/releases/tags/" + tag)
except urllib.error.HTTPError as error:
    if error.code != 404:
        raise
    release = request(
        "/releases",
        {
            "tag_name": tag,
            "target_commitish": commit,
            "name": "School Agent " + tag,
            "body": (root / "docs" / "releases" / (tag + ".md")).read_text().strip(),
            "draft": False,
            "prerelease": False,
            "make_latest": "true",
        },
    )
else:
    print("Release already exists; leaving it unchanged.")
print(release["html_url"])
