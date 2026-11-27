"""The pick action: another repository's files or package build, for a job in a repository with no compatibility.json."""

import base64
import contextlib
import hashlib
import io
import os
import tempfile
import zipfile

import pytest

import pick
from compatibility_tool import builds
from compatibility_world import MATCHING, OWNER, TOKEN, VOCABULARY, VOCABULARY_FILES, depends_on, git

CONSUMER = "tables"
PRODUCER = "adapter"
PACKAGE = "adapter-*.tgz"


def packed(commit):
    return f"adapter-0.0.0-commit-{commit}.tgz"


def picked(world, *argv, body, expected=0):
    """The pick, run as the action runs it in a consumer's pull request: its log, and the outputs it wrote."""
    world.pull_request(CONSUMER, 1, body=body)
    variables = world.ci(repository=CONSUMER, event=world.event(1, CONSUMER))
    outputs = world.root / "outputs"
    outputs.write_text("", encoding="utf-8")
    environment = world.environment(**variables, GITHUB_OUTPUT=outputs)
    printed = io.StringIO()
    was = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(environment)
        with pytest.MonkeyPatch.context() as patch, contextlib.redirect_stdout(printed):
            patch.setattr(tempfile, "tempdir", None)
            status = pick.main(["pick.py", *argv, "--into", str(world.root / "picked")])
    finally:
        os.environ.clear()
        os.environ.update(was)
    said = printed.getvalue()
    assert status == expected, f"exited {status}, {expected} expected\n{said}"
    written = dict(line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines())
    return said, written


def files(world, **given):
    return picked(world, f"{OWNER}/{VOCABULARY}", "--checkout", str(world.workspace / VOCABULARY), **given)


def package(world, **given):
    return picked(world, f"{OWNER}/{PRODUCER}", "--package", PACKAGE, **given)


def a_commit_on_main(world, line):
    return world.commit_on_main(PRODUCER, line)


def released(world, commit, data, notes=None):
    """A build-<commit> release of the producer, as the sandbox and the runtime publish one per commit of main."""
    tag = f"build-{commit}"
    git("tag", tag, commit, cwd=world.origin(PRODUCER))
    world.root.joinpath(packed(commit)).write_bytes(data)
    world.pull_requests.releases[PRODUCER, tag] = {
        "id": len(world.pull_requests.releases) + 1,
        "tag_name": tag,
        "body": notes if notes is not None else f"https://example.org/{tag}/{packed(commit)}",
        "assets": [
            {"name": packed(commit), "browser_download_url": world.root.joinpath(packed(commit)).as_uri()},
            {"name": f"other-{commit}.tgz", "browser_download_url": "file:///nowhere"},
        ],
    }


def in_package_builds(world, builds_by_commit):
    """One release, package-builds, holding a build of each commit as an asset, as the reference tables publish."""
    assets = []
    for commit, data in builds_by_commit.items():
        world.root.joinpath(packed(commit)).write_bytes(data)
        assets.append({"name": packed(commit), "browser_download_url": world.root.joinpath(packed(commit)).as_uri()})
    world.pull_requests.releases[PRODUCER, "package-builds"] = {
        "id": 900,
        "tag_name": "package-builds",
        "body": "Each asset is this package packed at the commit its version names.",
        "assets": assets[:1],
        "all_assets": assets,
    }


def sri(data):
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def an_artifact(world, head, files_in_it, status="completed", expired=False):
    """The package artifact of a pull request run of the producer at the head."""
    run = world.pull_requests.run(PRODUCER, head, event="pull_request", status=status)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        for name, data in files_in_it.items():
            archive.writestr(name, data)
    identifier = 7000 + run["id"]
    world.pull_requests.blobs[identifier] = zipped.getvalue()
    world.pull_requests.artifacts_by_run.setdefault(run["id"], []).append(
        {
            "id": identifier,
            "name": "package",
            "expired": expired,
            "archive_download_url": f"{world.api_url}/artifacts/{identifier}/zip",
        }
    )
    return run


class TestPickingAnotherRepositorysFilesOrPackageBuild:
    """Picking another repository's files or package build for a job · .github/actions/pick, scripts/pick.py

    A repository that installs another's package, or reads its files, with no compatibility.json to name it a
    counterpart, picks it in one step: the files at the producer's default branch with the pull request a
    `Depends-On:` line names merged in, as a counterpart is picked; the package as the newest build of the producer's
    default branch, or the build of the named pull request's head. The step says what it picked and how, and hands a
    later step the path, the commit and the how.
    """

    class TestGivenFilesAndNoNamedPullRequest:
        def test_are_checked_out_at_the_head_of_the_default_branch(self, world):
            said, written = files(world, body="")

            assert written["path"] == str(world.workspace / VOCABULARY)
            assert written["commit"] == world.commits[VOCABULARY]
            assert written["how"] == MATCHING
            assert (world.workspace / VOCABULARY / VOCABULARY_FILES[0]).is_file()
            assert world.commits[VOCABULARY] in said

    class TestGivenFilesAndANamedOpenPullRequest:
        def test_are_checked_out_with_it_merged_into_its_target(self, world):
            """are checked out with it merged into its target"""
            world.pull_request(VOCABULARY, 5, fill=lambda path: (path / "NOTICE").write_text("five\n"))

            _, written = files(world, body=depends_on(VOCABULARY, 5))

            assert written["how"] == "pull request #5 merged into main"
            assert (world.workspace / VOCABULARY / "NOTICE").read_text() == "five\n"
            assert (world.workspace / VOCABULARY / VOCABULARY_FILES[0]).is_file()

    class TestGivenFilesAndANamedMergedPullRequest:
        def test_are_checked_out_at_the_default_branch(self, world):
            world.pull_request(VOCABULARY, 5, merged=True, state="closed")

            _, written = files(world, body=depends_on(VOCABULARY, 5))

            assert written["commit"] == world.commits[VOCABULARY]
            assert written["how"] == MATCHING

    class TestGivenANamedPullRequestClosedWithoutMerging:
        def test_is_refused_naming_it(self, world):
            """is refused, naming it"""
            world.pull_request(VOCABULARY, 5, state="closed")

            said, written = files(world, body=depends_on(VOCABULARY, 5), expected=1)

            assert f"{OWNER}/{VOCABULARY}/pull/5 is closed without merging" in said
            assert written == {}

    class TestGivenAFolderThatHoldsFilesAlready:
        def test_is_refused_and_left_as_it_was(self, world):
            """is refused, and left as it was"""
            kept = world.workspace / VOCABULARY / "kept"
            kept.parent.mkdir()
            kept.write_text("mine\n")

            said, _ = files(world, body="", expected=1)

            assert "is there already" in said
            assert kept.read_text() == "mine\n"

    class TestGivenAPackageReleasedAsABuildOfEachCommit:
        def test_is_the_newest_build_of_the_default_branch_its_integrity_checked(self, world):
            """is the newest build of the default branch, its integrity checked"""
            built = a_commit_on_main(world, "built")
            data = b"the build of " + built.encode()
            released(world, built, data, notes=f"Built from commit {built}. Integrity `{sri(data)}`.\n")
            a_commit_on_main(world, "still building")

            said, written = package(world, body="")

            assert written["commit"] == built
            assert open(written["path"], "rb").read() == data
            assert written["how"] == (
                f"the newest build of its default branch, the release build-{built}; "
                "its sha512 integrity, given in the release's notes, checked"
            )
            assert written["how"] in said

        def test_says_so_when_the_notes_give_no_integrity(self, world):
            built = a_commit_on_main(world, "built")
            released(world, built, b"bytes")

            _, written = package(world, body="")

            assert written["how"].endswith("the release's notes give no integrity, so none was checked")

        def test_is_refused_when_it_matches_no_integrity_the_notes_give(self, world):
            built = a_commit_on_main(world, "built")
            released(world, built, b"tampered", notes=f"Integrity `{sri(b'released')}`.\n")

            said, written = package(world, body="", expected=1)

            assert f"{packed(built)} matches no integrity the notes of build-{built} give" in said
            assert written == {}

    class TestGivenAPackagePublishedAsAnAssetOfPackageBuilds:
        def test_is_the_newest_build_of_the_default_branch(self, world):
            older = a_commit_on_main(world, "older")
            newer = a_commit_on_main(world, "newer")
            a_commit_on_main(world, "still building")
            in_package_builds(world, {older: b"older", newer: b"newer"})

            _, written = package(world, body="")

            assert written["commit"] == newer
            assert open(written["path"], "rb").read() == b"newer"
            assert written["how"] == (
                f"the newest build of its default branch, {packed(newer)} of the release package-builds; "
                "the release's notes give no integrity, so none was checked"
            )

    class TestGivenAPackageOfANamedOpenPullRequest:
        def test_is_the_package_artifact_of_its_run_at_its_head(self, world):
            head = world.pull_request(PRODUCER, 7)
            run = an_artifact(world, head, {packed(head): b"the head's build", "release-notes.md": b"notes"})

            said, written = package(world, body=depends_on(PRODUCER, 7))

            assert written["commit"] == head
            assert open(written["path"], "rb").read() == b"the head's build"
            assert written["how"] == (
                f"pull request #7, the package artifact of its run {run['html_url']} at its head; "
                "a pull request's build has no release notes, so no integrity was checked"
            )
            assert world.pull_requests.authorizations[-1] is None, "the artifact's storage is sent no token"
            assert f"Bearer {TOKEN}" in world.pull_requests.authorizations

        def test_waits_for_the_artifact_while_a_run_at_its_head_is_unfinished(self, world, monkeypatch):
            head = world.pull_request(PRODUCER, 7)
            running = world.pull_requests.run(PRODUCER, head, event="pull_request")
            now = [0.0]

            def sleep(seconds):
                now[0] += seconds
                running["status"] = "completed"
                an_artifact(world, head, {packed(head): b"packed meanwhile"})

            monkeypatch.setattr(builds, "monotonic", lambda: now[0])
            monkeypatch.setattr(builds, "sleep", sleep)

            _, written = package(world, body=depends_on(PRODUCER, 7))

            assert open(written["path"], "rb").read() == b"packed meanwhile"

        def test_is_refused_when_no_run_at_its_head_has_packed_one(self, world):
            head = world.pull_request(PRODUCER, 7)
            an_artifact(world, head, {packed(head): b"gone"}, expired=True)

            said, _ = package(world, body=depends_on(PRODUCER, 7), expected=1)

            assert f"{OWNER}/{PRODUCER}/pull/7 has no package artifact at its head {head}" in said

    class TestGivenAPackageOfTwoNamedOpenPullRequestsOfTheProducer:
        def test_is_refused_naming_both(self, world):
            """is refused, naming both"""
            world.pull_request(PRODUCER, 7)
            world.pull_request(PRODUCER, 8)

            said, _ = package(world, body=depends_on(PRODUCER, 7) + depends_on(PRODUCER, 8), expected=1)

            assert "name #7 and #8 of" in said

    class TestGivenAPackageOfANamedMergedPullRequest:
        def test_is_the_newest_build_of_the_default_branch(self, world):
            world.pull_request(PRODUCER, 7, merged=True, state="closed")
            built = a_commit_on_main(world, "built")
            released(world, built, b"main's build")

            _, written = package(world, body=depends_on(PRODUCER, 7))

            assert written["commit"] == built
