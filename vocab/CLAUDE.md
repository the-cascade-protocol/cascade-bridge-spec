# vocab — Agent Context

- **A term's name is its first documentation.** Give it an `rdfs:comment` only
  for what the name cannot say, and never its cardinality: that is the shape's.
- **A test type's `rdfs:comment` is its comparison rule**, because a Bridge
  implements it and nothing here can run it. The rule, not the reasons for it.
- `ro-crate-1.2-read-terms.context.jsonld` gives each RO-Crate 1.2 term a crate
  uses the IRI the published context gives it, and no term that context does
  not give. A term is added with its published entry in
  `tests/adapter_profile/published_context_entries.json`, and the statements of
  each committed crate, as the published context gives them, are saved in
  `tests/adapter_profile/crate_graphs/`.
- `compatibility.context.jsonld` maps every key of a `compatibility.json` to a
  term here or a schema.org term.
