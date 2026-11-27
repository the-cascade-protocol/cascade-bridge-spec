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
NOTHING_CHECKED = "neither the release's notes nor GitHub give an integrity for it, so none was checked"
DIGEST_CHECKED = "GitHub's sha256 digest of the asset checked; the release's notes give no integrity"


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


def nothing_placed(world):
    return not (world.root / "picked").exists() and not (world.workspace / VOCABULARY).exists()


def a_commit_on_main(world, line):
    return world.commit_on_main(PRODUCER, line)


def github_digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def released(world, commit, data, notes=None, digest=None, holds_the_package=True):
    """A build-<commit> release of the producer, as the sandbox and the runtime publish one per commit of main."""
    tag = f"build-{commit}"
    git("tag", tag, commit, cwd=world.origin(PRODUCER))
    world.root.joinpath(packed(commit)).write_bytes(data)
    assets = [{"name": f"other-{commit}.tgz", "browser_download_url": "file:///nowhere"}]
    if holds_the_package:
        url = world.root.joinpath(packed(commit)).as_uri()
        assets.insert(0, {"name": packed(commit), "browser_download_url": url, "digest": digest})
    world.pull_requests.releases[PRODUCER, tag] = {
        "id": len(world.pull_requests.releases) + 1,
        "tag_name": tag,
        "body": notes if notes is not None else f"https://example.org/{tag}/{packed(commit)}",
        "assets": assets,
    }


def in_package_builds(world, builds_by_commit):
    """One release, package-builds, holding a build of each commit as an asset with GitHub's digest of it, as the
    reference tables publish."""
    assets = []
    for commit, data in builds_by_commit.items():
        world.root.joinpath(packed(commit)).write_bytes(data)
        url = world.root.joinpath(packed(commit)).as_uri()
        assets.append({"name": packed(commit), "browser_download_url": url, "digest": github_digest(data)})
    world.pull_requests.releases[PRODUCER, "package-builds"] = {
        "id": 900,
        "tag_name": "package-builds",
        "body": "Each asset is this package packed at the commit its version names.",
        "assets": assets[:1],
        "all_assets": assets,
    }


def sri(data):
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def an_artifact(world, head, files_in_it, status="completed", expired=False, digest=True, fork=False, workflow_id=1):
    """The package artifact of a pull request run of the producer at the head."""
    run = world.pull_requests.run(
        PRODUCER, head, event="pull_request", status=status, workflow_id=workflow_id, fork=fork
    )
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
            "digest": github_digest(zipped.getvalue()) if digest is True else digest,
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

    class TestGivenAForksPullRequestNamedForItsFiles:
        def test_is_refused_naming_it_and_nothing_is_checked_out(self, world):
            """is refused, naming it, and nothing is checked out"""
            world.pull_request(VOCABULARY, 5, fork=True, fill=lambda path: (path / "NOTICE").write_text("five\n"))

            said, written = files(world, body=depends_on(VOCABULARY, 5), expected=1)

            assert f"{OWNER}/{VOCABULARY}/pull/5 is from a-fork-owner/{VOCABULARY}" in said
            assert written == {} and nothing_placed(world)

    class TestGivenTheConsumersOwnNamedPullRequests:
        @pytest.mark.parametrize(
            "state,fork", [("open", True), ("closed", False)], ids=["one from a fork", "one closed without merging"]
        )
        def test_change_nothing_picked(self, world, state, fork):
            """change nothing picked

            The step merges nothing into the consumer's checkout, so its own pull requests name nothing for it.
            """
            world.pull_request(CONSUMER, 2, state=state, fork=fork)

            _, written = files(world, body=depends_on(CONSUMER, 2))

            assert written["how"] == MATCHING

    class TestGivenAFolderThatHoldsFilesAlready:
        def test_is_refused_and_left_as_it_was(self, world):
            """is refused, and left as it was"""
            kept = world.workspace / VOCABULARY / "kept"
            kept.parent.mkdir()
            kept.write_text("mine\n")

            said, _ = files(world, body="", expected=1)

            assert "is there already" in said
            assert kept.read_text() == "mine\n"

    class TestGivenACheckoutThatIsAFile:
        def test_is_refused_saying_so(self, world):
            """is refused, saying so"""
            (world.workspace / VOCABULARY).write_text("a file\n")

            said, _ = files(world, body="", expected=1)

            assert f"::error::{world.workspace / VOCABULARY} is a file" in said

    class TestGivenAPackageReleasedAsABuildOfEachCommit:
        def test_is_the_newest_build_of_the_default_branch_its_integrity_checked(self, world):
            """is the newest build of the default branch, its integrity checked"""
            built = a_commit_on_main(world, "built")
            data = b"the build of " + built.encode()
            released(world, built, data, notes=f"Built from commit {built}. Integrity `{sri(data)}`.\n")
            head = a_commit_on_main(world, "still building")

            said, written = package(world, body="")

            assert written["commit"] == built
            assert open(written["path"], "rb").read() == data
            assert written["how"] == (
                f"the newest build of its default branch, the release build-{built}, 1 commit behind its head {head}, "
                "which has no build yet; its sha512 integrity, given in the release's notes, checked"
            )
            assert written["how"] in said

        def test_is_checked_against_githubs_digest_when_the_notes_give_no_integrity(self, world):
            """is checked against GitHub's digest when the notes give no integrity"""
            built = a_commit_on_main(world, "built")
            released(world, built, b"bytes", digest=github_digest(b"bytes"))

            said, written = package(world, body="")

            assert (
                written["how"] == f"the newest build of its default branch, the release build-{built}; {DIGEST_CHECKED}"
            )
            assert "::warning::" not in said

        def test_is_checked_against_both_when_the_notes_give_an_integrity_too(self, world):
            """is checked against both when the notes give an integrity too"""
            built = a_commit_on_main(world, "built")
            released(world, built, b"bytes", notes=f"Integrity: {sri(b'bytes')}\n", digest=github_digest(b"bytes"))

            _, written = package(world, body="")

            assert written["how"].endswith(
                "its sha512 integrity, given in the release's notes, and GitHub's sha256 digest of the asset, checked"
            )

        def test_warns_when_neither_gives_an_integrity(self, world):
            built = a_commit_on_main(world, "built")
            released(world, built, b"bytes")

            said, written = package(world, body="")

            assert written["how"].endswith(NOTHING_CHECKED)
            assert f"::warning::{packed(built)} of build-{built}: {NOTHING_CHECKED}" in said

        def test_is_refused_when_it_matches_no_integrity_the_notes_give(self, world):
            built = a_commit_on_main(world, "built")
            released(world, built, b"tampered", notes=f"Integrity `{sri(b'released')}`.\n")

            said, written = package(world, body="", expected=1)

            assert f"{packed(built)} matches no integrity the notes of build-{built} give" in said
            assert written == {}

        def test_is_refused_when_it_does_not_match_githubs_digest(self, world):
            built = a_commit_on_main(world, "built")
            released(world, built, b"tampered", digest=github_digest(b"uploaded"))

            said, written = package(world, body="", expected=1)

            assert f"{packed(built)} does not match GitHub's sha256 digest of it" in said
            assert written == {} and nothing_placed(world)

    class TestGivenTheBridgesReleaseNotes:
        @pytest.mark.parametrize(
            "integrity,expected",
            [(None, 0), (b"the build", 0), (b"another build", 1)],
            ids=["with only its Sources line", "with its Integrity line", "with an Integrity line of other bytes"],
        )
        def test_read_its_sources_line_as_no_integrity(self, world, integrity, expected):
            """read its Sources line as no integrity

            The Bridge's notes give `Sources: sha256-` and the SHA-256 of its sources in hex, which is no integrity of
            any file: read as base64 it is 48 bytes, no SHA-256 at all.
            """
            built = a_commit_on_main(world, "built")
            notes = f"Commit: {built}\nSources: sha256-{hashlib.sha256(b'the sources').hexdigest()}\n"
            if integrity:
                notes += f"Integrity: {sri(integrity)}\n"
            released(world, built, b"the build", notes=notes)

            said, written = package(world, body="", expected=expected)

            if integrity is None:
                assert written["how"].endswith(NOTHING_CHECKED)
            elif expected == 0:
                assert written["how"].endswith("its sha512 integrity, given in the release's notes, checked")
            else:
                assert f"{packed(built)} matches no integrity the notes of build-{built} give" in said

    class TestGivenANewerBuildWithoutTheFile:
        def test_is_an_older_build_saying_how_far_behind_and_why(self, world):
            """is an older build, saying how far behind and why"""
            older = a_commit_on_main(world, "older")
            released(world, older, b"older", digest=github_digest(b"older"))
            newer = a_commit_on_main(world, "newer")
            released(world, newer, b"newer", holds_the_package=False)
            head = a_commit_on_main(world, "still building")

            _, written = package(world, body="")

            assert written["commit"] == older
            assert written["how"] == (
                f"the newest build of its default branch, the release build-{older}, 2 commits behind its head {head}: "
                f"1 newer commit has no build yet and 1 newer build holds no file named {PACKAGE}; {DIGEST_CHECKED}"
            )

    class TestGivenAPackagePublishedAsAnAssetOfPackageBuilds:
        def test_is_the_newest_build_of_the_default_branch_checked_against_githubs_digest(self, world):
            """is the newest build of the default branch, checked against GitHub's digest"""
            older = a_commit_on_main(world, "older")
            newer = a_commit_on_main(world, "newer")
            head = a_commit_on_main(world, "still building")
            in_package_builds(world, {older: b"older", newer: b"newer"})

            _, written = package(world, body="")

            assert written["commit"] == newer
            assert open(written["path"], "rb").read() == b"newer"
            assert written["how"] == (
                f"the newest build of its default branch, {packed(newer)} of the release package-builds, "
                f"1 commit behind its head {head}, which has no build yet; {DIGEST_CHECKED}"
            )

    class TestGivenAPackageOfANamedOpenPullRequest:
        def test_is_the_package_artifact_of_its_run_at_its_head(self, world):
            head = world.pull_request(PRODUCER, 7)
            run = an_artifact(world, head, {packed(head): b"the head's build", "release-notes.md": b"notes"})

            said, written = package(world, body=depends_on(PRODUCER, 7))

            assert written["commit"] == head
            assert open(written["path"], "rb").read() == b"the head's build"
            assert written["how"] == (
                f"pull request #7, the package artifact of its run {run['html_url']} at its head; GitHub's sha256 "
                f"digest of the artifact checked; no release notes give an integrity for a pull request's build, "
                f"which is {OWNER}/{PRODUCER}'s own run of a branch of its own"
            )
            assert world.pull_requests.authorizations[-1] is None, "the artifact's storage is sent no token"
            assert f"Bearer {TOKEN}" in world.pull_requests.authorizations

        def test_is_refused_when_it_does_not_match_githubs_digest_of_the_artifact(self, world):
            head = world.pull_request(PRODUCER, 7)
            an_artifact(world, head, {packed(head): b"swapped"}, digest=github_digest(b"uploaded"))

            said, _ = package(world, body=depends_on(PRODUCER, 7), expected=1)

            assert "does not match GitHub's sha256 digest of it" in said
            assert nothing_placed(world)

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

        def test_is_refused_at_once_while_only_a_workflow_that_packs_nothing_is_unfinished(self, world, monkeypatch):
            """is refused at once while only a workflow that packs nothing is unfinished"""
            earlier = world.pull_request(PRODUCER, 6, fill=lambda path: (path / "SIX").write_text("six\n"))
            an_artifact(world, earlier, {packed(earlier): b"an earlier build"}, workflow_id=1)
            head = world.pull_request(PRODUCER, 7, fill=lambda path: (path / "SEVEN").write_text("seven\n"))
            world.pull_requests.run(PRODUCER, head, event="pull_request", status="completed", workflow_id=1)
            world.pull_requests.run(PRODUCER, head, event="pull_request", status="in_progress", workflow_id=2)
            monkeypatch.setattr(builds, "sleep", lambda seconds: pytest.fail("waited on a workflow that packs nothing"))

            said, _ = package(world, body=depends_on(PRODUCER, 7), expected=1)

            assert f"{OWNER}/{PRODUCER}/pull/7 has no package artifact at its head {head}" in said

        def test_is_refused_when_no_run_at_its_head_has_packed_one(self, world):
            head = world.pull_request(PRODUCER, 7)
            an_artifact(world, head, {packed(head): b"gone"}, expired=True)

            said, _ = package(world, body=depends_on(PRODUCER, 7), expected=1)

            assert f"{OWNER}/{PRODUCER}/pull/7 has no package artifact at its head {head}" in said

        def test_is_never_the_artifact_of_a_forks_run_at_the_same_head(self, world):
            """is never the artifact of a fork's run at the same head"""
            head = world.pull_request(PRODUCER, 7)
            an_artifact(world, head, {packed(head): b"a fork's build"}, fork=True)

            said, _ = package(world, body=depends_on(PRODUCER, 7), expected=1)

            assert f"{OWNER}/{PRODUCER}/pull/7 has no package artifact at its head {head}" in said
            assert nothing_placed(world)

    class TestGivenAPackageOfAForksPullRequest:
        def test_is_refused_naming_it_and_nothing_is_placed(self, world):
            """is refused, naming it, and nothing is placed"""
            head = world.pull_request(PRODUCER, 7, fork=True)
            an_artifact(world, head, {packed(head): b"an outsider's build"})

            said, written = package(world, body=depends_on(PRODUCER, 7), expected=1)

            assert f"{OWNER}/{PRODUCER}/pull/7 is from a-fork-owner/{PRODUCER}" in said
            assert written == {} and nothing_placed(world)

        @pytest.mark.parametrize("between_from_a_fork", [False, True], ids=["through ours", "through a fork's"])
        def test_reached_through_another_pull_requests_body_is_refused(self, world, between_from_a_fork):
            """reached through another pull request's body, is refused

            A pull request's body is its author's to edit at any time, after a review too.
            """
            head = world.pull_request(PRODUCER, 7, fork=True)
            an_artifact(world, head, {packed(head): b"an outsider's build"})
            world.pull_request(VOCABULARY, 5, body=depends_on(PRODUCER, 7), fork=between_from_a_fork)

            said, written = package(world, body=depends_on(VOCABULARY, 5), expected=1)

            refused = (
                f"{VOCABULARY}/pull/5 is from a-fork-owner" if between_from_a_fork else f"{PRODUCER}/pull/7 is from"
            )
            assert f"{OWNER}/{refused}" in said
            assert written == {} and nothing_placed(world)

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
