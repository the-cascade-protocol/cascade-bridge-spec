import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import RDF, Graph, URIRef

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "fixtures" / "synthetic-json-adapter-with-failing-entries"
VOCABULARIES = ROOT / "fixtures" / "synthetic-vocabularies"
ENGINE = ROOT / "fixtures" / "fake-engine" / "engine.py"
JUDGE = ROOT / "engine" / "faults-of-a-report.rq"
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
    "label-written-as-a-node-of-nothing",
    "label-written-on-a-pointed-record",
    "label-written-only-as-empty",
    "label-zero-not-written",
    "last-update-not-written",
    "last-update-of-a-record-no-mapping-reads-reported-as-its-loss",
    "last-update-reported-at-the-unit-as-the-adapters-gap",
    "nearer-label-not-written",
    "null-and-array-no-empty-child",
    "phone-reported-only-at-the-record",
    "phone-the-adapter-does-not-report",
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


SYNTHETIC_BASE = SYNTHETIC_MANIFEST.resolve().as_uri()


def faults_over(manifest, report, base=SYNTHETIC_BASE):
    """The faults the judge finds in a report, given as outcomes by entry name or as Turtle, over a manifest read at
    `base`."""
    if not isinstance(report, str):
        report = written_at(base, report)
    graph = Graph().parse(data=report, format="turtle")
    graph.parse(data=manifest, format="turtle", publicID=base)
    return [str(row.fault) for row in graph.query(JUDGE.read_text(encoding="utf-8"))]


def written_at(base, outcomes):
    report = "@prefix earl: <http://www.w3.org/ns/earl#> .\n"
    for name, (outcome, check) in outcomes.items():
        by = "" if check is None else f" ; <https://ns.cascadeprotocol.org/bridge/v1-draft#failedCheck> <{check}>"
        report += (
            f"[] a earl:Assertion ; earl:test <{base}#{name}> ;"
            f" earl:result [ a earl:TestResult ; earl:outcome earl:{outcome}{by} ] .\n"
        )
    return report


ADAPTER_IRI = "https://example.org/adapter/"
ELSEWHERE = "file:///elsewhere/adapter/"


def manifest_of(paths, must_fail=(), adapter=ADAPTER_IRI):
    """A manifest at the root of the adapter at `adapter`, listing the files at `paths` under it, and its own IRI."""
    text = (
        "@prefix mf: <http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#> .\n"
        "@prefix bridge: <https://ns.cascadeprotocol.org/bridge/v1-draft#> .\n"
        f"<> bridge:adapter <./> ; mf:entries ( {' '.join(f'<{path}>' for path in paths)} ) .\n"
    )
    for path in must_fail:
        text += f"<{path}> bridge:expectedFailedCheck <{OTHER_CHECK}> .\n"
    return text, adapter + "manifest.ttl"


def report_of(outcomes, at=ELSEWHERE):
    """A report naming each path under `at` with its outcome, and the check that failed it where there is one."""
    report = "@prefix earl: <http://www.w3.org/ns/earl#> .\n"
    for path, (outcome, check) in outcomes.items():
        by = "" if check is None else f" ; <https://ns.cascadeprotocol.org/bridge/v1-draft#failedCheck> <{check}>"
        report += (
            f"[] a earl:Assertion ; earl:test <{at}{path}> ;"
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
    """Judging a report of entries that must fail · engine/faults-of-a-report.rq

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

    class TestGivenAnEntryNotReported:
        def test_is_refused(self):
            report = written({name: outcome for name, outcome in as_listed().items() if name != "label-empty"})
            assert faults_of(report) == ["label-empty has no outcome"]

    class TestGivenAManifestListingEntriesOfOtherKindsBesideOneThatMustFail:
        def test_holds_for_the_report_that_holds_without_it(self):
            assert faults_over(MIXED, mixed_report()) == []

        def test_refuses_an_input_only_entry_reported_passed(self):
            report = mixed_report() | {"example-0002": ("passed", None)}
            assert faults_over(MIXED, report) == ["input-only example-0002 is reported passed, not cantTell"]

        def test_holds_an_entry_that_must_pass_reported_cantTell(self):
            report = mixed_report() | {"example-0003": ("cantTell", None)}
            assert faults_over(MIXED, report) == []

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

    class TestGivenEntriesOneOfWhosePathsUnderTheAdapterEndsTheOther:
        MANIFEST, READ_AT = manifest_of(["a/x", "b/a/x"], must_fail=["a/x"])

        def test_holds_for_each_reported_as_listed(self):
            report = report_of({"a/x": ("failed", OTHER_CHECK), "b/a/x": ("passed", None)})
            assert faults_over(self.MANIFEST, report, self.READ_AT) == []

        def test_refuses_the_longer_reported_failed_naming_it_by_its_path_under_the_adapter(self):
            report = report_of({"a/x": ("failed", OTHER_CHECK), "b/a/x": ("failed", None)})
            assert faults_over(self.MANIFEST, report, self.READ_AT) == [
                "b/a/x is reported failed: a report that holds gives only passed, cantTell or untested"
            ]

    class TestGivenAnEntryThatMustFailNotReportedBesideOneWhosePathEndsInIt:
        MANIFEST, READ_AT = manifest_of(["x", "d/x"], must_fail=["x"])

        def test_refuses_the_other_reported_failed_by_its_check(self):
            report = report_of({"d/x": ("failed", OTHER_CHECK)})
            assert faults_over(self.MANIFEST, report, self.READ_AT) == [
                "d/x is reported failed: a report that holds gives only passed, cantTell or untested",
                "x has no outcome",
            ]

        def test_refuses_the_other_reported_passed(self):
            report = report_of({"d/x": ("passed", None)})
            assert faults_over(self.MANIFEST, report, self.READ_AT) == ["x has no outcome"]

    class TestGivenAReportWrittenUnderAFolderNamedAsTheFirstFolderOfAnEntry:
        """The report's one base is the one that makes the most of its tests entries: here `file:///w/t/`, never
        `file:///w/t/t/`, though `x` ends both of the report's tests."""

        MANIFEST, READ_AT = manifest_of(["x", "t/x"])
        MUST_FAIL, _ = manifest_of(["x", "t/x"], must_fail=["x"])
        AT = "file:///w/t/"

        def test_holds_for_each_reported_as_listed(self):
            report = report_of({"x": ("passed", None), "t/x": ("passed", None)}, at=self.AT)
            assert faults_over(self.MANIFEST, report, self.READ_AT) == []

        def test_holds_for_each_reported_as_listed_where_the_shorter_must_fail(self):
            report = report_of({"x": ("failed", OTHER_CHECK), "t/x": ("passed", None)}, at=self.AT)
            assert faults_over(self.MUST_FAIL, report, self.READ_AT) == []

    class TestGivenAReportNoneOfWhoseTestsIsAnEntryUnderAnyBase:
        MANIFEST, READ_AT = manifest_of(["x", "d/y"])

        def test_refuses_it_for_every_entry_having_no_outcome(self):
            report = report_of({"z": ("passed", None), "d/w": ("passed", None)})
            assert faults_over(self.MANIFEST, report, self.READ_AT) == ["d/y has no outcome", "x has no outcome"]

    class TestGivenTwoEntriesWithOneFragmentInFilesOfOneName:
        MANIFEST, READ_AT = manifest_of(["f.json#a", "d/f.json#a"])

        def test_names_each_by_its_path_under_the_adapter(self):
            assert faults_over(self.MANIFEST, report_of({"other": ("passed", None)}), self.READ_AT) == [
                "d/f.json#a has no outcome",
                "f.json#a has no outcome",
            ]

    class TestGivenManifestEntriesWithNoFragment:
        BASE = "https://example.org/cases/"
        MANIFEST = (
            "@prefix mf: <http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#> .\n"
            "@prefix bridge: <https://ns.cascadeprotocol.org/bridge/v1-draft#> .\n"
            "<> mf:entries ( <one.ttl> <two.ttl> ) .\n"
            f"<two.ttl> bridge:expectedFailedCheck <{OTHER_CHECK}> .\n"
        )

        def test_matches_each_to_its_report_by_its_iri(self):
            report = report_of({"one.ttl": ("passed", None), "two.ttl": ("failed", OTHER_CHECK)}, at=self.BASE)
            assert faults_over(self.MANIFEST, report, base=self.BASE + "manifest.ttl") == []

        def test_names_a_check_with_no_fragment_by_its_iri(self):
            report = report_of({"one.ttl": ("passed", None), "two.ttl": ("failed", None)}, at=self.BASE)
            assert faults_over(self.MANIFEST, report, base=self.BASE + "manifest.ttl") == [
                f"{self.BASE}two.ttl is reported failed, but not by {OTHER_CHECK}"
            ]
