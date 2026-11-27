import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import RDF, Graph, URIRef

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "fixtures" / "synthetic-json-adapter-with-failing-entries"
VOCABULARIES = ROOT / "fixtures" / "synthetic-vocabularies"
ENGINE = ROOT / "fixtures" / "fake-engine" / "engine.py"
JUDGE = ROOT / "engine" / "faults-of-a-report-against-expected-outcomes.rq"
MANIFEST = ADAPTER / "fixtures" / "manifest.ttl"

CHECK = URIRef("https://ns.cascadeprotocol.org/bridge/v1-draft#expectedFailedCheck")
THE_CHECK = "https://ns.cascadeprotocol.org/bridge/v1-draft#conversionWritesWhatTheAccountingCarries"
MUST_FAIL = [
    "caption-repeat-empty-beside-full",
    "contained-label-not-written",
    "contained-label-reported-other-gap",
    "contained-label-sibling-reported",
    "contained-record-held-back-whole",
    "empty-label-beside-last-update",
    "finding-of-the-other-unit",
    "held-back-note-beside-label",
    "label-false-not-written",
    "label-finding-at-the-unit",
    "label-finding-by-value-only",
    "label-not-written",
    "label-written-on-a-pointed-record",
    "label-written-only-as-empty",
    "label-zero-not-written",
    "last-update-not-written",
    "nearer-label-not-written",
    "null-and-array-no-empty-child",
    "record-below-an-element-held-back",
    "record-holding-it-is-nearer",
    "related-label-unmapped-value-gap",
    "remark-of-two-classes-one-held",
    "respelled-selector-label-unwritten",
    "selector-outside-the-unit",
    "selector-selects-no-node",
    "unmapped-contained-label-unreported",
]
ENTRIES = {
    str(entry).rpartition("#")[2]
    for entry in Graph()
    .parse(MANIFEST, format="turtle", publicID=MANIFEST.resolve().as_uri())
    .subjects(RDF.type, URIRef("https://ns.cascadeprotocol.org/bridge/v1-draft#IsomorphicConversionTest"))
}
MUST_PASS = sorted(ENTRIES - set(MUST_FAIL))


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


def faults_of(report, manifest=None):
    graph = Graph().parse(data=report, format="turtle")
    graph.parse(
        data=MANIFEST.read_text(encoding="utf-8") if manifest is None else manifest,
        format="turtle",
        publicID=MANIFEST.resolve().as_uri(),
    )
    return [str(row.fault) for row in graph.query(JUDGE.read_text(encoding="utf-8"))]


SYNTHETIC_MANIFEST = ROOT / "fixtures" / "synthetic-adapter" / "fixtures" / "manifest.ttl"
SYNTHETIC = SYNTHETIC_MANIFEST.read_text(encoding="utf-8")
OTHER_JUDGE = ROOT / "engine" / "faults-of-a-report.rq"
OTHER_CHECK = "https://example.org/a-check"
MIXED = (
    SYNTHETIC
    + f"\n<#example-0001> <https://ns.cascadeprotocol.org/bridge/v1-draft#expectedFailedCheck> <{OTHER_CHECK}> .\n"
)
SYNTHETIC_ENTRIES = [
    "example-0001",
    "example-0002",
    "example-0002-and-example-0007-name-one-record",
    "example-0003",
    "example-0004",
    "example-0005",
    "example-0006",
    "example-0008",
    "example-0008-names-two-records",
    "example-release-2026-01",
]


def correct_report_of_the_synthetic_adapter():
    return {name: ("passed", None) for name in SYNTHETIC_ENTRIES} | {
        "example-0002": ("cantTell", None),
        "example-release-2026-01": ("untested", None),
    }


def mixed_report():
    return correct_report_of_the_synthetic_adapter() | {"example-0001": ("failed", OTHER_CHECK)}


REPORTS_OF_THE_SYNTHETIC_ADAPTER = {
    "correct": correct_report_of_the_synthetic_adapter(),
    "input-only passed": correct_report_of_the_synthetic_adapter() | {"example-0002": ("passed", None)},
    "input-only untested": correct_report_of_the_synthetic_adapter() | {"example-0002": ("untested", None)},
    "input-only failed": correct_report_of_the_synthetic_adapter() | {"example-0002": ("failed", None)},
    "dataset completion passed": correct_report_of_the_synthetic_adapter()
    | {"example-release-2026-01": ("passed", None)},
    "must-pass failed": correct_report_of_the_synthetic_adapter() | {"example-0003": ("failed", None)},
    "must-pass inapplicable": correct_report_of_the_synthetic_adapter() | {"example-0003": ("inapplicable", None)},
    "must-pass cantTell": correct_report_of_the_synthetic_adapter() | {"example-0003": ("cantTell", None)},
    "must-pass untested": correct_report_of_the_synthetic_adapter() | {"example-0003": ("untested", None)},
    "entry not reported": {k: v for k, v in correct_report_of_the_synthetic_adapter().items() if k != "example-0004"},
}


SYNTHETIC_BASE = SYNTHETIC_MANIFEST.resolve().as_uri()


def faults_over(manifest, report, judge=JUDGE, base=SYNTHETIC_BASE):
    """The faults `judge` finds in a report, given as outcomes by entry name or as Turtle, over a manifest read at `base`."""
    if not isinstance(report, str):
        report = written_at(base, report)
    graph = Graph().parse(data=report, format="turtle")
    graph.parse(data=manifest, format="turtle", publicID=base)
    return [str(row.fault) for row in graph.query(judge.read_text(encoding="utf-8"))]


def written_at(base, outcomes):
    report = "@prefix earl: <http://www.w3.org/ns/earl#> .\n"
    for name, (outcome, check) in outcomes.items():
        by = "" if check is None else f" ; <https://ns.cascadeprotocol.org/bridge/v1-draft#failedCheck> <{check}>"
        report += (
            f"[] a earl:Assertion ; earl:test <{base}#{name}> ;"
            f" earl:result [ a earl:TestResult ; earl:outcome earl:{outcome}{by} ] .\n"
        )
    return report


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
        def test_lists_a_check_for_the_entries_that_must_fail_and_none_for_the_rest(self):
            manifest = Graph().parse(MANIFEST, format="turtle", publicID=MANIFEST.resolve().as_uri())
            listed = {str(entry).rpartition("#")[2] for entry in manifest.subjects(CHECK, None)}
            assert listed == set(MUST_FAIL)

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
            assert faults_of(report) == [
                "label-empty is reported failed: a report that holds gives only passed, cantTell or untested"
            ]

    class TestGivenAManifestWhoseEntriesAreNamedAnyWay:
        def test_matches_each_report_to_the_fragment_of_its_entry_never_to_its_name(self):
            renamed = MANIFEST.read_text(encoding="utf-8").replace(
                'mf:name "label-empty"', 'mf:name "The label is empty"'
            )
            assert faults_of(written(as_listed()), renamed) == []

    class TestGivenAReportOfATestThatIsNoEntryOfTheManifest:
        def test_is_refused(self):
            report = written(as_listed()) + (
                f"[] a earl:Assertion ; earl:test <{MANIFEST.resolve().as_uri()}#not-an-entry> ;"
                " earl:result [ a earl:TestResult ; earl:outcome earl:passed ] .\n"
            )
            assert faults_of(report) == [
                f"{MANIFEST.resolve().as_uri()}#not-an-entry is reported, and is no entry of the manifest"
            ]

    class TestGivenAnEntryNotReported:
        def test_is_refused(self):
            report = written({name: outcome for name, outcome in as_listed().items() if name != "label-empty"})
            assert faults_of(report) == ["label-empty has no outcome"]

    class TestGivenAManifestListingEntriesOfOtherKindsBesideOneThatMustFail:
        def test_holds_for_the_report_the_other_query_holds_beside_it(self):
            assert faults_over(MIXED, mixed_report()) == []

        def test_refuses_an_input_only_entry_reported_passed(self):
            report = mixed_report() | {"example-0002": ("passed", None)}
            assert faults_over(MIXED, report) == ["input-only example-0002 is reported passed, not cantTell"]

        def test_holds_an_entry_that_must_pass_reported_cantTell(self):
            report = mixed_report() | {"example-0003": ("cantTell", None)}
            assert faults_over(MIXED, report) == []

    class TestGivenAManifestListingNoEntryThatMustFail:
        """Each report is judged as engine/faults-of-a-report.rq judges it."""

        @pytest.mark.parametrize("name", sorted(REPORTS_OF_THE_SYNTHETIC_ADAPTER))
        def test_gives_the_faults_of_the_other_query(self, name):
            report = REPORTS_OF_THE_SYNTHETIC_ADAPTER[name]
            assert faults_over(SYNTHETIC, report) == faults_over(SYNTHETIC, report, OTHER_JUDGE)

        def test_gives_the_fault_of_the_other_query_for_a_report_with_no_outcome_beside_no_entry(self):
            manifest = "@prefix mf: <http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#> .\n<> mf:entries () .\n"
            assert faults_over(manifest, "") == ["its report records no outcome"]

    class TestGivenAReportWhoseEntryIrisAreUnderAnotherBaseThanTheManifest:
        MANIFEST_READ_AT = "https://example.org/adapter/fixtures/manifest.ttl"
        REPORTED_AT = "file:///elsewhere/adapter/fixtures/manifest.ttl"

        def test_matches_each_entry_by_its_path_under_the_adapter(self):
            report = written_at(self.REPORTED_AT, as_listed())
            assert faults_over(MANIFEST.read_text(encoding="utf-8"), report, base=self.MANIFEST_READ_AT) == []

        def test_refuses_an_entry_that_must_fail_reported_passed(self):
            report = written_at(self.REPORTED_AT, as_listed() | {"label-not-written": ("passed", None)})
            assert faults_over(MANIFEST.read_text(encoding="utf-8"), report, base=self.MANIFEST_READ_AT) == [
                "label-not-written is reported passed, not failed"
            ]

        def test_refuses_a_reported_test_that_is_no_entry(self):
            report = written_at(self.REPORTED_AT, as_listed() | {"not-an-entry": ("passed", None)})
            assert faults_over(MANIFEST.read_text(encoding="utf-8"), report, base=self.MANIFEST_READ_AT) == [
                f"{self.REPORTED_AT}#not-an-entry is reported, and is no entry of the manifest"
            ]

    class TestGivenManifestEntriesWithNoFragment:
        def test_matches_each_to_its_report_by_its_iri(self):
            base = "https://example.org/cases/"
            manifest = (
                "@prefix mf: <http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#> .\n"
                "@prefix bridge: <https://ns.cascadeprotocol.org/bridge/v1-draft#> .\n"
                "<> mf:entries ( <one.ttl> <two.ttl> ) .\n"
                f"<two.ttl> bridge:expectedFailedCheck <{OTHER_CHECK}> .\n"
            )
            report = (
                "@prefix earl: <http://www.w3.org/ns/earl#> .\n"
                f"[] earl:test <{base}one.ttl> ; earl:result [ earl:outcome earl:passed ] .\n"
                f"[] earl:test <{base}two.ttl> ; earl:result [ earl:outcome earl:failed ;"
                f" <https://ns.cascadeprotocol.org/bridge/v1-draft#failedCheck> <{OTHER_CHECK}> ] .\n"
            )
            assert faults_over(manifest, report, base=base + "manifest.ttl") == []
