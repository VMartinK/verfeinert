# Phase 8 Final Report

## Completed Phases

- Phase 8.0.1: scientific metric alignment with v1 methodology.
- Phase 8.1: package hardening and packaged schema resources.
- Phase 8.2: CI/CD workflow and CI documentation.
- Phase 8.3: external-user validation workflow.
- Phase 8.4: release-readiness audit.

## Package Status

Verfeinertv2 now supports installed-package schema validation through `importlib.resources` and package data under `verfeinert.schemas`.

Public imports validated:

- `verfeinert.core`
- `verfeinert.ansatz_generator`
- `verfeinert.ansatz_analyzer`
- `verfeinert.ansatz_evolver`
- `verfeinert.workflow`

## CI Status

CI workflow added at `.github/workflows/ci.yml`.

The workflow is designed for the future standalone repository root and validates:

- installation with `.[dev]`;
- schema parsing;
- public imports;
- full `unittest`;
- `pytest`;
- CX-01 smoke reproduction;
- MIXT-5G smoke reproduction;
- visualization optional-extra tests.

Local YAML parsing succeeded. Remote GitHub CI execution is pending push.

## External Validation Status

External validation script added at `scripts/validate_external_install.py`.

Validation result:

```text
status: passed
output_root: /tmp/verfeinertv2-external-validation
```

The first sandboxed run failed because pip could not reach build dependencies. After approved network access, the clean virtual environment installed Verfeinert and passed public import/schema checks plus CX-01 and MIXT-5G smoke examples.

## Test Status

Latest checkpoint:

```text
env PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib-verfeinertv2 ../.venv/bin/python -m unittest discover -s tests -q
```

Result:

```text
Ran 143 tests
OK (skipped=1)
```

All root JSON Schemas parsed successfully.

`pytest` was not installed in the visible local venv. The CI workflow installs `.[dev]` and runs pytest there.

## Release Blockers

No architecture, public API, package-installation, schema-resource, or smoke-example blocker was found.

Publication blockers to resolve before a real release:

- choose license;
- choose release version;
- run remote GitHub CI;
- decide package publishing automation.

## Remaining Technical Debt

- Full scientific reproduction remains opt-in and separate from smoke CI.
- Example notebooks are researcher interfaces and still use local script imports.
- Package build artifacts were not published.

## Recommended Release Actions

1. Extract `Verfeinertv2/` into the standalone `verfeinert` repository.
2. Run the new GitHub CI workflow.
3. Set license and release version metadata.
4. Perform a final public API review.
5. Tag a release candidate only after CI and metadata review pass.
