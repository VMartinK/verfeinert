# External Validation Report

## Summary

Phase 8.3 adds an external-user validation workflow for Verfeinertv2.

The validation script creates a temporary virtual environment, installs the package from the local source tree, clears `PYTHONPATH`, checks public imports and packaged schemas from outside the source directory, and runs CX-01 and MIXT-5G smoke reproduction examples into caller-owned output roots.

## Added Workflow

- Script: `scripts/validate_external_install.py`
- Test coverage: `tests/test_external_validation_script.py`

The script is stdlib-only before installation and does not import Verfeinert directly. The installed package is exercised only through public APIs.

## Validation Steps

1. Create temporary virtual environment.
2. Install Verfeinert from the selected source root.
3. Run public import and packaged-schema checks.
4. Run CX-01 smoke reproduction.
5. Run MIXT-5G smoke reproduction.
6. Write `external_validation_summary.json` under the selected output root.

## Local Execution

```bash
python scripts/validate_external_install.py --output-root /tmp/verfeinert-external-validation
```

If the environment cannot install runtime dependencies, rerun only after dependency installation is available. Scientific dependencies are intentionally not weakened for validation convenience.

## Current Status

Script-level tests validate command construction, public example selection, output-root routing, and the absence of direct framework imports or `sys.path` bootstraps.

Full clean-environment validation was attempted twice:

- sandboxed run: blocked by pip network access while resolving build dependencies;
- approved network-enabled run: passed.

Successful run summary:

```text
status: passed
output_root: /tmp/verfeinertv2-external-validation
steps:
  - install-package
  - public-imports-and-packaged-schemas
  - cx01-smoke-example
  - mixt5g-smoke-example
```

The package installed into a temporary virtual environment, packaged schema loading worked from outside the source tree, CX-01 smoke generated analysis artifacts, and MIXT-5G smoke generated evolution artifacts with lineage-preserving workflow output.
