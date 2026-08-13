# Release Metadata Report

## Summary

Phase 9.3 prepares release metadata for the future public `verfeinert`
repository. No GitHub repository was created, no code was pushed, no tag was
created, and no package was published.

## Final Metadata Decisions For This Phase

- Repository name: `verfeinert`.
- Python package name: `verfeinert`.
- License: `Apache-2.0`.
- License file: `LICENSE`.
- Current package version: `0.0.0`.
- First release-candidate proposal: `0.1.0rc1` after repository creation and
  remote CI validation.
- Author metadata: `Verfeinert contributors` until humans choose named authors.
- Citation file: `CITATION.cff`.

## Version Policy Proposal

- Keep `0.0.0` while Verfeinertv2 remains nested in the TFG workspace.
- Use `0.1.0rc1` for the first standalone public release candidate.
- Use `0.1.0` only after:
  - GitHub CI passes in the new repository;
  - public API names receive human review;
  - license and citation metadata are confirmed;
  - release notes are reviewed;
  - at least smoke reproduction workflows pass from a clean install.

Future versioning should follow semantic-versioning intent:

- patch versions for bug fixes and documentation corrections;
- minor versions for new framework capabilities that preserve public APIs;
- major versions for breaking schema or public API changes.

## Changelog Structure

Recommended headings:

```text
# Changelog

## Unreleased

## 0.1.0rc1 - YYYY-MM-DD

## 0.1.0 - YYYY-MM-DD
```

Each release should group changes by:

- Added;
- Changed;
- Fixed;
- Documentation;
- Scientific validation.

## Citation Metadata

Current citation metadata is intentionally conservative:

- title: `Verfeinert`;
- version: `0.0.0`;
- license: `Apache-2.0`;
- authors: `Verfeinert contributors`.

Manual release step: decide whether to replace contributor-group metadata with
named authors before public release.

## Release Checklist

Before GitHub repository creation:

1. Review `docs/migration/*` for TFG/thesis wording under the selected “review
   then include” policy.
2. Confirm `LICENSE`, `pyproject.toml`, `README.md`, and `CITATION.cff` agree on
   Apache-2.0.
3. Confirm `.gitignore` excludes generated outputs and build artifacts.
4. Confirm example output roots contain only `.gitkeep`.
5. Rerun privacy/security scans.

After GitHub repository creation:

1. Push the prepared repository.
2. Run GitHub CI.
3. Fix any CI-only packaging or dependency issues.
4. Review public API exports.
5. Set release-candidate version to `0.1.0rc1`.
6. Build package artifacts locally or in CI.
7. Create release notes from `CHANGELOG.md`.
8. Tag only after human approval.

Before a final public package release:

1. Run external installation validation.
2. Run CX-01 and MIXT-5G smoke reproductions.
3. Decide whether to run full expensive scientific reproduction workflows.
4. Confirm citation metadata and author list.
5. Publish only after final human confirmation.

## Remaining Manual Actions

- GitHub repository creation.
- Repository extraction from the surrounding workspace.
- Remote CI execution.
- Final author/citation review.
- First release-candidate version bump.
- Package publication decision.
