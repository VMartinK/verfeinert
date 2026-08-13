# Internal Reference Audit

## Summary

Phase 9.5.3 searched the public repository candidate for internal references
that should not appear unexpectedly after extraction.

Classification key:

- **A - Already correct:** safe, intentional, or acceptable for public release.
- **B - Requires update before extraction:** not a blocker, but should be
  rewritten or reviewed before the first public repository commit.
- **C - Release blocker:** must be fixed before extraction or publication.

Result: no **C release blockers** were found.

## Search Scope And Terms

Scope: `Verfeinertv2/`.

Search terms:

- `Verfeinertv2`;
- `tfg/`;
- `TFG`;
- `Thesis_Data_Processing`;
- `/home/`;
- `.vscode`;
- `C:\Users`;
- `\Users\`;
- local filesystem and temporary path references such as `/tmp`.

Reviewed areas:

- root metadata and README files;
- documentation;
- examples;
- scripts;
- notebooks;
- tests and fixtures;
- package source.

## A) Already Correct

| Finding | Location pattern | Reason |
| --- | --- | --- |
| Forbidden-token constants | `tests/test_*` | Tests intentionally scan for `/home/`, Windows user paths, `TFG`, and `Thesis_Data_Processing` to prevent accidental coupling. |
| Boundary rules against thesis/local paths | `docs/architecture/*` | Architecture docs intentionally state what package modules must not import or assume. |
| Migration provenance | `docs/migration/*` | Migration reports intentionally mention development context and are separately classified for manual review. |
| Temporary output examples | `README.md`, `docs/development/ci.md`, example docs, external-validation docs | `/tmp/...` paths are caller-owned scratch output examples, not committed data roots or private paths. |
| Notebook metadata | `examples/**/notebooks/*.ipynb` | Notebooks are unexecuted: zero outputs and zero execution counts. |
| Example output placeholders | `examples/**/outputs/.gitkeep` | Placeholder files are intended to preserve empty output-root directories. |
| Package docstring wording | `verfeinert/core/config/models.py` | Uses `Verfeinertv2` descriptively; not a functional coupling. Prefer wording update before extraction, but not a blocker. |

## B) Requires Update Before Extraction

| Finding | Representative locations | Recommended update |
| --- | --- | --- |
| Public-facing `Verfeinertv2` wording | `examples/CX01_reproduction/README.md`, `examples/MIXT5G_reproduction/README.md`, `examples/CX01_single_analysis/README.md`, example scripts, `docs/user/*`, `docs/development/ci.md`, several architecture docs | Rewrite to standalone `Verfeinert` or `verfeinert` wording before first public commit. |
| “From the `Verfeinertv2/` root” instructions | `docs/user/cx01_reproduction.md`, `docs/user/mixt5g_reproduction.md`, `docs/development/ci.md`, `examples/CX01_single_analysis/README.md` | Change to “from the repository root” or “from the cloned `verfeinert` repository root.” |
| TFG/thesis context in migration reports | `docs/migration/*audit*.md`, `repository_extraction_audit.md`, `privacy_security_audit.md`, `phase9_final_report.md` | Keep only if humans choose to publish migration provenance; otherwise exclude from the public docs set. |
| TFG-context metric fixture skip logic | `tests/test_metrics_reference_validation.py` | Safe because it skips outside the development workspace, but review if the public repo should avoid TFG wording entirely. |
| Placeholder documentation | `docs/README.md`, `docs/architecture/README.md`, `docs/user/README.md`, `docs/migration/README.md`, root `notebooks/README.md`, `configs/README.md`, `scripts/README.md` | Rewrite as public indexes or exclude placeholder-only areas. |
| Placeholder example | `examples/MIXT5G_evolution/README.md` | Exclude from the first public tree unless a roadmap placeholder is intentionally desired. |
| Temporary scanner paths in security report | `docs/migration/external_security_scan_report.md` | Safe release evidence, but should remain manual-review material if migration reports are published. |

## C) Release Blockers

None found.

Specifically, this audit did not find:

- private local absolute user paths in shipped examples or schemas;
- `.vscode` project settings intended for publication;
- executed notebook outputs;
- generated experiment outputs under example output roots;
- required imports from thesis-only directories;
- private infrastructure references.

## Notes For Extraction

Before creating the first public commit, perform a wording cleanup pass focused
on B findings. The cleanup should update public-facing prose only unless humans
decide to also remove TFG-context test skip wording. Migration reports can be
excluded instead of rewritten if the first public repository should present a
cleaner external history.
