"""forms = _path_forms.read(graph, adapter)         # the crate's graph and its bridge:Adapter node
form, place = _path_forms.place_of(forms, path)  # a bridge:sourcePath
copied = _path_forms.copies(forms, paths)        # (copy, path): a path an entry for a place or a contained form also accounts for
"""

from dataclasses import dataclass

from rdflib import URIRef

from _terms import BRIDGE


@dataclass(frozen=True)
class Form:
    envelope: URIRef
    prefix: str
    contained: bool
    kind: str | None
    content: str = ""


def read(graph, adapter):
    """The forms the adapter's envelopes declare, the longest prefix first."""
    forms = []
    for envelope in graph.objects(adapter, BRIDGE.envelope):
        content, contained, kind = (
            graph.value(envelope, BRIDGE[term])
            for term in ("pathOfContentInRecord", "pathOfContainedContentBelowContent", "pathOfRecordKindBelowContent")
        )
        if content is contained is kind is None:
            continue
        content = "" if content is None else str(content)
        for prefix, is_contained in ((content, False), (None if contained is None else content + str(contained), True)):
            if prefix is not None:
                kind_path = None if kind is None else prefix + str(kind)
                forms.append(Form(envelope, prefix, is_contained, kind_path, content))
    return sorted(forms, key=lambda form: (-len(form.prefix), form.prefix, str(form.envelope)))


def place_of(forms, path):
    """The form a path was written in, the longest prefix a / follows, and the path after it; else no form and the path."""
    for form in forms:
        if path.startswith(form.prefix + "/"):
            return form, path[len(form.prefix) :]
    return None, path


def copies(forms, written):
    """(copy, path) for each path written with no content prefix, at each path an entry for it also stands.

    A path written in no form, or in the form of no prefix, is a place: it stands in every form that has a prefix. A path
    written in the contained form of no content prefix stands in that contained form under each content prefix. A path
    written with a content prefix stands for itself. A copy is made only where the path reads as the form it is made in and
    no path stands there; a place is not copied into a contained form under a content prefix where the path of the same
    place in the contained form of no content prefix stands, the nearer entry."""
    standing = set(written)
    for path in sorted(standing):
        form, place = place_of(forms, path)
        is_a_place = form is None or not form.prefix
        if not is_a_place and not (form.contained and not form.content):
            continue
        for target in forms:
            if not target.prefix:
                continue
            if not is_a_place and not (
                target.contained and target.content and target.prefix == target.content + form.prefix
            ):
                continue
            copy = target.prefix + place
            if copy in standing or place_of(forms, copy)[0] != target:
                continue
            if is_a_place and target.contained and target.content:
                suffix = target.prefix[len(target.content) :]
                nearer = place_of(forms, suffix + place)[0]
                if (
                    suffix + place in standing
                    and nearer is not None
                    and nearer.contained
                    and not nearer.content
                    and nearer.prefix == suffix
                ):
                    continue
            yield copy, path
