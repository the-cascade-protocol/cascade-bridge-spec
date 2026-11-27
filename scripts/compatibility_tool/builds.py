"""A producer's package build, picked for a repository that installs it: the newest build of the producer's default
branch, or the build of the pull request a Depends-On: line names."""

import fnmatch
import hashlib
import io
import re
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from compatibility_tool import git, github, picking, releases
from compatibility_tool.console import Stop, note

TAGS = "refs/tags/build-"
PACKAGE_BUILDS = "package-builds"
COMMIT_IN_A_NAME = re.compile(r"-commit-([0-9a-f]{40})\b")
HISTORY = 100
ARTIFACT = "package"
POLL_SECONDS = 30
WAIT_SECONDS = 20 * 60
PER_PAGE = 100
sleep = time.sleep
monotonic = time.monotonic


@dataclass(frozen=True)
class Picked:
    path: Path
    commit: str
    how: str


def the_one(names, pattern, holder):
    matching = [name for name in names if fnmatch.fnmatchcase(name, pattern)]
    if len(matching) != 1:
        raise Stop(f"{holder} holds {len(matching)} files named {pattern}, where one is wanted: {', '.join(names)}")
    return matching[0]


def saved(data, name, into):
    into.mkdir(parents=True, exist_ok=True)
    path = into / Path(name).name
    path.write_bytes(data)
    return path.resolve()


def integrity_checked(data, name, notes, tag):
    given = list(releases.digests(notes))
    if not given:
        return "the release's notes give no integrity, so none was checked"
    for algorithm, digest in given:
        if hashlib.new(algorithm, data).digest() == digest:
            return f"its {algorithm} integrity, given in the release's notes, checked"
    raise Stop(f"{name} matches no integrity the notes of {tag} give: it is not the file that was released")


def every_asset(api, path, release):
    assets, page = [], 1
    while True:
        found = api.read(
            f"repos/{path}/releases/{release['id']}/assets?per_page={PER_PAGE}&page={page}",
            f"the assets of {path}'s {release.get('tag_name')}",
        )
        assets.extend(found)
        if len(found) < PER_PAGE:
            return assets
        page += 1


def release_or_none(api, path, tag):
    try:
        return api.get(f"repos/{path}/releases/tags/{tag}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise Stop(f"{path}'s release {tag} could not be read: {github.unreadable(error).said}") from error


def newest_built(url, tip, built):
    """The default branch's head where it has a build, else the nearest commit before it with one."""
    if tip in built:
        return tip
    with tempfile.TemporaryDirectory() as history:
        git.git("init", "--quiet", cwd=history)
        fetched = git.git("fetch", "--quiet", f"--depth={HISTORY}", "--filter=tree:0", url, "HEAD", cwd=history)
        if fetched.returncode != 0:
            raise git.unreachable(url, fetched)
        commits = git.git("rev-list", "--first-parent", "FETCH_HEAD", cwd=history).stdout.split()
    found = next((commit for commit in commits if commit in built), None)
    if found is None:
        raise Stop(f"none of the last {HISTORY} commits of {url}'s default branch has a build")
    return found


def of_the_default_branch(api, url, path, pattern, into):
    """A build of each commit is the release build-<commit>, or an asset of the release package-builds whose name
    carries the commit."""
    refs = git.ls_remote(url, "HEAD", f"{TAGS}*")
    tip = refs.get("HEAD")
    if not tip:
        raise Stop(f"{url} has no default branch")
    tagged = {ref.removeprefix(TAGS) for ref in refs if ref.startswith(TAGS) and not ref.endswith("^{}")}
    shelf = release_or_none(api, path, PACKAGE_BUILDS)
    shelved = {}
    for asset in every_asset(api, path, shelf) if shelf else ():
        name = str(asset.get("name"))
        commit = COMMIT_IN_A_NAME.search(name)
        if commit and fnmatch.fnmatchcase(name, pattern):
            shelved[commit[1]] = asset
    commit = newest_built(url, tip, tagged | set(shelved))
    if commit in tagged:
        tag = releases.TAG.format(commit=commit)
        release = api.read(f"repos/{path}/releases/tags/{tag}", f"{path}'s release {tag}")
        assets = {str(asset.get("name")): asset for asset in release.get("assets") or []}
        asset = assets[the_one(list(assets), pattern, tag)]
        where = f"the release {tag}"
    else:
        tag, release, asset = PACKAGE_BUILDS, shelf, shelved[commit]
        where = f"{asset['name']} of the release {PACKAGE_BUILDS}"
    data = releases.download(asset["browser_download_url"])
    checked = integrity_checked(data, asset["name"], release.get("body"), tag)
    return Picked(
        saved(data, asset["name"], into), commit, f"the newest build of its default branch, {where}; {checked}"
    )


def without_a_token_past_github(api, url):
    """The artifact's archive: GitHub answers with a redirect to its storage, which is sent no token."""

    class Unfollowed(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *arguments):
            return None

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cascade-compatibility",
            **({"Authorization": f"Bearer {github.token}"} if github.token else {}),
        },
    )
    try:
        with urllib.request.build_opener(Unfollowed).open(request, timeout=releases.DOWNLOAD_TIMEOUT_SECONDS) as answer:
            return answer.read()
    except urllib.error.HTTPError as error:
        if error.code in (301, 302, 303, 307, 308) and error.headers.get("Location"):
            return releases.download(error.headers["Location"])
        raise Stop(f"{url} could not be downloaded: {github.unreadable(error).said}") from error


def packed_at(api, path, head):
    """The newest run of a pull request at the head with an unexpired package artifact, and the artifact; or the runs
    at the head that are not finished."""
    runs = api.read(
        f"repos/{path}/actions/runs?head_sha={head}&event=pull_request&per_page={PER_PAGE}", f"{path}'s runs at {head}"
    )
    runs = sorted(
        (run for run in runs.get("workflow_runs") or [] if run.get("event") == "pull_request"),
        key=lambda run: run.get("id", 0),
        reverse=True,
    )
    for run in runs:
        artifacts = api.read(
            f"repos/{path}/actions/runs/{run['id']}/artifacts?name={ARTIFACT}",
            f"the artifacts of {path}'s run {run['id']}",
        )
        for artifact in artifacts.get("artifacts") or []:
            if artifact.get("name") == ARTIFACT and not artifact.get("expired"):
                return (run, artifact), []
    return None, [str(run.get("html_url") or run.get("id")) for run in runs if run.get("status") != "completed"]


def of_a_pull_request(api, path, entry, pattern, into):
    head, label = entry.head, entry.named.label
    deadline = monotonic() + WAIT_SECONDS
    said_so = False
    while True:
        found, unfinished = packed_at(api, path, head)
        if found:
            break
        if not unfinished:
            raise Stop(
                f"{label} has no package artifact at its head {head}: no run of it there packed one, or it has expired; "
                "rerun its packing run, then this"
            )
        if monotonic() >= deadline:
            raise Stop(
                f"waited {WAIT_SECONDS // 60} min for {label}'s package artifact; {', '.join(unfinished)} had not packed it"
            )
        if not said_so:
            note(
                f"{label}'s package artifact is not there yet: waiting up to {WAIT_SECONDS // 60} min for {', '.join(unfinished)}"
            )
            said_so = True
        sleep(POLL_SECONDS)
    run, artifact = found
    with zipfile.ZipFile(io.BytesIO(without_a_token_past_github(api, artifact["archive_download_url"]))) as archive:
        name = the_one(archive.namelist(), pattern, f"the package artifact of {run.get('html_url') or run['id']}")
        data = archive.read(name)
    return Picked(
        saved(data, name, into),
        head,
        f"pull request #{entry.named.number}, the package artifact of its run {run.get('html_url') or run['id']} "
        f"at its head; a pull request's build has no release notes, so no integrity was checked",
    )


def picked(api, url, reached, pattern, into):
    path = github.repository_path(url)
    named = picking.merging(reached, path)
    if len(named) > 1:
        raise Stop(f"Depends-On: lines name {picking.numbered(named)} of {path}, and a build is of one head: name one")
    if named:
        return of_a_pull_request(api, path, named[0], pattern, into)
    return of_the_default_branch(api, url, path, pattern, into)
