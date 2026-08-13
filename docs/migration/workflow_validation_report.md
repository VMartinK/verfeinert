# Workflow Validation Report

Phase 7 adds an end-to-end validation path proving that the migrated modules interoperate through canonical JSON.

## Scope

The validation covers:

- Sanz19 candidate generation with public generator APIs;
- canonical Candidate and StagedPackage export;
- structural-cost-only analyzer execution;
- AnalysisResult collection loading;
- evolver AnalysisResult ingestion;
- survivor selection;
- EvolutionRun JSON export and validation.

It excludes notebooks, QNodes, expensive metrics, plotting, legacy Verfeinert code, thesis postprocessing, and generated callable execution.

## Test

`tests/test_end_to_end_workflow.py` creates a tiny Sanz19 set, exports it to a temporary run root, analyzes it, ingests the resulting AnalysisResult JSON documents through the evolver boundary, selects one survivor, and writes a valid EvolutionRun JSON document.

The test verifies:

- candidate IDs are preserved from generation through analysis and evolution;
- `analysis_result_refs` link each candidate to its result;
- lineage and identity stay in canonical Candidate JSON;
- EvolutionRun provenance is explicit;
- the evolver records that it did not execute metrics.

## Result

The workflow validates the current JSON-first architecture. The generator, analyzer, and evolver can exchange canonical artifacts without pandas tables, notebook helpers, campaign branches, or legacy path assumptions.

Full unittest discovery passed after adding the Phase 7 tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Result: 127 tests passed.

## Deferred Work

- Full metric comparison for historical campaigns remains opt-in.
- Multi-generation orchestration belongs in the future evolver pipeline.
- Derived analytical tables remain secondary artifacts.
