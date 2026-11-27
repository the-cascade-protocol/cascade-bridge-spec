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
GITHUB_DIGEST = re.compile(r"^(sha256|sha384|sha512):([0-9a-f]+)$")
HISTORY = 100
ARTIFACT = "package"
POLL_SECONDS = 30
WAIT_SECONDS = 20 * 60
PER_PAGE = 100
NO_INTEGRITY = "neither the release's notes nor GitHub give an integrity for it, so none was checked"
sleep = time.sleep
monotonic = time.monotonic


@dataclass(frozen=True)
class Picked:
    path: Path
    commit: str
    how: str


def matching(names, pattern):
    return [name for name in names if fnmatch.fnmatchcase(name, pattern)]


def the_one(names, pattern, holder):
    found = matching(names, pattern)
    if len(found) != 1:
        raise Stop(f"{holder} holds {len(found)} files named {pattern}, where one is wanted: {', '.join(names)}")
    return found[0]


def saved(data, name, into):
    into.mkdir(parents=True, exist_ok=True)
    path = into / Path(name).name
    path.write_bytes(data)
    return path.resolve()


def github_digest_checked(data, name, digest, uploaded):
    """The algorithm of GitHub's digest of the bytes, once they match it; None where GitHub gives none."""
    given = GITHUB_DIGEST.match(str(digest or ""))
    if not given:
        return None
    algorithm = given[1]
    if hashlib.new(algorithm, data).hexdigest() != given[2]:
        raise Stop(
            f"{name} does not match GitHub's {algorithm} digest of it: it is not the {uploaded} that was uploaded"
        )
    return algorithm


def integrity_checked(data, asset, notes, tag):
    name = asset["name"]
    given = list(releases.digests(notes))
    noted = None
    if given:
        noted = next(
            (algorithm for algorithm, digest in given if hashlib.new(algorithm, data).digest() == digest), None
        )
        if noted is None:
            raise Stop(f"{name} matches no integrity the notes of {tag} give: it is not the file that was released")
    digested = github_digest_checked(data, name, asset.get("digest"), "file")
    if noted and digested:
        return (
            f"its {noted} integrity, given in the release's notes, and GitHub's {digested} digest of the asset, checked"
        )
    if noted:
        return f"its {noted} integrity, given in the release's notes, checked"
    if digested:
        return f"GitHub's {digested} digest of the asset checked; the release's notes give no integrity"
    print(f"::warning::{name} of {tag}: {NO_INTEGRITY}")
    return NO_INTEGRITY


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


def first_parents(url):
    with tempfile.TemporaryDirectory() as history:
        git.git("init", "--quiet", cwd=history)
        fetched = git.git("fetch", "--quiet", f"--depth={HISTORY}", "--filter=tree:0", url, "HEAD", cwd=history)
        if fetched.returncode != 0:
            raise git.unreachable(url, fetched)
        return git.git("rev-list", "--first-parent", "FETCH_HEAD", cwd=history).stdout.split()


def built_commits(url, tip, built):
    """Each commit of the default branch with a build, newest first, with the branch's head and how many commits behind
    it the commit is. The history is fetched only when the head's own build will not do."""
    if tip in built:
        yield tip, tip, 0
    commits = first_parents(url)
    head = commits[0] if commits else tip
    for steps, commit in enumerate(commits):
        if commit in built and commit != tip:
            yield commit, head, steps


def behind(steps, head, lacking, pattern):
    said = f"{steps} commit{'s' if steps != 1 else ''} behind its head {head}"
    unbuilt = max(0, steps - lacking)
    if steps == 1:
        return f"{said}, which has no build yet" if unbuilt else f"{said}, whose build holds no file named {pattern}"
    reasons = []
    if unbuilt:
        reasons.append(f"{unbuilt} newer commit{' has' if unbuilt == 1 else 's have'} no build yet")
    if lacking:
        reasons.append(f"{lacking} newer build{' holds' if lacking == 1 else 's hold'} no file named {pattern}")
    return f"{said}: {' and '.join(reasons)}"


def build_of(api, path, commit, tagged, shelf, shelved, pattern):
    """The tag, release, asset and where it is, of the commit's build holding a file of that name; None where its
    build holds none."""
    if commit in tagged:
        tag = releases.TAG.format(commit=commit)
        release = api.read(f"repos/{path}/releases/tags/{tag}", f"{path}'s release {tag}")
        assets = {str(asset.get("name")): asset for asset in release.get("assets") or []}
        if matching(assets, pattern):
            return tag, release, assets[the_one(list(assets), pattern, tag)], f"the release {tag}"
    if commit in shelved:
        asset = shelved[commit]
        return PACKAGE_BUILDS, shelf, asset, f"{asset['name']} of the release {PACKAGE_BUILDS}"
    return None


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
    lacking = 0
    for commit, head, steps in built_commits(url, tip, tagged | set(shelved)):
        found = build_of(api, path, commit, tagged, shelf, shelved, pattern)
        if found is None:
            lacking += 1
            continue
        tag, release, asset, where = found
        if steps:
            where = f"{where}, {behind(steps, head, lacking, pattern)}"
        data = releases.download(asset["browser_download_url"])
        checked = integrity_checked(data, asset, release.get("body"), tag)
        return Picked(
            saved(data, asset["name"], into), commit, f"the newest build of its default branch, {where}; {checked}"
        )
    raise Stop(
        f"none of the last {HISTORY} commits of {url}'s default branch has a build holding a file named {pattern}"
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


def from_the_producer(run, path):
    return str((run.get("head_repository") or {}).get("full_name") or "").lower() == path.lower()


def packed_at(api, path, head):
    """The newest run of a pull request at the head, from a branch of the producer itself, with an unexpired package
    artifact, and the artifact; or those runs at the head that are not finished."""
    runs = api.read(
        f"repos/{path}/actions/runs?head_sha={head}&event=pull_request&per_page={PER_PAGE}", f"{path}'s runs at {head}"
    )
    runs = sorted(
        (
            run
            for run in runs.get("workflow_runs") or []
            if run.get("event") == "pull_request" and from_the_producer(run, path)
        ),
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
    return None, [run for run in runs if run.get("status") != "completed"]


def packing_workflow(api, path):
    """The workflow of the run that packed the producer's newest package artifact from a branch of its own; None where
    no run has."""
    found = api.read(f"repos/{path}/actions/artifacts?name={ARTIFACT}&per_page={PER_PAGE}", f"{path}'s artifacts")
    for artifact in found.get("artifacts") or []:
        made_by = artifact.get("workflow_run") or {}
        if made_by.get("id") and made_by.get("head_repository_id") == made_by.get("repository_id"):
            return api.read(f"repos/{path}/actions/runs/{made_by['id']}", f"{path}'s run {made_by['id']}").get(
                "workflow_id"
            )
    return None


def of_a_pull_request(api, path, entry, pattern, into):
    head, label = entry.head, entry.named.label
    deadline = monotonic() + WAIT_SECONDS
    said_so = looked_up = False
    packing = None
    while True:
        found, unfinished = packed_at(api, path, head)
        if found:
            break
        if unfinished and not looked_up:
            packing, looked_up = packing_workflow(api, path), True
        if packing is not None:
            unfinished = [run for run in unfinished if run.get("workflow_id") == packing]
        if not unfinished:
            raise Stop(
                f"{label} has no package artifact at its head {head}: no run of it there packed one, or it has expired; "
                "rerun its packing run, then this"
            )
        waiting_on = ", ".join(str(run.get("html_url") or run.get("id")) for run in unfinished)
        if monotonic() >= deadline:
            raise Stop(
                f"waited {WAIT_SECONDS // 60} min for {label}'s package artifact; {waiting_on} had not packed it"
            )
        if not said_so:
            note(
                f"{label}'s package artifact is not there yet: waiting up to {WAIT_SECONDS // 60} min for {waiting_on}"
            )
            said_so = True
        sleep(POLL_SECONDS)
    run, artifact = found
    where = run.get("html_url") or run["id"]
    zipped = without_a_token_past_github(api, artifact["archive_download_url"])
    digested = github_digest_checked(zipped, f"the package artifact of {where}", artifact.get("digest"), "artifact")
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        name = the_one(archive.namelist(), pattern, f"the package artifact of {where}")
        data = archive.read(name)
    own = f"{path}'s own run of a branch of its own"
    if digested:
        checked = (
            f"GitHub's {digested} digest of the artifact checked; no release notes give an integrity for a pull "
            f"request's build, which is {own}"
        )
    else:
        checked = f"nothing gives an integrity for it, so none was checked: a pull request's build is {own}"
    return Picked(
        saved(data, name, into),
        head,
        f"pull request #{entry.named.number}, the package artifact of its run {where} at its head; {checked}",
    )


def picked(api, url, reached, pattern, into):
    path = github.repository_path(url)
    named = picking.merging(reached, path)
    if len(named) > 1:
        raise Stop(f"Depends-On: lines name {picking.numbered(named)} of {path}, and a build is of one head: name one")
    if named:
        return of_a_pull_request(api, path, entry=named[0], pattern=pattern, into=into)
    return of_the_default_branch(api, url, path, pattern, into)
