import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import Graph

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "fixtures" / "synthetic-json-adapter-with-failing-entries"
VOCABULARIES = ROOT / "fixtures" / "synthetic-vocabularies"
ENGINE = ROOT / "fixtures" / "fake-engine" / "engine.py"
JUDGE = ROOT / "engine" / "faults-of-a-report-against-expected-outcomes.rq"
MANIFEST = ADAPTER / "fixtures" / "manifest.ttl"

THE_CHECK = "https://ns.cascadeprotocol.org/bridge/v1-draft#conversionWritesWhatTheAccountingCarries"
MUST_FAIL = ["contained-label-not-written", "label-not-written", "last-update-not-written"]
MUST_PASS = [
    "contained-label-of-a-record-the-adapter-does-not-map",
    "every-carried-path-written",
    "label-empty",
    "label-not-written-and-reported",
    "last-update-not-written-and-reported",
]


def as_listed():
    return {name: ("failed", THE_CHECK) if name in MUST_FAIL else ("passed", None) for name in [*MUST_FAIL, *MUST_PASS]}


def written(outcomes):
    """An EARL report: each entry's outcome, and the check that failed it where there is one."""
    report = "@prefix earl: <http://www.w3.org/ns/earl#> .\n"
    for name, (outcome, check) in outcomes.items():
        by = "" if check is None else f" ; <https://ns.cascadeprotocol.org/bridge/v1-draft#failedCheck> <{check}>"
        report += (
            f"[] a earl:Assertion ; earl:test <{MANIFEST.resolve().as_uri()}#{name}> ;"
            f" earl:result [ a earl:TestResult ; earl:outcome earl:{outcome}{by} ] .\n"
        )
    return report


def faults_of(report):
    graph = Graph().parse(data=report, format="turtle")
    graph.parse(MANIFEST, format="turtle", publicID=MANIFEST.resolve().as_uri())
    return [str(row.fault) for row in graph.query(JUDGE.read_text(encoding="utf-8"))]


def reported_by_the_fake_engine(canned, tmp_path):
    earl = tmp_path / "report.ttl"
    run = subprocess.run(
        [sys.executable, str(ENGINE), "--canned", canned, "test", str(ADAPTER), "--earl", str(earl)]
        + ["--vocabularies", str(VOCABULARIES)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return earl.read_text(encoding="utf-8")


class TestJudgingAReportOfEntriesThatMustFail:
    """Judging a report of entries that must fail · engine/faults-of-a-report-against-expected-outcomes.rq

    A manifest may list, for an entry, the outcome a Bridge must report it with and, for a failed one, the check that
    fails it. An engine that converts and compares nothing reports every entry passed: that report holds for every
    other adapter's entries, and is refused for these.
    """

    class TestGivenEachEntryReportedAsTheManifestListsIt:
        def test_holds(self, tmp_path):
            assert faults_of(reported_by_the_fake_engine("listed", tmp_path)) == []

    class TestGivenEveryEntryReportedPassed:
        def test_is_refused_naming_each_entry_that_must_fail(self, tmp_path):
            assert faults_of(reported_by_the_fake_engine("everything-passed", tmp_path)) == [
                f"{name} is reported passed, not failed" for name in MUST_FAIL
            ]

    class TestGivenAnEntryFailedBy:
        @pytest.mark.parametrize(
            "check",
            [None, "https://example.org/a-check-of-another-rule"],
            ids=["no check", "another check"],
        )
        def test_anything_but_the_check_the_manifest_lists_is_refused(self, check):
            report = written(as_listed() | {"label-not-written": ("failed", check)})
            assert faults_of(report) == [
                "label-not-written is reported failed, but not by conversionWritesWhatTheAccountingCarries"
            ]

    class TestGivenAnEntryThatMustPassReportedFailed:
        def test_is_refused(self):
            report = written(as_listed() | {"label-empty": ("failed", THE_CHECK)})
            assert faults_of(report) == ["label-empty is reported failed, not passed"]

    class TestGivenAnEntryNotReported:
        def test_is_refused(self):
            report = written({name: outcome for name, outcome in as_listed().items() if name != "label-empty"})
            assert faults_of(report) == ["label-empty has no outcome"]
