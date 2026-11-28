# The commands an engine offers

All three of `test`, `convert` and `library`, not some. `test` and `convert` are callers of the library, and
[`library.md`](library.md) says what each does. Each names the adapter and the
vocabulary by their directories' `file:` IRIs, and the document and its facts
by their own, and reads a directory's files into that directory's map.

An engine states how to run it in its `compatibility.json`
([`../compatibility.md`](../compatibility.md)): a `setup` and a `command` for
each host, as argument vectors, and the tooling appends a command and its
arguments to each host's `command`.

## `test`

```
test <adapter directory> [--earl <file>] [--datasets] [--vocabularies <directory>] [--owed]
```

The library's `test`. `<adapter directory>` is the adapter's map and
`--vocabularies` the vocabulary's: a checkout of the repository the adapter's
`bridge:cascadeVocabularyRepository` names, at the version the run picked
([`../compatibility.md`](../compatibility.md)). `--earl` writes the report to
`<file>`. With `--datasets` the command also streams the datasets of
`bridge:DatasetCompletionTest` entries.

**The exit code means nothing to the tooling; the report does.** A run that wrote
no report does not hold. The tooling appends `test`, the adapter directory,
`--earl` and the report file, and `--vocabularies` and the checkout it picked.

An entry fails when its conversion does not write what the accounting carries
([`executing.md`](executing.md)). The adapter's author answers by having the mapping write
one of the properties looked for, or by having it report a finding at the value, or at an
element above it with the path's accounting entry made `bridge:carriedInPart` naming that
gap ([`../adapter/README.md`](../adapter/README.md)). The result's description gives, for
each of the first three, the path, then the properties looked for on the class owed, then the
address, as `<path>: no <property> on its <class> is written, and no finding is about it, at
"<address>"`, nothing of it cut, and for an occurrence owed only a finding of a gap its adapter reports, as
`<path>: no finding of <gap> is addressed at it, inside it, or at an element holding it whose path's entry names
that gap, at "<address>"`, several gaps joined by `or`; where there are more, it ends `; and <n> more`, and where the
engine offers `--owed`, `: run `test` with `--owed` to list every one`. A record that cannot be placed
is listed on a line of its own, in the description and under `--owed`, as `the record
selector "<selector>" <what it selects>, so no occurrence can be held to the record it
places`, where `<what it selects>` is `selects no node`, `selects <n> nodes`, `is no XPath,
or selects no set of nodes`, or `selects a node outside the unit at "<unit's selector>"`.

An engine may offer `--owed`; the compatibility tooling never passes it, and an engine
without it is as conformant as one with it. Where it does, `--owed` lists every unmet
occurrence, one per line after the entries and before the tally: `Owed`, the entry's name,
then the path, `at`, the occurrence's address, and the properties looked for on the class
owed, as `<path> at "<address>": no <property> on its <class> is written, and no finding is
about it`, the property and the class by IRI, several joined by `or`, or `<path> at "<address>": no finding of
<gap> is addressed at it, inside it, or at an element holding it whose path's entry names that gap`, the gap by IRI. It changes nothing in
the report. The line is read by an author, not by tooling, and its words may be reworded.

## `convert`

```
convert <adapter directory> <document> [--envelope <iri>] [--facts <file>] [--out <file>] [--findings <file>] [--format turtle|ntriples] [--vocabularies <directory>] [--owed]
```

The library's `convert`, on the adapter loaded from `<adapter directory>` and,
with `--vocabularies`, a checkout of the repository its
`bridge:cascadeVocabularyRepository` names, at the version the caller picked. `<document>` is
the document, a file the caller holds rather than one the adapter committed.
`--envelope` is the envelope IRI, resolved against the adapter's
`ro-crate-metadata.json`, so `#envelope-set` names the envelope that file
declares as `#envelope-set`. `--facts` is a Turtle file of the facts.
`--format` is the format, Turtle when it is not given.

The graph goes to `--out`, or to standard output, which carries the graph and
nothing else. `--findings` asks the library for the findings and the census, and
is where they go, never to standard output; without it, neither is asked for.
Where the library returns none, a run given `--findings` produces nothing.

**The exit code is the whole of what a caller learns**, because `convert` writes
no report: zero when the graph was produced, non-zero when it was not, and
standard output carries nothing in that case.

An engine may offer `--owed` on `convert` too, on the same terms: the compatibility tooling
never passes it, and an engine without it is as conformant as one with it. Where it does,
`convert` writes no graph: it prints `Owed`, the document's IRI and the count of unmet
occurrences (`<n> unmet`), then each one on a line of its own indented by two spaces, in the
form `test --owed` gives it without the entry's name, and exits zero. It is for an adapter's
author, to see what a document would fail a test entry for
([`../adapter/README.md`](../adapter/README.md)), and the line's words are for a person, not
for parsing.

## `library`

```
library <calls file> <results directory>
```

For conformance only: the tooling runs the cases of
[`../fixtures/library/`](../fixtures/library/) through it, appending
`library`, the calls file it wrote and an empty results directory. It makes
each call the calls file lists on the library and writes what each returned.
It judges nothing.

### The calls file

JSON, as [`library-calls.schema.json`](library-calls.schema.json) says:
`cases`, each a `name` and its `calls`, in the order they are made. A call is
an object of one member, named for the operation:

| member | its value |
|---|---|
| `describe` | `adapter`, the adapter IRI; `metadata`, the path of its `ro-crate-metadata.json`; `format` |
| `load` | `adapter`, a map, and `vocabulary`, a map, where the call gives one |
| `ask` | `document` |
| `convert` | `document` and `format`, and `findings` and `census`, each `true` where the call asks for it |
| `test` | `adapter` and `vocabulary`, as `load` takes them |

- A map is `iri`, its IRI, and `files`, an object from each key to the path of
  the file whose bytes the map holds under that key. It holds those files and
  no other.
- A `document` is `iri` and `path`, and, where the call gives them,
  `envelope`, the envelope IRI, and `facts`, an `iri` and a `path`.
- `format` is `turtle` or `ntriples`.
- Every path is absolute.

`ask` and `convert` are made on the adapter the latest `load` before them in
their case that did not fail returned. Where there is none, the call is not
made and nothing is written for it. After a `bridge:bridgeFailure`, the next
call of the case is made on the adapter loaded again from that `load`'s maps.

### The results directory

For the call at position *n* of a case, counting from 1, the command writes
into `<results directory>/<case name>/`:

- `<n>.json`, as [`library-result.schema.json`](library-result.schema.json)
  says: `{"failure": {"kind": …}}` where the call failed, `kind` the local
  name of its `bridge:FailureKind`, with `map`, `adapter` or `vocabulary`, and
  `path` for a `fileMissingFailure`, and an optional `message`; otherwise
  `{"answer": true}` or `{"answer": false}` for `ask`, `{}` for any other call,
  and for `convert` `{}` or the `detected` it returned, `{"detected": true}` or
  `{"detected": false}`;
- `<n>.graph`, the graph `describe` or `convert` returned, as returned;
- `<n>.findings`, the findings `convert` returned, where it returned any;
- `<n>.report`, the report `test` returned, as returned.

**The exit code means nothing to the tooling; the results do.** A call with no
result does not hold.

## `survey`

```
survey <adapter directory> <folder> [--envelope <iri>] [--tsv <file>] [--kind <kind>] [--under <path>]
```

An engine may offer `survey`; the tooling never calls it, as it never passes
`--owed`. It is for an adapter's author, to read which fields of a folder of real
documents the adapter's accounting has never decided about, which wait on a term
the vocabulary lacks, and which it leaves out on purpose, most common first.

It converts nothing: it lifts each file directly in `<folder>`, a subfolder being
skipped, and reads each path of each record against the adapter's source
accounting. It runs no mapping, query, schema or shapes and needs no vocabulary,
so a document that breaks the source schema is read like any other.
`--envelope` is resolved as `convert`'s is and applies to every file. A file it
cannot read is listed with its reason and the run goes on: it is empty, it does
not parse in the adapter's syntax, no envelope accepts it, it holds no record
(with `--envelope`, the envelope finds none), or it is a symbolic link.

It prints these lists, each by record kind, each row ranked by `documents`, then
`occurrences`, then place. `documents` counts the files that hold the place, once
each; `occurrences` counts the times it stands in all of them; a `Counts` line
under the header says so.

- **Never decided**: the paths no entry stands for, which are exactly the paths
  that would draw `cascade:SourcePathNotAccounted` on converting the same
  documents.
- **No term yet**: the paths whose entry is `bridge:noHome`, or
  `bridge:carriedInPart` naming a gap, with that gap; the second is marked as
  carried in part.
- **Left out on purpose**: the paths whose entry is `bridge:ignored`, with its
  `bridge:because`.

The verdicts are those of `bridge:verdicts` in [`../vocab/bridge.ttl`](../vocab/bridge.ttl).
A row is a place within a record kind, as the adapter's envelopes say what a
place is ([`../adapter/README.md`](../adapter/README.md#saying-where-a-place-stands-in-each-form-of-a-path)),
not a path: its counts are summed over the forms it was written in, and it names
them where there is more than one or one that is not the bare form; forms of one
place whose entries differ stand as separate rows. A record kind is read at the
envelope's `bridge:pathOfRecordKindBelowContent`; a contained resource has its own
where it names one and its container's where it does not. Kinds are read for JSON
envelopes only: an adapter whose envelopes declare none, or an XML one that
declares one (which gets a note saying so), is one group, and a record whose kind
cannot be read is `(no kind)`.

`--kind` keeps one record kind, and `--under` a place and the places below it,
step by step. `--tsv` writes every place seen, whatever its verdict, narrowed as
the lists are, to `<file>`: one line each, in the same order, tab separated after
a header line. A control character inside a cell is written as a space, as in the
readable output. Its words are for a person; its columns are what a script may
read:

| Column | Holds |
| --- | --- |
| `kind` | the record kind; empty where there is none |
| `path` | the place |
| `verdict` | the local name of the entry's `bridge:verdict`, or `neverDecided` |
| `gap` | the entry's `bridge:namesGap` as a full IRI; empty where it names none |
| `reason` | the entry's `bridge:because` |
| `documents`, `occurrences` | integers |
| `forms` | the forms written in, comma separated, `bare` for the bare one; empty where only the bare form was |

**The exit code is 0 once the adapter was read, whatever was found**, a folder
with no document included, and 2, never 1, where the adapter cannot be read, it
names no `bridge:sourceAccounting`, or `--envelope` names an envelope it does not
declare, each refused before any document is read, so an empty folder is refused
too; and where the folder cannot be read, `--tsv` cannot be written or the
arguments are wrong. Standard output carries nothing then.
