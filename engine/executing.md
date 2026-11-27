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
  empty (an empty or whitespace-only string, an element with no content); and the occurrence belongs to a record of
  a class that a `bridge:inRecordClass` of one of the path's `bridge:carriedAs` names. An occurrence that belongs
  to no record, such as one inside a nested record the conversion wrote nothing from, is not owed.
- *Met*: a `bridge:asProperty` of one of those `bridge:carriedAs` is written on such a record, on its versions, on
  their arrivals or on a node they point at that is no record, version or arrival of its own (a record of that class
  written elsewhere in the unit does not meet it); or a finding is about the path: its `sh:value` is the path, its
  `oa:hasBody` is the `bridge:namesGap` or `bridge:lookupNamesGap` of the path's entry, its address with its indexes
  left out is the path or below it, or it is of a gap the adapter declares and addressed at an element above the path.

An occurrence's *address* is where it stands in the document: the unit's selector, then the occurrence's place in the
unit, in the form of the adapter's selectors. A record the conversion wrote *stands* at the `rdf:value` of the
`oa:hasSelector` of each of its arrivals, the unit's selector where the mapping wrote none. An adapter declares
nothing more. **The record an occurrence belongs to** is told so:

1. A nested record holds everything in it. Where the envelope the unit was read in declares
   `bridge:pathOfContainedContentBelowContent`, each member at that path below the unit's content
   (`bridge:pathOfContentInRecord`) is a nested record. An occurrence inside a nested record, at its address or
   below it, can belong only to records that stand inside it; one outside every nested record, only to records that
   stand outside every nested record.
2. It belongs to the nearest: of the records it can belong to, those whose address shares the most leading steps with
   its address. On a tie, a record whose address holds the occurrence (the same address, or an ancestor of it) is
   nearer than one whose does not. Records still tied all hold it.

**Judge a report against the outcomes a manifest lists.** An entry may list a `bridge:expectedOutcome` and, where
that is `earl:failed`, the `bridge:expectedFailedCheck` that fails it. Each entry must be reported with the outcome
it lists, `earl:passed` where it lists none, and a failed one with its check as the `bridge:failedCheck` of its
result; [`faults-of-a-report-against-expected-outcomes.rq`](faults-of-a-report-against-expected-outcomes.rq) finds
each fault. A Bridge is held to
[`../fixtures/synthetic-json-adapter-with-failing-entries/`](../fixtures/synthetic-json-adapter-with-failing-entries/)
this way: a report that gives every entry `earl:passed` is refused.

**Report in EARL**: one `earl:Assertion` per entry, `earl:test` the entry's IRI,
`earl:subject` the Bridge, `earl:mode earl:automatic`, and an `earl:TestResult`
carrying the `earl:outcome`. A report is never written back to the adapter.

Every entry is `earl:inapplicable` when the adapter requires a profile the
Bridge does not offer, and `earl:failed` when the adapter cannot be prepared.
Otherwise an entry of a type the Bridge does not know is `earl:inapplicable`,
and one that cannot be run is `earl:failed`.
