import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = Draft202012Validator(
    json.loads((ROOT / "engine" / "library-result.schema.json").read_text(encoding="utf-8"))
)


class TestResultsAnEnginesLibraryCommandWrites:
    """Results an engine's library command writes · engine/library-result.schema.json, engine/command.md

    A library command writes one JSON file for each call: the failure it came to, the answer of an `ask`, whether the
    adapter accepts the document a `convert` converted, or nothing at all.
    """

    class TestGivenAResult:
        @pytest.mark.parametrize(
            "result",
            [{}, {"answer": False}, {"detected": True}, {"detected": False}, {"failure": {"kind": "documentFailure"}}],
        )
        def test_is_accepted_when_it_states_one_thing_the_call_returned(self, result):
            assert not list(VALIDATOR.iter_errors(result))

        @pytest.mark.parametrize(
            "result",
            [{"detected": "yes"}, {"detected": None}, {"answer": True, "detected": True}, {"accepted": True}],
        )
        def test_is_refused_when_it_states_whether_the_adapter_accepts_the_document_in_any_other_way(self, result):
            assert list(VALIDATOR.iter_errors(result))
