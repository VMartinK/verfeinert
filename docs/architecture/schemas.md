# Schema Contracts

Verfeinert schema files live under the repository-level `schemas/` directory
and are mirrored under `verfeinert/schemas/` for package resources. They use
JSON Schema Draft 2020-12. Runtime validation loads packaged schema resources
so installed packages do not depend on repository-relative paths.

## Versioning

The initial canonical schema versions are:

```text
verfeinert.candidate.v1
verfeinert.experiment.v1
verfeinert.staged_package.v1
verfeinert.analysis_result.v1
verfeinert.evolution_run.v1
verfeinert.comparison_result.v1
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

## Comparison Result Schema

`comparison_result.schema.json` records explicit global/comparative
postprocessing over selected AnalysisResult collections.

Required areas:

- comparison ID and transform version;
- explicit source refs;
- compatibility report;
- global Pareto and optional ranking rows;
- candidate rows preserving candidate and analysis refs;
- comparison provenance.

The schema keeps plotting and CSV export derived from the persisted
ComparisonResult rather than making figures or tables scientific source data.

## Cross-Schema References

`staged_package.schema.json` references `candidate.schema.json`. Runtime
validators use the packaged schema store, and tests enforce root/package mirror
parity.

Analysis and evolution schemas use lightweight candidate references instead of
embedding candidates by default.

## Extension Policy

Each schema has a top-level `extensions` object. Use it for experimental
module-specific additions that must travel with the canonical record. Do not
add fields to `metadata` or `extensions` merely to preserve legacy data that no
future module consumes.

## Open Design Decisions

- Decide whether runtime APIs should validate every document by default or
  expose explicit validation commands.
- Decide whether metric values need typed sub-schemas once analyzer APIs
  require stricter domain validation.
- Define transform records for future CSV/Parquet derived tables.
- Define a stable URI policy for packaged records stored outside local
  filesystems.
