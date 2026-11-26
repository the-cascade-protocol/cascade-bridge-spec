import socket
from types import SimpleNamespace

from rdflib import URIRef
from rdflib.namespace import RDF

import _crate
from _terms import BRIDGE
from adapter_profile_world import FIXTURE


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
