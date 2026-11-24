"""Which version of each repository a run uses, as Zuul checks out a required project."""

import json

import pytest

from compatibility_tool import github
from compatibility_tool.console import Stop
from compatibility_tool.github import Event
from compatibility_world import MATCHING, depends_on, git
from place_vocabulary import named_head


class TestPickingTheVersionOfEachRepositoryARunUses:
    """Picking the version of each repository a run uses · Depends-On:

    Nothing pins one repository to a commit of another. A run picks each: the pull requests named on `Depends-On:` lines
    merged into the branch they target, else the branch named like the one the run is on, else the default branch.
    """

    class TestGivenANamedPullRequest:
        def test_is_merged_into_the_branch_it_targets(self, world):
            head = world.pull_request("adapter", 7, fill=lambda path: (path / "NOTICE").write_text("named\n"))
            world.commit_on_main("adapter", "AFTER")
            engine, event = world.engine_under_test(body=depends_on("adapter", 7))

            world.tool(engine, **world.ci(event=event))

            adapter = world.record()["repositories"]["adapter"]
            assert adapter["how"] == "pull request #7 merged into main"
            assert (world.workspace / "adapter" / "NOTICE").read_text() == "named\n"
            assert adapter["commit"] != head, "the run uses the merge, not the pull request's head"
            assert (world.workspace / "adapter" / "AFTER").exists(), "what the branch gained since is there too"

    class TestGivenAPullRequestNamedByANamedPullRequest:
        def test_is_followed(self, world):
            world.pull_request("cascade-bridge-spec", 3)
            world.pull_request("adapter", 7, body=depends_on("cascade-bridge-spec", 3))
            engine, event = world.engine_under_test(body=depends_on("adapter", 7))

            world.tool(engine, **world.ci(event=event))

            specification = world.record()["repositories"]["cascade-bridge-spec"]
            assert specification["how"] == "pull request #3 merged into main"

    class TestGivenTwoNamedPullRequestsTargetingOneBranch:
        def test_merges_both_in(self, world):
            world.pull_request("adapter", 7, fill=lambda path: (path / "SEVEN").write_text("seven\n"))
            world.pull_request("adapter", 8, fill=lambda path: (path / "EIGHT").write_text("eight\n"))
            engine, event = world.engine_under_test(body=depends_on("adapter", 7) + depends_on("adapter", 8))

            world.tool(engine, **world.ci(event=event))

            assert world.record()["repositories"]["adapter"]["how"] == "pull requests #7 and #8 merged into main"
            assert (world.workspace / "adapter" / "SEVEN").exists()
            assert (world.workspace / "adapter" / "EIGHT").exists()

    class TestGivenTwoNamedPullRequestsTargetingDifferentBranches:
        def test_fails_the_check_naming_them(self, world):
            """fails the check, naming them"""
            world.branch("adapter", "stable/x")
            world.pull_request("adapter", 7)
            world.pull_request("adapter", 8, base="stable/x")
            engine, event = world.engine_under_test(body=depends_on("adapter", 7) + depends_on("adapter", 8))

            said = world.tool(engine, 1, **world.ci(event=event))

            assert "adapter/pull/7" in said and "adapter/pull/8" in said
            assert "target one branch" in said

    class TestGivenANamedPullRequestThatConflicts:
        def test_fails_the_check_naming_it(self, world):
            """fails the check, naming it"""
            world.pull_request("adapter", 7, fill=lambda path: (path / "README.md").write_text("seven\n"))
            world.pull_request("adapter", 8, fill=lambda path: (path / "README.md").write_text("eight\n"))
            engine, event = world.engine_under_test(body=depends_on("adapter", 7) + depends_on("adapter", 8))

            said = world.tool(engine, 1, **world.ci(event=event))

            assert "adapter/pull/8" in said
            assert "conflict" in said

    class TestGivenANamedPullRequestClosedWithoutMerging:
        def test_fails_the_check_naming_it(self, world):
            """fails the check, naming it"""
            world.pull_request("adapter", 7, state="closed")
            engine, event = world.engine_under_test(body=depends_on("adapter", 7))

            said = world.tool(engine, 1, **world.ci(event=event))

            assert "adapter/pull/7" in said
            assert "closed without merging" in said

    class TestGivenANamedPullRequestNamingThePullRequestUnderTestBack:
        def test_is_merged_into_the_branch_it_targets(self, world):
            world.pull_request(
                "adapter", 7, body=depends_on("engine", 1), fill=lambda path: (path / "NOTICE").write_text("7")
            )
            engine, event = world.engine_under_test(body=depends_on("adapter", 7))

            world.tool(engine, **world.ci(event=event))

            assert world.record()["repositories"]["adapter"]["how"] == "pull request #7 merged into main"
            assert "| pull request #7 merged into main |" in world.table()
            assert (world.workspace / "adapter" / "NOTICE").read_text() == "7"

    class TestGivenAMergedNamedPullRequest:
        def test_adds_nothing_and_the_matching_branch_is_used(self, world):
            """adds nothing, and the matching branch is used"""
            world.pull_request("adapter", 7, state="closed", merged=True)
            world.branch("adapter", "stable/x", fill=lambda path: (path / "STABLE").write_text("stable\n"))
            world.branch("cascade-bridge-spec", "stable/x")
            engine, event = world.engine_under_test(body=depends_on("adapter", 7), base="stable/x")

            world.tool(engine, **world.ci(event=event, branch="stable/x"))

            repositories = world.record()["repositories"]
            assert repositories["adapter"]["how"] == "stable/x, the branch matching the pull request's target"
            assert (
                repositories["cascade-bridge-spec"]["how"] == "stable/x, the branch matching the pull request's target"
            )
            assert (world.workspace / "adapter" / "STABLE").exists()

    class TestGivenARepositoryWithoutTheMatchingBranch:
        def test_is_used_at_its_default_branch(self, world):
            engine, event = world.engine_under_test(base="stable/x")

            world.tool(engine, **world.ci(event=event, branch="stable/x"))

            assert world.record()["repositories"]["adapter"]["how"] == "main, the default branch"

    class TestGivenANamedPullRequestInARepositoryTheRunChecksNothingOutFrom:
        def test_is_listed_as_not_used(self, world):
            world.pull_request("cascade-cli", 4)
            engine, event = world.engine_under_test(body=depends_on("cascade-cli", 4))

            said = world.tool(engine, **world.ci(event=event))

            assert "cascade-cli" in world.table()
            assert "not used" in world.table()
            assert "does not hold" not in said

    class TestGivenADescriptionChangedBetweenRuns:
        def test_is_read_again_by_the_second_run(self, world):
            world.pull_request("adapter", 7, fill=lambda path: (path / "NOTICE").write_text("named\n"))
            engine, event = world.engine_under_test()

            world.tool(engine, **world.ci(event=event))
            assert world.record()["repositories"]["adapter"]["how"] == MATCHING

            world.pull_requests.get("engine", 1)["body"] = depends_on("adapter", 7)
            world.tool(engine, **world.ci(event=event))
            assert world.record()["repositories"]["adapter"]["how"] == "pull request #7 merged into main"

    class TestGivenAPushRun:
        def test_uses_the_branch_it_runs_on_and_records_how_it_picked_it(self, world):
            """uses the branch it runs on and records how it picked it"""
            engine = world.engine([world.url("adapter")])

            world.tool(engine, **world.ci())

            repositories = world.record()["repositories"]
            assert repositories["adapter"]["how"] == "main, the branch this run is on"
            assert repositories["engine"]["commit"] == git("rev-parse", "HEAD", cwd=engine)

    class TestGivenARunStartedByHandOnABranchWithAnOpenPullRequest:
        def test_reads_the_pull_request_as_a_run_it_started_would(self, world):
            world.pull_request("adapter", 7, fill=lambda path: (path / "NOTICE").write_text("named\n"))
            engine, _ = world.engine_under_test(body=depends_on("adapter", 7))
            world.pull_requests.get("engine", 1)["head"]["ref"] = "feature"

            said = world.tool(engine, **world.ci(branch="feature", names_default=False))

            repositories = world.record()["repositories"]
            assert repositories["adapter"]["how"] == "pull request #7 merged into main"
            assert repositories["engine"]["how"] == "feature, the head of pull request #1"
            assert (world.workspace / "adapter" / "NOTICE").read_text() == "named\n"
            assert "A run started by hand on feature: its open pull request is #1" in said

    class TestGivenARunStartedByHand:
        @staticmethod
        def event_of(monkeypatch, tmp_path, api, branch="feature", ref_type="branch", payload=None):
            event = tmp_path / "event.json"
            event.write_text(json.dumps(payload or {}), encoding="utf-8")
            for name, value in {
                "GITHUB_REPOSITORY": "the-cascade-protocol/engine",
                "GITHUB_REF_NAME": branch,
                "GITHUB_REF_TYPE": ref_type,
                "GITHUB_EVENT_PATH": str(event),
            }.items():
                monkeypatch.setenv(name, value)
            return github.event(api)

        class Listing:
            """What GitHub says of the branch: which pull request has it as its head, and the repository's default."""

            def __init__(self, open_pull=None, default="main"):
                self.open_pull, self.default, self.asked = open_pull, default, []

            def default_branch(self, repository):
                self.asked.append("default branch")
                return self.default

            def open_pull_request_from(self, repository, branch):
                self.asked.append(f"pulls from {branch}")
                return self.open_pull

            def pull_request(self, named):
                return {"base": {"ref": "stable/x"}}

        def test_is_for_the_open_pull_request_whose_head_is_the_branch(self, monkeypatch, tmp_path):
            found = self.event_of(monkeypatch, tmp_path, self.Listing(open_pull=7))

            assert found == Event("the-cascade-protocol/engine", 7, "stable/x", hand_started_on="feature")

        def test_is_for_no_pull_request_when_none_is_open(self, monkeypatch, tmp_path):
            found = self.event_of(monkeypatch, tmp_path, self.Listing())

            assert found == Event("the-cascade-protocol/engine", None, "feature")

        def test_asks_about_no_pull_request_on_the_default_branch(self, monkeypatch, tmp_path):
            listing = self.Listing(open_pull=7)

            found = self.event_of(monkeypatch, tmp_path, listing, branch="main")

            assert found == Event("the-cascade-protocol/engine", None, "main")
            assert listing.asked == ["default branch"]

        def test_takes_the_default_branch_from_the_event_when_it_names_one(self, monkeypatch, tmp_path):
            listing = self.Listing(open_pull=7)
            payload = {"repository": {"default_branch": "trunk"}}

            found = self.event_of(monkeypatch, tmp_path, listing, branch="trunk", payload=payload)

            assert found == Event("the-cascade-protocol/engine", None, "trunk")
            assert listing.asked == []

        def test_asks_about_nothing_on_a_tag(self, monkeypatch, tmp_path):
            listing = self.Listing(open_pull=7)

            found = self.event_of(monkeypatch, tmp_path, listing, branch="v1", ref_type="tag")

            assert found == Event("the-cascade-protocol/engine", None, "v1")
            assert listing.asked == []

        def test_asks_about_nothing_when_a_pull_request_started_the_run(self, monkeypatch, tmp_path):
            listing = self.Listing(open_pull=9)
            payload = {"pull_request": {"number": 3}}

            found = self.event_of(monkeypatch, tmp_path, listing, branch="refs/pull/3/merge", payload=payload)

            assert found == Event("the-cascade-protocol/engine", 3, "stable/x")
            assert listing.asked == []

    class TestGivenASliceThatReadsTheVocabularyBesideTheRepositoryUnderTest:
        @staticmethod
        def the_vocabulary_picked(body, head=None):
            event = Event("the-cascade-protocol/cascade-bridge-spec", 5, "main")
            head = head or {"repo": {"clone_url": "https://github.com/someone/fork.git"}, "sha": "abc"}

            class Api:
                def pull_request(self, named):
                    if named.number == 5:
                        return {"body": body}
                    return {"head": head}

            return named_head(Api(), event)

        def test_is_the_head_of_the_vocabulary_pull_request_the_description_names(self):
            body = depends_on("cascade-vocabulary", 9) + depends_on("cascade-runtime-js", 3)

            assert self.the_vocabulary_picked(body) == ("https://github.com/someone/fork.git", "abc")

        def test_is_the_default_branch_when_the_description_names_none(self):
            assert self.the_vocabulary_picked(depends_on("cascade-runtime-js", 3)) is None

        def test_is_the_default_branch_on_a_push(self):
            assert named_head(None, Event("the-cascade-protocol/cascade-bridge-spec", None, "main")) is None

        def test_stops_when_the_vocabulary_pull_request_has_no_head_repository(self):
            with pytest.raises(Stop, match="has no head repository"):
                self.the_vocabulary_picked(depends_on("cascade-vocabulary", 9), head={"repo": None})

        def test_stops_naming_both_when_the_description_names_two_vocabulary_pull_requests(self):
            body = depends_on("cascade-vocabulary", 9) + depends_on("cascade-vocabulary", 10)

            with pytest.raises(Stop, match=r"cascade-vocabulary/pull/9.*cascade-vocabulary/pull/10"):
                self.the_vocabulary_picked(body)
