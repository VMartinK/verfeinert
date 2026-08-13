# Package Hardening Report

## Summary

Phase 8.1 prepares Verfeinertv2 to operate as an installed independent Python package.

The main package-hardening change is schema resource migration: framework validators now load canonical JSON Schemas from packaged resources instead of resolving paths relative to the development repository root.

## Implemented Changes

- Added packaged schema resources under `verfeinert.schemas`.
- Added public core schema-resource helpers:
  - `schema_names`;
  - `schema_filename`;
  - `read_schema_text`;
  - `load_schema`;
  - `schema_store`.
- Updated generator, analyzer, and evolver schema validation to use the core packaged resource loader.
- Updated package data configuration so `verfeinert.schemas/*.schema.json` is included in installed distributions.
- Removed package-root `sys.path` bootstraps from the CX-01 and MIXT-5G reproduction scripts.
- Added package-hardening tests for byte-for-byte schema resource matching, external-cwd public imports, and absence of repo-root schema assumptions in framework validators.

## Package Integrity

Root `schemas/` remains the repository-facing canonical schema directory. The packaged schema resources are byte-identical copies used for installed-package validation.

The installed-package validation path is now:

```text
verfeinert.core.schema_resources
        |
        v
importlib.resources.files("verfeinert.schemas")
        |
        v
generator/analyzer/evolver validation
```

No public Candidate, StagedPackage, AnalysisResult, or EvolutionRun payload shape changed in this phase.

## Verification

Focused package-hardening check:

```text
env PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib-verfeinertv2 ../.venv/bin/python -m unittest tests/test_package_hardening.py -q
```

Result:

```text
Ran 4 tests
OK
```

Full-suite verification is run after this report as the Phase 8.1 checkpoint before continuing to CI/CD.

## Open Items

- Clean virtual-environment installation from outside the source tree is validated in Phase 8.3.
- Future package hardening may move repository-facing schema synchronization into a developer script if schemas change frequently.
