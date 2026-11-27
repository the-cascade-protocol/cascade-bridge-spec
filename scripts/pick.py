#!/usr/bin/env python3
"""Usage:

    python3 scripts/pick.py <owner/repository> --checkout <folder>
    python3 scripts/pick.py <owner/repository> --package <file name pattern> [--into <folder>]

--checkout: the repository's files, placed at <folder>, picked as a counterpart is: the pull requests a Depends-On:
line names merged into the branch they target, else the branch named like the one the run is on, else the default
branch. --package: the one file of that name in the build of the head of the pull request of the repository a
Depends-On: line names, from that run's package artifact, else in the newest build of its default branch, a release
build-<commit> or an asset of the release package-builds; saved in <folder>. Prints what it picked and how, and writes
path, commit and how to $GITHUB_OUTPUT when it is set. Exit status is 1 when nothing was picked.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

from compatibility_tool import builds, git, github, picking
from compatibility_tool.console import Stop


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repository")
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--checkout", type=Path)
    what.add_argument("--package")
    parser.add_argument("--into", type=Path, default=Path(tempfile.gettempdir()) / "cascade-picked")
    return parser.parse_args(argv)


def files(url, reached, event, into):
    if into.exists() and any(into.iterdir()):
        raise Stop(f"{into} is there already and holds files: name a folder that is not there, or is empty")
    choice = picking.choose(url, github.repository_path(url), reached, event)
    picking.place(url, choice, into)
    return builds.Picked(into.resolve(), git.local_commit(into, "HEAD"), choice.how)


def written(picked):
    outputs = os.environ.get("GITHUB_OUTPUT")
    if outputs:
        with open(outputs, "a", encoding="utf-8") as handle:
            handle.write(f"path={picked.path}\ncommit={picked.commit}\nhow={picked.how}\n")


def main(argv):
    args = parse(argv[1:])
    github.take_token()
    api = github.Api()
    try:
        url = github.url_on_this_server(github.repository_path(f"/{args.repository}"))
        event = github.event(api)
        reached = picking.follow(api, event, [url], None)
        if args.checkout:
            picked = files(url, reached, event, args.checkout)
        else:
            picked = builds.picked(api, url, reached, args.package, args.into / github.repository_name(url))
    except Stop as stop:
        print(f"::error::{stop}")
        return 1
    print(f"{args.repository} at {picked.commit}: {picked.how}; placed at {picked.path}")
    written(picked)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
