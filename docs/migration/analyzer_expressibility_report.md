# Analyzer Expressibility Report

## Completed Scope

Phase 5.5 added optional expressibility execution through
`verfeinert/ansatz_analyzer/metrics/expressibility.py` and shared runtime
guards in `metrics/runtime.py`.

The analyzer pipeline can now include `expressibility` when
`AnalyzerExecutionPermissions(allow_expensive_metrics=True)` is configured.
Without an explicit state callable, the pipeline writes a canonical skipped
metric record instead of executing hidden work.

## Scientific Behavior

The migrated metric uses the validated fidelity-sampling concept:

- sample pairs of random parameter vectors;
- evaluate explicit state-vector callables;
- bin state fidelities;
- compare against the Haar fidelity distribution;
- report `D_KL` and `expressibility = -log10(D_KL)`.

The implementation is record-first and returns canonical `MetricRecord`
objects. It does not import or require PennyLane, NumPy, pandas, notebooks, or
generated callable packages.

## Execution Boundary

Expressibility is an expensive metric. Execution requires
`allow_expensive_metrics=True`. QNode execution is a separate explicit flag and
remains false for the state-callable implementation unless a future backend
declares otherwise.

Metric metadata records backend label, configuration, state-call count, seed,
fidelity summary values, elapsed time, and truthful execution flags.

## Verification

Command run from `Verfeinertv2/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_ansatz_analyzer_phase_5_5_expressibility.py -q
```

Result:

```text
Ran 8 tests in 0.050s
OK
```

## Deferred

Backend adapters for generated QNodes and parallel execution remain future
work. Optional quantum dependencies are declared as extras and are not required
for the default analyzer import path.
