import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import Graph, URIRef
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF

import _crate
from _terms import BRIDGE
from adapter_profile_world import FIXTURE, ROOT

SAVED_GRAPHS = Path(__file__).parent / "crate_graphs"
SAVED_BASE = "https://crate.example/"
COMMITTED_CRATES = [
    ROOT / name
    for name in subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", "*ro-crate-metadata.json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
]


class TestCheckingAnAdapterPackageAgainstTheProfile:
    """Checking an adapter package against the profile · rocrate-validator, adapter/profile/must/

    An adapter package conforms when `rocrate-validator` passes it against RO-Crate 1.2 and this profile. Each `.ttl` or
    `.py` file under `adapter/profile/must/` is one requirement, and a requirement that could not be checked fails the
    package and says why.
    """

    class TestGivenAPackageNamedByAFileURI:
        """given a package named by a `file:` URI"""

        def test_reads_the_package_from_the_folder_the_uri_names(self, crate):
            """reads the package from the folder the URI names"""
            context = SimpleNamespace(settings=SimpleNamespace(rocrate_uri=crate.adapter.as_uri()))
            assert _crate.from_context(context).adapter == crate.adapter.resolve()

    class TestGivenACrateWhoseContextNamesTheRoCrateContextByItsWebAddress:
        """given a crate whose context names the RO-Crate context by its web address"""

        def test_reads_the_crate_without_opening_a_network_connection(self, monkeypatch):
            def refused(*arguments, **keywords):
                raise OSError("the network is denied to this test")

            monkeypatch.setattr(socket, "getaddrinfo", refused)
            monkeypatch.setattr(socket.socket, "connect", refused)

            crate = _crate.load(FIXTURE)

            assert crate.root == URIRef(FIXTURE.resolve().as_uri() + "/")
            assert (crate.root, RDF.type, BRIDGE.Adapter) in crate.graph

        @pytest.mark.parametrize("crate_file", COMMITTED_CRATES, ids=lambda crate_file: crate_file.parent.name)
        def test_reads_each_committed_crate_into_the_statements_the_published_context_gives(self, crate_file):
            saved = SAVED_GRAPHS / (crate_file.parent.relative_to(ROOT).as_posix().replace("/", "-") + ".nt")
            assert saved.is_file(), f"{saved.name} is the crate's statements as the published context gives them"

            assert to_isomorphic(_crate.parsed(crate_file, SAVED_BASE)) == to_isomorphic(
                Graph().parse(saved, format="nt")
            )

    class TestGivenACrateThatNeedsMoreThanTheContextTheLoaderReadsOffline:
        """given a crate that needs more than the context the loader reads offline"""

        def test_refuses_a_term_the_read_terms_do_not_define(self, tmp_path):
            crate_file = tmp_path / "ro-crate-metadata.json"
            crate_file.write_text(
                json.dumps({"@context": [_crate.RO_CRATE_CONTEXT], "@graph": [{"@id": "./", "author": "someone"}]}),
                encoding="utf-8",
            )

            with pytest.raises(ValueError, match="author"):
                _crate.parsed(crate_file, SAVED_BASE)

        def test_refuses_a_context_named_by_any_other_web_address(self, tmp_path):
            crate_file = tmp_path / "ro-crate-metadata.json"
            crate_file.write_text(
                json.dumps({"@context": "https://example.org/context", "@graph": [{"@id": "./"}]}), encoding="utf-8"
            )

            with pytest.raises(ValueError, match="https://example.org/context"):
                _crate.parsed(crate_file, SAVED_BASE)
