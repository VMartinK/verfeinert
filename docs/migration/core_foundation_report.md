# Core Foundation Implementation Report

## Created Files

This implementation adds the first functional `verfeinert.core` layer inside
`Verfeinertv2/` only. The existing `Verfeinert/` implementation was not
modified.

Core source files added:

- `verfeinert/core/config/` for validated Python and YAML run configuration;
- `verfeinert/core/execution/` for sequential and multiprocessing executors;
- `verfeinert/core/io/` for path guards and JSON/YAML serialization;
- `verfeinert/core/metadata/` for run provenance and execution flags;
- `verfeinert/core/schemas/` for shared schema and column constants;
- `verfeinert/core/hashing.py` and `verfeinert/core/validation.py`.

Documentation added:

- `docs/architecture/core.md`;
- `docs/architecture/execution.md`;
- `docs/architecture/data_and_output_policy.md`;
- `docs/architecture/visualization.md`.

Tests added:

- `tests/test_core_config.py`;
- `tests/test_core_execution.py`;
- `tests/test_core_io_metadata.py`;
- `tests/test_core_dependency_boundaries.py`.

`pyproject.toml` now declares `PyYAML>=6` as the only runtime dependency.

## Reused Behavior From Current Implementation

No source code, notebooks, generated outputs, or experiment artifacts were
copied from the existing `Verfeinert/` tree. The reused behavior is architectural
and contract-level, based on the migration audit:

- table-first records remain the stable boundary between future generator,
  analyzer, and evolver modules;
- run IDs, candidate IDs, metric columns, Pareto columns, schema labels, and
  threshold labels are centralized as shared schema constants;
- reproducibility behavior is made reusable through stable hashing, input
  hashes, effective config capture, random seed capture, timestamping, optional
  Git commit discovery, and truthful execution flags;
- experiment roots are caller-provided and validated so source, inputs, and
  outputs stay separate;
- scientific execution remains outside the generator and default core layer.

## Verification

Executed from `Verfeinertv2/`:

```text
python3 -m unittest discover -s tests -q
```

Result:

```text
Ran 10 tests in 0.024s
OK
```

Static checks:

```text
python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"
python3 -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) for path in pathlib.Path('verfeinert').rglob('*.py')]; print('python ast ok')"
find Verfeinertv2 -type d -name __pycache__
```

Results:

```text
pyproject ok
python ast ok
no __pycache__ directories
```

`pytest` was not executed because it is not installed in the visible Python
environments. The tests are written with `unittest` so they remain collectable
by pytest once the optional dev dependency is installed.

## Deferred Decisions

- Compatibility shims for current notebook imports are deferred until the
  scientific modules begin migration.
- Generator, analyzer, and evolver scientific APIs are not migrated yet.
- Metric-level, generation-level, campaign-level, joblib, Dask, MPI, and HPC
  execution are documented as future extension points only.
- Visualization implementation is deferred to
  `verfeinert/ansatz_analyzer/visualization/`; this phase only defines the
  architecture contract.
- Final citation metadata, license text, and independent repository CI policy
  remain to be finalized before extraction.

## Risks

- Multiprocessing requires functions passed to executors to be picklable; future
  scientific modules should keep worker functions module-level or otherwise
  pickle-compatible.
- Strict path separation may require migration scripts to make existing thesis
  input/output roots explicit before they can use Verfeinertv2 APIs.
- Schema constants are intentionally minimal. Additional table columns should
  be added only when two or more framework modules genuinely share them.
