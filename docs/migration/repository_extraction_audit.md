# Repository Extraction Audit

## Summary

Phase 9.0 audits `Verfeinertv2/` as the future public `verfeinert`
repository root. No repository was created, extracted, pushed, or published.

Default policy for migration history is **review then include**: migration and
audit documents are useful public provenance, but documents that mention TFG or
thesis context should receive a human review before the first public release.

## Proposed Public Repository Tree

```text
verfeinert/
  .github/workflows/ci.yml
  .gitignore
  CHANGELOG.md
  CITATION.cff
  CONTRIBUTING.md
  LICENSE
  README.md
  pyproject.toml
  configs/
  docs/
    architecture/
    development/
    migration/
    user/
  examples/
    CX01_single_analysis/
    CX01_reproduction/
    MIXT5G_evolution/
    MIXT5G_reproduction/
    schemas/
  notebooks/
  schemas/
  scripts/
  tests/
  verfeinert/
```

## A) Include In Public Repository

- `verfeinert/`: package source, including packaged schema resources.
- `schemas/`: repository-facing canonical JSON Schemas.
- `tests/`: fast unit, contract, package-hardening, reference-fixture, and
  smoke tests.
- `tests/fixtures/reference_metrics/`: tiny deterministic scientific reference
  fixtures.
- `.github/workflows/ci.yml`: CI definition for the standalone repository.
- `pyproject.toml`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`,
  `CITATION.cff`, `LICENSE`, `.gitignore`.
- `docs/architecture`, `docs/user`, `docs/development`: public framework,
  user, and developer documentation.
- `examples/**/config`, `examples/**/scripts`, `examples/**/notebooks`,
  `examples/**/comparison`, and `examples/schemas`: researcher-facing examples
  and small reference summaries.
- `examples/**/outputs/.gitkeep`: placeholder files only.
- `scripts/validate_external_install.py`: release validation utility.

## B) Exclude From Public Repository

- Generated outputs under `examples/**/outputs/*` except `.gitkeep`.
- Local experiment outputs, result roots, plot exports, temporary validation
  outputs, and generated package artifacts.
- Virtual environments: `.venv/`, `venv/`, `env/`, `ENV/`.
- Python and test caches: `__pycache__/`, `.pytest_cache/`, coverage output.
- Packaging/build artifacts: `build/`, `dist/`, `*.egg-info/`, wheels, source
  archives.
- Large or private data roots such as `data/raw/`, `data/cache/`, local
  `results/`, `outputs/`, and binary arrays/models.
- Any material outside `Verfeinertv2/` from the surrounding TFG workspace.

## C) Review Manually Before Release

- `docs/migration/*`: include after human review. These reports intentionally
  mention migration context, historical Verfeinert v1 references, TFG, and
  thesis-processing material.
- Example notebooks: currently unexecuted with no outputs, but should be
  reviewed again after any future notebook edit.
- Citation author metadata: currently `Verfeinert contributors`; update if
  humans choose named authors before release.

## Extraction Checklist

1. Copy the contents of `Verfeinertv2/` into the new standalone repository root.
2. Ensure `.gitignore` is active before adding files.
3. Confirm `examples/**/outputs/` contains only `.gitkeep`.
4. Run privacy/security searches again in the extracted repository.
5. Run CI locally or in GitHub before release tagging.
6. Do not copy any sibling TFG repository material.

## Remaining Decisions

- Final release version and tag name.
- Final author list and citation metadata.
- Whether all migration reports should be published in the first release or
  moved to a later provenance appendix after human review.
