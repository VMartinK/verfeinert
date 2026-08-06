# Schema Contracts

Verfeinert schema files live under the repository-level `schemas/` directory
and use JSON Schema Draft 2020-12. The `$id` values are future stable public
schema URIs. Tests resolve the files locally.

## Versioning

The initial canonical schema versions are:

```text
verfeinert.candidate.v1
verfeinert.experiment.v1
verfeinert.staged_package.v1
verfeinert.analysis_result.v1
verfeinert.evolution_run.v1
```

Schema versions are semantic data-contract labels, not package versions. Any
breaking field change requires a new schema version.

## Candidate Schema

`candidate.schema.json` is the canonical ansatz record.

Required top-level fields:

- `schema_version`;
- `candidate_id`;
- `identity`;
- `circuit`;
- `lineage`;
- `metadata`;
- `provenance`.

The schema requires a nested circuit with operations and parameter references.
It intentionally avoids historical flat fields such as `circuit_id`,
`operations` at the top level, or table-oriented count columns.

## Experiment Schema

`experiment.schema.json` defines caller-owned experiment configuration.

Required areas:

- input records with IDs, kind, URI, optional schema version, and optional hash;
- output root URI and artifact policy;
- execution mode, scope, worker count, and candidate parallelization flag;
- reproducibility options;
- optional module configuration blocks.

The schema does not define local or project-specific paths, local absolute paths, or named
historical campaigns.

## Staged Package Schema

`staged_package.schema.json` describes candidate packages exchanged between
modules. It embeds canonical candidate documents and records generated artifacts
as package outputs.

The package manifest includes execution flags constrained to:

```text
qnodes_executed = false
scientific_metrics_executed = false
generated_callables_imported = false
```

This keeps generator-stage packages distinct from analysis outputs.

## Analysis Result Schema

`analysis_result.schema.json` records analyzer outputs. It references a
candidate by ID and optional URI/hash rather than embedding a full candidate.

Required areas:

- candidate reference;
- metrics;
- cost;
- classifications;
- provenance.

Metric records can represent computed, skipped, or failed metrics.

## Evolution Run Schema

`evolution_run.schema.json` records evolver state and outcomes.

Required areas:

- run metadata;
- configuration;
- generations;
- candidate, survivor, and archive references;
- provenance.

The schema is intentionally reference-based so a run can point to candidate
packages and analysis results without duplicating large documents.

## Cross-Schema References

`staged_package.schema.json` references `candidate.schema.json`. Tests load the
schema store locally, but published consumers should resolve the public `$id`
URIs once the framework repository is independent.

Analysis and evolution schemas use lightweight candidate references instead of
embedding candidates by default.

## Extension Policy

Each schema has a top-level `extensions` object. Use it for experimental
module-specific additions that must travel with the canonical record. Do not
add fields to `metadata` or `extensions` merely to preserve legacy data that no
future module consumes.

## Open Design Decisions

- Decide whether to publish schemas in package data, documentation, or both.
- Decide whether runtime APIs should validate every document by default or
  expose explicit validation commands.
- Decide whether metric values need typed sub-schemas once analyzer APIs
  begins.
- Define transform records for future CSV/Parquet derived tables.
- Define a stable URI policy for packaged records stored outside local
  filesystems.
