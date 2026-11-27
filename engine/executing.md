# Executing a test manifest

**Load the crate and the manifest as one graph**: `ro-crate-metadata.json` as
JSON-LD and the manifest as Turtle, each with the adapter IRI the caller gave
([`library.md`](library.md)) followed by its path as base, so the manifest's
`<../>` is the crate's root entity.

**Apply each entry's type's rule**: its `rdfs:comment` in
[`../vocab/bridge.ttl`](../vocab/bridge.ttl). A Bridge also executes
[`../fixtures/versioning/manifest.ttl`](../fixtures/versioning/manifest.ttl), and
one offering `bridge:sparql-1.1`
[`../fixtures/lift/manifest.ttl`](../fixtures/lift/manifest.ttl) and the Cascade
vocabulary repository's
[`tests/vectors/naming/manifest.ttl`](https://github.com/the-cascade-protocol/cascade-vocabulary/blob/main/tests/vectors/naming/manifest.ttl), each loaded on
its own.

**Fail an entry whose conversion does not write what the accounting carries.** `test` reports an entry that
converts an input, of any type, `earl:failed`, with `bridge:conversionWritesWhatTheAccountingCarries` as the
`bridge:failedCheck` of its result, when an occurrence of a source path in that input is owed and not met. The result
names the path, the occurrence's address, the class owed and the properties looked for. `convert` is unchanged:
findings are data there, never failures ([`library.md`](library.md)).

- *Owed*: the accounting marks the path `bridge:carried` or `bridge:carriedInPart`; the occurrence's value is not
  empty; no other member of the occurrence's element is empty and carried as one of the same properties (one value
  written from several members cannot be written when one of them is empty); and the occurrence belongs to a record of
  a class that a `bridge:inRecordClass` of one of the path's `bridge:carriedAs` names. An occurrence that belongs
  to no record, such as one inside a nested record the conversion wrote nothing from, is not owed.
- *Empty*: nothing but white space is left once markup is taken out of the value. An empty or white-space-only
  string; a string holding only XML or XHTML elements with no text in them (`<p> </p>`,
  `<div xmlns="..."><br/></div>`); an XML element holding, at any depth, no text and no attribute value other than
  white space, so that `<value><code code="I10"/></value>` is not empty, the attribute's value being content; an XML
  attribute whose value is white space.
- *Met*: a `bridge:asProperty` of one of those `bridge:carriedAs` is written on a record the occurrence belongs to,
  on its versions, on their arrivals or on a node they point at that is no record, version or arrival of its own (a
  record of that class written elsewhere in the unit does not meet it); or a finding from the same unit's conversion
  meets it: either its address is the occurrence's address or below it, or its address is above the occurrence's
  address and its `oa:hasBody` is the `bridge:namesGap` or `bridge:lookupNamesGap` of the path's entry. These are
  alternatives. "Above" is measured on the occurrence's own address, indexes included, never on the path. A finding
  with no address, a finding elsewhere in the unit whatever its body, and a finding whose `sh:value` is the path
  alone meet nothing.

An occurrence's *address* is where it stands in the document: the unit's selector, then the occurrence's place in the
unit, in the form of the adapter's selectors; each member of a JSON array is an occurrence, and the array itself is not. A record the conversion wrote *stands* at the `rdf:value` of the
`oa:hasSelector` of each of its arrivals, the unit's selector where the mapping wrote none. An adapter declares
nothing more. **The record an occurrence belongs to** is found so:

1. A nested record holds everything in it. Where the envelope the unit was read in declares
   `bridge:pathOfContainedContentBelowContent`, each member at that path below the unit's content
   (`bridge:pathOfContentInRecord`) is a nested record. An occurrence inside a nested record, at its address or
   below it, can belong only to records that stand inside it; one outside every nested record, only to records that
   stand outside every nested record.
2. It belongs to the nearest: of the records it can belong to, those whose address shares the most leading steps with
   its address, steps compared by name and position. On a tie, a record whose address holds the occurrence (the same
   address, or an ancestor of it) is nearer than one whose does not. Records still tied all hold it. A datum of an
   enclosing element that the adapter carries on no record is reported by a finding at it, which meets the
   occurrence whichever record it is held to.
3. An element reported as not carried at all holds nothing. An occurrence belongs to no record, and is not owed, where
   a finding of the same unit's conversion is addressed at it or at an element holding it, and that finding's
   `oa:hasBody` is a gap of kind `bridge:elementNotCarried`. It is the same case as an occurrence inside a nested
   record the conversion wrote nothing from. A gap of any other kind, `bridge:valueNotMapped` included, drops nothing
   below it: it meets the occurrence only as *Met* says. A `bridge:carriedInPart` entry may not name a gap of kind
   `bridge:elementNotCarried`
   ([`../adapter/profile/must/source_accounting.py`](../adapter/profile/must/source_accounting.py)).

**Judge a report against the outcomes a manifest lists.** An entry that lists a `bridge:expectedFailedCheck` must be
reported `earl:failed` with that check as the `bridge:failedCheck` of its result, and every other entry
`earl:passed`. A report's assertion is matched to the entry whose IRI has the fragment of the reported
`earl:test`; a reported test whose fragment is no entry of the manifest is a fault, and so is an entry not reported.
[`faults-of-a-report-against-expected-outcomes.rq`](faults-of-a-report-against-expected-outcomes.rq) finds each
fault. A Bridge is held to
[`../fixtures/synthetic-json-adapter-with-failing-entries/`](../fixtures/synthetic-json-adapter-with-failing-entries/)
this way: a report that gives every entry `earl:passed` is refused.

**Report in EARL**: one `earl:Assertion` per entry, `earl:test` the entry's IRI,
`earl:subject` the Bridge, `earl:mode earl:automatic`, and an `earl:TestResult`
carrying the `earl:outcome`. A report is never written back to the adapter.

Every entry is `earl:inapplicable` when the adapter requires a profile the
Bridge does not offer, and `earl:failed` when the adapter cannot be prepared.
Otherwise an entry of a type the Bridge does not know is `earl:inapplicable`,
and one that cannot be run is `earl:failed`.
