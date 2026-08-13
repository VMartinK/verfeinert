# Release Extraction Checklist

## Summary

This checklist is the Phase 9.5.4 pre-extraction handoff for the future public
`verfeinert` repository. It does not perform extraction, repository creation,
commits, tags, pushes, or publication.

Status key:

- `[x]` complete in the current release candidate.
- `[ ]` pending manual action.

## Metadata

- [x] Apache-2.0 `LICENSE` present.
- [ ] `CITATION.cff` present and syntactically valid; final author metadata
  still needs human confirmation.
- [ ] `README.md` reviewed for current release-candidate readiness; standalone
  wording cleanup remains.
- [ ] `CONTRIBUTING.md` present and should be human-reviewed before first
  public commit.
- [x] `CHANGELOG.md` present.
- [ ] Final author metadata confirmed by humans.
- [ ] First public release-candidate version chosen.

## Package

- [x] Public namespace is `verfeinert`.
- [x] Package metadata declares package name `verfeinert`.
- [x] Apache-2.0 metadata is present in `pyproject.toml`.
- [x] Root schemas are present under `schemas/`.
- [x] Packaged schemas are present under `verfeinert/schemas/`.
- [x] Public imports were validated during Phase 8 external validation.
- [ ] Public-facing `Verfeinertv2` wording needs cleanup before extraction.

## Examples

- [x] CX-01 reproduction example included.
- [x] MIXT-5G reproduction example included.
- [x] Schema examples included for tests and documentation.
- [ ] CX-01 single-analysis example requires manual inclusion decision.
- [ ] `examples/MIXT5G_evolution/` placeholder excluded or rewritten.
- [x] Generated outputs excluded except `.gitkeep`.
- [x] Notebooks cleaned: zero outputs and zero execution counts.

## Security

- [x] Privacy audit completed.
- [x] Trivy vulnerability/misconfiguration scan completed.
- [x] Trivy secret scan completed.
- [x] pip-audit dependency scan completed.
- [x] No C release blockers found in Phase 9.5 internal-reference audit.
- [ ] Repeat privacy/security scans after extraction and before publication.

## Documentation

- [x] Documentation classification completed.
- [ ] Architecture docs should receive standalone-name wording cleanup.
- [ ] User docs should receive standalone-name wording cleanup.
- [ ] Migration docs require human decision: selected provenance archive or
  exclusion from first public repository.
- [ ] Placeholder docs rewritten or excluded.

## Release

- [ ] Version decision pending.
- [ ] Repository creation pending manual action.
- [ ] First public commit prepared.
- [ ] GitHub CI run in the future public repository.
- [ ] Release notes prepared from `CHANGELOG.md`.
- [ ] Tagging decision pending manual approval.
- [ ] Package publication pending separate manual approval.

## Final Pre-Extraction Commands

Run these from the current workspace immediately before extraction:

```bash
git status --short Verfeinertv2
find Verfeinertv2 -maxdepth 4 \( -name build -o -name dist -o -name '*.egg-info' -o -name __pycache__ -o -name .pytest_cache -o -name '.venv' -o -name '.ipynb_checkpoints' \) -print
find Verfeinertv2/examples -path '*/outputs/*' -type f -print
```

After extraction, rerun:

```bash
python -m unittest discover -s tests -q
python scripts/validate_external_install.py --output-root /tmp/verfeinert-external-validation
```

Use `pytest` only when the development extra is installed.
