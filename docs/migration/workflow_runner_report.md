# Workflow Runner Report

## Created Files

- `verfeinert/workflow/__init__.py`
- `verfeinert/workflow/config.py`
- `verfeinert/workflow/provenance.py`
- `verfeinert/workflow/runner.py`

The top-level package namespace now includes `workflow` in `verfeinert.__all__`.

## Implemented API

- `WorkflowConfig`
- `GenerationStageConfig`
- `AnalyzerStageConfig`
- `EvolutionStageConfig`
- `WorkflowRunner`
- `WorkflowResult`
- `run_workflow`
- `workflow_provenance`

## Behavior

The runner provides one public entry point for a JSON-first run:

```text
public candidate records
  -> canonical staged package
  -> analyzer pipeline
  -> result collection
  -> evolver selection
  -> EvolutionRun JSON
  -> optional ranking JSON/CSV
```

It supports public Sanz19 generation and externally provided candidate records. Provided records are used by the reproduction examples for campaign-specific factories while keeping framework modules generic.

## Boundaries

The workflow package does not import PennyLane, Matplotlib, pandas, notebooks, thesis processing folders, generated callables, or legacy source packages. It does not contain CX-01 or MIXT-5G branches.

## Validation

Focused Phase 7 tests passed with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_end_to_end_workflow.py tests/test_workflow_runner.py tests/test_cx01_reproduction.py tests/test_mixt5g_reproduction.py -q
```

Full unittest discovery also passed with 127 tests.

## Deferred Decisions

- Whether the evolver should own the reusable multi-generation workflow loop.
- How optional scientific metric callables should be configured for reproducible full-campaign runs.
- Whether future workflow manifests should become a formal canonical schema.
