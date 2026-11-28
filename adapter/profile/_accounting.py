from rdflib import Graph
from rdflib.namespace import RDF

from _path_forms import copies, read
from _terms import BRIDGE


def accounting_of(crate):
    """The graph of the one accounting the adapter names, empty where source_accounting.py has a fault to report."""
    named = list(crate.graph.objects(crate.root, BRIDGE.sourceAccounting))
    path = crate.file_at(named[0]) if len(named) == 1 else None
    if path is None:
        return Graph()
    try:
        return Graph().parse(path, format="turtle")
    except Exception:
        return Graph()


def paths_accounted(crate, accounting):
    """Every path the accounting's entries account for: the path of each, and, for one written for a place, that place
    in each form the adapter's envelopes declare."""
    written = {
        str(path)
        for entry in accounting.subjects(RDF.type, BRIDGE.PathEntry)
        for path in accounting.objects(entry, BRIDGE.sourcePath)
    }
    return written | {copy for copy, _ in copies(read(crate.graph, crate.root), written)}
