# CI Report

## Summary

Phase 8.2 adds release-oriented CI for the future standalone Verfeinert repository.

The workflow validates package installation, schemas, public imports, unit tests, pytest collection, and smoke examples. Visualization is covered by a separate optional-extra job.

## Implemented Workflow

- `.github/workflows/ci.yml`
- Base matrix:
  - Python 3.11;
  - Python 3.12.
- Base checks:
  - install `.[dev]`;
  - parse root JSON Schemas;
  - validate public imports and packaged schema loading;
  - run `unittest`;
  - run `pytest`;
  - run CX-01 smoke reproduction;
  - run MIXT-5G smoke reproduction.
- Visualization job:
  - install `.[dev,visualization]`;
  - run visualization tests.

## Dependency Policy

NumPy and PennyLane are installed through base runtime dependencies. They are no longer hidden behind optional extras because Phase 8.0.1 made the v1-aligned scientific metric methodology authoritative.

`joblib` remains optional under the `quantum` extra. `pandas` remains dev/test-only.

## Local Verification

The workflow file is static YAML and will execute in GitHub after extraction to the standalone repository root. Local Phase 8.2 verification continues with the same full `unittest` suite and schema parse checks used by Phase 8.1.
