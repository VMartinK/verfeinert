# Analyzer Trainability Report

## Completed Scope

Phase 5.6 added optional trainability execution through
`verfeinert/ansatz_analyzer/metrics/trainability.py`.

The analyzer pipeline can include `trainability` when
`AnalyzerExecutionPermissions(allow_expensive_metrics=True)` is configured.
Without an explicit state callable, the pipeline writes a canonical skipped
metric record.

## Scientific Methodology

The migrated methodology is explicitly Local-X:

```text
H = sum_i X_i
```

The configuration field is:

```yaml
trainability:
  hamiltonian: local_x
```

Non-Local-X Hamiltonian labels, including TFIM, are rejected. The metric uses
finite-difference gradients over explicit state-vector callables and reports
the active-gradient mean-squared proxy as `trainability`,
`holmes_metric`, and `mean_squared_gradient_active`.

## Execution Metadata

Metric metadata records backend label, configuration, sampled parameter
indices, number of repeats, gradient components, state evaluations, active and
inactive parameter counts, seed, Hamiltonian definition, elapsed time, and
truthful execution flags.

No PennyLane, NumPy, pandas, notebooks, generated callable packages, or QNodes
are imported or executed by default.

## Verification

Command run from `Verfeinertv2/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_ansatz_analyzer_phase_5_6_trainability.py -q
```

Result:

```text
Ran 8 tests in 0.057s
OK
```

## Deferred

Analytic gradients, PennyLane backend adapters, parallel execution, and larger
scientific regression fixtures remain future optional work.
