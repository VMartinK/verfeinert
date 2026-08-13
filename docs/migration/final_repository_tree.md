# Final Repository Tree

## Summary

Phase 9.5.2 defines the expected public repository structure for the future
standalone `verfeinert` repository. This is a preparation document only: no
repository was extracted, created, pushed, tagged, or published.

## Proposed Public Repository Tree

```text
verfeinert/
├── .github/
│   └── workflows/
│       └── ci.yml
├── verfeinert/
│   ├── core/
│   ├── ansatz_generator/
│   ├── ansatz_analyzer/
│   ├── ansatz_evolver/
│   ├── workflow/
│   └── schemas/
├── schemas/
├── examples/
│   ├── CX01_reproduction/
│   │   ├── comparison/
│   │   ├── config/
│   │   ├── notebooks/
│   │   ├── outputs/
│   │   │   └── .gitkeep
│   │   └── scripts/
│   ├── MIXT5G_reproduction/
│   │   ├── comparison/
│   │   ├── config/
│   │   ├── notebooks/
│   │   ├── outputs/
│   │   │   └── .gitkeep
│   │   └── scripts/
│   └── schemas/
├── tests/
│   └── fixtures/
├── docs/
│   ├── architecture/
│   ├── development/
│   ├── migration/
│   └── user/
├── scripts/
├── LICENSE
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── CITATION.cff
├── pyproject.toml
└── .gitignore
```

## Included Components

- `verfeinert/`: public Python namespace and package schema resources.
- `schemas/`: canonical repository-facing JSON schemas.
- `tests/`: fast contract, unit, smoke, package-hardening, and reference
  validation tests.
- `tests/fixtures/`: tiny deterministic fixtures that support public test
  behavior.
- `.github/workflows/ci.yml`: prepared CI workflow for the standalone
  repository.
- `scripts/validate_external_install.py`: public maintainer validation script.
- `examples/CX01_reproduction/`: public CX-01 reproduction workflow.
- `examples/MIXT5G_reproduction/`: public MIXT-5G reproduction workflow.
- `examples/schemas/`: canonical schema examples used by tests and docs.
- `docs/architecture/`, `docs/development/`, and reviewed `docs/user/` content.
- `LICENSE`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CITATION.cff`,
  `pyproject.toml`, and `.gitignore`.

## Manual Review Before Inclusion

- `examples/CX01_single_analysis/`: useful researcher workflow, but older than
  the reproduction examples. Include only after deciding whether the public
  repository should ship both an introductory example and reproduction examples.
- `docs/migration/`: include selected records only after reviewing
  `public_documentation_classification.md`.
- Placeholder README files in `docs/`, `configs/`, `scripts/`, `notebooks/`,
  and some example directories should be rewritten or excluded.
- `tests/test_metrics_reference_validation.py`: review TFG-context skip logic
  if the first public repository should avoid all TFG wording in tests.

## Excluded Components

- Generated outputs under `examples/**/outputs/*`, except `.gitkeep`.
- `examples/MIXT5G_evolution/`: placeholder-only future example; exclude from
  the first public tree unless humans want public roadmap placeholders.
- Root `notebooks/`: placeholder-only directory; exclude or replace with real
  notebook index before publication.
- Generated artifacts, local experiment data, cache directories, build outputs,
  virtual environments, temporary external-validation output, and scanner raw
  outputs.
- Any surrounding workspace material outside `Verfeinertv2/`, including legacy
  implementation, thesis-processing notebooks, local data, and private research
  outputs.

## Verification Results

- Internal scans found public-facing `Verfeinertv2` wording that should be
  updated before extraction.
- No thesis-only directories are required by the proposed public package tree.
- Example output directories currently contain only `.gitkeep`.
- Notebook inspection found zero outputs and zero executed cells.
- Generated-artifact scans found no build, dist, egg-info, cache, checkpoint,
  or virtual-environment directories under the public candidate tree.

## Remaining Manual Decisions

1. Decide whether `examples/CX01_single_analysis/` ships in the first public
   repository.
2. Decide whether selected `docs/migration/` provenance records ship publicly.
3. Rewrite placeholder documentation indexes before publication or exclude them.
4. Apply standalone wording updates from `internal_reference_audit.md`.
5. Confirm author metadata and first release-candidate version before GitHub
   creation.
