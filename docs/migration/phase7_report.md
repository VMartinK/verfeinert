# Phase 7 Report

## Summary

Phase 7 adds a public workflow runner and two reproduction examples that prove the current Verfeinertv2 modules can interoperate through canonical JSON artifacts.

## Implemented

- `verfeinert.workflow` package:
  - `WorkflowConfig`;
  - stage configuration records;
  - `WorkflowRunner`;
  - `WorkflowResult`;
  - workflow provenance helper.
- End-to-end module validation test.
- CX-01 reproduction example.
- MIXT-5G reproduction example.
- Architecture, user, and migration documentation.

## Validation Coverage

Tests cover:

- generator to canonical Candidate/StagedPackage export;
- analyzer structural-cost AnalysisResult output;
- evolver AnalysisResult ingestion;
- selection and EvolutionRun export;
- workflow runner artifact manifests;
- output-root separation;
- CX-01 smoke reproduction;
- MIXT-5G bounded evolution smoke reproduction;
- absence of campaign branches and forbidden heavy/notebook dependencies in workflow internals.

## Verification

Completed checks:

```bash
python3 -m json.tool schemas/candidate.schema.json
python3 -m json.tool schemas/staged_package.schema.json
python3 -m json.tool schemas/analysis_result.schema.json
python3 -m json.tool schemas/evolution_run.schema.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -q
```

Result: 127 unittest tests passed. `pytest` was not installed in the local Python environment, so the optional pytest pass was skipped.

## Decisions

- The workflow runner is orchestration only.
- Campaign-specific reproduction factories live in examples.
- Smoke profiles are deterministic and cheap.
- Full scientific metric reproduction remains explicit opt-in.
- Derived ranking artifacts are written as secondary outputs, not canonical exchange contracts.

## Remaining Limitations

- The workflow runner handles one batch per invocation.
- MIXT-5G uses an example-local bounded loop for now.
- Full expressibility/trainability comparison requires future metric runtime fixtures and reference outputs.
- A formal workflow manifest schema may be useful later, but Phase 7 keeps `WorkflowResult` as a JSON-safe runtime manifest.
