# Analyzer Foundation Report

## Summary

This phase implements the first real `verfeinert.ansatz_analyzer` foundation
layer inside `Verfeinertv2/` only. The implementation follows the Phase 4
audit and design documents and keeps canonical JSON as the exchange boundary.

No existing `Verfeinert/` code, old notebooks, `Thesis_Data_Processing`,
legacy `python/` code, schemas, or `ansatz_generator` modules were modified.

## Created Or Updated Files

Analyzer package:

- `verfeinert/ansatz_analyzer/config.py`;
- `verfeinert/ansatz_analyzer/models.py`;
- `verfeinert/ansatz_analyzer/validation.py`;
- `verfeinert/ansatz_analyzer/io.py`;
- `verfeinert/ansatz_analyzer/results.py`;
- `verfeinert/ansatz_analyzer/pipeline.py`;
- `verfeinert/ansatz_analyzer/metrics/__init__.py`;
- `verfeinert/ansatz_analyzer/metrics/structural_cost.py`;
- `verfeinert/ansatz_analyzer/__init__.py`.

Tests:

- `tests/test_ansatz_analyzer_foundation.py`.

Documentation:

- `docs/architecture/analyzer_foundation.md`;
- `docs/migration/analyzer_foundation_report.md`.

Project metadata:

- `pyproject.toml` now lists `jsonschema>=4` as a runtime dependency because
  analyzer I/O validates canonical schemas at runtime.

## Implemented Behavior

The foundation analyzer can:

- load canonical Candidate JSON;
- load canonical StagedPackage JSON and preserve candidate order;
- validate Candidate, StagedPackage, and AnalysisResult documents through the
  existing schemas;
- build internal `CandidateView` and `OperationView` records;
- compute structural cost from canonical candidate records;
- use explicit reference bounds or derive bounds from the selected candidates;
- record warning state when operation count is used as a depth proxy;
- assemble canonical `verfeinert.analysis_result.v1` documents;
- write AnalysisResult JSON under guarded caller-provided output roots.

The foundation analyzer does not:

- execute QNodes;
- import or execute generated callable modules;
- compute expressibility or trainability;
- compute Pareto classifications or rankings;
- write CSV/Parquet tables;
- generate plots;
- run or modify notebooks.

## Relation To Current Analyzer

Migrated directly:

- the structural cost concept from the Beta analyzer;
- reference-normalized weighted components;
- warning when depth is approximated by operation count;
- reference-range status metadata;
- truthful execution flags.

Refactored:

- pandas metadata tables became record-first `CandidateView` inputs;
- notebook-compatible payloads became canonical AnalysisResult JSON;
- local JSON/path helpers were replaced by `verfeinert.core`;
- campaign/notebook fields were removed from foundation configuration;
- table exports were deferred.

Deferred:

- expressibility;
- trainability;
- metric execution runtime;
- Pareto/classification;
- ranking;
- visualization;
- notebook endpoints;
- historical Beta table adapters.

## Verification

Executed from `Verfeinertv2/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Result:

```text
Ran 46 tests
OK
```

`pytest` is still an optional development tool and is not installed in the
visible Python environment used for this run:

```text
/usr/bin/python3: No module named pytest
```

## Open Decisions

- Whether future metric-specific values need stricter sub-schemas.
- How uncertainty, diagnostic samples, and runtime traces should be represented
  inside metric metadata.
- Whether analyzer result collections need a separate canonical schema.
- Which optional dependency groups should own PennyLane, NumPy, pandas, and
  Matplotlib once expensive metrics and visualization are migrated.
- Whether structural cost should later expose additional named cost models.
