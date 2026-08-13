# Ansatz Generator Exporters

The `verfeinert.ansatz_generator.exporters` package is the public boundary
between generator-owned records and Verfeinert canonical JSON contracts.
It lets researchers generate ansatz candidates, export canonical Candidate
JSON, and stage candidate collections without writing example-specific
projection code.

## Public API

The stable imports are available from `verfeinert.ansatz_generator`:

- `CandidateJsonExportConfig`
- `export_candidate_json`
- `write_candidate_json`
- `StagedPackageJsonExportConfig`
- `StagedPackageJsonExportResult`
- `export_staged_package_json`
- `write_staged_package_json`

The in-memory `export_*` functions return validated dictionaries. The
`write_*` functions validate before writing and use `verfeinert.core` path
guards so output roots remain caller-owned and separate from package source.

## Candidate JSON

`export_candidate_json()` maps public generator records into
`verfeinert.candidate.v1`:

- `candidate_id` is derived from the generator source ID or from an explicit
  caller prefix.
- `circuit` preserves backend-independent gates, qubits, ordered operations,
  and first-appearance trainable parameters.
- `lineage` preserves generation, parent/root relationships, and mutation
  provenance when present.
- `metadata` keeps generator annotations and caller-provided labels.
- `provenance` records source kind, source label, software version, Git commit
  when discoverable, input hashes, and creation time.
- `identity.structural_hash` is computed from the canonical circuit payload;
  `identity.lineage_hash` is computed from canonical lineage.

The exporter does not import generated callables, create QNodes, run metrics,
or depend on analyzer/evolver internals.

## Staged Package JSON

`export_staged_package_json()` and `write_staged_package_json()` map candidate
collections into `verfeinert.staged_package.v1`. The staged exporter first
builds a canonical ID map for the whole collection, then exports each
candidate with parent/root links resolved against that map.

When writing, package artifacts are relative to the package root. Individual
candidate JSON files are optional and are recorded as metadata artifacts with
content hashes. Execution flags are always truthful and false:

- `qnodes_executed=false`
- `scientific_metrics_executed=false`
- `generated_callables_imported=false`

## Internal And External Representations

Generator records remain implementation records optimized for template
building, structural mutation, and campaign logic. Canonical Candidate
and StagedPackage JSON are the external exchange formats shared with analyzer,
evolver, examples, and downstream researchers.

Historical compiler outputs remain separate from these exporters. Public
examples use the canonical exporters instead of local conversion helpers.

## Future Compatibility

Future generator adapters should target the same exporter surface. New source
record types may expose `to_dict()` or public mapping fields, but they should
not require notebook, external data-processing, analyzer, evolver, plotting, or quantum-runtime
dependencies at export time.
