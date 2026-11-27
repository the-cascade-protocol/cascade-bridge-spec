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
names the path, the occurrence's address, and the class owed and the properties looked for, or, for an occurrence owed
only a finding (*Reported by the adapter*), the gaps looked for. `convert` is unchanged:
findings are data there, never failures ([`library.md`](library.md)).

**Owed.** An occurrence is owed when the accounting marks its path `bridge:carried` or `bridge:carriedInPart`, or its
path's entry names a `bridge:adapterReportsGap`; its value is not empty; and no child of its element at another path is empty and carried as one of the same properties (one
value written from several children cannot be written when one of them is empty). A repeat of its own path at another
index is no other child, and an empty repeat un-owes nothing but itself.

**Where things stand.** An occurrence's *address* is where it stands in the document: the unit's selector, then the
occurrence's place in the unit, in the form of the adapter's selectors; each member of a JSON array is an occurrence,
and the array itself is not. A record the conversion wrote *stands* at the `rdf:value` of the `oa:hasSelector` of each
of its arrivals, the unit's selector where the mapping wrote none. An adapter declares nothing more, and an engine reads
no `bridge:inSourceRecordType` for this. Addresses are compared as steps, each step by name, namespace and position,
never as written. A record's arrival selector and a finding's address are read by following them through the document
and writing the node they select as the occurrence addresses are written, so
`*[namespace-uri()='urn:hl7-org:v3' and local-name()='section'][1]` and
`*[local-name()='section' and namespace-uri()='urn:hl7-org:v3'][1]` are one step, as are a JSON Pointer and its
percent-encoded spelling. A record whose arrival selector selects no node, more than one, or a node outside the unit
cannot be placed, and fails the entry by `bridge:conversionWritesWhatTheAccountingCarries`, the result naming the
selector: a record that cannot be placed must not silently own nothing.

**The record an occurrence belongs to.** Where the envelope the unit was read in declares
`bridge:pathOfContainedContentBelowContent`, each member at that path below the unit's content
(`bridge:pathOfContentInRecord`) is a nested record, and it holds everything in it: an occurrence inside a nested
record, at its address or below it, can belong only to records that stand inside that nested record, where any does.
Where none does, it can belong only to records that stand outside every nested record, as an occurrence outside every
nested record can: so a contained Medication that the mapping reads into its MedicationRequest's record owes its code
to that record. Of the records it can belong to, it belongs to the nearest: those whose address shares the most leading
steps with its address. On a tie, a record whose address holds the occurrence (the same address, or an ancestor of it)
is nearer than one whose does not. Records still tied all belong to it, and a property written on any of them meets it.
An occurrence is owed only when that record is of a class that a `bridge:inRecordClass` of one of the path's
`bridge:carriedAs` names, or when its path's entry names a `bridge:adapterReportsGap`, whatever record it belongs to,
or none.

**Met.** A `bridge:asProperty` of one of those `bridge:carriedAs` meets the occurrence when it is written on a record
the occurrence belongs to, on its versions, on their arrivals or on a node they point at that is no record, version or
arrival of its own; a record of that class written elsewhere in the unit does not meet it, and neither does a property
whose only value written in those places is empty.

A finding from the same unit's conversion meets it when either its address is the occurrence's address or below it, or its address is above the
occurrence's address and its `oa:hasBody` is the `bridge:namesGap` or `bridge:lookupNamesGap` of the path's entry. A
written property and a finding are alternatives. "Above" is measured on the occurrence's own address, indexes
included, never on the path. A finding addressed at the unit's selector is above every occurrence in the unit. A
finding elsewhere in the unit whatever its body, and a finding whose `sh:value` is the path alone, meet nothing. The
check does not count values: one of the properties written on a record meets every occurrence of the path that belongs
to that record. The engine cannot tell which written value came from which occurrence, since a mapping may join them,
and a count would fail honest conversions.

**Reported by the adapter.** A `bridge:adapterReportsGap` is a gap the adapter's own findings queries report at each
occurrence of the path that no record carries, so a Bridge reports nothing from it ([`sparql.md`](sparql.md)) and
holds the adapter to it. An occurrence of such a path that nothing excuses (*Excused*), and that belongs to no record
of a class one of the path's `bridge:carriedAs` names or to no record at all, is met only by a finding from the same
unit's conversion whose `oa:hasBody` is one of the entry's `bridge:adapterReportsGap`, addressed at the occurrence,
below it, or above it at an address that is itself an occurrence of a path whose entry names that gap too. One that
does belong to such a record is met as *Met* says, and a finding of the adapter's gap above it meets nothing. So where
the entries for `/telecom`, `/telecom/system` and `/telecom/value` each name a contact point's gap, one finding of it
at `/telecom/0` meets the contact point and the system and value inside it; a finding at the record meets none of
them. Each occurrence is reported by the adapter alone, where it stands, and an entry cannot say its adapter reports a
gap that it reports nowhere.

**Excused.** An element reported as not carried at all holds nothing. An occurrence belongs to no record, and is not
owed, where a finding of the same unit's conversion is addressed at it or at an element holding it, that finding's
`oa:hasBody` is a gap of kind `bridge:elementNotCarried`, and no record the conversion wrote stands at that element or
below it. Where one does, the adapter said nothing there is carried and carried something: the finding un-owes
nothing, and the occurrences are judged as if it were not there. A gap of any other kind, `bridge:valueNotMapped`
included, excuses nothing below it: it meets the occurrence only as *Met* says. A finding of a gap of kind
`bridge:elementNotCarried` is addressed at the element nothing of which is carried, not at a value inside it. A
`bridge:carriedInPart` entry may not name a gap of kind `bridge:elementNotCarried`
([`../adapter/profile/must/source_accounting.py`](../adapter/profile/must/source_accounting.py)).

**Empty.** Whether a text is empty is decided by the syntax of the source, the same way for an occurrence and for a
value written: a value written is empty exactly when the same text would be an empty occurrence in the unit's source
syntax. In XML a text or an attribute value is empty when it holds only space, tab, carriage return and line feed
(U+0020, U+0009, U+000D, U+000A); a no-break space (`&#160;`) or an em space (U+2003) is text, and so is markup
written as text (`&lt;p&gt; &lt;/p&gt;` is the text `<p> </p>`), so a value written as it stands from any of them is
a value, not an empty one. In JSON a string is empty when it holds only Unicode white space once each complete tag,
from `<` to the next `>`, is taken out: an empty or white-space-only string; a string holding only XML or XHTML
elements with no text in them (`<p> </p>`, `<div xmlns="..."><br/></div>`), which is empty even where a tag has an
attribute (`<img src="x"/>`), a string being read for its text alone; a `<` with no `>` after it is text. In XML, an
element holding, at any depth, no text and no attribute value other than white
space, so that `<value><code code="I10"/></value>` is not empty, the attribute's value being content; an XML
attribute whose value is white space. In JSON, `null` and an array with no member stand as no occurrence: nothing is
owed for either, and neither is an empty child of its element. An object holding nothing but empty values, `{}`
included, is empty. A number, `true` and `false` are values, never empty. A value written that is a node, a blank
node or an IRI that is a version's own IRI followed by `#` and a name, is empty when every member it has is empty,
however deep, a node among its own members adding nothing; its `rdf:type` is no member, so a node with no member but
its type is a value, and a typed node is empty when every other member it has is. A node with no members is a value.
Any other IRI, a code, a class or another record, is a value by its name, whatever is said of it.

**Judge a report against the outcomes a manifest lists.** An entry that lists a `bridge:expectedFailedCheck` must be
reported `earl:failed` with that check as the `bridge:failedCheck` of its result;
[`faults-of-a-report.rq`](faults-of-a-report.rq) finds each fault of a report, of these entries and every other. A
report has one base, the one under which the most of its tests are entries at the same path, and a test is the entry
at the same path under that base and no other; where no base makes any test an entry, every entry has no outcome.
With `?everyOutcome` bound it also returns each result it finds no fault in, its fault empty, which is how the
compatibility tool's case report learns which entry each test is. A
Bridge is held to
[`../fixtures/synthetic-json-adapter-with-failing-entries/`](../fixtures/synthetic-json-adapter-with-failing-entries/)
this way: a report that gives every entry `earl:passed` is refused.

**Report in EARL**: one `earl:Assertion` per entry, `earl:test` the entry's IRI,
`earl:subject` the Bridge, `earl:mode earl:automatic`, and an `earl:TestResult`
carrying the `earl:outcome`. A report is never written back to the adapter.

Every entry is `earl:inapplicable` when the adapter requires a profile the
Bridge does not offer, and `earl:failed` when the adapter cannot be prepared.
Otherwise an entry of a type the Bridge does not know is `earl:inapplicable`,
and one that cannot be run is `earl:failed`.
