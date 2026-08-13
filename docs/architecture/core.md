# Core Architecture

`verfeinert.core` is the lightweight shared layer for Verfeinert. It exists
to make the generator, analyzer, evolver, workflow runner, and CLI agree on stable
configuration, execution, I/O, metadata, schemas, validation, and hashing
contracts without moving scientific behavior into the shared package.

The public repository is organized around a stable `verfeinert` namespace.
Historical reference implementations may inform validation, but they are not
runtime dependencies and are not imported by `core`.

## Responsibilities

`core` owns:

- validated run, path, and execution configuration records;
- YAML loading that resolves to the same Python objects as direct config
  construction;
- executor construction for currently supported candidate-level sequential and
  multiprocessing execution;
- JSON/YAML serialization helpers for reproducible records;
- path guards that keep package source, experiment inputs, and experiment
  outputs separate;
- run provenance metadata and optional Git commit capture;
- shared identifiers, column names, schema version labels, threshold labels,
  lightweight validators, and stable hashing.

`core` must not own:

- circuit construction, ansatz templates, mutations, or candidate compilation;
- QNode construction or scientific metric execution;
- Pareto policies, report generation, or plotting;
- evolver population, archive, or selection logic;
- project-specific paths, notebooks, figures, or generated outputs.

## Dependency Boundary

Allowed dependencies are the Python standard library and the minimal package
dependency needed for YAML parsing, `PyYAML`. The module must not import
`verfeinert.ansatz_generator`, `verfeinert.ansatz_analyzer`,
`verfeinert.ansatz_evolver`, `pennylane`, `matplotlib`, `pandas`, `numpy`, or
notebook APIs.

The target dependency direction is:

```text
core
  <- ansatz_generator
  <- ansatz_analyzer
  <- ansatz_evolver
```

Reverse dependencies are forbidden. This keeps `core` extractable and usable by
external researchers without installing the full scientific stack.

## Schema Policy

Schema constants in `core.schemas` define names that must remain stable across
module boundaries, such as run IDs, candidate IDs, metric table columns, Pareto
table columns, and schema version labels. They are deliberately limited to
shared records. Module-specific scientific columns should stay in the owning
module until at least two framework modules need them.

## Extension Policy

New core APIs should be added only when a migrated module already needs the
shared behavior. Prefer explicit small modules over a broad `utils` namespace.
When a future function would require scientific dependencies or experiment
execution, it belongs outside `core`.
